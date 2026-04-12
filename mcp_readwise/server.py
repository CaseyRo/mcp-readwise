"""FastMCP server for Readwise."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_readwise import __version__
from mcp_readwise.auth import BearerTokenVerifier
from mcp_readwise.config import settings

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
        import subprocess
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
from mcp_readwise.tools.highlights import (
    create_highlight,
    delete_highlight,
    get_highlight,
    list_highlights,
    search_highlights,
    update_highlight,
)
from mcp_readwise.tools.books import get_book, list_books
from mcp_readwise.tools.tags import (
    create_tag,
    delete_tag,
    list_tags,
    tag_highlight,
)
from mcp_readwise.tools.reader import (
    get_document,
    list_documents,
    save_url,
    update_progress,
)
from mcp_readwise.tools.export import export_highlights

_api_key = settings.mcp_api_key.get_secret_value()
_auth = BearerTokenVerifier(api_key=_api_key) if _api_key else None

mcp = FastMCP("mcp-readwise", auth=_auth)

# Highlights — search & read
mcp.tool(search_highlights)
mcp.tool(list_highlights)
mcp.tool(get_highlight)

# Highlights — write
mcp.tool(create_highlight)
mcp.tool(update_highlight)
mcp.tool(delete_highlight)

# Books
mcp.tool(list_books)
mcp.tool(get_book)

# Tags
mcp.tool(list_tags)
mcp.tool(create_tag)
mcp.tool(delete_tag)
mcp.tool(tag_highlight)

# Reader
mcp.tool(list_documents)
mcp.tool(get_document)
mcp.tool(save_url)
mcp.tool(update_progress)

# Export
mcp.tool(export_highlights)


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
        "tools": 17,
    })


def main() -> None:
    """Entry point for the mcp-readwise server."""
    if settings.transport == "http":
        mcp.run(transport="http", host=settings.host, port=settings.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
