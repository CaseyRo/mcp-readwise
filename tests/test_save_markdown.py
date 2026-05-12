"""Tests for the save_markdown tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _mock_save_response(title: str = "Untitled", **overrides):
    base = {
        "id": "reader-md-123",
        "title": title,
        "author": "",
        "source_url": "",
        "category": "epub",
        "location": "new",
        "summary": "",
        "tags": [],
        "created_at": "2026-05-11T00:00:00Z",
        "updated_at": "2026-05-11T00:00:00Z",
        "saved_at": "2026-05-11T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestSaveMarkdownPayload:
    @pytest.mark.asyncio
    async def test_basic_save_posts_html_and_synthetic_url(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured["path"] = path
            captured["kwargs"] = kwargs
            return _mock_save_response(title=kwargs.get("title", "Untitled"))

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown="# Hello\n\nWorld.")

        assert captured["path"] == "/api/v3/save/"
        kwargs = captured["kwargs"]
        assert kwargs["html"].startswith("<h1>Hello</h1>")
        assert kwargs["category"] == "epub"
        assert kwargs["location"] == "new"
        assert kwargs["should_clean_html"] is False
        assert kwargs["title"] == "Hello"
        assert kwargs["url"].startswith("https://mcp-readwise.local/md/")
        assert kwargs["saved_using"] == "mcp-readwise"

    @pytest.mark.asyncio
    async def test_explicit_title_overrides_h1(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured.update(kwargs)
            return _mock_save_response(title=kwargs["title"])

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown="# Body H1", title="Explicit Title")

        assert captured["title"] == "Explicit Title"

    @pytest.mark.asyncio
    async def test_frontmatter_provides_metadata(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured.update(kwargs)
            return _mock_save_response(title=kwargs["title"])

        md = (
            "---\n"
            "title: From Frontmatter\n"
            "author: Casey\n"
            "tags: [research, draft]\n"
            "summary: A brief description.\n"
            "---\n"
            "# Body header\n\nContent here."
        )

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown=md)

        assert captured["title"] == "From Frontmatter"
        assert captured["author"] == "Casey"
        assert captured["tags"] == ["research", "draft"]
        assert captured["summary"] == "A brief description."

    @pytest.mark.asyncio
    async def test_explicit_tags_replace_frontmatter_tags(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured.update(kwargs)
            return _mock_save_response(title=kwargs["title"])

        md = "---\ntitle: T\ntags: [fm-a, fm-b]\n---\nBody"

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown=md, tags=["explicit"])

        assert captured["tags"] == ["explicit"]

    @pytest.mark.asyncio
    async def test_category_override(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured.update(kwargs)
            return _mock_save_response(title=kwargs["title"], category="note")

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown="# T", category="note")

        assert captured["category"] == "note"

    @pytest.mark.asyncio
    async def test_note_is_translated_to_notes(self):
        captured: dict = {}

        async def fake_post(path, **kwargs):
            captured.update(kwargs)
            return _mock_save_response(title=kwargs["title"])

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            await save_markdown(markdown="# T", note="annotation")

        assert captured["notes"] == "annotation"
        assert "note" not in captured  # singular not forwarded

    @pytest.mark.asyncio
    async def test_synthetic_url_stable_for_repeated_save(self):
        urls: list[str] = []

        async def fake_post(path, **kwargs):
            urls.append(kwargs["url"])
            return _mock_save_response(title=kwargs["title"])

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(side_effect=fake_post)

            from mcp_readwise.tools.markdown import save_markdown

            md = "# Stable Title\n\nIdentical body content."
            await save_markdown(markdown=md)
            await save_markdown(markdown=md)

        assert urls[0] == urls[1]


class TestSaveMarkdownResponse:
    @pytest.mark.asyncio
    async def test_returns_reader_document(self):
        response = _mock_save_response(
            title="Returned",
            tags={"a": True, "b": True},
            location="later",
        )

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(return_value=response)

            from mcp_readwise.tools.markdown import save_markdown

            result = await save_markdown(markdown="# T", location="later")

        assert result.id == "reader-md-123"
        assert result.title == "Returned"
        assert result.location == "later"
        assert sorted(result.tags) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_falls_back_to_request_metadata_when_response_empty(self):
        # Sparse response — Reader echoes back what we sent, sometimes minimally
        response = {"id": "reader-x", "tags": {}, "saved_at": "2026-05-11T00:00:00Z"}

        with patch("mcp_readwise.tools.markdown.client") as mock_client:
            mock_client.post = AsyncMock(return_value=response)

            from mcp_readwise.tools.markdown import save_markdown

            result = await save_markdown(markdown="# Title Here", tags=["a"])

        assert result.id == "reader-x"
        assert result.title == "Title Here"
        assert result.tags == ["a"]
        assert result.source_url.startswith("https://mcp-readwise.local/md/")
