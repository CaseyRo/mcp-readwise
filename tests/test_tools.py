"""Tests for tool functions — books, tags, reader, export."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    SAMPLE_BOOK,
    SAMPLE_READER_DOC,
    SAMPLE_TAG,
)


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

        assert result.deleted is True
        assert result.id == 10



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
