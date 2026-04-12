"""Reader tools — list documents, get document, save URL, update progress."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from pydantic import AnyHttpUrl, Field

from mcp_readwise.client import client
from mcp_readwise.models.reader import ReaderDocument, ReaderListResult

_DOC_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_doc_id(document_id: str) -> str:
    """Validate document ID to prevent path manipulation."""
    if not _DOC_ID_PATTERN.match(document_id):
        raise ValueError(
            f"Invalid document_id: must be 1-64 alphanumeric/dash/underscore characters"
        )
    return document_id


async def list_documents(
    location: Optional[
        Literal["new", "later", "shortlist", "archive", "feed"]
    ] = None,
    category: Optional[
        Literal[
            "article", "email", "rss", "highlight", "note",
            "pdf", "epub", "tweet", "video",
        ]
    ] = None,
    updated_after: Optional[str] = None,
    page: int = 1,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> ReaderListResult:
    """List documents in Readwise Reader with optional filters.

    location accepts: 'new' (inbox), 'later', 'shortlist', 'archive', 'feed'.
    category accepts: 'article', 'email', 'rss', 'highlight', 'note', 'pdf',
    'epub', 'tweet', 'video'.
    Use updated_after with an ISO 8601 date to get recently updated docs.
    """
    params: dict = {"page": page, "page_size": limit}
    if location:
        params["location"] = location
    if category:
        params["category"] = category
    if updated_after:
        params["updatedAfter"] = updated_after

    data = await client.get("/api/v3/list/", **params)
    raw_results = data.get("results", [])
    total = data.get("count", len(raw_results))
    next_url = data.get("nextPageCursor")
    next_page = page + 1 if next_url else None

    results = []
    for item in raw_results:
        tags = []
        if isinstance(item.get("tags"), dict):
            tags = list(item["tags"].keys())
        elif isinstance(item.get("tags"), list):
            tags = [t.get("name", t) if isinstance(t, dict) else str(t) for t in item["tags"]]

        results.append(
            ReaderDocument(
                id=str(item.get("id", "")),
                title=item.get("title", ""),
                author=item.get("author", ""),
                source_url=item.get("source_url", item.get("url", "")),
                category=item.get("category", ""),
                location=item.get("location", ""),
                reading_progress=item.get("reading_progress", 0.0),
                word_count=item.get("word_count", 0),
                summary=item.get("summary", ""),
                tags=tags,
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
        )

    return ReaderListResult(results=results, total=total, next_page=next_page)


async def get_document(document_id: str) -> ReaderDocument:
    """Get a single Reader document by ID with full content.

    Returns the complete document including title, author, content,
    summary, reading progress, tags, and source URL.
    """
    _validate_doc_id(document_id)
    data = await client.get(f"/api/v3/get/{document_id}/")
    tags = []
    if isinstance(data.get("tags"), dict):
        tags = list(data["tags"].keys())
    elif isinstance(data.get("tags"), list):
        tags = [t.get("name", t) if isinstance(t, dict) else str(t) for t in data["tags"]]

    content = data.get("content", data.get("html", ""))
    if len(content) > 50_000:
        content = content[:50_000]

    return ReaderDocument(
        id=str(data.get("id", "")),
        title=data.get("title", ""),
        author=data.get("author", ""),
        source_url=data.get("source_url", data.get("url", "")),
        category=data.get("category", ""),
        location=data.get("location", ""),
        reading_progress=data.get("reading_progress", 0.0),
        word_count=data.get("word_count", 0),
        summary=data.get("summary", ""),
        content=content,
        tags=tags,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


async def save_url(
    url: AnyHttpUrl,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
    location: Literal["new", "later", "shortlist", "archive"] = "new",
    notes: Optional[str] = None,
) -> ReaderDocument:
    """Save a URL to Readwise Reader.

    This is the primary way to add content to Reader. The service fetches
    and parses the article automatically. Only http:// and https:// URLs
    are accepted.

    location controls where it appears: 'new' (inbox), 'later', 'shortlist',
    or 'archive'. Default is 'new'.
    """
    payload: dict = {"url": str(url), "location": location}
    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    if notes:
        payload["notes"] = notes

    data = await client.post("/api/v3/save/", **payload)

    doc_tags = []
    if isinstance(data.get("tags"), dict):
        doc_tags = list(data["tags"].keys())
    elif isinstance(data.get("tags"), list):
        doc_tags = [t.get("name", t) if isinstance(t, dict) else str(t) for t in data["tags"]]

    return ReaderDocument(
        id=str(data.get("id", "")),
        title=data.get("title", title or ""),
        author=data.get("author", ""),
        source_url=data.get("source_url", url),
        category=data.get("category", ""),
        location=data.get("location", location),
        reading_progress=0.0,
        tags=doc_tags,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


async def update_progress(
    document_id: str,
    reading_progress: Annotated[float, Field(ge=0.0, le=1.0)],
) -> ReaderDocument:
    """Update the reading progress for a Reader document.

    reading_progress is a float from 0.0 (unread) to 1.0 (finished).
    Returns the updated document.
    """
    _validate_doc_id(document_id)
    await client.patch(
        f"/api/v3/update/{document_id}/",
        reading_progress=reading_progress,
    )
    return await get_document(document_id)
