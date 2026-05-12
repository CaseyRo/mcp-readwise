"""Tests for the save_markdown_as_epub tool."""

from __future__ import annotations


import pytest

# Configure env before any settings import — but config is loaded at module
# import time, so we use monkeypatch on settings attributes per-test instead.
from mcp_readwise.config import settings
from mcp_readwise.smtp_client import SendResult
from mcp_readwise.tools.epub_sender import (
    ConfigurationError,
    save_markdown_as_epub,
)


@pytest.fixture
def configured(monkeypatch):
    """Set the three required env-derived settings."""
    monkeypatch.setattr(settings, "readwise_library_email", "casey@library.readwise.io")
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_test_key"))
    monkeypatch.setattr(settings, "epub_from_address", "mcp@cdit-dev.de")
    yield


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub out pandoc + SMTP. Returns a dict that captures call args."""
    captured = {}

    async def fake_render(markdown, metadata, cover_path, idempotency_key):
        captured["markdown"] = markdown
        captured["metadata"] = metadata
        captured["cover_path"] = cover_path
        captured["idempotency_key"] = idempotency_key
        scheme = "x-mcp-readwise-idempotency" if idempotency_key else "uuid"
        return b"PK\x03\x04stub-epub-bytes", scheme

    async def fake_send(from_addr, to_addr, subject, body_text, epub_bytes, filename):
        captured["smtp"] = {
            "from_addr": from_addr,
            "to_addr": to_addr,
            "subject": subject,
            "filename": filename,
            "size": len(epub_bytes),
        }
        return SendResult(
            message_id="msg-12345",
            accepted_at="2026-05-12T10:00:00+00:00",
            server_response="250 OK",
        )

    async def fake_cover(url):
        captured["cover_url"] = url
        return None

    monkeypatch.setattr("mcp_readwise.tools.epub_sender.render_epub", fake_render)
    monkeypatch.setattr("mcp_readwise.tools.epub_sender.send_epub", fake_send)
    monkeypatch.setattr("mcp_readwise.tools.epub_sender._resolve_cover", fake_cover)

    return captured


class TestTitleResolution:
    @pytest.mark.asyncio
    async def test_explicit_title_wins(self, configured, stub_pipeline):
        await save_markdown_as_epub(
            markdown="---\ntitle: Frontmatter\n---\n# H1 Body",
            title="Explicit",
        )
        assert stub_pipeline["metadata"]["title"] == "Explicit"

    @pytest.mark.asyncio
    async def test_frontmatter_title_wins_over_h1(self, configured, stub_pipeline):
        await save_markdown_as_epub(
            markdown="---\ntitle: Frontmatter\n---\n# H1 Body"
        )
        assert stub_pipeline["metadata"]["title"] == "Frontmatter"

    @pytest.mark.asyncio
    async def test_h1_fallback(self, configured, stub_pipeline):
        await save_markdown_as_epub(markdown="# From H1\n\nBody.")
        assert stub_pipeline["metadata"]["title"] == "From H1"

    @pytest.mark.asyncio
    async def test_untitled_fallback(self, configured, stub_pipeline):
        await save_markdown_as_epub(markdown="just paragraph text.")
        assert stub_pipeline["metadata"]["title"] == "Untitled"


class TestParamOverrides:
    @pytest.mark.asyncio
    async def test_explicit_params_override_frontmatter(self, configured, stub_pipeline):
        md = (
            "---\n"
            "author: FM Author\n"
            "summary: FM Summary\n"
            "tags: [fm-a, fm-b]\n"
            "note: FM Note\n"
            "---\n"
            "# T"
        )
        await save_markdown_as_epub(
            markdown=md,
            author="Explicit Author",
            summary="Explicit Summary",
            tags=["explicit"],
            note="Explicit Note",
        )
        meta = stub_pipeline["metadata"]
        assert meta["author"] == "Explicit Author"
        assert meta["summary"] == "Explicit Summary"
        assert meta["tags"] == ["explicit"]
        assert meta["note"] == "Explicit Note"

    @pytest.mark.asyncio
    async def test_note_param_forwarded_not_dropped(self, configured, stub_pipeline):
        await save_markdown_as_epub(
            markdown="# T", note="A specific annotation."
        )
        assert stub_pipeline["metadata"]["note"] == "A specific annotation."

    @pytest.mark.asyncio
    async def test_frontmatter_note_fallback_when_no_explicit(
        self, configured, stub_pipeline
    ):
        # Spec scenario: frontmatter `note:` populates when explicit absent.
        await save_markdown_as_epub(
            markdown='---\nnote: "From the author."\n---\n# T'
        )
        assert stub_pipeline["metadata"]["note"] == "From the author."


class TestIdempotencyKey:
    @pytest.mark.asyncio
    async def test_key_forwarded_to_render(self, configured, stub_pipeline):
        await save_markdown_as_epub(
            markdown="# T", idempotency_key="my-stable-key"
        )
        assert stub_pipeline["idempotency_key"] == "my-stable-key"

    @pytest.mark.asyncio
    async def test_result_carries_idempotency_scheme(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(
            markdown="# T", idempotency_key="k"
        )
        assert result.identifier_scheme == "x-mcp-readwise-idempotency"

    @pytest.mark.asyncio
    async def test_no_key_uses_uuid_scheme(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T")
        assert result.identifier_scheme == "uuid"
        assert stub_pipeline["idempotency_key"] is None


class TestLocationParam:
    @pytest.mark.asyncio
    async def test_location_echoed_in_result(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T", location="later")
        assert result.location == "later"

    @pytest.mark.asyncio
    async def test_location_does_not_affect_smtp(self, configured, stub_pipeline):
        await save_markdown_as_epub(markdown="# T", location="archive")
        # The SMTP recipient is always the library email regardless of location
        assert (
            stub_pipeline["smtp"]["to_addr"] == "casey@library.readwise.io"
        )

    @pytest.mark.asyncio
    async def test_location_defaults_to_new(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T")
        assert result.location == "new"


class TestConfigurationError:
    @pytest.mark.asyncio
    async def test_missing_library_email(self, monkeypatch):
        monkeypatch.setattr(settings, "readwise_library_email", "")
        from pydantic import SecretStr
        monkeypatch.setattr(settings, "resend_api_key", SecretStr("k"))
        monkeypatch.setattr(settings, "epub_from_address", "from@cdit.de")
        with pytest.raises(ConfigurationError, match="READWISE_LIBRARY_EMAIL"):
            await save_markdown_as_epub(markdown="# T")

    @pytest.mark.asyncio
    async def test_missing_all_three_lists_all(self, monkeypatch):
        from pydantic import SecretStr
        monkeypatch.setattr(settings, "readwise_library_email", "")
        monkeypatch.setattr(settings, "resend_api_key", SecretStr(""))
        monkeypatch.setattr(settings, "epub_from_address", "")
        with pytest.raises(ConfigurationError) as exc_info:
            await save_markdown_as_epub(markdown="# T")
        msg = str(exc_info.value)
        assert "READWISE_LIBRARY_EMAIL" in msg
        assert "RESEND_API_KEY" in msg
        assert "EPUB_FROM_ADDRESS" in msg

    @pytest.mark.asyncio
    async def test_error_does_not_leak_secret_value(self, monkeypatch):
        from pydantic import SecretStr
        monkeypatch.setattr(settings, "readwise_library_email", "")
        monkeypatch.setattr(
            settings, "resend_api_key", SecretStr("super-secret-key")
        )
        monkeypatch.setattr(settings, "epub_from_address", "from@cdit.de")
        with pytest.raises(ConfigurationError) as exc_info:
            await save_markdown_as_epub(markdown="# T")
        assert "super-secret-key" not in str(exc_info.value)


class TestRecipientNotMasked:
    @pytest.mark.asyncio
    async def test_recipient_returned_in_full(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T")
        # Full address, not c***@... masked
        assert result.recipient == "casey@library.readwise.io"
        assert "*" not in result.recipient


class TestAsyncContractNote:
    @pytest.mark.asyncio
    async def test_note_leads_with_send_confirmation(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T")
        assert result.note.startswith("Sent.")
        assert "minutes" in result.note.lower()
        assert "verify_epub_received" in result.note


class TestCoverImage:
    @pytest.mark.asyncio
    async def test_cover_url_param_passes_to_resolver(self, configured, stub_pipeline):
        await save_markdown_as_epub(
            markdown="# T", cover_image_url="https://example.com/c.jpg"
        )
        assert stub_pipeline["cover_url"] == "https://example.com/c.jpg"

    @pytest.mark.asyncio
    async def test_frontmatter_image_url_triggers_cover_download(
        self, configured, stub_pipeline
    ):
        # Spec scenario: frontmatter `image_url:` is the cover source path.
        await save_markdown_as_epub(
            markdown="---\nimage_url: https://example.com/fm-cover.png\n---\n# T"
        )
        assert stub_pipeline["cover_url"] == "https://example.com/fm-cover.png"

    @pytest.mark.asyncio
    async def test_no_cover_proceeds_without_error(self, configured, stub_pipeline):
        result = await save_markdown_as_epub(markdown="# T")
        assert result.success is True
        assert stub_pipeline["cover_url"] is None


class TestDocstring:
    def test_starts_with_async_uppercase(self):
        assert save_markdown_as_epub.__doc__.lstrip().startswith("ASYNC")

    def test_contains_all_three_env_var_names(self):
        doc = save_markdown_as_epub.__doc__
        assert "READWISE_LIBRARY_EMAIL" in doc
        assert "RESEND_API_KEY" in doc
        assert "EPUB_FROM_ADDRESS" in doc

    def test_directs_not_to_tell_human(self):
        doc = save_markdown_as_epub.__doc__.lower()
        assert "do not tell the human" in doc
        assert "verify_epub_received" in doc

    def test_documents_location_as_informational(self):
        doc = save_markdown_as_epub.__doc__.lower()
        assert "informational" in doc
        assert "follow-up" in doc

    def test_documents_idempotency_key_purpose(self):
        doc = save_markdown_as_epub.__doc__.lower()
        assert "idempotency_key" in doc
        assert "dedup" in doc or "duplicate" in doc.lower()
