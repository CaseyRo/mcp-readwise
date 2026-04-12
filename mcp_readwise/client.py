"""Centralized async HTTP client for the Readwise API."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

import httpx

from mcp_readwise.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0
_BOOK_CACHE_SIZE = 256


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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request with retry and rate-limit backoff."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method, path, params=params, json=json
                )
                if resp.status_code == 429:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning("Rate limited (429), backing off %.1fs", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                if resp.status_code == 204:
                    return None
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Server error %d, retry %d/%d in %.1fs",
                        exc.response.status_code,
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    last_exc = exc
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Connection error, retry %d/%d in %.1fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    last_exc = exc
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("Retries exhausted")

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
        """Get book metadata, using cache to avoid repeated API calls."""
        if book_id in self._book_cache:
            return self._book_cache[book_id]
        try:
            data = await self.get(f"/api/v2/books/{book_id}")
            meta = {
                "book_title": data.get("title", ""),
                "book_author": data.get("author", ""),
                "source_url": data.get("source_url", ""),
            }
            if len(self._book_cache) < _BOOK_CACHE_SIZE:
                self._book_cache[book_id] = meta
            return meta
        except Exception:
            logger.warning("Failed to fetch book metadata for %d", book_id)
            return {"book_title": "", "book_author": "", "source_url": ""}

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
