"""Error-path-safe wrapped output schema — unit + in-memory Client coverage.

Pins the fix for the three wrapped-result tools (``list_tags``,
``tag_highlight``, ``reader_get_by_url``): their published ``output_schema``
must validate BOTH the success ``{"result": ...}`` wire shape AND a top-level
``{"error": ...}`` payload, without changing tool name/params/return.
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastmcp import Client, FastMCP

from mcp_readwise.output_schema import (
    register_error_safe_wrapped,
    relax_wrapped_output_schema,
)

jsonschema = pytest.importorskip("jsonschema")


# --- relax helper ---------------------------------------------------------


class TestRelaxHelper:
    def test_drops_required_adds_error_allows_extra(self):
        original = {
            "type": "object",
            "properties": {"result": {"type": "array", "items": {"type": "string"}}},
            "required": ["result"],
            "x-fastmcp-wrap-result": True,
        }
        relaxed = relax_wrapped_output_schema(original)

        # required gone, error added, extras allowed, wrapper preserved
        assert "required" not in relaxed
        assert "error" in relaxed["properties"]
        assert "result" in relaxed["properties"]  # additive — never removed
        assert relaxed["additionalProperties"] is True
        assert relaxed["x-fastmcp-wrap-result"] is True
        # input not mutated
        assert original.get("required") == ["result"]

    def test_idempotent(self):
        original = {
            "type": "object",
            "properties": {"result": {"type": "array"}},
            "required": ["result"],
            "x-fastmcp-wrap-result": True,
        }
        once = relax_wrapped_output_schema(original)
        twice = relax_wrapped_output_schema(once)
        assert twice == once

    def test_does_not_clobber_existing_error_property(self):
        original = {
            "type": "object",
            "properties": {
                "result": {"type": "array"},
                "error": {"type": "string"},  # already present
            },
            "x-fastmcp-wrap-result": True,
        }
        relaxed = relax_wrapped_output_schema(original)
        assert relaxed["properties"]["error"] == {"type": "string"}

    def test_relaxed_schema_validates_both_shapes(self):
        original = {
            "type": "object",
            "properties": {"result": {"type": "array", "items": {"type": "string"}}},
            "required": ["result"],
            "x-fastmcp-wrap-result": True,
        }
        relaxed = relax_wrapped_output_schema(original)
        validator = jsonschema.Draft7Validator(relaxed)
        assert not list(validator.iter_errors({"result": ["a", "b"]}))  # success
        assert not list(validator.iter_errors({"error": "boom"}))  # error
        assert not list(validator.iter_errors({}))  # empty/partial


# --- registration helper, end-to-end via in-memory Client -----------------


class TestRegisterErrorSafeWrapped:
    @pytest.mark.asyncio
    async def test_success_wire_shape_preserved(self):
        mcp = FastMCP("t")

        async def list_things() -> list[str]:
            """A list-returning tool (wrapped under result)."""
            return ["a", "b"]

        register_error_safe_wrapped(
            mcp, list_things, title="X", annotations={"readOnlyHint": True}
        )

        async with Client(mcp) as client:
            res = await client.call_tool("list_things", {})

        # fastmcp still wraps the list under {"result": ...}
        assert res.structured_content == {"result": ["a", "b"]}
        assert res.data == ["a", "b"]

    @pytest.mark.asyncio
    async def test_error_payload_validates_against_published_schema(self):
        """A top-level {"error": ...} structured payload must validate against
        the tool's published output_schema (the mcp-zernio guard)."""
        mcp = FastMCP("t")

        async def maybe_optional() -> Optional[dict]:
            """Optional-returning tool (wrapped under result)."""
            return None

        tool = register_error_safe_wrapped(mcp, maybe_optional, title="Y")

        async with Client(mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}

        schema = tools["maybe_optional"].outputSchema
        assert "result" not in set(schema.get("required") or [])
        validator = jsonschema.Draft7Validator(schema)
        # Both the in-memory tool object and the client-side schema agree.
        assert tool.output_schema.get("x-fastmcp-wrap-result") is True
        assert not list(validator.iter_errors({"error": "upstream blew up"}))
        assert not list(validator.iter_errors({"result": {"k": "v"}}))

    @pytest.mark.asyncio
    async def test_metadata_only_no_param_change(self):
        """annotations/title/tags are metadata only — the input schema and tool
        name must be untouched by the helper."""
        mcp = FastMCP("t")

        async def by_url(url: str, limit: int = 10) -> Optional[dict]:
            """Optional-returning tool with params."""
            return None

        register_error_safe_wrapped(
            mcp, by_url, title="By URL", annotations={"readOnlyHint": True}
        )

        async with Client(mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}

        t = tools["by_url"]
        props = set((t.inputSchema.get("properties") or {}).keys())
        assert props == {"url", "limit"}
        assert set(t.inputSchema.get("required") or []) == {"url"}


# --- the three REAL tools, as registered on the production server ---------


class TestRealServerWrappedTools:
    WRAPPED = {"list_tags", "tag_highlight", "reader_get_by_url"}

    @pytest.mark.asyncio
    async def test_real_tools_error_path_safe_via_client(self):
        from mcp_readwise.server import mcp

        async with Client(mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}

        for name in self.WRAPPED:
            schema = tools[name].outputSchema
            assert schema.get("x-fastmcp-wrap-result") is True, name
            assert "result" in (schema.get("properties") or {}), name
            assert "result" not in set(schema.get("required") or []), name
            validator = jsonschema.Draft7Validator(schema)
            assert not list(validator.iter_errors({"error": "boom"})), name
