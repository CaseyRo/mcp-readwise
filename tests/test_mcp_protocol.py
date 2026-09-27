"""The MCP surface through the public client, not ``mcp._list_tools()``.

The older wiring tests reach into a private fastmcp method that a major upgrade
is free to rename. These go through ``fastmcp.Client`` over the in-memory
transport, so they catch the framework upgrade that stops the server importing,
drops a tool from the manifest, loses annotations on the wire, or breaks
dispatch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from mcp_readwise.server import mcp

EXPECTED_TOOLS = {
    "create_highlight",
    "create_tag",
    "delete_highlight",
    "delete_tag",
    "list_tags",
    "reader_get_by_url",
    "reader_list_documents",
    "reading_status",
    "save_markdown",
    "save_markdown_as_epub",
    "save_url",
    "tag_highlight",
    "update_highlight",
    "update_progress",
    "verify_epub_received",
    "writing_material",
}


@pytest.mark.asyncio
async def test_server_registers_its_tools():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert EXPECTED_TOOLS <= names, f"missing: {EXPECTED_TOOLS - names}"


@pytest.mark.asyncio
async def test_read_only_tools_are_annotated_over_the_wire():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    ann = tools["list_tags"].annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.openWorldHint is True
    assert tools["delete_tag"].annotations.destructiveHint is True


@pytest.mark.asyncio
async def test_a_read_only_tool_call_round_trips():
    # Upstream HTTP client mocked: nothing reaches Readwise.
    with patch("mcp_readwise.tools.tags.client") as upstream:
        upstream.get = AsyncMock(
            return_value={"results": [{"id": 10, "name": "identity"}]}
        )
        async with Client(mcp) as client:
            result = await client.call_tool("list_tags", {})

    upstream.get.assert_awaited_once_with("/api/v2/tags/")
    [tag] = result.structured_content["result"]
    assert (tag["id"], tag["name"]) == (10, "identity")
