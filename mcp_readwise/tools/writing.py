"""writing_material tool — composable bundle for drafting from highlights."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from mcp_readwise.client import client
from mcp_readwise.engagement import get_index
from mcp_readwise.models.source import Source
from mcp_readwise.models.writing import HighlightInMaterial, WritingMaterial


_SOURCE_FIRST_DEFAULT_LIMIT = 200
_TOPIC_FIRST_DEFAULT_LIMIT = 30


def _validate_args(
    book_id: Optional[int],
    document_id: Optional[str],
    title_search: Optional[str],
    topic: Optional[str],
) -> str:
    """Ensure exactly one of the four args is set; return its name."""
    provided = [
        ("book_id", book_id is not None),
        ("document_id", bool(document_id)),
        ("title_search", bool(title_search)),
        ("topic", bool(topic)),
    ]
    set_args = [name for name, is_set in provided if is_set]
    if len(set_args) == 0:
        raise ValueError(
            "writing_material requires exactly one of: book_id, "
            "document_id, title_search, topic"
        )
    if len(set_args) > 1:
        raise ValueError(
            f"writing_material accepts exactly one of book_id, document_id, "
            f"title_search, topic. Got: {', '.join(set_args)}"
        )
    return set_args[0]


def _resolve_title_search(
    query: str, sources: dict[str, Source]
) -> Source:
    """Find a single source by case-insensitive title contains-match.

    Raises if zero or multiple sources match.
    """
    q = query.strip().lower()
    matches = [s for s in sources.values() if q in s.title.lower()]
    if not matches:
        raise ValueError(
            f"No source matched title_search={query!r}. "
            "Try a different query or use book_id / document_id."
        )
    if len(matches) > 1:
        candidates = ", ".join(
            f"{m.title!r} (book_id={m.book_id}, document_id={m.document_id})"
            for m in matches[:10]
        )
        raise ValueError(
            f"Multiple sources matched title_search={query!r}. "
            f"Disambiguate by ID. Candidates: {candidates}"
        )
    return matches[0]


def _resolve_source(
    *,
    book_id: Optional[int],
    document_id: Optional[str],
    title_search: Optional[str],
    sources: dict[str, Source],
) -> Source:
    """Look up a single Source from the engagement index by id or title."""
    if book_id is not None:
        s = sources.get(f"book:{book_id}")
        if s is None:
            raise ValueError(f"No source found for book_id={book_id}")
        return s
    if document_id:
        s = sources.get(f"doc:{document_id}")
        if s is not None:
            return s
        # Document might be the v3 ID joined to a v2 book — search by document_id field
        for src in sources.values():
            if src.document_id == document_id:
                return src
        raise ValueError(f"No source found for document_id={document_id!r}")
    if title_search:
        return _resolve_title_search(title_search, sources)
    raise ValueError("No identifier provided")


async def _fetch_highlights_for_book(
    book_id: int, limit: int
) -> tuple[list[HighlightInMaterial], int]:
    """Paginate /api/v2/highlights/?book_id=X up to `limit` non-discarded.

    Returns (highlights_list, total_seen). Stops once we have `limit` items.
    """
    out: list[HighlightInMaterial] = []
    total = 0
    page = 1
    while len(out) < limit:
        page_size = min(100, limit - len(out) + 50)  # over-fetch a bit
        data = await client.get(
            "/api/v2/highlights/", book_id=book_id, page=page, page_size=page_size
        )
        items = data.get("results", []) if data else []
        if not items:
            break
        for h in items:
            total += 1
            if h.get("is_discard"):
                continue
            tags = h.get("tags", []) or []
            tag_names = [
                t.get("name", "") if isinstance(t, dict) else str(t) for t in tags
            ]
            out.append(
                HighlightInMaterial(
                    id=h.get("id", 0),
                    text=h.get("text", "") or "",
                    note=h.get("note", "") or "",
                    tags=tag_names,
                    highlighted_at=h.get("highlighted_at", "") or "",
                    is_favorite=bool(h.get("is_favorite", False)),
                    book_id=h.get("book_id"),
                )
            )
            if len(out) >= limit:
                break
        next_url = data.get("next") if data else None
        if not next_url:
            break
        page += 1
    return out, total


async def _fetch_v3_summary(document_id: str) -> str:
    """Pull the Reader-generated summary for a v3 document (best-effort)."""
    try:
        data = await client.get(f"/api/v3/get/{document_id}/")
        return data.get("summary", "") or "" if data else ""
    except Exception:
        return ""


async def _source_first(
    source: Source, limit: int
) -> WritingMaterial:
    """Build a WritingMaterial bundle for a single source."""
    highlights: list[HighlightInMaterial] = []
    total = 0
    if source.book_id:
        highlights, total = await _fetch_highlights_for_book(
            source.book_id, limit
        )
        for h in highlights:
            h.book_title = source.title
            h.book_author = source.author

    summary = ""
    if source.document_id:
        summary = await _fetch_v3_summary(source.document_id)

    has_notes = any(h.note.strip() for h in highlights)

    return WritingMaterial(
        sources=[source],
        highlights=highlights,
        grouped_by_source={source.title: highlights} if source.title else {},
        summary=summary,
        has_notes=has_notes,
        has_legacy=source.is_legacy,
        has_more=total > len(highlights),
        total_highlights=total,
    )


def _book_id_for_highlight(item: dict[str, Any]) -> Optional[int]:
    """Extract book_id from a search-result attributes dict."""
    attrs = item.get("attributes", {}) or {}
    return attrs.get("book_id") or item.get("book_id")


async def _topic_first(
    topic: str, min_engagement: float, limit: int, sources: dict[str, Source]
) -> WritingMaterial:
    """Build a WritingMaterial bundle for a topic search."""
    # Use the existing semantic search path (kept internal, not registered as
    # an MCP tool after Section 6).
    payload = {
        "vector_search_term": topic,
        "full_text_queries": [
            {"field_name": "highlight_plaintext", "search_term": topic}
        ],
    }
    data = await client.post("/api/mcp/highlights", **payload)
    raw_results = (data or {}).get("results", [])

    out: list[HighlightInMaterial] = []
    selected_sources: dict[int, Source] = {}
    grouped: dict[str, list[HighlightInMaterial]] = {}

    for item in raw_results:
        if len(out) >= limit:
            break
        h_book_id = _book_id_for_highlight(item)
        if not h_book_id:
            continue
        source = sources.get(f"book:{h_book_id}")
        if source is None:
            continue
        if source.engagement.raw < min_engagement:
            continue

        attrs = item.get("attributes", {}) or {}
        text = (
            attrs.get("highlight_plaintext")
            or attrs.get("text")
            or item.get("text", "")
            or ""
        )
        note = attrs.get("highlight_note") or item.get("note", "") or ""
        raw_tags = (
            attrs.get("highlight_tags")
            or attrs.get("document_tags")
            or item.get("tags")
            or []
        )
        if isinstance(raw_tags, str):
            tag_names = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tag_names = [
                t.get("name", "") if isinstance(t, dict) else str(t) for t in raw_tags
            ]
        else:
            tag_names = []

        h = HighlightInMaterial(
            id=item.get("id", 0),
            text=text,
            note=note,
            tags=tag_names,
            highlighted_at=attrs.get("highlighted_at", "") or "",
            is_favorite=bool(attrs.get("is_favorite", False)),
            book_id=h_book_id,
            book_title=source.title,
            book_author=source.author,
        )
        out.append(h)
        selected_sources[h_book_id] = source
        grouped.setdefault(source.title, []).append(h)

    sources_list = sorted(
        selected_sources.values(), key=lambda s: s.engagement.raw, reverse=True
    )
    has_notes = any(h.note.strip() for h in out)
    has_legacy = any(s.is_legacy for s in sources_list)

    return WritingMaterial(
        sources=sources_list,
        highlights=out,
        grouped_by_source=grouped,
        summary="",
        has_notes=has_notes,
        has_legacy=has_legacy,
        has_more=False,  # topic search doesn't paginate; limit is the cap
        total_highlights=len(out),
    )


async def writing_material(
    book_id: Optional[int] = None,
    document_id: Optional[str] = None,
    title_search: Optional[str] = None,
    topic: Optional[str] = None,
    min_engagement: Annotated[float, Field(ge=0.0, le=5.0)] = 0.7,
    limit: Optional[Annotated[int, Field(ge=1, le=200)]] = None,
) -> WritingMaterial:
    """Bundle the inputs an LLM needs to draft from Readwise content.

    Provide exactly one of:
      - `book_id`: int — v2 book id (source-first; up to 200 highlights)
      - `document_id`: str — v3 document UUID (source-first)
      - `title_search`: str — fuzzy title match (source-first; errors on
        ambiguous matches with the candidate list)
      - `topic`: str — concept/theme search (topic-first; up to 30 highlights
        across multiple sources, filtered by `min_engagement`)

    `min_engagement` defaults to 0.7 — the floor for "any source with
    highlights." Lower it (e.g. 0.4) to include lightly-engaged legacy items
    or finished-but-unhighlighted articles.

    `limit` defaults differ by path: 200 for source-first (return everything
    in a single source, capped for safety), 30 for topic-first.
    """
    arg = _validate_args(book_id, document_id, title_search, topic)

    sources_dict = await get_index()

    if arg == "topic":
        effective_limit = limit if limit is not None else _TOPIC_FIRST_DEFAULT_LIMIT
        return await _topic_first(topic, min_engagement, effective_limit, sources_dict)

    effective_limit = limit if limit is not None else _SOURCE_FIRST_DEFAULT_LIMIT
    source = _resolve_source(
        book_id=book_id,
        document_id=document_id,
        title_search=title_search,
        sources=sources_dict,
    )
    return await _source_first(source, effective_limit)
