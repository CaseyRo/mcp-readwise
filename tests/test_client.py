"""Tests for the ReadwiseClient — retries, rate limits, headers."""

from __future__ import annotations

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
        mock_resp_429.headers = {}  # No Retry-After → exponential backoff

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

    @pytest.mark.asyncio
    async def test_retry_after_header_respected(self, make_client):
        """When 429 includes a Retry-After header, the client waits that long."""
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "47"}

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"ok": True}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_resp_429
            return mock_resp_ok

        sleep_waits = []

        async def capture_sleep(seconds):
            sleep_waits.append(seconds)

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", side_effect=capture_sleep):
                result = await make_client.get("/api/v2/export/")

        assert result == {"ok": True}
        assert sleep_waits == [47.0]

    @pytest.mark.asyncio
    async def test_retry_after_capped(self, make_client):
        """Retry-After values above the cap are clamped (defend against malicious or bug responses)."""
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "9999"}  # 2.5 hours — way too long

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp_429 if call_count == 1 else mock_resp_ok

        sleep_waits = []

        async def capture_sleep(seconds):
            sleep_waits.append(seconds)

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", side_effect=capture_sleep):
                await make_client.get("/api/v2/export/")

        # Capped at _RETRY_AFTER_CAP_SECONDS (90.0)
        assert sleep_waits == [90.0]

    @pytest.mark.asyncio
    async def test_429_retry_budget_independent_from_5xx(self, make_client):
        """A storm of 429s shouldn't exhaust the 5xx retry slot.

        With _MAX_RETRIES=3 and _MAX_RETRIES_429=6, six 429s in a row should
        still recover when the seventh request succeeds — even though that's
        more than _MAX_RETRIES total attempts.
        """
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "1"}

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"ok": True}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp_429 if call_count <= 5 else mock_resp_ok

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", new_callable=AsyncMock):
                result = await make_client.get("/api/v2/export/")

        assert call_count == 6
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_429_budget_eventually_exhausts(self, make_client):
        """After _MAX_RETRIES_429 + 1 consecutive 429s, the client gives up."""
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "1"}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp_429

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.HTTPStatusError, match="retry budget exhausted"):
                    await make_client.get("/api/v2/export/")

        # Exactly _MAX_RETRIES_429 + 1 = 7 attempts before bailing
        assert call_count == 7

    @pytest.mark.asyncio
    async def test_malformed_retry_after_falls_back_to_exponential(self, make_client):
        """Non-numeric Retry-After value should fall through to exponential backoff."""
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {}
        mock_resp_ok.raise_for_status = MagicMock()

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp_429 if call_count == 1 else mock_resp_ok

        sleep_waits = []

        async def capture_sleep(seconds):
            sleep_waits.append(seconds)

        with patch.object(make_client._client, "request", side_effect=mock_request):
            with patch("mcp_readwise.client.asyncio.sleep", side_effect=capture_sleep):
                await make_client.get("/api/v2/export/")

        # First retry → 2^1 = 2.0 seconds (HTTP-date format not supported; falls back)
        assert sleep_waits == [2.0]


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
