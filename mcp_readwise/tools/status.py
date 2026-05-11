"""reading_status tool — engagement-aware library snapshot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from pydantic import Field

from mcp_readwise.engagement import _parse_iso, get_index
from mcp_readwise.models.source import Source
from mcp_readwise.models.status import (
    JunkDrawer,
    ReadingStatus,
    SignalDensity,
    ThisWindow,
)


_EVERGREEN_CAP = 10
_CURRENT_CAP = 10
_TOP_ENGAGED_CAP = 10
_JUNK_DRAWER_EXAMPLES = 5
_CURRENT_WINDOW_DAYS = 30


def _is_active_in_window(
    source: Source, start: datetime, end: datetime
) -> bool:
    """True if any of the source's activity timestamps fall in [start, end]."""
    candidates = [
        source.last_highlighted_at,
        source.last_opened_at,
        source.last_moved_at,
        source.saved_at,
    ]
    for ts in candidates:
        d = _parse_iso(ts) if ts else None
        if d is not None and start <= d <= end:
            return True
    return False


def _max_active_at(source: Source) -> Optional[datetime]:
    """The most recent activity timestamp on this source, or None."""
    candidates = [
        source.last_highlighted_at,
        source.last_opened_at,
        source.last_moved_at,
        source.saved_at,
    ]
    parsed = [_parse_iso(ts) for ts in candidates if ts]
    parsed = [p for p in parsed if p is not None]
    return max(parsed) if parsed else None


def _bucket_for(source: Source) -> str:
    """Map a Source to one of finished / in_progress / saved_only.

    Used for placing window-active sources into the right `this_window` list.
    Legacy sources (no v3 data) are bucketed by their highlight presence:
    legacy + highlights → in_progress (engaged), legacy alone shouldn't
    appear in window without recent activity.
    """
    if source.location == "archive":
        return "finished"
    if source.reading_progress is not None and source.reading_progress >= 0.9:
        return "finished"
    if source.reading_progress is not None and source.reading_progress > 0:
        return "in_progress"
    if source.num_highlights > 0:
        # No v3 progress data but has highlights → engaged but unknown completion
        return "in_progress"
    return "saved_only"


def _highlight_timestamps_in_corpus(sources: list[Source]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Find the oldest and newest highlight timestamps across the corpus."""
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None
    for s in sources:
        d = _parse_iso(s.last_highlighted_at) if s.last_highlighted_at else None
        if d is not None:
            if newest is None or d > newest:
                newest = d
            if oldest is None or d < oldest:
                oldest = d
    return oldest, newest


def _compute_signal_density(sources: list[Source]) -> SignalDensity:
    """Build the SignalDensity payload from the engagement index."""
    total_highlights = sum(s.num_highlights for s in sources)
    sources_count = sum(1 for s in sources if s.num_highlights > 0 or s.document_id)

    # tag/note density requires booleans aggregated per source — approximate
    # with "fraction of highlighted sources that have any user note/tag" since
    # we don't track per-highlight counts in the Source aggregate. This is a
    # density of *sources with annotation*, not raw note count. Document this
    # in the field description; it's the right shape for the LLM's narrative.
    highlighted = [s for s in sources if s.num_highlights > 0]
    if highlighted:
        notes_per_highlight = sum(1 for s in highlighted if s.has_user_note) / sum(
            s.num_highlights for s in highlighted
        )
        tags_per_highlight = sum(1 for s in highlighted if s.has_user_tag) / sum(
            s.num_highlights for s in highlighted
        )
    else:
        notes_per_highlight = 0.0
        tags_per_highlight = 0.0

    # year_span uses oldest vs newest highlight timestamp
    oldest, newest = _highlight_timestamps_in_corpus(highlighted)
    if oldest is not None and newest is not None:
        year_span = max(0, int((newest - oldest).days / 365))
    else:
        year_span = 0

    return SignalDensity(
        sources_count=sources_count,
        total_highlights=total_highlights,
        tags_per_highlight=round(tags_per_highlight, 4),
        notes_per_highlight=round(notes_per_highlight, 4),
        year_span=year_span,
    )


def _build_this_window(
    sources: list[Source], start: datetime, end: datetime
) -> ThisWindow:
    """Bucketize window-active sources by status; pick top_engaged."""
    finished: list[Source] = []
    in_progress: list[Source] = []
    saved_only: list[Source] = []
    active: list[Source] = []
    for s in sources:
        if not _is_active_in_window(s, start, end):
            continue
        active.append(s)
        bucket = _bucket_for(s)
        if bucket == "finished":
            finished.append(s)
        elif bucket == "in_progress":
            in_progress.append(s)
        else:
            saved_only.append(s)

    top_engaged = sorted(
        active, key=lambda s: s.engagement.raw, reverse=True
    )[:_TOP_ENGAGED_CAP]
    return ThisWindow(
        finished=finished,
        in_progress=in_progress,
        saved_only=saved_only,
        top_engaged=top_engaged,
    )


def _build_evergreen_top(sources: list[Source]) -> list[Source]:
    """Top sources by engagement intensity (no recency); cap at 10."""
    eligible = [
        s
        for s in sources
        if s.engagement.base_layer in ("highlighted", "legacy", "finished_no_hl")
    ]
    eligible.sort(key=lambda s: s.engagement.intensity, reverse=True)
    return eligible[:_EVERGREEN_CAP]


def _build_current_top(sources: list[Source], now: datetime) -> list[Source]:
    """Top sources by raw engagement, restricted to last 30d activity; cap 10."""
    cutoff = now - timedelta(days=_CURRENT_WINDOW_DAYS)
    recent: list[Source] = []
    for s in sources:
        latest = _max_active_at(s)
        if latest is not None and latest >= cutoff:
            recent.append(s)
    recent.sort(key=lambda s: s.engagement.raw, reverse=True)
    return recent[:_CURRENT_CAP]


def _build_junk_drawer(sources: list[Source]) -> JunkDrawer:
    """Surface saved-cold/warm sources older than the grace window."""
    candidates = [
        s for s in sources if "junk_drawer_candidate" in s.engagement.flags
    ]

    def _saved_or_zero(s: Source) -> str:
        return s.saved_at or ""

    candidates.sort(key=_saved_or_zero)  # oldest first
    return JunkDrawer(count=len(candidates), examples=candidates[:_JUNK_DRAWER_EXAMPLES])


async def reading_status(
    window_days: Annotated[int, Field(ge=1, le=90)] = 7,
    week_offset: Annotated[int, Field(ge=-52, le=0)] = 0,
) -> ReadingStatus:
    """Single-call snapshot of your reading library.

    Returns a structured response covering: recent activity (`this_window`),
    durable interests (`evergreen_top`, ranked by engagement intensity with
    recency removed), current attention (`current_top`, ranked by full
    engagement over the last 30 days), unprocessed material (`junk_drawer`),
    and corpus-shape signals (`signal_density`).

    `window_days` controls the size of `this_window` (default 7).
    `week_offset` shifts the window into the past — `0` is now, `-1` is the
    7-day window ending 7 days ago, etc.

    The underlying engagement index is cached for ~30 minutes so repeated
    calls within a session are cheap.
    """
    sources_dict = await get_index()
    sources = list(sources_dict.values())
    now = datetime.now(timezone.utc)

    # Window: end is `now` shifted back by week_offset weeks
    end = now + timedelta(days=window_days * week_offset)
    start = end - timedelta(days=window_days)

    return ReadingStatus(
        this_window=_build_this_window(sources, start, end),
        evergreen_top=_build_evergreen_top(sources),
        current_top=_build_current_top(sources, now),
        junk_drawer=_build_junk_drawer(sources),
        signal_density=_compute_signal_density(sources),
        window_days=window_days,
        week_offset=week_offset,
    )
