## Why

The current mcp-readwise server is a Node.js/TypeScript wrapper around the official `@readwise/readwise-mcp` npm module. It exposes exactly one tool (`search_readwise_highlights`) via a hand-rolled Express HTTP layer that manually implements JSON-RPC routing — none of which aligns with our standard MCP server stack (Python, FastMCP 3.x, Cloudflare MCP Portal, Komodo deployment). The single-tool surface is severely limiting: you cannot list books, manage tags, create highlights, save URLs to Reader, or export data. A full rewrite to our standard stack gives us near-complete Readwise API coverage, consistent infrastructure, and maintainable code.

## What Changes

- **BREAKING**: Complete rewrite from Node.js/TypeScript to Python FastMCP 3.x. The npm package, `package.json`, `tsconfig.json`, and all TypeScript source files are removed.
- **BREAKING**: Tool name changes. `search_readwise_highlights` becomes `search_highlights` (plus many new tools). Tool names follow our standard convention: plain function names without a server prefix (the Cloudflare MCP Portal adds the server namespace automatically, e.g. `readwise_search_highlights`). Existing Claude Desktop / MCP client configurations will need updating.
- New `pyproject.toml` with `hatchling` build system, `fastmcp>=3.2.2`, `httpx`, `pydantic`, `pydantic-settings` dependencies.
- New package structure: `mcp_readwise/` with `server.py`, `config.py`, `client.py`, `models/`, `tools/` following the pattern established in mcp-siyuan, mcp-klartext, mcp-writings, etc.
- New `compose.yaml` replacing `docker-compose.yml` + `docker-compose.dev.yml`. Standard pattern: `TRANSPORT=http`, `MCP_API_KEY`, `FASTMCP_HOME=/data/fastmcp`, port 8000 internal.
- New `Dockerfile` using `python:3.12-slim` base image with pip install, non-root user.
- New `komodo.toml` for Komodo stack deployment.
- Cloudflare MCP Portal integration via bearer token auth (same as mcp-siyuan, mcp-klartext).
- ~15 new MCP tools covering highlights, books, tags, Reader documents, and export (see Capabilities below).
- Updated README.md and documentation.
- SiYuan documentation page for CDIT MCP server standards.

## Capabilities

### New Capabilities

- `highlight-tools`: Search (vector + full-text + hybrid), list with filters, get by ID, create, update, delete highlights. Includes bulk export with cursor pagination. Response models join book metadata (title, author, URL) into every highlight to eliminate follow-up calls.
- `book-tools`: List books/sources with category/source/annotation-density filters. Get book by ID. Categories: books, articles, tweets, podcasts, supplementals.
- `tag-tools`: List all tags, create tag, delete tag, add/remove tag on highlight (single tool with `action` parameter).
- `reader-tools`: List Reader documents with location/category filters, get document by ID (full content), save URL to Reader (with optional title/tags/location/notes), update reading progress.
- `server-infrastructure`: Python FastMCP server setup — `config.py` (pydantic-settings), `client.py` (centralized httpx client with auth, retries, rate-limit backoff), bearer token auth via `BearerTokenVerifier`, HTTP transport.
- `deployment-config`: `compose.yaml`, `Dockerfile` (python:3.12-slim), `komodo.toml` for Komodo stack deployment, Cloudflare MCP Portal configuration.
- `mcp-standards-doc`: SiYuan documentation page covering CDIT's standard MCP server patterns — project structure, dependencies, config, auth, Docker, Komodo, Cloudflare Portal, tool design principles.

### Modified Capabilities

_(none — this is a full rewrite, no existing specs to modify)_

## Impact

**Code**: All TypeScript source (`src/mcp-http-server.ts`), Node.js config (`package.json`, `tsconfig.json`, `package-lock.json`), and Node.js Docker files (`Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`, `docker-compose.dev.yml`) are replaced with Python equivalents. The `examples/` directory and `test-server.js` are removed.

**Dependencies**: Moves from npm ecosystem (`@readwise/readwise-mcp`, `@modelcontextprotocol/sdk`, `express`, `axios`, `zod`) to Python ecosystem (`fastmcp`, `httpx`, `pydantic`, `pydantic-settings`). Managed via `pyproject.toml` + `uv`.

**API surface**: Grows from 1 tool to ~15 tools. Tool names use plain function names without a server prefix (matching mcp-siyuan convention: `search`, `get_document`, `list_books` — the Cloudflare Portal adds the `readwise_` namespace). All tools follow LLM ergonomic design principles — self-describing parameters with `Literal` types for enums, sensible defaults, pagination envelopes with `total`/`next_cursor`, and response models that include joined context (book titles/authors in highlight responses).

**Infrastructure**: Docker image switches from `node:22-alpine` to `python:3.12-slim`. Internal port changes from 3000 to 8000. Komodo stack replaces manual Docker Compose deployment. Cloudflare MCP Portal provides external HTTPS access with bearer token auth.

**External systems**: Readwise API (`readwise.io`) and Readwise Reader API — both use `X-Access-Token` header authentication. Rate limiting handled centrally in `client.py` with exponential backoff.

**Documentation**: README rewritten for Python/FastMCP. New SiYuan page documents the CDIT MCP server standard for use across all future MCP server projects.
