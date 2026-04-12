"""FastMCP server for Readwise."""

from __future__ import annotations

import os

from fastmcp import FastMCP

from mcp_readwise.auth import BearerTokenVerifier
from mcp_readwise.config import settings
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

_api_key = os.getenv("MCP_API_KEY", "")
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


def main() -> None:
    """Entry point for the mcp-readwise server."""
    if settings.transport == "http":
        mcp.run(transport="http", host=settings.host, port=settings.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
