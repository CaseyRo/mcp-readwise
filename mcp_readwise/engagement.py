"""Engagement index — joins v2 books and v3 documents, scores each source.

The engagement index is the load-bearing primitive for the read tools
(`reading_status` and `writing_material`). It paginates the Readwise v2
export and Reader v3 list once per TTL window, joins them by ULID and URL,
and computes a vector engagement score per source.

See `openspec/changes/workflow-shaped-tools/design.md` for the formula
and decision rationale.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from mcp_readwise.client import client
from mcp_readwise.config import settings
from mcp_readwise.models.source import EngagementScore, Source

logger = logging.getLogger(__name__)


# ============= Tag denylist =============

_DEFAULT_TAG_DENYLIST: frozenset[str] = frozenset(
    {
        "h1", "h2", "h3", "h4", "h5", "h6",
        ".h1", ".h2", ".h3", ".h4", ".h5", ".h6",
        "discard", "favorite",
        "orange", "blue", "red", "green", "yellow", "purple",
    }
)


def _resolve_tag_denylist() -> frozenset[str]:
    """Build the tag denylist from settings, falling back to defaults."""
    raw = settings.engagement_tag_denylist
    if not raw:
        return _DEFAULT_TAG_DENYLIST
    custom = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return frozenset(custom)


def _is_user_tag(tag_name: str, denylist: frozenset[str]) -> bool:
    """True if the tag name should earn the annotation bonus."""
    if not tag_name:
        return False
    n = tag_name.strip().lower()
    if not n:
        return False
    if len(n) <= 1:
        return False
    if n in denylist:
        return False
    return True


def _is_structural_note(note: str) -> bool:
    """True if the note is auto-generated structural metadata (e.g. '.h1')."""
    s = (note or "").strip()
    if not s:
        return True
    if s.startswith(".") and len(s) <= 4:
        return True
    return False


# ============= Helpers =============

_ULID_RE = re.compile(r"^private://read/([a-zA-Z0-9_-]+)/?$")


def extract_ulid(source_url: Optional[str]) -> Optional[str]:
    """Extract a v3 document ULID from a `private://read/<ULID>` URL.

    Returns None for public URLs, empty inputs, or non-matching strings.
    """
    if not source_url:
        return None
    m = _ULID_RE.match(source_url.strip())
    return m.group(1) if m else None


def _parse_iso(timestamp: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp; return None on empty or malformed input."""
    if not timestamp:
        return None
    try:
        s = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ============= Scoring =============

_BASE_VALUES: dict[str, float] = {
    "highlighted": 0.70,
    "finished_no_hl": 0.50,
    "reading": 0.30,
    "saved_warm": 0.15,
    "saved_cold": 0.10,
    "legacy": 0.40,
}


def compute_base_layer(
    *,
    has_highlights: bool,
    is_legacy: bool,
    location: Optional[str],
    reading_progress: Optional[float],
) -> str:
    """Determine `base_layer` per the priority rules in design D3.

    Priority (first match wins):
      1. is_legacy → "legacy"  (v2-only sources score on the legacy track,
                                 even when they carry highlights — the spike
                                 era and absence of v3 data make this distinct
                                 from Reader-era highlighted engagement)
      2. has_highlights → "highlighted"  (overrides v3 progress/location for
                                          Reader-era sources where progress
                                          may be unsynced)
      3. location == "archive" OR progress >= 0.9 → "finished_no_hl"
      4. 0 < progress < 0.9 → "reading"
      5. location == "later", progress=0 → "saved_warm"
      6. otherwise → "saved_cold"
    """
    if is_legacy:
        return "legacy"
    if has_highlights:
        return "highlighted"
    if location == "archive":
        return "finished_no_hl"
    if reading_progress is not None and reading_progress >= 0.9:
        return "finished_no_hl"
    if reading_progress is not None and reading_progress > 0:
        return "reading"
    if location == "later":
        return "saved_warm"
    return "saved_cold"


def compute_density(num_highlights: int, base_layer: str) -> float:
    """Density bonus from non-discarded highlight count."""
    if base_layer not in ("highlighted", "legacy"):
        return 0.0
    if num_highlights >= 30:
        return 0.70
    if num_highlights >= 10:
        return 0.50
    if num_highlights >= 3:
        return 0.30
    if num_highlights >= 1:
        return 0.10
    return 0.0


def compute_recency(last_highlighted_at: Optional[str], now: datetime) -> float:
    """Recency tweak from max(highlighted_at)."""
    last = _parse_iso(last_highlighted_at)
    if last is None:
        return 0.0
    age = now - last
    if age <= timedelta(days=30):
        return 0.20
    if age >= timedelta(days=365 * 5):
        return -0.10
    return 0.0


def compute_annotation(
    has_user_note: bool, has_user_tag: bool, has_favorite: bool
) -> float:
    """Annotation bonus from notes, custom tags, and is_favorite."""
    bonus = 0.0
    if has_user_note:
        bonus += 0.30
    if has_user_tag:
        bonus += 0.10
    if has_favorite:
        bonus += 0.20
    return bonus


def compute_return_signal(
    highlight_dates: list[datetime],
    first_opened_at: Optional[str],
    last_opened_at: Optional[str],
    now: datetime,
) -> tuple[float, list[str]]:
    """Detect return signals; return (score, flags).

    Two stacking signals:
      1. Multi-era cluster: gap > 2 years between consecutive `highlighted_at` → +0.30
      2. Reader-era reopen: `last_opened_at` within 30d AND `first_opened_at` > 90d → +0.20
    """
    score = 0.0
    flags: list[str] = []

    if len(highlight_dates) >= 2:
        sorted_dates = sorted(highlight_dates)
        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i - 1]) > timedelta(days=730):
                score += 0.30
                flags.append("multi_era_return")
                break

    first = _parse_iso(first_opened_at)
    last = _parse_iso(last_opened_at)
    if first is not None and last is not None:
        if (now - last) <= timedelta(days=30) and (now - first) > timedelta(days=90):
            score += 0.20
            flags.append("reader_return")

    return score, flags


def compute_engagement(
    source: Source,
    highlight_dates: list[datetime],
    now: datetime,
) -> EngagementScore:
    """Assemble the full vector engagement score.

    The Source must have these aggregate fields populated by the index
    builder: `last_highlighted_at`, `has_user_note`, `has_user_tag`,
    `has_favorite`. The `highlight_dates` argument is the parsed list of
    highlight timestamps used for return-signal cluster detection.
    """
    has_highlights = source.num_highlights > 0
    base_layer = compute_base_layer(
        has_highlights=has_highlights,
        is_legacy=source.is_legacy,
        location=source.location,
        reading_progress=source.reading_progress,
    )

    base_value = _BASE_VALUES[base_layer]
    density = compute_density(source.num_highlights, base_layer)
    annotation = compute_annotation(
        has_user_note=source.has_user_note,
        has_user_tag=source.has_user_tag,
        has_favorite=source.has_favorite,
    )
    recency = compute_recency(source.last_highlighted_at, now)
    return_signal, return_flags = compute_return_signal(
        highlight_dates,
        source.first_opened_at,
        source.last_opened_at,
        now,
    )

    intensity = base_value + density + annotation
    raw = intensity + recency + return_signal

    flags = list(return_flags)
    # Junk drawer detection: cold/warm + no highlights + saved > 30d ago
    if base_layer in ("saved_cold", "saved_warm") and not has_highlights:
        saved_dt = _parse_iso(source.saved_at)
        if saved_dt and (now - saved_dt) > timedelta(days=30):
            flags.append("junk_drawer_candidate")

    return EngagementScore(
        raw=raw,
        intensity=intensity,
        recency=recency,
        return_strength=return_signal,
        base_layer=base_layer,
        flags=flags,
    )


# ============= Index builder =============


@dataclass
class _IndexCache:
    sources: dict[str, Source]
    built_at: float


_index_cache: Optional[_IndexCache] = None
_index_lock = asyncio.Lock()


async def _paginate_export() -> list[dict[str, Any]]:
    """Paginate `/api/v2/export/`, returning all books with highlights inline."""
    all_books: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        params: dict[str, Any] = {}
        if cursor:
            params["pageCursor"] = cursor
        data = await client.get("/api/v2/export/", **params)
        results = data.get("results", []) if data else []
        all_books.extend(results)
        next_cursor = data.get("nextPageCursor") if data else None
        if not next_cursor:
            break
        cursor = str(next_cursor)
    return all_books


# Library locations only — `feed` (RSS) is deliberately excluded. An
# unfiltered /api/v3/list/ returns every feed item too (observed 15k+ docs →
# ~156 pages at the Reader API's 20 req/min limit → ~7-minute cold builds
# that time out every reading_status call at the gateway). Feed items are
# not part of the user's library; highlighted feed items still surface via
# the v2 export on the legacy track.
_INDEX_LOCATIONS: tuple[str, ...] = ("new", "later", "shortlist", "archive")


async def _paginate_v3_list() -> list[dict[str, Any]]:
    """Paginate `/api/v3/list/` per library location, skipping `feed`."""
    all_docs: list[dict[str, Any]] = []
    for location in _INDEX_LOCATIONS:
        page_cursor: Optional[str] = None
        while True:
            params: dict[str, Any] = {"page_size": 100, "location": location}
            if page_cursor:
                params["pageCursor"] = page_cursor
            data = await client.get("/api/v3/list/", **params)
            results = data.get("results", []) if data else []
            all_docs.extend(results)
            next_cursor = data.get("nextPageCursor") if data else None
            if not next_cursor:
                break
            page_cursor = str(next_cursor)
    return all_docs


def _aggregate_highlights(
    highlights: list[dict[str, Any]],
    denylist: frozenset[str],
) -> tuple[int, Optional[str], list[datetime], bool, bool, bool]:
    """Walk highlights for one source; return aggregates.

    Returns: (num_non_discarded, last_highlighted_at, parsed_dates,
              has_user_note, has_user_tag, has_favorite)
    """
    last_highlighted: Optional[str] = None
    parsed_dates: list[datetime] = []
    has_user_note = False
    has_user_tag = False
    has_favorite = False
    count = 0

    for h in highlights:
        if h.get("is_discard"):
            continue
        count += 1

        hl_at = h.get("highlighted_at", "")
        if hl_at:
            if not last_highlighted or hl_at > last_highlighted:
                last_highlighted = hl_at
            d = _parse_iso(hl_at)
            if d is not None:
                parsed_dates.append(d)

        note = h.get("note", "")
        if note and not _is_structural_note(note):
            has_user_note = True

        for tag in h.get("tags", []) or []:
            tag_name = tag.get("name", "") if isinstance(tag, dict) else str(tag)
            if _is_user_tag(tag_name, denylist):
                has_user_tag = True

        if h.get("is_favorite"):
            has_favorite = True

    return count, last_highlighted, parsed_dates, has_user_note, has_user_tag, has_favorite


def _build_v3_indices(
    docs: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build (by_ulid, by_url) lookup dicts from v3 docs."""
    by_ulid: dict[str, dict[str, Any]] = {}
    by_url: dict[str, dict[str, Any]] = {}
    for doc in docs:
        doc_id = doc.get("id")
        if doc_id:
            by_ulid[str(doc_id)] = doc
        url = doc.get("source_url", "") or ""
        if url:
            by_url[url] = doc
    return by_ulid, by_url


def _join_v3(
    book: dict[str, Any],
    by_ulid: dict[str, dict[str, Any]],
    by_url: dict[str, dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Find the v3 doc for a v2 book, or None."""
    if book.get("source") != "reader":
        return None
    source_url = book.get("source_url", "") or ""
    ulid = extract_ulid(source_url)
    if ulid and ulid in by_ulid:
        return by_ulid[ulid]
    if source_url in by_url:
        return by_url[source_url]
    return None


async def build_index() -> dict[str, Source]:
    """Paginate v2 export and v3 list; join, score, return the index.

    Cold-call cost depends on corpus size. For ~150 sources / 730 highlights
    expect ~3 export pages + ~5 list pages (~8 API calls, 1–3s).
    """
    logger.info("Building engagement index...")
    started = time.time()

    export_books, v3_docs = await asyncio.gather(
        _paginate_export(),
        _paginate_v3_list(),
    )

    by_ulid, by_url = _build_v3_indices(v3_docs)
    denylist = _resolve_tag_denylist()
    now = datetime.now(timezone.utc)
    sources: dict[str, Source] = {}
    matched_v3_ids: set[str] = set()

    # Pass 1: every export book with its highlights
    for ebook in export_books:
        book_id = ebook.get("user_book_id") or ebook.get("id")
        if not book_id:
            continue

        v3_doc = _join_v3(ebook, by_ulid, by_url)
        if v3_doc and v3_doc.get("id"):
            matched_v3_ids.add(str(v3_doc["id"]))

        is_legacy = v3_doc is None

        highlights = ebook.get("highlights", []) or []
        (
            num_hl,
            last_hl_at,
            hl_dates,
            has_note,
            has_tag,
            has_fav,
        ) = _aggregate_highlights(highlights, denylist)

        source = Source(
            book_id=int(book_id),
            document_id=str(v3_doc["id"]) if v3_doc and v3_doc.get("id") else None,
            title=ebook.get("title", "") or "",
            author=ebook.get("author", "") or "",
            source_url=ebook.get("source_url", "") or "",
            category=ebook.get("category", "") or "",
            num_highlights=num_hl,
            source_field=ebook.get("source", "") or "",
            location=v3_doc.get("location") if v3_doc else None,
            reading_progress=v3_doc.get("reading_progress") if v3_doc else None,
            saved_at=v3_doc.get("saved_at") if v3_doc else None,
            first_opened_at=v3_doc.get("first_opened_at") if v3_doc else None,
            last_opened_at=v3_doc.get("last_opened_at") if v3_doc else None,
            last_moved_at=v3_doc.get("last_moved_at") if v3_doc else None,
            last_highlighted_at=last_hl_at,
            has_user_note=has_note,
            has_user_tag=has_tag,
            has_favorite=has_fav,
            is_legacy=is_legacy,
        )

        if is_legacy and last_hl_at:
            last_d = _parse_iso(last_hl_at)
            if last_d and (now - last_d) <= timedelta(days=365):
                source.legacy_recency = "warm"
            else:
                source.legacy_recency = "cold"

        source.engagement = compute_engagement(source, hl_dates, now)
        sources[f"book:{book_id}"] = source

    # Pass 2: v3 docs without an export book (saved-only, no highlights)
    for doc in v3_docs:
        doc_id = doc.get("id")
        if not doc_id or str(doc_id) in matched_v3_ids:
            continue
        source = Source(
            document_id=str(doc_id),
            title=doc.get("title", "") or "",
            author=doc.get("author", "") or "",
            source_url=doc.get("source_url", "") or "",
            category=doc.get("category", "") or "",
            num_highlights=0,
            source_field="reader",
            location=doc.get("location"),
            reading_progress=doc.get("reading_progress", 0.0),
            saved_at=doc.get("saved_at", "") or "",
            first_opened_at=doc.get("first_opened_at", "") or "",
            last_opened_at=doc.get("last_opened_at", "") or "",
            last_moved_at=doc.get("last_moved_at", "") or "",
            is_legacy=False,
        )
        source.engagement = compute_engagement(source, [], now)
        sources[f"doc:{doc_id}"] = source

    elapsed = time.time() - started
    logger.info(
        "Engagement index built: %d sources in %.2fs (%d export books, %d v3 docs)",
        len(sources),
        elapsed,
        len(export_books),
        len(v3_docs),
    )
    return sources


async def get_index(force_refresh: bool = False) -> dict[str, Source]:
    """Return the engagement index, building or refreshing as TTL allows.

    Concurrent calls are serialized via an asyncio.Lock so the index is
    built at most once per TTL window.
    """
    global _index_cache
    async with _index_lock:
        ttl = settings.engagement_index_ttl_seconds
        now = time.time()
        if (
            not force_refresh
            and _index_cache is not None
            and (now - _index_cache.built_at) < ttl
        ):
            return _index_cache.sources
        sources = await build_index()
        _index_cache = _IndexCache(sources=sources, built_at=now)
        return sources


def invalidate_cache() -> None:
    """Force the next get_index() call to rebuild."""
    global _index_cache
    _index_cache = None


def index_status() -> dict[str, Any]:
    """Snapshot of the cache state for /health or diagnostics."""
    if _index_cache is None:
        return {"built": False}
    age = time.time() - _index_cache.built_at
    return {
        "built": True,
        "built_at": _index_cache.built_at,
        "age_seconds": int(age),
        "source_count": len(_index_cache.sources),
        "ttl_seconds": settings.engagement_index_ttl_seconds,
    }
