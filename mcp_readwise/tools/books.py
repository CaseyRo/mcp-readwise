"""Book/source tools — list and get."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from mcp_readwise.client import client
from mcp_readwise.models.books import BookListResult, BookResult


async def list_books(
    category: Optional[
        Literal["books", "articles", "tweets", "podcasts", "supplementals"]
    ] = None,
    source: Optional[str] = None,
    num_highlights_gte: Optional[int] = None,
    updated_after: Optional[str] = None,
    page: int = 1,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> BookListResult:
    """List books and sources with optional filtering.

    category accepts: 'books', 'articles', 'tweets', 'podcasts', 'supplementals'.
    Use num_highlights_gte to filter to sources with at least N highlights.
    Use updated_after with an ISO 8601 date to get recently updated sources.
    """
    params: dict = {"page": page, "page_size": limit}
    if category:
        params["category"] = category
    if source:
        params["source"] = source
    if updated_after:
        params["updated__gt"] = updated_after

    data = await client.get("/api/v2/books/", **params)
    raw_results = data.get("results", [])
    total = data.get("count", len(raw_results))
    next_url = data.get("next")
    next_page = page + 1 if next_url else None

    results = []
    for item in raw_results:
        if num_highlights_gte and item.get("num_highlights", 0) < num_highlights_gte:
            continue
        results.append(
            BookResult(
                id=item.get("id", 0),
                title=item.get("title", ""),
                author=item.get("author", ""),
                category=item.get("category", ""),
                source=item.get("source", ""),
                num_highlights=item.get("num_highlights", 0),
                cover_image_url=item.get("cover_image_url", ""),
                source_url=item.get("source_url", ""),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
        )

    return BookListResult(results=results, total=total, next_page=next_page)


async def get_book(book_id: int) -> BookResult:
    """Get a single book/source by ID.

    Returns full book metadata including title, author, category, source,
    highlight count, cover image URL, and source URL.
    """
    data = await client.get(f"/api/v2/books/{book_id}")
    return BookResult(
        id=data.get("id", 0),
        title=data.get("title", ""),
        author=data.get("author", ""),
        category=data.get("category", ""),
        source=data.get("source", ""),
        num_highlights=data.get("num_highlights", 0),
        cover_image_url=data.get("cover_image_url", ""),
        source_url=data.get("source_url", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )
