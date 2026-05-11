"""Tests for the reading_status tool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from mcp_readwise.models.source import EngagementScore, Source
from mcp_readwise.tools.status import reading_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_source(
    *,
    title: str,
    raw: float = 0.0,
    intensity: float = 0.0,
    base_layer: str = "saved_cold",
    book_id: int | None = None,
    document_id: str | None = None,
    last_highlighted_at: str = "",
    location: str | None = None,
    reading_progress: float | None = None,
    saved_at: str = "",
    flags: list[str] | None = None,
    is_legacy: bool = False,
    num_highlights: int = 0,
) -> Source:
    return Source(
        book_id=book_id,
        document_id=document_id,
        title=title,
        num_highlights=num_highlights,
        location=location,
        reading_progress=reading_progress,
        last_highlighted_at=last_highlighted_at or None,
        saved_at=saved_at or None,
        is_legacy=is_legacy,
        engagement=EngagementScore(
            raw=raw,
            intensity=intensity,
            recency=raw - intensity,
            return_strength=0.0,
            base_layer=base_layer,
            flags=flags or [],
        ),
    )


@pytest.mark.asyncio
async def test_default_invocation_populates_sections():
    """All five sections present, even on a small corpus."""
    now = _now()
    sources = {
        "book:1": _make_source(
            title="Article A",
            book_id=1,
            num_highlights=3,
            location="archive",
            reading_progress=1.0,
            last_highlighted_at=(now - timedelta(days=2)).isoformat(),
            raw=1.20,
            intensity=1.00,
            base_layer="highlighted",
        ),
        "book:2": _make_source(
            title="Legacy Book",
            book_id=2,
            num_highlights=25,
            is_legacy=True,
            last_highlighted_at=(now - timedelta(days=2200)).isoformat(),
            raw=0.80,
            intensity=0.90,
            base_layer="legacy",
        ),
    }
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    assert result.window_days == 7
    assert result.evergreen_top
    assert result.current_top
    assert result.signal_density.sources_count >= 2


@pytest.mark.asyncio
async def test_empty_corpus_does_not_crash():
    """Zero sources returns empty lists, not error."""
    with patch("mcp_readwise.tools.status.get_index", return_value={}):
        result = await reading_status()

    assert result.evergreen_top == []
    assert result.current_top == []
    assert result.junk_drawer.count == 0
    assert result.signal_density.sources_count == 0
    assert result.signal_density.year_span == 0


@pytest.mark.asyncio
async def test_evergreen_ranks_by_intensity():
    """A legacy book with high intensity beats a recent article with high raw."""
    now = _now()
    sources = {
        "book:1": _make_source(
            title="recent_article",
            book_id=1,
            num_highlights=3,
            last_highlighted_at=(now - timedelta(days=2)).isoformat(),
            location="archive",
            raw=1.20,
            intensity=1.00,
            base_layer="highlighted",
        ),
        "book:2": _make_source(
            title="legacy_book_deep",
            book_id=2,
            num_highlights=25,
            is_legacy=True,
            last_highlighted_at=(now - timedelta(days=2200)).isoformat(),
            raw=0.80,
            intensity=1.20,  # base 0.40 + density 0.50 + annotation 0.30 = 1.20
            base_layer="legacy",
        ),
    }
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    # Legacy book with higher intensity should top evergreen_top
    assert result.evergreen_top[0].title == "legacy_book_deep"


@pytest.mark.asyncio
async def test_current_top_excludes_old_sources():
    """A source last active 60d ago should not appear in current_top."""
    now = _now()
    sources = {
        "book:1": _make_source(
            title="recent",
            book_id=1,
            num_highlights=3,
            last_highlighted_at=(now - timedelta(days=2)).isoformat(),
            location="archive",
            raw=1.0,
            intensity=0.8,
            base_layer="highlighted",
        ),
        "book:2": _make_source(
            title="too_old",
            book_id=2,
            num_highlights=3,
            last_highlighted_at=(now - timedelta(days=60)).isoformat(),
            location="archive",
            raw=1.0,
            intensity=1.0,
            base_layer="highlighted",
        ),
    }
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    current_titles = [s.title for s in result.current_top]
    assert "recent" in current_titles
    assert "too_old" not in current_titles


@pytest.mark.asyncio
async def test_junk_drawer_surfaces_flagged_sources():
    """junk_drawer contains sources with the junk_drawer_candidate flag."""
    now = _now()
    sources = {
        "doc:1": _make_source(
            title="forgotten_article_1",
            document_id="d1",
            location="later",
            reading_progress=0.0,
            saved_at=(now - timedelta(days=120)).isoformat(),
            flags=["junk_drawer_candidate"],
            base_layer="saved_warm",
            raw=0.15,
            intensity=0.15,
        ),
        "doc:2": _make_source(
            title="forgotten_article_2",
            document_id="d2",
            location="later",
            reading_progress=0.0,
            saved_at=(now - timedelta(days=90)).isoformat(),
            flags=["junk_drawer_candidate"],
            base_layer="saved_warm",
            raw=0.15,
            intensity=0.15,
        ),
        "doc:3": _make_source(
            title="just_saved",
            document_id="d3",
            location="later",
            reading_progress=0.0,
            saved_at=(now - timedelta(days=2)).isoformat(),
            flags=[],
            base_layer="saved_warm",
            raw=0.15,
            intensity=0.15,
        ),
    }
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    assert result.junk_drawer.count == 2
    titles = [s.title for s in result.junk_drawer.examples]
    assert "just_saved" not in titles
    # oldest first
    assert titles[0] == "forgotten_article_1"


@pytest.mark.asyncio
async def test_signal_density_handles_decade_corpus():
    """year_span works across decade-old highlights."""
    sources = {
        "book:1": _make_source(
            title="old_book",
            book_id=1,
            num_highlights=5,
            is_legacy=True,
            last_highlighted_at="2016-06-06T04:56:00Z",
            base_layer="legacy",
        ),
        "book:2": _make_source(
            title="new_article",
            book_id=2,
            num_highlights=2,
            location="archive",
            last_highlighted_at="2026-04-15T05:54:00Z",
            base_layer="highlighted",
        ),
    }
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    assert result.signal_density.year_span >= 9
    assert result.signal_density.total_highlights == 7


@pytest.mark.asyncio
async def test_top_n_caps():
    """evergreen_top and current_top are each capped at 10."""
    now = _now()
    sources = {}
    for i in range(20):
        sources[f"book:{i}"] = _make_source(
            title=f"src_{i}",
            book_id=i,
            num_highlights=3,
            location="archive",
            last_highlighted_at=(now - timedelta(days=i)).isoformat(),
            raw=1.0 - i * 0.01,
            intensity=1.0 - i * 0.01,
            base_layer="highlighted",
        )
    with patch("mcp_readwise.tools.status.get_index", return_value=sources):
        result = await reading_status()

    assert len(result.evergreen_top) == 10
    assert len(result.current_top) == 10
