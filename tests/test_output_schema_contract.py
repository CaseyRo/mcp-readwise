"""Backward-compat contract tests for typed output-schema coverage.

The Cloudflare MCP portal is synced manually and live clients validate tool
`structured_content` against the published `output_schema`. These tests pin
the two invariants we must never regress on (the exact bug class fixed in
mcp-zernio):

1. Every output model validates BOTH a success payload AND an error payload
   (so an error-shaped return never trips strict client validation).
2. The top-level field names each tool emits today are preserved exactly —
   additive-only changes. List/Optional-returning tools keep their fastmcp
   `{"result": ...}` wrapper wire shape.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_readwise.models.books import BookListResult, BookResult
from mcp_readwise.models.epub import EpubSendResult, VerifyResult
from mcp_readwise.models.highlights import (
    DeletionResult,
    ExportResult,
    HighlightListResult,
    HighlightResult,
)
from mcp_readwise.models.reader import (
    ReaderDocument,
    ReaderListPage,
    ReaderListResult,
)
from mcp_readwise.models.source import EngagementScore, Source
from mcp_readwise.models.status import (
    JunkDrawer,
    ReadingStatus,
    SignalDensity,
    ThisWindow,
)
from mcp_readwise.models.tags import TagResult
from mcp_readwise.models.writing import HighlightInMaterial, WritingMaterial


# Every model used (directly or nested) in a tool's output_schema.
ALL_OUTPUT_MODELS = [
    HighlightResult,
    HighlightListResult,
    DeletionResult,
    ExportResult,
    TagResult,
    BookResult,
    BookListResult,
    ReaderDocument,
    ReaderListResult,
    ReaderListPage,
    EpubSendResult,
    VerifyResult,
    Source,
    EngagementScore,
    ReadingStatus,
    ThisWindow,
    JunkDrawer,
    SignalDensity,
    WritingMaterial,
    HighlightInMaterial,
]


class TestErrorPayloadValidates:
    """Rule 3: every output model must validate an error-shaped payload."""

    @pytest.mark.parametrize("model", ALL_OUTPUT_MODELS)
    def test_bare_error_payload(self, model):
        m = model.model_validate({"error": "something failed"})
        assert m.error == "something failed"

    @pytest.mark.parametrize("model", ALL_OUTPUT_MODELS)
    def test_empty_payload_validates(self, model):
        # An empty dict (e.g. a degraded/partial response) must not raise —
        # all non-guaranteed fields carry defaults.
        model.model_validate({})

    @pytest.mark.parametrize("model", ALL_OUTPUT_MODELS)
    def test_extra_keys_tolerated(self, model):
        # extra="allow" — an upstream adding a field must not break clients.
        m = model.model_validate({"error": None, "a_brand_new_upstream_key": 42})
        assert m.error is None


class TestNoSharedMutableDefaults:
    """Collection defaults use default_factory — no instance bleed-through."""

    def test_reading_status_lists_isolated(self):
        a = ReadingStatus()
        b = ReadingStatus()
        a.evergreen_top.append(Source())
        a.this_window.finished.append(Source())
        assert b.evergreen_top == []
        assert b.this_window.finished == []

    def test_engagement_flags_isolated(self):
        s1 = Source()
        s2 = Source()
        s1.engagement.flags.append("x")
        assert s2.engagement.flags == []


# --- Top-level wire-shape preservation -----------------------------------

# The EXACT top-level field names each object-returning tool emits today.
# Adding `error` is allowed (additive); renaming/removing any of these is not.
EXPECTED_TOP_LEVEL = {
    "create_highlight": {
        "id", "text", "note", "tags", "book_id", "book_title",
        "book_author", "source_url", "highlighted_at", "created_at",
        "updated_at", "is_favorite", "is_discard",
    },
    "update_highlight": {
        "id", "text", "note", "tags", "book_id", "book_title",
        "book_author", "source_url", "highlighted_at", "created_at",
        "updated_at", "is_favorite", "is_discard",
    },
    "delete_highlight": {"deleted", "id"},
    "delete_tag": {"deleted", "id"},
    "create_tag": {"id", "name"},
    "save_url": {
        "id", "title", "author", "source_url", "category", "location",
        "reading_progress", "word_count", "summary", "content", "tags",
        "created_at", "updated_at", "saved_at", "first_opened_at",
        "last_opened_at", "last_moved_at", "reading_status",
    },
    "save_markdown": {
        "id", "title", "author", "source_url", "category", "location",
        "reading_progress", "word_count", "summary", "content", "tags",
        "created_at", "updated_at", "saved_at", "first_opened_at",
        "last_opened_at", "last_moved_at", "reading_status",
    },
    "update_progress": {
        "id", "title", "author", "source_url", "category", "location",
        "reading_progress", "word_count", "summary", "content", "tags",
        "created_at", "updated_at", "saved_at", "first_opened_at",
        "last_opened_at", "last_moved_at", "reading_status",
    },
    "save_markdown_as_epub": {
        "success", "delivery_status", "accepted_at", "recipient", "message_id",
        "file_size_bytes", "title", "location", "identifier_scheme", "note",
    },
    "verify_epub_received": {"found", "document", "note"},
    "reader_list_documents": {"results", "count", "next_cursor"},
    "reading_status": {
        "this_window", "evergreen_top", "current_top", "junk_drawer",
        "signal_density", "window_days", "week_offset",
    },
    "writing_material": {
        "sources", "highlights", "grouped_by_source", "summary",
        "has_notes", "has_legacy", "has_more", "total_highlights",
    },
}

# Tools whose return is a top-level JSON array / scalar / optional. fastmcp
# wraps these under {"result": ...}; we must NOT promote them to object models
# (that would change the wire shape the portal already published).
WRAPPED_RESULT_TOOLS = {"list_tags", "tag_highlight", "reader_get_by_url"}


def _list_tools():
    from mcp_readwise.server import mcp

    return {t.name: t for t in asyncio.run(mcp._list_tools())}


class TestTopLevelFieldsPreserved:
    def test_all_sixteen_registered(self):
        tools = _list_tools()
        assert len(tools) == 16

    def test_object_tools_preserve_field_names(self):
        tools = _list_tools()
        for name, expected in EXPECTED_TOP_LEVEL.items():
            schema = tools[name].output_schema
            props = set((schema.get("properties") or {}).keys())
            # Every original top-level name is still present...
            missing = expected - props
            assert not missing, f"{name} dropped fields: {missing}"
            # ...and the only additions are the additive `error` guard.
            added = props - expected
            assert added <= {"error"}, f"{name} added unexpected top-level fields: {added}"

    def test_object_tools_required_not_tightened(self):
        # Relaxing `required` is safe; tightening it would reject previously
        # valid payloads. After hardening, required must be a subset of the
        # original top-level field set (in practice it is now empty).
        tools = _list_tools()
        for name, expected in EXPECTED_TOP_LEVEL.items():
            schema = tools[name].output_schema
            required = set(schema.get("required") or [])
            assert required <= expected, f"{name} requires non-original fields: {required - expected}"

    def test_wrapped_tools_keep_result_wrapper(self):
        tools = _list_tools()
        for name in WRAPPED_RESULT_TOOLS:
            schema = tools[name].output_schema
            # Success wire shape is unchanged: still wrapped, ``result`` present.
            assert schema.get("x-fastmcp-wrap-result") is True, name
            props = set((schema.get("properties") or {}).keys())
            assert "result" in props, name
            # The ONLY additive top-level property allowed is the ``error`` guard.
            assert props - {"result"} <= {"error"}, name

    def test_wrapped_tools_are_error_path_safe(self):
        # The mcp-zernio bug class: a wrapped-result tool whose schema requires
        # ``result`` rejects a top-level {"error": ...} payload. After the fix,
        # ``result`` must NOT be required and extra keys must be tolerated, so an
        # error payload validates against the published schema.
        jsonschema = pytest.importorskip("jsonschema")
        tools = _list_tools()
        for name in WRAPPED_RESULT_TOOLS:
            schema = tools[name].output_schema
            assert "result" not in set(schema.get("required") or []), name
            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors({"error": "boom"}))
            assert not errors, f"{name} rejects error payload: {errors}"


# --- Success payloads still validate (no false positives) -----------------


class TestSuccessPayloadsValidate:
    def test_highlight_success(self):
        m = HighlightResult.model_validate(
            {"id": 1, "text": "t", "book_id": 5, "tags": ["a"]}
        )
        assert m.id == 1
        assert m.error is None

    def test_deletion_success(self):
        m = DeletionResult.model_validate({"deleted": True, "id": 7})
        assert m.deleted is True
        assert m.id == 7

    def test_reader_document_success_and_derivation(self):
        m = ReaderDocument.model_validate(
            {"id": "x", "location": "archive", "reading_progress": 0.0}
        )
        assert m.reading_status == "finished"
        assert m.error is None

    def test_epub_send_success(self):
        m = EpubSendResult.model_validate(
            {
                "success": True,
                "accepted_at": "2026-06-10T00:00:00+00:00",
                "recipient": "lib@readwise.io",
                "message_id": "m1",
                "file_size_bytes": 100,
                "title": "T",
                "location": "new",
                "identifier_scheme": "uuid",
                "note": "ok",
            }
        )
        assert m.success is True
        assert m.error is None
