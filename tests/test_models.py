"""Tests for Pydantic model derivations."""

from __future__ import annotations

import pytest

from mcp_readwise.models.reader import ReaderDocument
from mcp_readwise.models.source import EngagementScore, Source


class TestReadingStatusDerivation:
    """Cover the four branches of the reading_status derivation rule."""

    def test_archive_overrides_progress(self):
        """location='archive' implies finished even when progress=0."""
        doc = ReaderDocument(
            id="x",
            location="archive",
            reading_progress=0.0,
        )
        assert doc.reading_status == "finished"

    def test_progress_at_threshold(self):
        """reading_progress >= 0.9 → finished."""
        doc = ReaderDocument(id="x", location="new", reading_progress=0.92)
        assert doc.reading_status == "finished"

    def test_progress_just_below_threshold(self):
        """reading_progress just under 0.9 → in_progress."""
        doc = ReaderDocument(id="x", location="new", reading_progress=0.89)
        assert doc.reading_status == "in_progress"

    def test_partially_read(self):
        """0 < reading_progress < 0.9 → in_progress."""
        doc = ReaderDocument(id="x", location="later", reading_progress=0.5)
        assert doc.reading_status == "in_progress"

    def test_zero_progress_in_inbox(self):
        """progress=0 in non-archive → saved_only."""
        doc = ReaderDocument(id="x", location="new", reading_progress=0.0)
        assert doc.reading_status == "saved_only"

    def test_zero_progress_in_later(self):
        """progress=0 in later → saved_only (still untouched)."""
        doc = ReaderDocument(id="x", location="later", reading_progress=0.0)
        assert doc.reading_status == "saved_only"

    def test_archive_with_full_progress(self):
        """archive + progress=1 → finished (consistent)."""
        doc = ReaderDocument(id="x", location="archive", reading_progress=1.0)
        assert doc.reading_status == "finished"

    def test_pdf_with_0_9(self):
        """PDF reaching 0.9 (footer cutoff) → finished."""
        doc = ReaderDocument(
            id="x",
            location="new",
            category="pdf",
            reading_progress=0.9,
        )
        assert doc.reading_status == "finished"


class TestSourceModel:
    """Smoke tests for the Source / EngagementScore models."""

    def test_source_defaults(self):
        s = Source(book_id=100, title="x")
        assert s.is_legacy is False
        assert s.engagement.raw == 0.0
        assert s.engagement.base_layer == "saved_cold"
        assert isinstance(s.engagement.flags, list)

    def test_engagement_score_components(self):
        es = EngagementScore(
            raw=1.20,
            intensity=1.00,
            recency=0.20,
            return_strength=0.0,
            base_layer="highlighted",
            flags=["recent"],
        )
        # raw should be the sum of intensity + recency + return_strength
        assert pytest.approx(es.raw, abs=1e-6) == es.intensity + es.recency + es.return_strength

    def test_optional_v3_fields_can_be_none(self):
        s = Source(
            book_id=100,
            title="legacy book",
            is_legacy=True,
            location=None,
            reading_progress=None,
        )
        assert s.location is None
        assert s.reading_progress is None
