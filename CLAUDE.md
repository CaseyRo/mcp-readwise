# CLAUDE.md

Project overview, structure and conventions: see [AGENTS.md](AGENTS.md) and [README.md](README.md).

```bash
uv sync && uv run pytest && uv run ruff check .
```

## Scope: what this server adds over the official connector

The official claude.ai Readwise connector (`mcp__claude_ai_readwise_MCP__…`) covers Reader search/list/create/move/tags, highlight CRUD and highlight tags, highlight vector search and daily review. This server keeps only the gap: EPUB delivery (`save_markdown_as_epub`, `verify_epub_received`), branded `save_markdown`, engagement-scored `reading_status` / `writing_material`, `update_progress`, `reader_get_by_url` (exact URL lookup) and v2 tags (`list_tags` for ids, `create_tag`, `delete_tag`). Don't re-add tools the connector already has.

## fastmcp 4 idioms

- Tools are plain async functions registered in `server.py` with `mcp.tool(fn, title=..., annotations=...)`; output models must stay additive-only (`tests/test_output_schema_contract.py`).
- Raise `fastmcp.exceptions.ToolError` for caller mistakes.
- Test over the wire with the in-memory `fastmcp.Client(mcp)` (`tests/test_mcp_protocol.py`); see the `mcp-testing` skill.
- Releases are tag-only via GitHub Actions + Komodo; `main` is protected (PR + `test` check). See the `cdit-release-pipeline` skill.
- Fleet context, auth and the Cloudflare portal (catalog needs a manual sync after tool-surface changes): `CDiT-infrastructure/docs/wiki/topics/mcp-fleet.md`.
