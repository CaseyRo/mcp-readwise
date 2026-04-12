"""Highlight tools — search, list, get, create, update, delete."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from mcp_readwise.client import client
from mcp_readwise.models.highlights import (
    HighlightListResult,
    HighlightResult,
)


async def search_highlights(
    query: str,
    search_type: Literal["semantic", "fulltext", "hybrid"] = "hybrid",
    book_id: Optional[int] = None,
    tags: Optional[list[str]] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> HighlightListResult:
    """Search highlights using semantic (vector), full-text, or hybrid search.

    Use 'semantic' for concept/meaning queries like 'ideas about habit formation'.
    Use 'fulltext' for exact phrase matching like 'atomic habits'.
    Use 'hybrid' (default) when unsure — combines both signals.

    Returns highlights with book title, author, and source URL inline.
    """
    payload: dict = {}

    if search_type in ("semantic", "hybrid"):
        payload["vector_search_term"] = query

    if search_type in ("fulltext", "hybrid"):
        full_text_queries = [
            {"field_name": "highlight_plaintext", "search_term": query}
        ]
        if tags:
            for tag in tags:
                full_text_queries.append(
                    {"field_name": "highlight_tags", "search_term": tag}
                )
        payload["full_text_queries"] = full_text_queries

    data = await client.post("/api/mcp/highlights", **payload)
    raw_results = data.get("results", []) if data else []

    results = []
    for item in raw_results[:limit]:
        if book_id and item.get("book_id") != book_id:
            continue
        enriched = await client.enrich_highlight(item)
        tag_list = [t.get("name", "") for t in item.get("tags", [])] if isinstance(item.get("tags"), list) else []
        results.append(
            HighlightResult(
                id=item.get("id", 0),
                text=item.get("text", ""),
                note=item.get("note", ""),
                tags=tag_list,
                book_id=item.get("book_id", 0),
                book_title=enriched.get("book_title", ""),
                book_author=enriched.get("book_author", ""),
                source_url=enriched.get("source_url", ""),
                highlighted_at=item.get("highlighted_at", ""),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
        )

    return HighlightListResult(results=results, total=len(results))


async def list_highlights(
    book_id: Optional[int] = None,
    tag: Optional[str] = None,
    updated_after: Optional[str] = None,
    page: int = 1,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> HighlightListResult:
    """List highlights with optional filtering by book, tag, or recency.

    Use updated_after with an ISO 8601 date string to get recent highlights,
    e.g. '2024-01-01' or '2024-01-01T00:00:00Z'.

    Returns highlights plus total count and next_page for pagination.
    """
    params: dict = {"page": page, "page_size": limit}
    if book_id:
        params["book_id"] = book_id
    if updated_after:
        params["updated__gt"] = updated_after

    data = await client.get("/api/v2/highlights/", **params)
    raw_results = data.get("results", [])
    total = data.get("count", len(raw_results))
    next_url = data.get("next")
    next_page = page + 1 if next_url else None

    results = []
    for item in raw_results:
        tag_list = [t.get("name", "") for t in item.get("tags", [])] if isinstance(item.get("tags"), list) else []
        if tag and tag not in tag_list:
            continue
        enriched = await client.enrich_highlight(item)
        results.append(
            HighlightResult(
                id=item.get("id", 0),
                text=item.get("text", ""),
                note=item.get("note", ""),
                tags=tag_list,
                book_id=item.get("book_id", 0),
                book_title=enriched.get("book_title", ""),
                book_author=enriched.get("book_author", ""),
                source_url=enriched.get("source_url", ""),
                highlighted_at=item.get("highlighted_at", ""),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
        )

    return HighlightListResult(results=results, total=total, next_page=next_page)


async def get_highlight(highlight_id: int) -> HighlightResult:
    """Get a single highlight by ID with book metadata included.

    Returns the full highlight including text, note, tags, book title,
    book author, and source URL.
    """
    data = await client.get(f"/api/v2/highlights/{highlight_id}")
    enriched = await client.enrich_highlight(data)
    tag_list = [t.get("name", "") for t in data.get("tags", [])] if isinstance(data.get("tags"), list) else []

    return HighlightResult(
        id=data.get("id", 0),
        text=data.get("text", ""),
        note=data.get("note", ""),
        tags=tag_list,
        book_id=data.get("book_id", 0),
        book_title=enriched.get("book_title", ""),
        book_author=enriched.get("book_author", ""),
        source_url=enriched.get("source_url", ""),
        highlighted_at=data.get("highlighted_at", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


async def create_highlight(
    text: str,
    book_id: int,
    note: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> HighlightResult:
    """Create a new highlight on a book.

    Requires the highlight text and the book_id it belongs to.
    Optionally add a note and tags. Returns the full created highlight.
    """
    highlight_data: dict = {"text": text, "book_id": book_id}
    if note:
        highlight_data["note"] = note

    payload = {"highlights": [highlight_data]}
    data = await client.post("/api/v2/highlights/", **payload)

    results = data if isinstance(data, list) else data.get("results", [data])
    item = results[0] if results else {}

    if tags:
        for tag_name in tags:
            await client.post(
                f"/api/v2/highlights/{item.get('id')}/tags/",
                name=tag_name,
            )

    if item.get("id"):
        return await get_highlight(item["id"])

    return HighlightResult(id=item.get("id", 0), text=text, book_id=book_id)


async def update_highlight(
    highlight_id: int,
    text: Optional[str] = None,
    note: Optional[str] = None,
) -> HighlightResult:
    """Update an existing highlight's text or note.

    Only the provided fields are updated. Returns the full updated highlight.
    """
    payload: dict = {}
    if text is not None:
        payload["text"] = text
    if note is not None:
        payload["note"] = note

    await client.patch(f"/api/v2/highlights/{highlight_id}", **payload)
    return await get_highlight(highlight_id)


async def delete_highlight(highlight_id: int) -> dict:
    """Delete a highlight by ID.

    Returns a confirmation with the deleted highlight's ID.
    """
    await client.delete(f"/api/v2/highlights/{highlight_id}")
    return {"deleted": True, "id": highlight_id}
