"""Tests for the ReadwiseClient — retries, rate limits, headers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest


@pytest.fixture
def _patch_settings():
    """Patch settings before client module is imported."""
    import os
    os.environ["READWISE_TOKEN"] = "test-token-12345"


@pytest.fixture
def make_client(_patch_settings):
    """Create a fresh ReadwiseClient with mocked httpx."""
    from mcp_readwise.client import ReadwiseClient

    client = ReadwiseClient()
    return client


class TestClientInit:
    def test_auth_header_set(self, make_client):
        headers = make_client._client.headers
        assert "authorization" in headers
        assert headers["authorization"] == "Token test-token-12345"

    def test_base_url_set(self, make_client):
        assert str(make_client._client.base_url) == "https://readwise.io"


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_server_error(self, make_client):
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "server error", request=MagicMock(), response=mock_resp_500
            )
        )

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"results": []}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return mock_resp_500
            return mock_resp_ok

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", new_callable=AsyncMock):
                result = await make_client.get("/api/v2/highlights/")

        assert call_count == 3
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, make_client):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"ok": True}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return mock_resp_429
            return mock_resp_ok

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", new_callable=AsyncMock):
                result = await make_client.get("/api/v2/tags/")

        assert call_count == 2
        assert result == {"ok": True}


class TestBookCache:
    @pytest.mark.asyncio
    async def test_caches_book_metadata(self, make_client):
        from tests.conftest import SAMPLE_BOOK

        call_count = 0

        async def mock_get(path, **params):
            nonlocal call_count
            call_count += 1
            return SAMPLE_BOOK

        with patch.object(make_client, "get", side_effect=mock_get):
            meta1 = await make_client.get_book_metadata(100)
            meta2 = await make_client.get_book_metadata(100)

        assert meta1["book_title"] == "Atomic Habits"
        assert meta2["book_title"] == "Atomic Habits"
        assert call_count == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_enrich_highlight_adds_book_fields(self, make_client):
        highlight = {"id": 1, "text": "test", "book_id": 100}

        make_client._book_cache[100] = {
            "book_title": "Atomic Habits",
            "book_author": "James Clear",
            "source_url": "https://example.com",
        }

        enriched = await make_client.enrich_highlight(highlight)
        assert enriched["book_title"] == "Atomic Habits"
        assert enriched["book_author"] == "James Clear"
