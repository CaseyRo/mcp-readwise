"""Reference resources exposed over MCP.

These surface the contract data an agent would otherwise have to infer from
error messages or the README: the EPUB brand stylesheet, the supported
frontmatter schema, the Reader location/category enums, and the
engagement-scoring rubric (base layers, score components, flags).

Registered onto the server via `register_resources(mcp)` from server.py so
the FastMCP instance stays the single source of truth.
"""

from __future__ import annotations

import json
from importlib import resources

from fastmcp import FastMCP

from mcp_readwise.config import settings
from mcp_readwise.engagement import (
    _BASE_VALUES,
    _resolve_tag_denylist,
    index_status,
)

# Mirrors the Literal enums declared on the Reader tools. Kept here as plain
# data so an agent can read the accepted values without parsing the schema.
READER_LOCATIONS = ["new", "later", "shortlist", "archive", "feed"]
READER_LOCATION_NOTES = {
    "new": "Inbox — freshly saved, unsorted.",
    "later": "Read-it-later queue.",
    "shortlist": "Prioritized to read next.",
    "archive": "Done/read — implies finished in engagement scoring.",
    "feed": "RSS/feed items (read-only on save).",
}
READER_CATEGORIES = [
    "article", "email", "rss", "highlight", "note",
    "pdf", "epub", "tweet", "video",
]

# Frontmatter accepted by save_markdown / save_markdown_as_epub. Mirrors the
# resolution pipeline in markdown_render.resolve_metadata.
FRONTMATTER_SCHEMA = {
    "title": {"type": "string", "note": "Falls back to first # H1, then 'Untitled'."},
    "author": {"type": "string"},
    "summary": {"type": "string"},
    "tags": {"type": "list[string]", "note": "Bracketed list, e.g. [research, draft]."},
    "published_date": {"type": "string", "note": "ISO 8601 date."},
    "image_url": {"type": "string", "note": "Cover/hero image (save_markdown only)."},
    "note": {"type": "string", "note": "Preface note block (save_markdown_as_epub)."},
}

# Human-readable description of the engagement-score buckets and flags so an
# agent reading reading_status output knows what each component means.
ENGAGEMENT_RUBRIC = {
    "base_layers": {
        "highlighted": {"value": _BASE_VALUES["highlighted"], "meaning": "Reader-era source with non-discarded highlights."},
        "finished_no_hl": {"value": _BASE_VALUES["finished_no_hl"], "meaning": "Archived or progress >= 0.9, no highlights."},
        "reading": {"value": _BASE_VALUES["reading"], "meaning": "0 < reading_progress < 0.9."},
        "saved_warm": {"value": _BASE_VALUES["saved_warm"], "meaning": "In 'later', progress 0 — saved with intent."},
        "saved_cold": {"value": _BASE_VALUES["saved_cold"], "meaning": "Saved, untouched, no intent signal."},
        "legacy": {"value": _BASE_VALUES["legacy"], "meaning": "v2-only source (pre-Reader Kindle/iBooks era)."},
    },
    "score_components": {
        "raw": "intensity + recency + return_strength (the default ranking).",
        "intensity": "base_value + density + annotation (recency removed).",
        "recency": "+0.20 if highlighted <=30d ago; -0.10 if >5y; else 0.",
        "return_strength": "multi_era_return (+0.30) and/or reader_return (+0.20).",
    },
    "density_bonus": {
        ">=30 highlights": 0.70, ">=10": 0.50, ">=3": 0.30, ">=1": 0.10,
        "note": "Only applies to highlighted/legacy base layers.",
    },
    "annotation_bonus": {
        "has_user_note": 0.30, "has_user_tag": 0.10, "has_favorite": 0.20,
    },
    "flags": {
        "multi_era_return": "Gap > 2 years between consecutive highlights.",
        "reader_return": "Reopened within 30d after first opening > 90d ago.",
        "junk_drawer_candidate": "Cold/warm, no highlights, saved > 30d ago.",
    },
}


def _epub_style_css() -> str:
    """Read the packaged CDIT EPUB stylesheet."""
    return (
        resources.files("mcp_readwise.assets.epub")
        .joinpath("cdit-style.css")
        .read_text(encoding="utf-8")
    )


def register_resources(mcp: FastMCP) -> None:
    """Register all reference resources onto the given FastMCP instance."""

    @mcp.resource(
        "readwise://epub/style.css",
        name="CDIT EPUB stylesheet",
        description="The brand stylesheet applied to EPUBs rendered by save_markdown_as_epub.",
        mime_type="text/css",
    )
    def epub_style() -> str:
        return _epub_style_css()

    @mcp.resource(
        "readwise://schema/frontmatter",
        name="Markdown frontmatter schema",
        description="Frontmatter fields accepted by save_markdown and save_markdown_as_epub.",
        mime_type="application/json",
    )
    def frontmatter_schema() -> str:
        return json.dumps(FRONTMATTER_SCHEMA, indent=2)

    @mcp.resource(
        "readwise://enums/reader",
        name="Reader location & category enums",
        description="Accepted location and category values for Reader tools.",
        mime_type="application/json",
    )
    def reader_enums() -> str:
        return json.dumps(
            {
                "locations": READER_LOCATIONS,
                "location_notes": READER_LOCATION_NOTES,
                "categories": READER_CATEGORIES,
            },
            indent=2,
        )

    @mcp.resource(
        "readwise://engagement/rubric",
        name="Engagement scoring rubric",
        description="Base layers, score components, density/annotation bonuses, and flags used by reading_status.",
        mime_type="application/json",
    )
    def engagement_rubric() -> str:
        return json.dumps(ENGAGEMENT_RUBRIC, indent=2)

    @mcp.resource(
        "readwise://engagement/status",
        name="Engagement index status",
        description="Live cache state of the engagement index (built?, age, source count, TTL).",
        mime_type="application/json",
    )
    def engagement_index_status() -> str:
        return json.dumps(index_status(), indent=2)

    @mcp.resource(
        "readwise://config",
        name="Server configuration",
        description="Non-secret server configuration: transport, index TTL, EPUB-sender readiness, tag denylist.",
        mime_type="application/json",
    )
    def server_config() -> str:
        return json.dumps(
            {
                "transport": settings.transport,
                "engagement_index_ttl_seconds": settings.engagement_index_ttl_seconds,
                "tag_denylist": sorted(_resolve_tag_denylist()),
                "tag_denylist_is_default": not settings.engagement_tag_denylist,
                "epub_sender_configured": settings.epub_sender_configured,
                "epub_max_bytes": settings.epub_max_bytes,
                "epub_lang": settings.epub_lang,
            },
            indent=2,
        )
