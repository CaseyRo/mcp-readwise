"""Tests for the SMTP transport module."""

from __future__ import annotations


import aiosmtplib
import pytest

from mcp_readwise.smtp_client import (
    SmtpDeliveryError,
    _build_message,
    _is_transient,
    send_epub,
)


class TestBuildMessage:
    def test_mime_structure(self):
        msg = _build_message(
            "from@example.com",
            "to@library.readwise.io",
            "My Subject",
            "Body text.",
            b"PK\x03\x04epub-bytes",
            "doc.epub",
        )
        assert msg["From"] == "from@example.com"
        assert msg["To"] == "to@library.readwise.io"
        assert msg["Subject"] == "My Subject"
        # Walk parts to find attachment
        attachments = [p for p in msg.iter_attachments()]
        assert len(attachments) == 1
        att = attachments[0]
        assert att.get_content_type() == "application/epub+zip"
        assert att.get_filename() == "doc.epub"

    def test_attachment_payload_roundtrip(self):
        original = b"\x50\x4b\x03\x04test-bytes"
        msg = _build_message(
            "a@a.com", "b@b.com", "S", "body", original, "x.epub"
        )
        att = next(msg.iter_attachments())
        # EmailMessage decodes base64 transparently
        assert att.get_content() == original

    def test_message_id_header_set_with_sender_domain(self):
        # CDI-1311: the reported message_id must be a real header on the wire,
        # not a fabricated UUID. It should carry the sender's domain.
        msg = _build_message(
            "mcp-readwise@cdit-dev.de", "to@b.com", "S", "body", b"e", "x.epub"
        )
        mid = msg.get("Message-ID", "")
        assert mid.startswith("<") and mid.endswith(">")
        assert mid.endswith("@cdit-dev.de>")


class TestIsTransient:
    def test_4xx_is_transient(self):
        assert _is_transient(421) is True
        assert _is_transient(450) is True
        assert _is_transient(499) is True

    def test_5xx_is_not_transient(self):
        assert _is_transient(500) is False
        assert _is_transient(550) is False

    def test_auth_codes_are_not_transient(self):
        assert _is_transient(535) is False
        assert _is_transient(530) is False

    def test_none_is_transient(self):
        # Connection error with no code → retry
        assert _is_transient(None) is True


class TestSendEpub:
    @pytest.mark.asyncio
    async def test_happy_path(self, monkeypatch):
        async def fake_send(*args, **kwargs):
            return ({}, "250 OK Queued")

        monkeypatch.setattr("aiosmtplib.send", fake_send)

        result = await send_epub(
            "from@a.com",
            "to@b.com",
            "Subject",
            "body",
            b"epub",
            "x.epub",
        )
        assert "OK" in result.server_response or "queued" in result.server_response.lower()
        assert result.message_id  # populated even when SMTP doesn't return one

    @pytest.mark.asyncio
    async def test_message_id_from_header_not_random(self, monkeypatch):
        # The returned message_id is the (stripped) Message-ID header, so it
        # corresponds to a real, traceable id rather than a throwaway UUID.
        captured = {}

        async def fake_send(message, *args, **kwargs):
            captured["mid"] = message.get("Message-ID", "")
            return ({}, "250 OK Queued")

        monkeypatch.setattr("aiosmtplib.send", fake_send)
        result = await send_epub(
            "mcp@cdit-dev.de", "to@b.com", "S", "body", b"epub", "x.epub"
        )
        assert result.message_id == captured["mid"].strip("<>")
        assert result.message_id  # non-empty

    @pytest.mark.asyncio
    async def test_refused_recipient_raises_no_false_success(self, monkeypatch):
        # CDI-1311 Defect 1: a non-empty per-recipient errors dict (relay
        # refused the recipient without raising) must NOT be reported as a
        # successful send.
        async def fake_send(*args, **kwargs):
            return ({"to@b.com": (550, "mailbox unavailable")}, "queued")

        monkeypatch.setattr("aiosmtplib.send", fake_send)
        with pytest.raises(SmtpDeliveryError, match="refused"):
            await send_epub("f@a.com", "to@b.com", "S", "b", b"e", "x.epub")

    @pytest.mark.asyncio
    async def test_retry_on_4xx(self, monkeypatch):
        attempts = []

        async def fake_send(*args, **kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                raise aiosmtplib.SMTPResponseException(421, "try again later")
            return ({}, "250 OK")

        # Patch asyncio.sleep so backoffs don't slow the test
        async def fake_sleep(_):
            pass

        monkeypatch.setattr("aiosmtplib.send", fake_send)
        monkeypatch.setattr("mcp_readwise.smtp_client.asyncio.sleep", fake_sleep)

        result = await send_epub("f@a.com", "t@b.com", "S", "b", b"e", "x.epub")
        assert len(attempts) == 2
        assert result is not None

    @pytest.mark.asyncio
    async def test_retry_budget_exhausted_raises(self, monkeypatch):
        async def always_fail(*args, **kwargs):
            raise aiosmtplib.SMTPResponseException(421, "still rate-limited")

        async def fake_sleep(_):
            pass

        monkeypatch.setattr("aiosmtplib.send", always_fail)
        monkeypatch.setattr("mcp_readwise.smtp_client.asyncio.sleep", fake_sleep)

        with pytest.raises(SmtpDeliveryError):
            await send_epub("f@a.com", "t@b.com", "S", "b", b"e", "x.epub")

    @pytest.mark.asyncio
    async def test_5xx_raises_immediately_no_retry(self, monkeypatch):
        attempts = []

        async def fake_send(*args, **kwargs):
            attempts.append(1)
            raise aiosmtplib.SMTPResponseException(550, "permanent")

        monkeypatch.setattr("aiosmtplib.send", fake_send)

        with pytest.raises(SmtpDeliveryError, match="550"):
            await send_epub("f@a.com", "t@b.com", "S", "b", b"e", "x.epub")
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_auth_failure_535_raises_immediately(self, monkeypatch):
        attempts = []

        async def fake_send(*args, **kwargs):
            attempts.append(1)
            raise aiosmtplib.SMTPResponseException(535, "auth failed")

        monkeypatch.setattr("aiosmtplib.send", fake_send)

        with pytest.raises(SmtpDeliveryError, match="535"):
            await send_epub("f@a.com", "t@b.com", "S", "b", b"e", "x.epub")
        assert len(attempts) == 1
