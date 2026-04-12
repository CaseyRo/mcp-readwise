"""Shared test fixtures."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


# Set test env vars before any imports touch Settings
os.environ.setdefault("READWISE_TOKEN", "test-token-12345")
os.environ.setdefault("READWISE_BASE_URL", "https://readwise.io")


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx responses."""

    def _make(json_data: Any, status_code: int = 200):
        resp = AsyncMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status = AsyncMock()
        if status_code >= 400:
            import httpx
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=AsyncMock(), response=resp
            )
        return resp

    return _make


SAMPLE_BOOK = {
    "id": 100,
    "title": "Atomic Habits",
    "author": "James Clear",
    "category": "books",
    "source": "kindle",
    "num_highlights": 42,
    "cover_image_url": "https://example.com/cover.jpg",
    "source_url": "https://example.com/book",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-06-01T00:00:00Z",
}

SAMPLE_HIGHLIGHT = {
    "id": 1001,
    "text": "Every action you take is a vote for the type of person you wish to become.",
    "note": "Key identity concept",
    "tags": [{"id": 10, "name": "identity"}, {"id": 11, "name": "habits"}],
    "book_id": 100,
    "highlighted_at": "2024-02-15T10:00:00Z",
    "created_at": "2024-02-15T10:00:00Z",
    "updated_at": "2024-02-15T10:00:00Z",
}

SAMPLE_TAG = {"id": 10, "name": "identity"}

SAMPLE_READER_DOC = {
    "id": "reader-abc123",
    "title": "How to Build Habits That Last",
    "author": "Example Author",
    "source_url": "https://example.com/article",
    "url": "https://example.com/article",
    "category": "article",
    "location": "new",
    "reading_progress": 0.0,
    "word_count": 2500,
    "summary": "An article about building lasting habits.",
    "content": "<p>Article content here</p>",
    "tags": {"habits": True, "productivity": True},
    "created_at": "2024-03-01T00:00:00Z",
    "updated_at": "2024-03-01T00:00:00Z",
}
