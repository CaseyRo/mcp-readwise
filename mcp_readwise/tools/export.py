"""Export tool — bulk highlight export with cursor pagination."""

from __future__ import annotations

from typing import Optional

from mcp_readwise.client import client
from mcp_readwise.models.highlights import ExportResult


async def export_highlights(
    updated_after: Optional[str] = None,
    book_ids: Optional[list[int]] = None,
    cursor: Optional[str] = None,
) -> ExportResult:
    """Bulk export highlights, optionally filtered by date or specific books.

    Use cursor from a previous response to paginate through large exports.
    Each result includes the full highlight with book metadata attached.

    This uses the export endpoint — use it for bulk data retrieval, not for
    interactive queries. For interactive use, prefer search_highlights or
    list_highlights instead.
    """
    params: dict = {}
    if updated_after:
        params["updatedAfter"] = updated_after
    if book_ids:
        params["ids"] = ",".join(str(bid) for bid in book_ids)
    if cursor:
        params["pageCursor"] = cursor

    data = await client.get("/api/v2/export/", **params)
    results = data.get("results", [])
    next_cursor = data.get("nextPageCursor")

    return ExportResult(results=results, next_cursor=next_cursor)
