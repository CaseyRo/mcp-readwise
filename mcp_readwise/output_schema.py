"""Error-path-safe output schema helpers for wrapped-result tools.

A handful of tools return a top-level JSON array / scalar / optional
(``list[...]``, ``Optional[Model]``) rather than an object. fastmcp wraps
those under ``{"result": ...}`` and marks the published ``output_schema`` with
``x-fastmcp-wrap-result: true`` and ``required: ["result"]``.

That ``required: ["result"]`` is the bug class fixed in mcp-zernio: a strict
client (or the manually-synced Cloudflare MCP portal) validates a tool's
``structured_content`` against the published schema, so a top-level
``{"error": ...}`` payload — which carries no ``result`` key — is *rejected*.

`register_error_safe_wrapped` registers such a tool while relaxing its
generated schema additively so BOTH shapes validate:

  * success: ``{"result": <array|scalar|object|null>}`` (unchanged wire shape —
    ``x-fastmcp-wrap-result`` is preserved, so fastmcp still wraps the return);
  * error:   ``{"error": "..."}`` (top-level), plus any partial/empty payload.

The relaxation is purely additive — it never renames or removes ``result``,
never changes the tool's name, params, or success return shape. It only:
  * drops ``required`` (so a missing ``result`` no longer fails validation),
  * adds an optional top-level ``error`` property, and
  * sets ``additionalProperties: true`` (extra="allow" parity).
"""

from __future__ import annotations

from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool

# Optional top-level error property mirroring the models' ``error: str | None``.
_ERROR_PROPERTY: dict[str, Any] = {
    "anyOf": [{"type": "string"}, {"type": "null"}],
    "default": None,
}


def relax_wrapped_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return an error-path-safe copy of a wrapped-result output schema.

    Additive only: keeps the ``result`` property and ``x-fastmcp-wrap-result``
    so the success wire shape is identical, but makes ``result`` optional, adds
    an optional top-level ``error``, and allows extra keys. Idempotent.
    """
    relaxed = dict(schema)
    # A missing ``result`` (i.e. a top-level error payload) must not fail.
    relaxed.pop("required", None)

    properties = dict(relaxed.get("properties") or {})
    # Additive: never clobber an existing ``error`` shape if one is present.
    properties.setdefault("error", dict(_ERROR_PROPERTY))
    relaxed["properties"] = properties

    # extra="allow" parity at the top level — an error/partial payload with
    # only ``error`` (and no ``result``) validates cleanly.
    relaxed["additionalProperties"] = True
    return relaxed


def register_error_safe_wrapped(
    mcp: FastMCP,
    fn: Callable[..., Any],
    *,
    title: str | None = None,
    annotations: dict[str, Any] | None = None,
    tags: set[str] | None = None,
) -> FunctionTool:
    """Register ``fn`` as a tool with an error-path-safe wrapped output schema.

    Equivalent to ``mcp.tool(fn, title=..., annotations=..., tags=...)`` for a
    wrapped-result tool, except the generated ``output_schema`` is relaxed so a
    top-level ``{"error": ...}`` payload also validates against it. The tool's
    name, parameters, and success return shape are unchanged.
    """
    tool = FunctionTool.from_function(
        fn,
        title=title,
        annotations=annotations,
        tags=tags,
    )

    # Only wrapped-result tools carry the bug; relax them. Object-returning
    # tools (no wrapper) already validate error payloads via their model's
    # extra="allow" + optional ``error`` field, so leave their schema untouched.
    if tool.output_schema and tool.output_schema.get("x-fastmcp-wrap-result"):
        tool.output_schema = relax_wrapped_output_schema(tool.output_schema)

    mcp.add_tool(tool)
    return tool
