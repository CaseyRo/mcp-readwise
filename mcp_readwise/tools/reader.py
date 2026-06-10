"""Reader tools — list documents, get document, save URL, update progress."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from fastmcp import Context
from pydantic import AnyHttpUrl, Field

from mcp_readwise.client import client
from mcp_readwise.models.reader import (
    ReaderDocument,
    ReaderListPage,
    ReaderListResult,
)

# Safety cap for `reader_get_by_url` — the v3 list endpoint has no URL filter,
# so we paginate and match client-side. 20 pages * 100 items = 2000 docs scanned
# before giving up, which covers the practical "archive lookup" use case
# without unbounded API load. (CDI-1147)
_GET_BY_URL_MAX_PAGES = 20
_GET_BY_URL_PAGE_SIZE = 100

_DOC_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_doc_id(document_id: str) -> str:
    """Validate document ID to prevent path manipulation."""
    if not _DOC_ID_PATTERN.match(document_id):
        raise ValueError(
            "Invalid document_id: must be 1-64 alphanumeric/dash/underscore characters"
        )
    return document_id


def _parse_tags(raw: object) -> list[str]:
    """Normalize the v3 list endpoint's tag shape (dict-keyed or list) to names."""
    if isinstance(raw, dict):
        return list(raw.keys())
    if isinstance(raw, list):
        return [t.get("name", t) if isinstance(t, dict) else str(t) for t in raw]
    return []


def _item_to_document(item: dict) -> ReaderDocument:
    """Build a ReaderDocument from a raw v3 list/get response dict.

    Used by `list_documents`, `reader_list_documents`, and `reader_get_by_url`
    so all three share one normalization path.
    """
    return ReaderDocument(
        id=str(item.get("id", "")),
        title=item.get("title", "") or "",
        author=item.get("author", "") or "",
        source_url=item.get("source_url") or item.get("url", "") or "",
        category=item.get("category", "") or "",
        location=item.get("location", "") or "",
        reading_progress=item.get("reading_progress", 0.0) or 0.0,
        word_count=item.get("word_count", 0) or 0,
        summary=item.get("summary", "") or "",
        tags=_parse_tags(item.get("tags")),
        created_at=item.get("created_at", "") or "",
        updated_at=item.get("updated_at", "") or "",
        saved_at=item.get("saved_at", "") or "",
        first_opened_at=item.get("first_opened_at", "") or "",
        last_opened_at=item.get("last_opened_at", "") or "",
        last_moved_at=item.get("last_moved_at", "") or "",
    )


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
                saved_at=item.get("saved_at", ""),
                first_opened_at=item.get("first_opened_at", ""),
                last_opened_at=item.get("last_opened_at", ""),
                last_moved_at=item.get("last_moved_at", ""),
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
        saved_at=data.get("saved_at", ""),
        first_opened_at=data.get("first_opened_at", ""),
        last_opened_at=data.get("last_opened_at", ""),
        last_moved_at=data.get("last_moved_at", ""),
    )


async def save_url(
    url: AnyHttpUrl,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
    location: Literal["new", "later", "shortlist", "archive"] = "new",
    note: Optional[str] = None,
) -> ReaderDocument:
    """Save a URL to Readwise Reader.

    This is the primary way to add content to Reader. The service fetches
    and parses the article automatically. Only http:// and https:// URLs
    are accepted.

    location controls where it appears: 'new' (inbox), 'later', 'shortlist',
    or 'archive'. Default is 'new'. Use `note` (singular) for any annotation
    you want attached to the saved document.
    """
    # `url` arrives as a Pydantic `AnyHttpUrl`. Always coerce to `str` before
    # using it anywhere downstream (request payload, response fallback, model
    # construction) — `ReaderDocument.source_url` is typed `str` and Pydantic v2
    # does NOT auto-coerce `AnyHttpUrl` → `str` (CDI-1149).
    url_str = str(url)
    payload: dict = {"url": url_str, "location": location}
    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    if note:
        # Reader v3 endpoint accepts the field as `notes` (plural); MCP surface
        # standardizes on singular `note` to match the highlights endpoints.
        payload["notes"] = note

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
        source_url=data.get("source_url") or url_str,
        category=data.get("category", ""),
        location=data.get("location", location),
        reading_progress=0.0,
        tags=doc_tags,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        saved_at=data.get("saved_at", ""),
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


# --- CDI-1147: by-URL / archive lookup (beyond the engagement cache) ---


def _canonicalize_url(url: str) -> str:
    """Lower-case scheme+host and strip trailing slash for loose URL matching.

    Readwise stores `source_url` as the canonical URL it resolved from the
    save call. Users searching for a doc by URL often paste a slightly
    different form (with/without trailing slash, different case host).
    This keeps the match forgiving without going full URL-normalization.
    """
    s = str(url).strip()
    # Drop fragment
    if "#" in s:
        s = s.split("#", 1)[0]
    # Drop trailing slash (but keep root "/")
    if s.endswith("/") and s.count("/") > 3:
        s = s[:-1]
    # Lower-case the scheme+host portion only
    if "://" in s:
        scheme, rest = s.split("://", 1)
        if "/" in rest:
            host, path = rest.split("/", 1)
            s = f"{scheme.lower()}://{host.lower()}/{path}"
        else:
            s = f"{scheme.lower()}://{rest.lower()}"
    return s


async def reader_list_documents(
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
    page_cursor: Optional[str] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 100,
) -> ReaderListPage:
    """List Reader documents from the full library (not just the engagement cache).

    Goes directly against Readwise Reader v3 `/api/v3/list/` and returns the
    raw document records. Unlike `reading_status` / `writing_material`, this
    surface is URL/archive-shaped, not engagement-shaped — use it to browse
    archived/saved-but-unread material that never made it into the
    engagement index.

    Pagination is cursor-based: pass `next_cursor` from the previous page
    back as `page_cursor`. `next_cursor` is `null` on the final page.

    Filters:
      - `location`: 'new' (inbox), 'later', 'shortlist', 'archive', or 'feed'.
      - `category`: 'article', 'email', 'rss', 'highlight', 'note', 'pdf',
        'epub', 'tweet', 'video'.
      - `updated_after`: ISO 8601 datetime to fetch only docs updated since.

    Tip: `location='archive'` is the typical entry point for "the article
    I archived a while back" lookups.
    """
    params: dict = {"limit": limit}
    if location:
        params["location"] = location
    if category:
        params["category"] = category
    if updated_after:
        params["updatedAfter"] = updated_after
    if page_cursor:
        params["pageCursor"] = page_cursor

    data = await client.get("/api/v3/list/", **params)
    raw_results = data.get("results", []) or []
    next_cursor = data.get("nextPageCursor")
    count = data.get("count", len(raw_results))

    results = [_item_to_document(item) for item in raw_results]
    return ReaderListPage(results=results, count=count, next_cursor=next_cursor)


async def reader_get_by_url(
    url: AnyHttpUrl,
    location: Optional[
        Literal["new", "later", "shortlist", "archive", "feed"]
    ] = None,
    ctx: Context | None = None,
) -> Optional[ReaderDocument]:
    """Find a single Reader document by its source URL.

    The v3 list endpoint has no `url` filter, so this paginates the library
    and matches `source_url` client-side (case-insensitive on host, ignoring
    trailing slash and fragment). Returns the first match, or `None` if no
    document with that URL is in the library.

    Pass `location` to narrow the scan (e.g. `location='archive'` is much
    faster when you know the doc was archived). Without `location`, the scan
    covers the entire library, capped at ~2000 docs as a safety guard.

    Returns the same `ReaderDocument` shape as `get_document` (without
    `content` — call `get_document` with the returned `id` for the body).
    """
    target = _canonicalize_url(str(url))

    cursor: Optional[str] = None
    for page_num in range(_GET_BY_URL_MAX_PAGES):
        params: dict = {"limit": _GET_BY_URL_PAGE_SIZE}
        if location:
            params["location"] = location
        if cursor:
            params["pageCursor"] = cursor

        if ctx is not None:
            await ctx.report_progress(
                progress=page_num, total=_GET_BY_URL_MAX_PAGES
            )

        data = await client.get("/api/v3/list/", **params)
        for item in data.get("results", []) or []:
            candidate = (
                item.get("source_url")
                or item.get("url")
                or ""
            )
            if not candidate:
                continue
            if _canonicalize_url(candidate) == target:
                if ctx is not None:
                    await ctx.info(f"Matched on page {page_num + 1}")
                return _item_to_document(item)

        cursor = data.get("nextPageCursor")
        if not cursor:
            break

    if ctx is not None:
        await ctx.info("No matching document found in the scanned pages.")
    return None
