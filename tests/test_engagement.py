"""Tests for the engagement scoring module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from mcp_readwise import engagement
from mcp_readwise.engagement import (
    _DEFAULT_TAG_DENYLIST,
    _is_user_tag,
    _is_structural_note,
    _parse_iso,
    compute_annotation,
    compute_base_layer,
    compute_density,
    compute_engagement,
    compute_recency,
    compute_return_signal,
    extract_ulid,
)
from mcp_readwise.models.source import Source


# ============= Helpers =============


class TestExtractUlid:
    def test_private_read_url(self):
        assert (
            extract_ulid("private://read/01kq6xmbv7922ranv0p1qa214m")
            == "01kq6xmbv7922ranv0p1qa214m"
        )

    def test_private_read_url_with_trailing_slash(self):
        assert (
            extract_ulid("private://read/01kq6xmbv7922ranv0p1qa214m/")
            == "01kq6xmbv7922ranv0p1qa214m"
        )

    def test_public_https_url(self):
        assert extract_ulid("https://example.com/article") is None

    def test_empty_string(self):
        assert extract_ulid("") is None

    def test_none(self):
        assert extract_ulid(None) is None

    def test_malformed(self):
        assert extract_ulid("private://read/") is None


class TestIsUserTag:
    def test_legitimate_user_tag(self):
        assert _is_user_tag("productivity", _DEFAULT_TAG_DENYLIST) is True

    def test_structural_h1_filtered(self):
        assert _is_user_tag("h1", _DEFAULT_TAG_DENYLIST) is False

    def test_structural_dot_h1_filtered(self):
        assert _is_user_tag(".h1", _DEFAULT_TAG_DENYLIST) is False

    def test_color_filtered(self):
        assert _is_user_tag("orange", _DEFAULT_TAG_DENYLIST) is False

    def test_favorite_filtered(self):
        assert _is_user_tag("favorite", _DEFAULT_TAG_DENYLIST) is False

    def test_single_char_filtered(self):
        assert _is_user_tag("a", _DEFAULT_TAG_DENYLIST) is False

    def test_empty_filtered(self):
        assert _is_user_tag("", _DEFAULT_TAG_DENYLIST) is False

    def test_case_insensitive(self):
        assert _is_user_tag("ORANGE", _DEFAULT_TAG_DENYLIST) is False


class TestIsStructuralNote:
    def test_dot_h1(self):
        assert _is_structural_note(".h1") is True

    def test_empty_treated_as_structural(self):
        assert _is_structural_note("") is True

    def test_real_note(self):
        assert _is_structural_note("Amazing insight about X") is False


# ============= Base layer =============


class TestComputeBaseLayer:
    def test_highlighted_overrides_progress(self):
        assert (
            compute_base_layer(
                has_highlights=True,
                is_legacy=False,
                location="new",
                reading_progress=0.0,
            )
            == "highlighted"
        )

    def test_legacy_when_v2_only(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=True,
                location=None,
                reading_progress=None,
            )
            == "legacy"
        )

    def test_archive_finished(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location="archive",
                reading_progress=0.0,
            )
            == "finished_no_hl"
        )

    def test_progress_threshold(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location="new",
                reading_progress=0.92,
            )
            == "finished_no_hl"
        )

    def test_reading(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location="new",
                reading_progress=0.5,
            )
            == "reading"
        )

    def test_saved_warm(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location="later",
                reading_progress=0.0,
            )
            == "saved_warm"
        )

    def test_saved_cold(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location="new",
                reading_progress=0.0,
            )
            == "saved_cold"
        )

    def test_saved_cold_when_no_v3(self):
        assert (
            compute_base_layer(
                has_highlights=False,
                is_legacy=False,
                location=None,
                reading_progress=None,
            )
            == "saved_cold"
        )


# ============= Density =============


class TestComputeDensity:
    def test_only_for_highlighted_or_legacy(self):
        assert compute_density(50, "saved_cold") == 0.0
        assert compute_density(50, "reading") == 0.0
        assert compute_density(50, "finished_no_hl") == 0.0

    def test_30_plus_highlights(self):
        assert compute_density(30, "highlighted") == 0.70
        assert compute_density(100, "legacy") == 0.70

    def test_10_29_band(self):
        assert compute_density(10, "highlighted") == 0.50
        assert compute_density(29, "legacy") == 0.50

    def test_3_9_band(self):
        assert compute_density(3, "highlighted") == 0.30
        assert compute_density(9, "legacy") == 0.30

    def test_1_2_band(self):
        assert compute_density(1, "highlighted") == 0.10
        assert compute_density(2, "legacy") == 0.10

    def test_zero(self):
        assert compute_density(0, "highlighted") == 0.0


# ============= Recency =============


class TestComputeRecency:
    def test_within_30d(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        ts = (now - timedelta(days=10)).isoformat()
        assert compute_recency(ts, now) == 0.20

    def test_neutral_band(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        ts = (now - timedelta(days=180)).isoformat()
        assert compute_recency(ts, now) == 0.0

    def test_older_than_5y(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        ts = (now - timedelta(days=2000)).isoformat()
        assert compute_recency(ts, now) == -0.10

    def test_none_input(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        assert compute_recency(None, now) == 0.0

    def test_empty_string(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        assert compute_recency("", now) == 0.0

    def test_malformed(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        assert compute_recency("not-a-date", now) == 0.0


# ============= Annotation =============


class TestComputeAnnotation:
    def test_only_note(self):
        assert compute_annotation(True, False, False) == 0.30

    def test_only_tag(self):
        assert compute_annotation(False, True, False) == 0.10

    def test_only_favorite(self):
        assert compute_annotation(False, False, True) == 0.20

    def test_all_three_stack(self):
        assert compute_annotation(True, True, True) == pytest.approx(0.60)

    def test_none(self):
        assert compute_annotation(False, False, False) == 0.0


# ============= Return signal =============


class TestComputeReturnSignal:
    def test_no_signals(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        score, flags = compute_return_signal([], None, None, now)
        assert score == 0.0
        assert flags == []

    def test_multi_era_cluster(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        dates = [
            datetime(2018, 1, 1, tzinfo=timezone.utc),
            datetime(2018, 6, 1, tzinfo=timezone.utc),
            datetime(2024, 11, 1, tzinfo=timezone.utc),
        ]
        score, flags = compute_return_signal(dates, None, None, now)
        assert score == 0.30
        assert "multi_era_return" in flags

    def test_single_era_no_signal(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        dates = [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 1, tzinfo=timezone.utc),
        ]
        score, flags = compute_return_signal(dates, None, None, now)
        assert score == 0.0
        assert flags == []

    def test_reader_reopen(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        first = (now - timedelta(days=180)).isoformat()
        last = (now - timedelta(days=5)).isoformat()
        score, flags = compute_return_signal([], first, last, now)
        assert score == 0.20
        assert "reader_return" in flags

    def test_both_signals_stack(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        dates = [
            datetime(2018, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 11, 1, tzinfo=timezone.utc),
        ]
        first = (now - timedelta(days=200)).isoformat()
        last = (now - timedelta(days=2)).isoformat()
        score, flags = compute_return_signal(dates, first, last, now)
        assert score == pytest.approx(0.50)
        assert "multi_era_return" in flags
        assert "reader_return" in flags


# ============= compute_engagement integration =============


class TestComputeEngagement:
    def _now(self):
        return datetime(2026, 5, 9, tzinfo=timezone.utc)

    def test_reader_article_recent_modest(self):
        """Reader article, 3 highlights, last hl within 30d, no annotation, no return.
        Expected: 0.70 + 0.30 + 0.20 + 0 + 0 = 1.20
        """
        now = self._now()
        last_hl = (now - timedelta(days=10)).isoformat()
        s = Source(
            document_id="abc",
            title="Klein on AI",
            num_highlights=3,
            location="archive",
            reading_progress=1.0,
            last_highlighted_at=last_hl,
            is_legacy=False,
        )
        score = compute_engagement(s, [_parse_iso(last_hl)], now)
        assert score.base_layer == "highlighted"
        assert score.raw == pytest.approx(1.20)
        assert score.intensity == pytest.approx(1.00)
        assert score.recency == pytest.approx(0.20)
        assert score.return_strength == 0.0

    def test_legacy_book_deep_old(self):
        """Legacy book, 25 highlights, last hl 6 years ago, no annotation, no return.
        Expected: 0.40 + 0.50 + (-0.10) + 0 + 0 = 0.80
        """
        now = self._now()
        last_hl = (now - timedelta(days=2200)).isoformat()
        s = Source(
            book_id=42,
            title="The Truth",
            num_highlights=25,
            is_legacy=True,
            last_highlighted_at=last_hl,
        )
        score = compute_engagement(s, [_parse_iso(last_hl)], now)
        assert score.base_layer == "legacy"
        assert score.raw == pytest.approx(0.80)
        assert score.intensity == pytest.approx(0.90)
        assert score.recency == pytest.approx(-0.10)

    def test_cold_inbox(self):
        """saved_cold, no highlights, no annotation, no return.
        Expected: 0.10
        """
        now = self._now()
        s = Source(
            document_id="cold-1",
            title="Untouched",
            num_highlights=0,
            location="new",
            reading_progress=0.0,
            is_legacy=False,
        )
        score = compute_engagement(s, [], now)
        assert score.base_layer == "saved_cold"
        assert score.raw == pytest.approx(0.10)

    def test_intensity_excludes_recency_and_return(self):
        """Verify the vector decomposition.
        intensity = base + density + annotation
        raw = intensity + recency + return_strength
        """
        now = self._now()
        last_hl = (now - timedelta(days=2200)).isoformat()
        s = Source(
            book_id=42,
            title="X",
            num_highlights=25,
            is_legacy=True,
            last_highlighted_at=last_hl,
            has_user_note=True,
        )
        score = compute_engagement(s, [_parse_iso(last_hl)], now)
        # 0.40 + 0.50 + 0.30 = 1.20
        assert score.intensity == pytest.approx(1.20)
        # 1.20 - 0.10 (5y+) + 0 = 1.10
        assert score.raw == pytest.approx(1.10)
        # decomposition holds
        assert score.raw == pytest.approx(
            score.intensity + score.recency + score.return_strength
        )

    def test_junk_drawer_flag_set_when_old_and_untouched(self):
        now = self._now()
        old_save = (now - timedelta(days=90)).isoformat()
        s = Source(
            document_id="x",
            title="forgotten",
            num_highlights=0,
            location="later",
            reading_progress=0.0,
            saved_at=old_save,
            is_legacy=False,
        )
        score = compute_engagement(s, [], now)
        assert "junk_drawer_candidate" in score.flags

    def test_junk_drawer_flag_not_set_within_grace(self):
        now = self._now()
        recent_save = (now - timedelta(days=5)).isoformat()
        s = Source(
            document_id="y",
            title="just-saved",
            num_highlights=0,
            location="later",
            reading_progress=0.0,
            saved_at=recent_save,
            is_legacy=False,
        )
        score = compute_engagement(s, [], now)
        assert "junk_drawer_candidate" not in score.flags


# ============= build_index integration =============


@pytest.fixture
def reset_engagement_cache():
    """Reset the module-level cache before each integration test."""
    engagement.invalidate_cache()
    yield
    engagement.invalidate_cache()


class TestBuildIndex:
    @pytest.mark.asyncio
    async def test_join_reader_imported_with_ulid(self, reset_engagement_cache):
        """A Reader-imported book joins to its v3 doc by ULID."""
        export_pages = [
            {
                "results": [
                    {
                        "user_book_id": 100,
                        "title": "Decoding Greatness",
                        "author": "Friedman",
                        "category": "books",
                        "source": "reader",
                        "source_url": "private://read/01kq6xmbv7922ranv0p1qa214m",
                        "highlights": [
                            {
                                "id": 1,
                                "text": "x",
                                "highlighted_at": "2026-04-28T05:56:13Z",
                                "tags": [],
                                "is_favorite": False,
                                "is_discard": False,
                            }
                        ],
                    }
                ],
                "nextPageCursor": None,
            }
        ]
        v3_pages = [
            {
                "results": [
                    {
                        "id": "01kq6xmbv7922ranv0p1qa214m",
                        "title": "Decoding Greatness",
                        "category": "epub",
                        "location": "new",
                        "reading_progress": 0.28,
                        "source_url": "private://read/01kq6xmbv7922ranv0p1qa214m",
                        "saved_at": "2026-04-27T07:30:00Z",
                    }
                ],
                "nextPageCursor": None,
            }
        ]

        export_iter = iter(export_pages)
        v3_iter = iter(v3_pages)

        async def fake_get(path, **params):
            if path == "/api/v2/export/":
                return next(export_iter)
            if path == "/api/v3/list/":
                if params.get("location") == "new":
                    return next(v3_iter)
                return {"results": [], "nextPageCursor": None}
            return {}

        with patch.object(engagement.client, "get", new=AsyncMock(side_effect=fake_get)):
            sources = await engagement.build_index()

        assert "book:100" in sources
        s = sources["book:100"]
        assert s.is_legacy is False
        assert s.document_id == "01kq6xmbv7922ranv0p1qa214m"
        assert s.location == "new"
        assert s.reading_progress == 0.28
        assert s.engagement.base_layer == "highlighted"

    @pytest.mark.asyncio
    async def test_legacy_when_source_is_kindle(self, reset_engagement_cache):
        """A Kindle book has no v3 join → legacy."""
        export_pages = [
            {
                "results": [
                    {
                        "user_book_id": 200,
                        "title": "Sapiens",
                        "author": "Harari",
                        "category": "books",
                        "source": "kindle",
                        "source_url": "",
                        "highlights": [
                            {
                                "id": 2,
                                "text": "x",
                                "highlighted_at": "2018-03-21T04:56:00Z",
                                "tags": [],
                            },
                            {
                                "id": 3,
                                "text": "y",
                                "highlighted_at": "2018-04-01T04:56:00Z",
                                "tags": [],
                            },
                        ],
                    }
                ],
                "nextPageCursor": None,
            }
        ]
        export_iter = iter(export_pages)

        async def fake_get(path, **params):
            if path == "/api/v2/export/":
                return next(export_iter)
            if path == "/api/v3/list/":
                return {"results": [], "nextPageCursor": None}
            return {}

        with patch.object(engagement.client, "get", new=AsyncMock(side_effect=fake_get)):
            sources = await engagement.build_index()

        s = sources["book:200"]
        assert s.is_legacy is True
        assert s.engagement.base_layer == "legacy"
        assert s.legacy_recency == "cold"  # 2018 highlights → > 365d

    @pytest.mark.asyncio
    async def test_v3_only_saved_no_highlights(self, reset_engagement_cache):
        """A saved-but-not-highlighted v3 doc shows up with no v2 entry."""
        export_pages = [{"results": [], "nextPageCursor": None}]
        v3_pages = [
            {
                "results": [
                    {
                        "id": "saved-only-1",
                        "title": "Untouched article",
                        "category": "article",
                        "location": "later",
                        "reading_progress": 0.0,
                        "source_url": "https://example.com/x",
                        "saved_at": "2026-05-01T00:00:00Z",
                    }
                ],
                "nextPageCursor": None,
            }
        ]

        export_iter = iter(export_pages)
        v3_iter = iter(v3_pages)

        async def fake_get(path, **params):
            if path == "/api/v2/export/":
                return next(export_iter)
            if path == "/api/v3/list/":
                if params.get("location") == "later":
                    return next(v3_iter)
                return {"results": [], "nextPageCursor": None}
            return {}

        with patch.object(engagement.client, "get", new=AsyncMock(side_effect=fake_get)):
            sources = await engagement.build_index()

        s = sources["doc:saved-only-1"]
        assert s.is_legacy is False
        assert s.book_id is None
        assert s.engagement.base_layer == "saved_warm"
        assert s.engagement.raw == pytest.approx(0.15)

    @pytest.mark.asyncio
    async def test_v3_list_never_requests_feed(self, reset_engagement_cache):
        """The index paginator queries per library location and skips `feed`.

        Regression: an unfiltered /api/v3/list/ pulled 15k+ feed items,
        making cold builds take ~7 minutes at the 20 req/min rate limit and
        timing out every reading_status call upstream.
        """
        requested_locations: list = []

        async def fake_get(path, **params):
            if path == "/api/v2/export/":
                return {"results": [], "nextPageCursor": None}
            if path == "/api/v3/list/":
                requested_locations.append(params.get("location"))
                return {"results": [], "nextPageCursor": None}
            return {}

        with patch.object(engagement.client, "get", new=AsyncMock(side_effect=fake_get)):
            await engagement.build_index()

        assert requested_locations == ["new", "later", "shortlist", "archive"]
        assert "feed" not in requested_locations
        assert None not in requested_locations  # never an unfiltered list call


# ============= TTL caching =============


class TestTTLCache:
    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl(self, monkeypatch):
        engagement.invalidate_cache()

        call_count = 0

        async def fake_build():
            nonlocal call_count
            call_count += 1
            return {"book:1": Source(book_id=1, title="x")}

        monkeypatch.setattr(engagement, "build_index", fake_build)

        await engagement.get_index()
        await engagement.get_index()
        await engagement.get_index()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cache_rebuilds_after_ttl(self, monkeypatch):
        engagement.invalidate_cache()

        call_count = 0

        async def fake_build():
            nonlocal call_count
            call_count += 1
            return {"book:1": Source(book_id=1, title="x")}

        monkeypatch.setattr(engagement, "build_index", fake_build)

        # First call builds
        await engagement.get_index()
        assert call_count == 1

        # Force expiry by setting built_at far in the past
        engagement._index_cache.built_at = 0.0
        await engagement.get_index()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_force_refresh_rebuilds(self, monkeypatch):
        engagement.invalidate_cache()

        call_count = 0

        async def fake_build():
            nonlocal call_count
            call_count += 1
            return {}

        monkeypatch.setattr(engagement, "build_index", fake_build)

        await engagement.get_index()
        await engagement.get_index(force_refresh=True)

        assert call_count == 2
