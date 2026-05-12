"""FastMCP server for Readwise."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_readwise import __version__
from mcp_readwise.auth import BearerTokenVerifier
from mcp_readwise.config import settings
from mcp_readwise.engagement import index_status
from mcp_readwise.tools.highlights import (
    create_highlight,
    delete_highlight,
    update_highlight,
)
from mcp_readwise.tools.epub_sender import save_markdown_as_epub
from mcp_readwise.tools.epub_verifier import verify_epub_received
from mcp_readwise.tools.markdown import save_markdown
from mcp_readwise.tools.reader import (
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

mcp = FastMCP("mcp-readwise", auth=_auth)

# Read tools — engagement-aware (the v0.4.0 surface)
mcp.tool(reading_status)
mcp.tool(writing_material)

# Highlights — write
mcp.tool(create_highlight)
mcp.tool(update_highlight)
mcp.tool(delete_highlight)

# Tags
mcp.tool(list_tags)
mcp.tool(create_tag)
mcp.tool(delete_tag)
mcp.tool(tag_highlight)

# Reader — write/update only (read paths absorbed by reading_status / writing_material)
mcp.tool(save_url)
mcp.tool(save_markdown)
mcp.tool(save_markdown_as_epub)
mcp.tool(verify_epub_received)
mcp.tool(update_progress)

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
        "tools": 14,
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
