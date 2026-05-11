"""Centralized async HTTP client for the Readwise API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from mcp_readwise.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_MAX_RETRIES_429 = 6
_BACKOFF_BASE = 2.0
_RETRY_AFTER_CAP_SECONDS = 90.0
_BOOK_CACHE_SIZE = 512


class ReadwiseClient:
    """Async HTTP client for Readwise v2 and Reader v3 APIs.

    Handles auth headers, retries, and rate-limit backoff centrally.
    """

    def __init__(self) -> None:
        token = settings.readwise_token.get_secret_value()
        base_url = settings.readwise_base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        self._book_cache: dict[int, dict[str, Any]] = {}

    def _parse_retry_after(self, resp: httpx.Response) -> float | None:
        """Parse the Retry-After header (seconds form). Returns None if absent or invalid."""
        try:
            raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        except (AttributeError, TypeError):
            return None
        if not raw or not isinstance(raw, str):
            return None
        try:
            seconds = float(raw)
        except ValueError:
            return None
        return max(0.0, min(seconds, _RETRY_AFTER_CAP_SECONDS))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request with retry and rate-limit backoff.

        429 responses honor the Retry-After header when present, capped at
        90 seconds. Without Retry-After, exponential backoff is used. 429s
        have an independent retry budget (`_MAX_RETRIES_429`) since rate
        limits are normal upstream behavior, not failures; this keeps a
        429 storm from exhausting the 5xx retry slot.
        """
        server_error_attempts = 0
        rate_limited_attempts = 0
        while True:
            try:
                resp = await self._client.request(
                    method, path, params=params, json=json
                )
                if resp.status_code == 429:
                    rate_limited_attempts += 1
                    if rate_limited_attempts > _MAX_RETRIES_429:
                        raise httpx.HTTPStatusError(
                            "429 Too Many Requests (retry budget exhausted)",
                            request=resp.request,
                            response=resp,
                        )
                    retry_after = self._parse_retry_after(resp)
                    if retry_after is not None:
                        wait = retry_after
                        logger.warning(
                            "Rate limited (429), Retry-After=%.1fs (attempt %d/%d)",
                            wait,
                            rate_limited_attempts,
                            _MAX_RETRIES_429,
                        )
                    else:
                        wait = _BACKOFF_BASE ** rate_limited_attempts
                        logger.warning(
                            "Rate limited (429), exponential backoff %.1fs (attempt %d/%d)",
                            wait,
                            rate_limited_attempts,
                            _MAX_RETRIES_429,
                        )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                if resp.status_code == 204:
                    return None
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    server_error_attempts += 1
                    if server_error_attempts > _MAX_RETRIES:
                        raise
                    wait = _BACKOFF_BASE ** server_error_attempts
                    logger.warning(
                        "Server error %d, retry %d/%d in %.1fs",
                        exc.response.status_code,
                        server_error_attempts,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout):
                server_error_attempts += 1
                if server_error_attempts > _MAX_RETRIES:
                    raise
                wait = _BACKOFF_BASE ** server_error_attempts
                logger.warning(
                    "Connection error, retry %d/%d in %.1fs",
                    server_error_attempts,
                    _MAX_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

    async def get(self, path: str, **params: Any) -> Any:
        cleaned = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", path, params=cleaned or None)

    async def post(self, path: str, **data: Any) -> Any:
        cleaned = {k: v for k, v in data.items() if v is not None}
        return await self._request("POST", path, json=cleaned or None)

    async def patch(self, path: str, **data: Any) -> Any:
        cleaned = {k: v for k, v in data.items() if v is not None}
        return await self._request("PATCH", path, json=cleaned or None)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # --- Book metadata cache for joining into highlight responses ---

    async def get_book_metadata(self, book_id: int) -> dict[str, Any]:
        """Get book metadata, using cache to avoid repeated API calls.

        Returns a dict with `book_title`, `book_author`, `source_url`,
        `source` (kindle/reader/ibooks/...), `num_highlights`, and `category`.
        The richer fields are needed by the engagement scoring module.
        """
        if book_id in self._book_cache:
            return self._book_cache[book_id]
        try:
            data = await self.get(f"/api/v2/books/{book_id}")
            meta = {
                "book_title": data.get("title", ""),
                "book_author": data.get("author", ""),
                "source_url": data.get("source_url", ""),
                "source": data.get("source", ""),
                "num_highlights": data.get("num_highlights", 0),
                "category": data.get("category", ""),
            }
            if len(self._book_cache) < _BOOK_CACHE_SIZE:
                self._book_cache[book_id] = meta
            return meta
        except Exception:
            logger.warning("Failed to fetch book metadata for %d", book_id)
            return {
                "book_title": "",
                "book_author": "",
                "source_url": "",
                "source": "",
                "num_highlights": 0,
                "category": "",
            }

    async def enrich_highlight(self, highlight: dict[str, Any]) -> dict[str, Any]:
        """Add book metadata to a highlight dict."""
        book_id = highlight.get("book_id")
        if book_id:
            meta = await self.get_book_metadata(book_id)
            highlight.update(meta)
        return highlight

    async def close(self) -> None:
        await self._client.aclose()


client = ReadwiseClient()
