"""FastMCP server for Readwise."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_readwise import __version__
from mcp_readwise.auth import BearerTokenVerifier
from mcp_readwise.config import settings
from mcp_readwise.engagement import get_index, index_status
from mcp_readwise.tools.highlights import (
    create_highlight,
    delete_highlight,
    update_highlight,
)
from mcp_readwise.tools.epub_sender import save_markdown_as_epub
from mcp_readwise.tools.epub_verifier import verify_epub_received
from mcp_readwise.tools.markdown import save_markdown
from mcp_readwise.tools.reader import (
    reader_get_by_url,
    reader_list_documents,
    save_url,
    update_progress,
)
from mcp_readwise.tools.status import reading_status
from mcp_readwise.tools.tags import (
    create_tag,
    delete_tag,
    list_tags,
    tag_highlight,
)
from mcp_readwise.tools.writing import writing_material
from mcp_readwise.prompts import register_prompts
from mcp_readwise.resources import register_resources

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_start_time = datetime.now(timezone.utc)


def _resolve_git_commit() -> str:
    """Get git commit from env var, baked file, or git command."""
    from_env = os.getenv("GIT_COMMIT", "")
    if from_env and from_env != "unknown":
        return from_env
    # Check for baked-in file (Docker image)
    try:
        with open("/app/.git_commit") as f:
            val = f.read().strip()
            if val and val != "unknown":
                return val
    except FileNotFoundError:
        pass
    # Fallback: git command (local dev)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


_git_commit = _resolve_git_commit()

_api_key = settings.mcp_api_key.get_secret_value()
if settings.transport == "http" and not _api_key:
    raise SystemExit(
        "MCP_API_KEY is required in HTTP mode. Refusing to start "
        "an unauthenticated server."
    )
_auth = BearerTokenVerifier(api_key=_api_key) if _api_key else None


@asynccontextmanager
async def _lifespan(app):
    """Pre-warm the engagement index in the background so the first
    reading_status / writing_material call doesn't pay cold-start cost."""
    async def _prewarm():
        try:
            await get_index()
        except Exception:
            logger.warning("Engagement index pre-warm failed", exc_info=True)

    task = asyncio.create_task(_prewarm())
    try:
        yield
    finally:
        if not task.done():
            task.cancel()


_INSTRUCTIONS = """\
mcp-readwise is an engagement-aware bridge to a personal Readwise + Readwise
Reader library. It does NOT mirror Readwise's REST surface — it exposes a small
set of workflow-shaped tools built on a cached engagement index that joins v2
books, their highlights, and v3 Reader documents into scored `Source`s.

Picking a read tool:
  - `reading_status` — single-call library snapshot: recent activity, durable
    interests (evergreen), current attention, the junk drawer, and corpus
    signal density. Start here to orient.
  - `writing_material` — gather highlights + notes + summary for drafting, by
    `book_id` / `document_id` / `title_search` (one source) or `topic` (across
    sources). Exactly one selector; ambiguous title_search errors list
    candidate ids.
  - `reader_list_documents` / `reader_get_by_url` — go past the engagement
    cache to browse or look up the full Reader library (e.g. archived docs).

Saving content:
  - `save_url` — save a public URL; Reader fetches and parses it.
  - `save_markdown` — synchronous; posts owned markdown as Reader-ready HTML
    (returns the ReaderDocument in the same call).
  - `save_markdown_as_epub` — ASYNC: renders a real EPUB 3 with CDIT brand
    styling and emails it to your Readwise Library. It returns after SMTP
    delivery; the document appears in Reader 1–5 minutes later. DO NOT tell the
    human it is available until `verify_epub_received` confirms ingest. Pass an
    `idempotency_key` so retries don't duplicate. Requires the env vars
    READWISE_LIBRARY_EMAIL, RESEND_API_KEY, EPUB_FROM_ADDRESS — it raises
    ConfigurationError (listing the missing ones) if unset.

Env vars: the read/save/tag/highlight tools need READWISE_TOKEN. Only
`save_markdown_as_epub` needs the three EPUB-sender vars above;
`verify_epub_received` does not.

Reference data lives in resources (readwise://...): the EPUB stylesheet, the
frontmatter schema, Reader location/category enums, and the engagement-scoring
rubric. Guided prompts cover the two signature flows:
publish_research_to_reader and draft_from_highlights.
"""

mcp = FastMCP(
    "mcp-readwise",
    instructions=_INSTRUCTIONS,
    auth=_auth,
    lifespan=_lifespan,
)

# All tools touch the live Readwise API → openWorldHint=True everywhere.
_OPEN = {"openWorldHint": True}

# Read tools — engagement-aware (the v0.4.0 surface)
mcp.tool(
    reading_status,
    title="Reading status snapshot",
    annotations={**_OPEN, "readOnlyHint": True},
)
mcp.tool(
    writing_material,
    title="Gather writing material",
    annotations={**_OPEN, "readOnlyHint": True},
)

# Highlights — write
mcp.tool(
    create_highlight,
    title="Create highlight",
    annotations=_OPEN,
)
mcp.tool(
    update_highlight,
    title="Update highlight",
    annotations={**_OPEN, "idempotentHint": True},
)
mcp.tool(
    delete_highlight,
    title="Delete highlight",
    annotations={**_OPEN, "destructiveHint": True, "idempotentHint": True},
)

# Tags
mcp.tool(
    list_tags,
    title="List tags",
    annotations={**_OPEN, "readOnlyHint": True},
)
mcp.tool(
    create_tag,
    title="Create tag",
    annotations={**_OPEN, "idempotentHint": True},
)
mcp.tool(
    delete_tag,
    title="Delete tag",
    annotations={**_OPEN, "destructiveHint": True, "idempotentHint": True},
)
mcp.tool(
    tag_highlight,
    title="Add or remove a highlight tag",
    annotations={**_OPEN, "idempotentHint": True},
)

# Reader — write/update tools
mcp.tool(
    save_url,
    title="Save URL to Reader",
    annotations=_OPEN,
)
mcp.tool(
    save_markdown,
    title="Save markdown to Reader",
    annotations={**_OPEN, "idempotentHint": True},
)
mcp.tool(
    save_markdown_as_epub,
    title="Save markdown to Reader as EPUB (async)",
    annotations={**_OPEN, "idempotentHint": True},
)
mcp.tool(
    verify_epub_received,
    title="Verify EPUB received",
    annotations={**_OPEN, "readOnlyHint": True},
)
mcp.tool(
    update_progress,
    title="Update reading progress",
    annotations={**_OPEN, "idempotentHint": True},
)

# Reader — by-URL / archive lookup beyond the engagement cache (CDI-1147)
mcp.tool(
    reader_list_documents,
    title="List Reader documents",
    annotations={**_OPEN, "readOnlyHint": True},
)
mcp.tool(
    reader_get_by_url,
    title="Get Reader document by URL",
    annotations={**_OPEN, "readOnlyHint": True},
)

# Reference resources + guided-workflow prompts
register_resources(mcp)
register_prompts(mcp)

# NOTE: v0.4.0 BREAKING — the following read primitives are no longer
# registered as MCP tools. Their client functions remain available for
# internal use by the engagement module:
#   - search_highlights, list_highlights, get_highlight
#   - list_books, get_book
#   - list_documents, get_document
#   - export_highlights
# Migrate callers to `reading_status` (orientation, status, patterns) or
# `writing_material` (highlights for drafting, source bundles).


def _build_version() -> str:
    """Combine semver with git commit for a unique build identifier."""
    if _git_commit and _git_commit != "unknown":
        return f"{__version__}+{_git_commit}"
    return __version__


_build = _build_version()


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "healthy",
        "service": "mcp-readwise",
        "version": __version__,
        "build": _build,
        "git_commit": _git_commit,
        "uptime_seconds": int((datetime.now(timezone.utc) - _start_time).total_seconds()),
        "tools": 16,
        "engagement_index": index_status(),
        "epub_sender": {
            "configured": settings.epub_sender_configured,
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "from_address": settings.epub_from_address,
            "library_email_set": bool(settings.readwise_library_email),
        },
    })


def main() -> None:
    """Entry point for the mcp-readwise server."""
    if settings.transport == "http":
        mcp.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
            stateless_http=True,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
