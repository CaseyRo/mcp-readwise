"""Tests for the writing_material tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mcp_readwise.models.source import EngagementScore, Source
from mcp_readwise.tools.writing import writing_material


def _src(**kwargs) -> Source:
    defaults = dict(
        title="Sample",
        num_highlights=3,
        is_legacy=False,
        engagement=EngagementScore(
            raw=1.20,
            intensity=1.00,
            recency=0.20,
            base_layer="highlighted",
        ),
    )
    defaults.update(kwargs)
    return Source(**defaults)


@pytest.mark.asyncio
async def test_neither_arg_raises():
    with patch("mcp_readwise.tools.writing.get_index", return_value={}):
        with pytest.raises(ValueError, match="exactly one"):
            await writing_material()


@pytest.mark.asyncio
async def test_multiple_args_raises():
    with patch("mcp_readwise.tools.writing.get_index", return_value={}):
        with pytest.raises(ValueError, match="exactly one"):
            await writing_material(book_id=1, topic="x")


@pytest.mark.asyncio
async def test_book_id_lookup():
    src = _src(book_id=100, title="Atomic Habits", num_highlights=2)
    sources = {"book:100": src}

    highlights_response = {
        "results": [
            {
                "id": 1001,
                "text": "habits compound",
                "note": "key idea",
                "tags": [],
                "highlighted_at": "2026-04-01T00:00:00Z",
                "is_favorite": False,
                "is_discard": False,
                "book_id": 100,
            },
            {
                "id": 1002,
                "text": "identity matters",
                "note": "",
                "tags": [],
                "highlighted_at": "2026-04-02T00:00:00Z",
                "is_favorite": True,
                "is_discard": False,
                "book_id": 100,
            },
        ],
        "next": None,
    }

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with patch.object(
            __import__("mcp_readwise.tools.writing", fromlist=["client"]).client,
            "get",
            new=AsyncMock(return_value=highlights_response),
        ):
            result = await writing_material(book_id=100)

    assert len(result.sources) == 1
    assert result.sources[0].book_id == 100
    assert len(result.highlights) == 2
    assert result.has_notes is True
    assert "Atomic Habits" in result.grouped_by_source


@pytest.mark.asyncio
async def test_document_id_lookup():
    src = _src(document_id="doc-uuid-1", num_highlights=0)
    sources = {"doc:doc-uuid-1": src}

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        # No fetch happens because no book_id; summary fetch is mocked
        with patch(
            "mcp_readwise.tools.writing._fetch_v3_summary",
            new=AsyncMock(return_value="The author argues..."),
        ):
            result = await writing_material(document_id="doc-uuid-1")

    assert len(result.sources) == 1
    assert result.summary == "The author argues..."
    assert result.has_notes is False


@pytest.mark.asyncio
async def test_title_search_single_match():
    src = _src(book_id=42, title="Antifragile")
    sources = {"book:42": src}

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with patch.object(
            __import__("mcp_readwise.tools.writing", fromlist=["client"]).client,
            "get",
            new=AsyncMock(return_value={"results": [], "next": None}),
        ):
            result = await writing_material(title_search="antifragile")

    assert len(result.sources) == 1
    assert result.sources[0].title == "Antifragile"


@pytest.mark.asyncio
async def test_title_search_ambiguous_raises():
    s1 = _src(book_id=1, title="AI Agents in 2026")
    s2 = _src(book_id=2, title="AI Hype Cycle")
    sources = {"book:1": s1, "book:2": s2}

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with pytest.raises(ValueError, match="Multiple sources matched"):
            await writing_material(title_search="AI")


@pytest.mark.asyncio
async def test_title_search_no_match_raises():
    s1 = _src(book_id=1, title="Atomic Habits")
    sources = {"book:1": s1}

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with pytest.raises(ValueError, match="No source matched"):
            await writing_material(title_search="quantum entanglement")


@pytest.mark.asyncio
async def test_topic_floor_excludes_low_engagement():
    """A topic search result whose source falls below floor is dropped."""
    high = _src(
        book_id=1,
        title="High",
        engagement=EngagementScore(raw=1.20, intensity=1.0, base_layer="highlighted"),
    )
    low = _src(
        book_id=2,
        title="Low",
        engagement=EngagementScore(raw=0.30, intensity=0.30, base_layer="reading"),
    )
    sources = {"book:1": high, "book:2": low}

    search_response = {
        "results": [
            {
                "id": 1,
                "score": 0.95,
                "attributes": {
                    "highlight_plaintext": "from high",
                    "book_id": 1,
                },
            },
            {
                "id": 2,
                "score": 0.90,
                "attributes": {
                    "highlight_plaintext": "from low",
                    "book_id": 2,
                },
            },
        ]
    }

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with patch.object(
            __import__("mcp_readwise.tools.writing", fromlist=["client"]).client,
            "post",
            new=AsyncMock(return_value=search_response),
        ):
            result = await writing_material(topic="x", min_engagement=0.7)

    # Only the highlight from the high-engagement source should pass
    assert len(result.highlights) == 1
    assert result.highlights[0].book_title == "High"


@pytest.mark.asyncio
async def test_has_legacy_flag():
    """has_legacy is True when any returned source is legacy."""
    legacy = _src(
        book_id=1,
        title="Sapiens",
        is_legacy=True,
        engagement=EngagementScore(raw=0.80, intensity=0.90, base_layer="legacy"),
    )
    sources = {"book:1": legacy}

    search_response = {
        "results": [
            {"id": 1, "attributes": {"highlight_plaintext": "x", "book_id": 1}}
        ]
    }

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with patch.object(
            __import__("mcp_readwise.tools.writing", fromlist=["client"]).client,
            "post",
            new=AsyncMock(return_value=search_response),
        ):
            result = await writing_material(topic="x", min_engagement=0.5)

    assert result.has_legacy is True


@pytest.mark.asyncio
async def test_default_limits_split_by_path():
    """Source-first defaults to 200 cap; topic-first defaults to 30 cap.

    We don't actually return that many, but the limit is plumbed through.
    """
    src = _src(book_id=100, title="x", num_highlights=0)
    sources = {"book:100": src}

    seen_page_size = []

    async def fake_get(*args, **kwargs):
        seen_page_size.append(kwargs.get("page_size"))
        return {"results": [], "next": None}

    with patch("mcp_readwise.tools.writing.get_index", return_value=sources):
        with patch.object(
            __import__("mcp_readwise.tools.writing", fromlist=["client"]).client,
            "get",
            new=AsyncMock(side_effect=fake_get),
        ):
            result = await writing_material(book_id=100)

    # Source-first should request a page_size consistent with limit=200
    assert seen_page_size  # got called at least once
    assert max(seen_page_size) >= 100  # over-fetch logic uses min(100, limit-len+50)
    assert result.has_more is False
    assert result.total_highlights == 0
