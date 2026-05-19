"""Tests for tool functions — highlights, books, tags, reader, export."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    SAMPLE_BOOK,
    SAMPLE_HIGHLIGHT,
    SAMPLE_READER_DOC,
    SAMPLE_TAG,
)


# --- Highlight tools ---


class TestSearchHighlights:
    @pytest.mark.asyncio
    async def test_hybrid_search(self):
        # MCP search endpoint returns {id, score, attributes: {...}}
        mcp_result = {
            "id": 1001,
            "score": 0.95,
            "attributes": {
                "highlight_plaintext": "Every action you take is a vote for the type of person you wish to become.",
                "highlight_note": "Key identity concept",
                "document_title": "Atomic Habits",
                "document_author": "James Clear",
                "document_tags": ["identity", "habits"],
                "book_id": 100,
            },
        }
        mock_response = {"results": [mcp_result]}

        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.highlights import search_highlights

            result = await search_highlights(query="habit formation")

        assert len(result.results) == 1
        assert "Every action" in result.results[0].text
        assert result.results[0].book_title == "Atomic Habits"
        assert result.results[0].book_author == "James Clear"
        assert result.results[0].tags == ["identity", "habits"]

    @pytest.mark.asyncio
    async def test_search_with_book_filter(self):
        h1 = {"id": 1001, "score": 0.9, "attributes": {"highlight_plaintext": "text1", "book_id": 100, "document_title": "Book A", "document_author": ""}}
        h2 = {"id": 1002, "score": 0.8, "attributes": {"highlight_plaintext": "text2", "book_id": 200, "document_title": "Book B", "document_author": ""}}
        mock_response = {"results": [h1, h2]}

        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.highlights import search_highlights

            result = await search_highlights(query="test", book_id=100)

        assert len(result.results) == 1
        assert result.results[0].book_id == 100


class TestListHighlights:
    @pytest.mark.asyncio
    async def test_list_with_pagination(self):
        mock_response = {
            "results": [SAMPLE_HIGHLIGHT],
            "count": 42,
            "next": "https://readwise.io/api/v2/highlights/?page=2",
        }

        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.enrich_highlight = AsyncMock(
                return_value={**SAMPLE_HIGHLIGHT, "book_title": "", "book_author": "", "source_url": ""}
            )

            from mcp_readwise.tools.highlights import list_highlights

            result = await list_highlights(page=1, limit=50)

        assert result.total == 42
        assert result.next_page == 2
        assert len(result.results) == 1


class TestHighlightCRUD:
    @pytest.mark.asyncio
    async def test_get_highlight(self):
        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.get = AsyncMock(return_value=SAMPLE_HIGHLIGHT)
            mock_client.enrich_highlight = AsyncMock(
                return_value={**SAMPLE_HIGHLIGHT, "book_title": "Atomic Habits", "book_author": "James Clear", "source_url": ""}
            )

            from mcp_readwise.tools.highlights import get_highlight

            result = await get_highlight(highlight_id=1001)

        assert result.id == 1001
        assert result.book_title == "Atomic Habits"

    @pytest.mark.asyncio
    async def test_delete_highlight(self):
        with patch("mcp_readwise.tools.highlights.client") as mock_client:
            mock_client.delete = AsyncMock(return_value=None)

            from mcp_readwise.tools.highlights import delete_highlight

            result = await delete_highlight(highlight_id=1001)

        assert result == {"deleted": True, "id": 1001}


# --- Book tools ---


class TestBookTools:
    @pytest.mark.asyncio
    async def test_list_books(self):
        mock_response = {"results": [SAMPLE_BOOK], "count": 1, "next": None}

        with patch("mcp_readwise.tools.books.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.books import list_books

            result = await list_books(category="books")

        assert len(result.results) == 1
        assert result.results[0].title == "Atomic Habits"
        assert result.next_page is None

    @pytest.mark.asyncio
    async def test_list_books_annotation_filter(self):
        low_book = {**SAMPLE_BOOK, "id": 101, "num_highlights": 2}
        mock_response = {"results": [SAMPLE_BOOK, low_book], "count": 2, "next": None}

        with patch("mcp_readwise.tools.books.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.books import list_books

            result = await list_books(num_highlights_gte=10)

        assert len(result.results) == 1
        assert result.results[0].num_highlights == 42

    @pytest.mark.asyncio
    async def test_get_book(self):
        with patch("mcp_readwise.tools.books.client") as mock_client:
            mock_client.get = AsyncMock(return_value=SAMPLE_BOOK)

            from mcp_readwise.tools.books import get_book

            result = await get_book(book_id=100)

        assert result.id == 100
        assert result.author == "James Clear"


# --- Tag tools ---


class TestTagTools:
    @pytest.mark.asyncio
    async def test_list_tags(self):
        mock_response = {"results": [SAMPLE_TAG, {"id": 11, "name": "habits"}]}

        with patch("mcp_readwise.tools.tags.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.tags import list_tags

            result = await list_tags()

        assert len(result) == 2
        assert result[0].name == "identity"

    @pytest.mark.asyncio
    async def test_create_tag(self):
        with patch("mcp_readwise.tools.tags.client") as mock_client:
            mock_client.post = AsyncMock(return_value={"id": 99, "name": "new-tag"})

            from mcp_readwise.tools.tags import create_tag

            result = await create_tag(name="new-tag")

        assert result.id == 99
        assert result.name == "new-tag"

    @pytest.mark.asyncio
    async def test_delete_tag(self):
        with patch("mcp_readwise.tools.tags.client") as mock_client:
            mock_client.delete = AsyncMock(return_value=None)

            from mcp_readwise.tools.tags import delete_tag

            result = await delete_tag(tag_id=10)

        assert result == {"deleted": True, "id": 10}

    @pytest.mark.asyncio
    async def test_tag_highlight_add(self):
        with patch("mcp_readwise.tools.tags.client") as mock_client:
            mock_client.post = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(
                return_value=[{"id": 10, "name": "identity"}, {"id": 99, "name": "new-tag"}]
            )

            from mcp_readwise.tools.tags import tag_highlight

            result = await tag_highlight(highlight_id=1001, tag="new-tag", action="add")

        assert "new-tag" in result


# --- Reader tools ---


class TestReaderTools:
    @pytest.mark.asyncio
    async def test_list_documents(self):
        mock_response = {
            "results": [SAMPLE_READER_DOC],
            "count": 1,
            "nextPageCursor": None,
        }

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.reader import list_documents

            result = await list_documents(location="new")

        assert len(result.results) == 1
        assert result.results[0].title == "How to Build Habits That Last"
        assert result.results[0].tags == ["habits", "productivity"]

    @pytest.mark.asyncio
    async def test_save_url(self):
        saved = {**SAMPLE_READER_DOC, "location": "shortlist"}

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.post = AsyncMock(return_value=saved)

            from mcp_readwise.tools.reader import save_url

            result = await save_url(
                url="https://example.com/article",
                location="shortlist",
                tags=["reading"],
            )

        assert result.location == "shortlist"
        assert result.source_url == "https://example.com/article"

    @pytest.mark.asyncio
    async def test_save_url_share_google_redirect(self):
        """CDI-1149: share.google URLs come in as AnyHttpUrl; when the
        Readwise response omits source_url, the fallback must coerce to str
        rather than leaking the AnyHttpUrl into ReaderDocument(str)."""
        # Simulate a response that lacks source_url (the failure mode reported)
        saved = {
            "id": "reader-share-google",
            "title": "",
            "author": "",
            "category": "article",
            "location": "new",
        }

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.post = AsyncMock(return_value=saved)

            from mcp_readwise.tools.reader import save_url

            result = await save_url(
                url="https://share.google/IZ41z97ziAth2cme3",
                location="new",
            )

        # Construction succeeded — no Pydantic validation error
        assert result.id == "reader-share-google"
        # source_url falls back to the input URL, coerced to plain str
        assert isinstance(result.source_url, str)
        assert result.source_url.startswith("https://share.google/")

    @pytest.mark.asyncio
    async def test_reader_list_documents_archive(self):
        """CDI-1147: cursor-paginated browse hits the full library, not
        just the engagement cache."""
        archived = {**SAMPLE_READER_DOC, "location": "archive"}
        mock_response = {
            "results": [archived],
            "count": 1,
            "nextPageCursor": "cursor-xyz",
        }

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.reader import reader_list_documents

            result = await reader_list_documents(location="archive")

        assert len(result.results) == 1
        assert result.results[0].location == "archive"
        assert result.next_cursor == "cursor-xyz"
        # Verify the API was called with location=archive and limit
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["location"] == "archive"
        assert call_kwargs["limit"] == 100

    @pytest.mark.asyncio
    async def test_reader_list_documents_cursor_pagination(self):
        """page_cursor is passed through as pageCursor (Reader v3 spelling)."""
        mock_response = {"results": [], "count": 0, "nextPageCursor": None}

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.reader import reader_list_documents

            result = await reader_list_documents(
                location="archive", page_cursor="abc-123"
            )

        assert result.next_cursor is None
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["pageCursor"] == "abc-123"

    @pytest.mark.asyncio
    async def test_reader_get_by_url_match(self):
        """CDI-1147: get_by_url scans pages and returns the matching doc."""
        target = {**SAMPLE_READER_DOC, "id": "match", "source_url": "https://example.com/article"}
        other = {**SAMPLE_READER_DOC, "id": "miss", "source_url": "https://other.com/x"}
        mock_response = {
            "results": [other, target],
            "count": 2,
            "nextPageCursor": None,
        }

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.reader import reader_get_by_url

            result = await reader_get_by_url(
                url="https://example.com/article/",  # trailing slash differs
                location="archive",
            )

        assert result is not None
        assert result.id == "match"
        assert result.source_url == "https://example.com/article"

    @pytest.mark.asyncio
    async def test_reader_get_by_url_miss_returns_none(self):
        """Missing URL returns None, doesn't raise. (CDI-1147 acceptance)"""
        mock_response = {"results": [], "count": 0, "nextPageCursor": None}

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.reader import reader_get_by_url

            result = await reader_get_by_url(url="https://nowhere.example/x")

        assert result is None

    @pytest.mark.asyncio
    async def test_reader_get_by_url_paginates(self):
        """Walk cursor pages until match found."""
        page1 = {
            "results": [{**SAMPLE_READER_DOC, "id": "p1", "source_url": "https://a.test/"}],
            "count": 2,
            "nextPageCursor": "next-cursor",
        }
        page2 = {
            "results": [{**SAMPLE_READER_DOC, "id": "p2", "source_url": "https://b.test/"}],
            "count": 2,
            "nextPageCursor": None,
        }

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(side_effect=[page1, page2])

            from mcp_readwise.tools.reader import reader_get_by_url

            result = await reader_get_by_url(url="https://b.test/")

        assert result is not None
        assert result.id == "p2"
        # Second call must have carried the cursor
        second_call_kwargs = mock_client.get.call_args_list[1][1]
        assert second_call_kwargs["pageCursor"] == "next-cursor"

    @pytest.mark.asyncio
    async def test_get_document_truncates_content(self):
        long_doc = {**SAMPLE_READER_DOC, "content": "x" * 100_000}

        with patch("mcp_readwise.tools.reader.client") as mock_client:
            mock_client.get = AsyncMock(return_value=long_doc)

            from mcp_readwise.tools.reader import get_document

            result = await get_document(document_id="reader-abc123")

        assert len(result.content) == 50_000


# --- Export tool ---


class TestExportTool:
    @pytest.mark.asyncio
    async def test_export_with_cursor(self):
        mock_response = {
            "results": [{"id": 1, "highlights": []}],
            "nextPageCursor": "cursor-abc",
        }

        with patch("mcp_readwise.tools.export.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.export import export_highlights

            result = await export_highlights()

        assert len(result.results) == 1
        assert result.next_cursor == "cursor-abc"

    @pytest.mark.asyncio
    async def test_export_filters(self):
        mock_response = {"results": [], "nextPageCursor": None}

        with patch("mcp_readwise.tools.export.client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)

            from mcp_readwise.tools.export import export_highlights

            await export_highlights(
                updated_after="2024-01-01",
                book_ids=[100, 200],
            )

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["updatedAfter"] == "2024-01-01"
        assert call_kwargs[1]["ids"] == "100,200"
