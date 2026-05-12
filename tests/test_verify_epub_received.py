"""Tests for the verify_epub_received tool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mcp_readwise.models.reader import ReaderDocument, ReaderListResult
from mcp_readwise.tools.epub_verifier import verify_epub_received


def _make_doc(title: str, doc_id: str = "doc-1") -> ReaderDocument:
    return ReaderDocument(
        id=doc_id,
        title=title,
        author="",
        source_url="",
        category="epub",
        location="new",
        reading_progress=0.0,
        word_count=0,
        summary="",
        tags=[],
        created_at="",
        updated_at="2026-05-12T10:05:00Z",
        saved_at="2026-05-12T10:05:00Z",
    )


def _iso_ago(seconds: float) -> str:
    """ISO 8601 timestamp `seconds` ago."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class TestFoundPath:
    @pytest.mark.asyncio
    async def test_exact_title_match(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(
                results=[_make_doc("My Brief")], total=1, next_page=None
            )

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="My Brief", since=_iso_ago(120)
        )
        assert result.found is True
        assert result.document is not None
        assert result.document.title == "My Brief"
        assert result.note == "Found in Reader Library."

    @pytest.mark.asyncio
    async def test_fuzzy_partial_match_default(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(
                results=[_make_doc("My Brief - Q2 2026")],
                total=1,
                next_page=None,
            )

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="My Brief", since=_iso_ago(120)
        )
        assert result.found is True

    @pytest.mark.asyncio
    async def test_fuzzy_false_requires_exact_match(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(
                results=[_make_doc("My Brief - Q2 2026")],
                total=1,
                next_page=None,
            )

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="My Brief", since=_iso_ago(120), fuzzy=False
        )
        assert result.found is False

    @pytest.mark.asyncio
    async def test_case_insensitive(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(
                results=[_make_doc("MY BRIEF")], total=1, next_page=None
            )

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="my brief", since=_iso_ago(120)
        )
        assert result.found is True


class TestNotYetTimeBands:
    @pytest.mark.asyncio
    async def test_under_60s_too_early(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="X", since=_iso_ago(30)
        )
        assert result.found is False
        assert "Too early" in result.note

    @pytest.mark.asyncio
    async def test_60s_to_5min_pending(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="X", since=_iso_ago(180)
        )
        assert result.found is False
        assert "Not yet" in result.note
        assert "1–2 minutes" in result.note

    @pytest.mark.asyncio
    async def test_5_to_15min_late(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="X", since=_iso_ago(600)
        )
        assert result.found is False
        assert "Late" in result.note
        assert "May have failed" in result.note

    @pytest.mark.asyncio
    async def test_over_15min_failed(self, monkeypatch):
        async def fake_list(**kwargs):
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        result = await verify_epub_received(
            title="X", since=_iso_ago(1200)
        )
        assert result.found is False
        assert "Not found" in result.note
        assert "Resend dashboard" in result.note


class TestQueryParameters:
    @pytest.mark.asyncio
    async def test_filters_by_category_epub_and_updated_after(self, monkeypatch):
        captured = {}

        async def fake_list(**kwargs):
            captured.update(kwargs)
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )
        since = "2026-05-12T10:00:00Z"
        await verify_epub_received(title="X", since=since)
        assert captured["category"] == "epub"
        assert captured["updated_after"] == since
        assert captured["limit"] == 50


class TestDoesNotRequireEpubSenderConfig:
    @pytest.mark.asyncio
    async def test_runs_without_epub_env_vars(self, monkeypatch):
        # Explicitly clear epub-sender settings — the verify tool should not care.
        from pydantic import SecretStr

        from mcp_readwise.config import settings as global_settings

        monkeypatch.setattr(global_settings, "readwise_library_email", "")
        monkeypatch.setattr(global_settings, "resend_api_key", SecretStr(""))
        monkeypatch.setattr(global_settings, "epub_from_address", "")

        async def fake_list(**kwargs):
            return ReaderListResult(results=[], total=0, next_page=None)

        monkeypatch.setattr(
            "mcp_readwise.tools.epub_verifier.list_documents", fake_list
        )

        # Should not raise ConfigurationError
        result = await verify_epub_received(title="X", since=_iso_ago(30))
        assert result.found is False
