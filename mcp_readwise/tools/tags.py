"""Tag tools — list, create, delete, tag/untag highlights."""

from __future__ import annotations

from typing import Literal

from mcp_readwise.client import client
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


async def delete_tag(tag_id: int) -> dict:
    """Delete a tag by ID.

    Returns a confirmation with the deleted tag's ID.
    """
    await client.delete(f"/api/v2/tags/{tag_id}")
    return {"deleted": True, "id": tag_id}


async def tag_highlight(
    highlight_id: int,
    tag: str,
    action: Literal["add", "remove"],
) -> list[str]:
    """Add or remove a tag on a highlight.

    Use action='add' to tag a highlight (creates the tag if it doesn't exist).
    Use action='remove' to untag it.
    Returns the highlight's updated list of tag names.
    """
    if action == "add":
        await client.post(
            f"/api/v2/highlights/{highlight_id}/tags/", name=tag
        )
    else:
        tags_data = await client.get(f"/api/v2/highlights/{highlight_id}/tags/")
        tag_list = tags_data if isinstance(tags_data, list) else tags_data.get("results", [])
        for t in tag_list:
            if t.get("name") == tag:
                await client.delete(
                    f"/api/v2/highlights/{highlight_id}/tags/{t['id']}"
                )
                break

    updated = await client.get(f"/api/v2/highlights/{highlight_id}/tags/")
    result_list = updated if isinstance(updated, list) else updated.get("results", [])
    return [t.get("name", "") for t in result_list]
