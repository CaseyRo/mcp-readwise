"""Tests for the fastmcp 3.4.2 uplift — annotations, structured output,
resources, prompts, and Context threading.

These assert the additive, backward-compatible surface introduced in
feat/fastmcp-uplift without re-testing existing tool behavior.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from mcp_readwise.models.highlights import DeletionResult


# --- Typed deletion model -------------------------------------------------


class TestDeletionResult:
    @pytest.mark.asyncio
    async def test_delete_highlight_returns_typed_model(self):
        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.delete = AsyncMock(return_value=None)
            from mcp_readwise.tools.highlights import delete_highlight

            result = await delete_highlight(highlight_id=1001)

        assert isinstance(result, DeletionResult)
        assert result.deleted is True
        assert result.id == 1001

    @pytest.mark.asyncio
    async def test_delete_tag_returns_typed_model(self):
        with patch("mcp_readwise.tools.tags.client") as mock_client:
            mock_client.delete = AsyncMock(return_value=None)
            from mcp_readwise.tools.tags import delete_tag

            result = await delete_tag(tag_id=10)

        assert isinstance(result, DeletionResult)
        assert result.deleted is True
        assert result.id == 10


# --- Context threading (ctx is optional; tools still work without it) -----


class _SpyContext:
    """Minimal stand-in for fastmcp Context that records calls."""

    def __init__(self):
        self.infos: list[str] = []
        self.progress: list[tuple] = []

    async def info(self, message):
        self.infos.append(message)

    async def report_progress(self, progress, total=None):
        self.progress.append((progress, total))


class TestContextThreading:
    @pytest.mark.asyncio
    async def test_epub_sender_reports_progress(self, monkeypatch):
        from pydantic import SecretStr

        from mcp_readwise.config import settings
        from mcp_readwise.smtp_client import SendResult
        from mcp_readwise.tools.epub_sender import save_markdown_as_epub

        monkeypatch.setattr(settings, "readwise_library_email", "c@lib.readwise.io")
        monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_k"))
        monkeypatch.setattr(settings, "epub_from_address", "mcp@cdit.de")

        async def fake_render(markdown, metadata, cover_path, idempotency_key):
            return b"PK\x03\x04bytes", "uuid"

        async def fake_send(**kwargs):
            return SendResult(
                message_id="m", accepted_at="2026-05-12T10:00:00+00:00",
                server_response="250 OK",
            )

        async def fake_cover(url):
            return None

        monkeypatch.setattr("mcp_readwise.tools.epub_sender.render_epub", fake_render)
        monkeypatch.setattr("mcp_readwise.tools.epub_sender.send_epub", fake_send)
        monkeypatch.setattr("mcp_readwise.tools.epub_sender._resolve_cover", fake_cover)

        ctx = _SpyContext()
        result = await save_markdown_as_epub(markdown="# T", ctx=ctx)

        assert result.success is True
        # Progress went 0 -> 1 -> 3 of 3, and at least one info was emitted
        assert (3, 3) in ctx.progress
        assert ctx.infos

    @pytest.mark.asyncio
    async def test_reader_get_by_url_reports_progress(self):
        from mcp_readwise.tools.reader import reader_get_by_url

        match = {
            "id": "match",
            "source_url": "https://example.com/article",
            "title": "Hit",
        }
        page = {"results": [match], "count": 1, "nextPageCursor": None}

        ctx = _SpyContext()
        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=page)
            result = await reader_get_by_url(
                url="https://example.com/article", ctx=ctx
            )

        assert result is not None
        assert result.id == "match"
        assert ctx.progress  # at least the first page progress
        assert any("page" in m.lower() for m in ctx.infos)


# --- Server wiring: instructions, annotations, resources, prompts ---------


class TestServerWiring:
    @pytest.mark.asyncio
    async def test_instructions_set(self):
        from mcp_readwise.server import mcp

        assert mcp.instructions
        assert "save_markdown_as_epub" in mcp.instructions
        assert "verify_epub_received" in mcp.instructions

    @pytest.mark.asyncio
    async def test_all_tools_have_open_world_and_title(self):
        from mcp_readwise.server import mcp

        tools = await mcp._list_tools()
        assert len(tools) == 16
        for t in tools:
            assert t.annotations is not None, t.name
            assert t.annotations.openWorldHint is True, t.name
            assert t.title, t.name

    @pytest.mark.asyncio
    async def test_destructive_tools_flagged(self):
        from mcp_readwise.server import mcp

        tools = {t.name: t for t in await mcp._list_tools()}
        for name in ("delete_highlight", "delete_tag"):
            assert tools[name].annotations.destructiveHint is True, name

    @pytest.mark.asyncio
    async def test_read_tools_flagged_readonly(self):
        from mcp_readwise.server import mcp

        tools = {t.name: t for t in await mcp._list_tools()}
        for name in (
            "reading_status",
            "writing_material",
            "list_tags",
            "verify_epub_received",
            "reader_list_documents",
            "reader_get_by_url",
        ):
            assert tools[name].annotations.readOnlyHint is True, name

    @pytest.mark.asyncio
    async def test_resources_registered(self):
        from mcp_readwise.server import mcp

        resources = await mcp._list_resources()
        uris = {str(r.uri) for r in resources}
        assert "readwise://epub/style.css" in uris
        assert "readwise://schema/frontmatter" in uris
        assert "readwise://enums/reader" in uris
        assert "readwise://engagement/rubric" in uris

    @pytest.mark.asyncio
    async def test_reader_enums_resource_content(self):
        from mcp_readwise.server import mcp

        rr = await mcp.read_resource("readwise://enums/reader")
        text = rr.contents[0].content
        data = json.loads(text)
        assert "archive" in data["locations"]
        assert "article" in data["categories"]

    @pytest.mark.asyncio
    async def test_prompts_registered(self):
        from mcp_readwise.server import mcp

        prompts = {p.name for p in await mcp._list_prompts()}
        assert "publish_research_to_reader" in prompts
        assert "draft_from_highlights" in prompts
