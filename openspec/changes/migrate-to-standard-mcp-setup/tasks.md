## 1. Project Scaffold

- [x] 1.1 Create `pyproject.toml` with hatchling build, fastmcp/httpx/pydantic/pydantic-settings dependencies, dev group (pytest, pytest-asyncio, pytest-httpx, ruff), and `mcp-readwise` entry point
- [x] 1.2 Create package structure: `mcp_readwise/__init__.py`, `__main__.py`, `py.typed`
- [x] 1.3 Create `mcp_readwise/config.py` — Settings class with `readwise_token` (SecretStr), `transport`, `host`, `port`, `mcp_api_key`, `readwise_base_url`
- [x] 1.4 Create `mcp_readwise/auth.py` — copy BearerTokenVerifier from mcp-siyuan
- [x] 1.5 Run `uv sync` to generate `uv.lock`

## 2. HTTP Client

- [x] 2.1 Create `mcp_readwise/client.py` — ReadwiseClient class wrapping httpx.AsyncClient with X-Access-Token header, base URL routing (v2/v3), connection pooling
- [x] 2.2 Add exponential backoff on HTTP 429 and retry logic (3 retries on 5xx/timeouts)
- [x] 2.3 Add in-memory book metadata cache (LRU, 15-minute TTL) for joining book context into highlight responses

## 3. Response Models

- [x] 3.1 Create `mcp_readwise/models/__init__.py`
- [x] 3.2 Create `mcp_readwise/models/highlights.py` — HighlightResult (with book_title, book_author, source_url), HighlightListResult (pagination envelope), ExportResult (cursor envelope)
- [x] 3.3 Create `mcp_readwise/models/books.py` — BookResult, BookListResult
- [x] 3.4 Create `mcp_readwise/models/tags.py` — TagResult, TagListResult
- [x] 3.5 Create `mcp_readwise/models/reader.py` — ReaderDocument, ReaderListResult

## 4. Highlight Tools

- [x] 4.1 Create `mcp_readwise/tools/__init__.py`
- [x] 4.2 Create `mcp_readwise/tools/highlights.py` — `search_highlights` (query, search_type Literal, book_id, tags, limit)
- [x] 4.3 Add `list_highlights` (book_id, tag, updated_after, page, limit) with pagination envelope
- [x] 4.4 Add `get_highlight` (highlight_id) with joined book metadata
- [x] 4.5 Add `create_highlight` (text, book_id, note, tags) returning full object
- [x] 4.6 Add `update_highlight` (highlight_id, text, note) returning full object
- [x] 4.7 Add `delete_highlight` (highlight_id) returning confirmation

## 5. Book Tools

- [x] 5.1 Create `mcp_readwise/tools/books.py` — `list_books` (category Literal, source, num_highlights_gte, updated_after, page, limit)
- [x] 5.2 Add `get_book` (book_id) returning full book object

## 6. Tag Tools

- [x] 6.1 Create `mcp_readwise/tools/tags.py` — `list_tags` returning all tags
- [x] 6.2 Add `create_tag` (name) returning created tag
- [x] 6.3 Add `delete_tag` (tag_id) returning confirmation
- [x] 6.4 Add `tag_highlight` (highlight_id, tag, action Literal add/remove) returning updated tag list

## 7. Reader Tools

- [x] 7.1 Create `mcp_readwise/tools/reader.py` — `list_documents` (location Literal, category Literal, updated_after, page, limit)
- [x] 7.2 Add `get_document` (document_id) returning full document with content
- [x] 7.3 Add `save_url` (url, title, tags, location Literal, notes) returning created document
- [x] 7.4 Add `update_progress` (document_id, reading_progress float 0.0-1.0) returning updated document

## 8. Export Tool

- [x] 8.1 Create `mcp_readwise/tools/export.py` — `export_highlights` (updated_after, book_ids, cursor) with cursor pagination

## 9. Server Assembly

- [x] 9.1 Create `mcp_readwise/server.py` — FastMCP instantiation, tool registration (all tools from modules), BearerTokenVerifier, main() entry point matching mcp-siyuan pattern
- [x] 9.2 Verify all tools register correctly and server starts in both stdio and HTTP modes

## 10. Docker & Deployment

- [x] 10.1 Create new `Dockerfile` — python:3.12-slim, pip install, non-root mcp user, port 8000, health check
- [x] 10.2 Create new `compose.yaml` — TRANSPORT=http, HOST=0.0.0.0, env vars, fastmcp-data volume, memory limit 512m
- [x] 10.3 Create `komodo.toml` — git-mcp-readwise stack, ubuntu-smurf-mirror, env vars, tags ["mcp"]
- [x] 10.4 Remove old Node.js files: `src/`, `package.json`, `package-lock.json`, `tsconfig.json`, `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`, `docker-compose.dev.yml`, `test-server.js`, `examples/`, `DOCKER.md`, `MCP-vs-REST.md`

## 11. Testing

- [x] 11.1 Create `tests/` directory with `conftest.py` (shared fixtures: mock client, settings)
- [x] 11.2 Write tests for ReadwiseClient (retry, rate limit, header injection)
- [x] 11.3 Write tests for highlight tools (search, list, CRUD)
- [x] 11.4 Write tests for book, tag, reader, and export tools
- [x] 11.5 Verify Docker build and health check pass

## 12. Documentation

- [x] 12.1 Rewrite README.md for Python/FastMCP — installation (uv/pip), configuration, Docker, available tools
- [x] 12.2 Update AGENTS.md with new project structure and conventions
- [x] 12.3 Create SiYuan documentation page: "CDIT MCP Server Standards" covering project structure, dependencies, config, auth, Docker, Komodo, Cloudflare Portal, tool design principles with real examples from mcp-siyuan and mcp-readwise

## 13. Deploy & Verify

- [x] 13.1 Build and test Docker image locally
- [ ] 13.2 Deploy to Komodo via git push
- [ ] 13.3 Configure Cloudflare MCP Portal for mcp-readwise.cdit-dev.de
- [ ] 13.4 Verify all tools work through Cloudflare Portal from Claude Desktop
