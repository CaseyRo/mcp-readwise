"""Tag tools — list, create, delete (v2 highlight tags)."""

from __future__ import annotations

from mcp_readwise.client import client
from mcp_readwise.models.highlights import DeletionResult
from mcp_readwise.models.tags import TagResult


async def list_tags() -> list[TagResult]:
    """List all tags in your Readwise library.

    Returns every tag with its ID and name. No pagination needed —
    tag collections are typically small.
    """
    data = await client.get("/api/v2/tags/")
    raw_results = data.get("results", []) if isinstance(data, dict) else data
    return [
        TagResult(id=item.get("id", 0), name=item.get("name", ""))
        for item in raw_results
    ]


async def create_tag(name: str) -> TagResult:
    """Create a new tag.

    Returns the created tag with its ID and name.
    """
    data = await client.post("/api/v2/tags/", name=name)
    return TagResult(id=data.get("id", 0), name=data.get("name", name))


async def delete_tag(tag_id: int) -> DeletionResult:
    """Delete a tag by ID.

    Returns a confirmation with the deleted tag's ID. This is irreversible —
    the tag is removed from every highlight it was applied to.
    """
    await client.delete(f"/api/v2/tags/{tag_id}")
    return DeletionResult(deleted=True, id=tag_id)

