## Context

mcp-readwise is currently a Node.js/TypeScript server (~770 lines) that wraps `@readwise/readwise-mcp` via Express with hand-rolled JSON-RPC. It exposes one tool (`search_readwise_highlights`) and uses a custom HTTP layer instead of the MCP SDK's built-in transport.

Our standard MCP server stack (proven across mcp-siyuan, mcp-klartext, mcp-writings, mcp-lexoffice, mcp-watermelon, mcp-zernio) uses:
- Python 3.12+ with FastMCP 3.x
- `pyproject.toml` + `hatchling` + `uv`
- `pydantic-settings` for config, `httpx` for HTTP client
- `compose.yaml` + `Dockerfile` (python:3.12-slim) + `komodo.toml`
- Cloudflare MCP Portal for external access with bearer token auth

The Readwise API has two main surfaces:
1. **Readwise API** (readwise.io/api/v2/) — highlights, books, tags, export
2. **Reader API** (readwise.io/api/v3/) — Reader documents, save URLs, reading progress

## Goals / Non-Goals

**Goals:**
- Rewrite to standard Python/FastMCP stack matching our other MCP servers
- Achieve near-complete Readwise API coverage (~15 tools)
- Follow established naming and structure conventions (mcp-siyuan as reference)
- Deploy via Komodo + Cloudflare MCP Portal
- Document CDIT MCP server standards in SiYuan for future reference

**Non-Goals:**
- Backward compatibility with the Node.js server (clean break)
- Readwise v1 API support (deprecated)
- Webhooks or real-time sync from Readwise
- Custom caching layer (Readwise API is fast enough for MCP use)
- Readwise account management tools (auth token rotation, etc.)

## Decisions

### 1. Package structure: `mcp_readwise/` with domain-split tools

Follow the mcp-siyuan pattern exactly:

```
mcp_readwise/
  __init__.py
  __main__.py
  server.py          # FastMCP app, tool registration, entry point
  config.py          # pydantic-settings: Settings class
  client.py          # Centralized httpx AsyncClient for Readwise API
  auth.py            # BearerTokenVerifier (copy from mcp-siyuan)
  models/
    __init__.py
    highlights.py    # HighlightResult, HighlightListResult, ExportResult
    books.py         # BookResult, BookListResult
    tags.py          # TagResult
    reader.py        # ReaderDocument, ReaderListResult
  tools/
    __init__.py
    highlights.py    # search_highlights, list_highlights, get_highlight, create/update/delete
    books.py         # list_books, get_book
    tags.py          # list_tags, create_tag, delete_tag, tag_highlight
    reader.py        # list_documents, get_document, save_url, update_progress
    export.py        # export_highlights
```

**Why over a flat structure**: Domain-split tools scale better as we add tools. Each file stays under ~200 lines. Matches mcp-siyuan which has `tools/read.py`, `tools/write.py`, `tools/smart.py`, `tools/export.py`.

### 2. Centralized httpx client with retry and rate-limit handling

Single `ReadwiseClient` class in `client.py` that all tools import. Handles:
- Base URL configuration (v2 for highlights/books/tags, v3 for Reader)
- `X-Access-Token` header injection
- Exponential backoff on 429 (rate limit) responses
- 3 retries on transient errors (5xx, timeouts)
- `httpx.AsyncClient` with connection pooling

**Why not per-tool HTTP calls**: Duplicated auth headers, no centralized rate limiting, inconsistent error handling. The mcp-siyuan `client.py` pattern works well.

### 3. Tool naming: snake_case function names, no prefix

Tools are plain Python async functions named with snake_case: `search_highlights`, `list_books`, `get_document`, `save_url`. FastMCP uses the function name as the tool name. The Cloudflare MCP Portal adds the server namespace prefix automatically.

**Why no `readwise_` prefix**: Our convention (mcp-siyuan uses `search`, `get_document`, `list_notebooks`). The portal handles namespacing. Avoids redundancy when the server is already named `readwise`.

**Alternative considered**: kebab-case like mcp-things (`get-tasks`, `capture-task`). Rejected because mcp-siyuan (our most recent and cleanest reference) uses snake_case, and Python function names are naturally snake_case.

### 4. Response models join book metadata into highlights

Every highlight response includes `book_title`, `book_author`, and `source_url` inline — not just `book_id`. This is the single highest-value ergonomic decision from the MCP tool reviewer. It eliminates the most common follow-up call pattern.

**Why**: Without this, the LLM calls `search_highlights` then immediately calls `get_book` for each result to learn titles. With joined metadata, a single tool call is self-contained.

**Implementation**: The `ReadwiseClient` fetches book metadata and caches it per-session. The highlight response model includes the joined fields.

### 5. Pagination envelopes on all list/search results

All tools that return lists use a standard envelope:
```python
class PaginatedResult(BaseModel):
    results: list[T]
    total: int
    next_page: Optional[int] = None      # for page-based (v2 API)
    next_cursor: Optional[str] = None     # for cursor-based (export, v3)
```

**Why**: Without `total`, the LLM cannot determine if it has seen everything. Without `next_page`/`next_cursor`, it cannot paginate. Both are critical for LLM autonomy.

### 6. Search tool with `search_type` parameter defaulting to hybrid

`search_highlights` accepts `search_type: Literal["semantic", "fulltext", "hybrid"]` defaulting to `"hybrid"`. This maps to the Readwise MCP search endpoint which supports vector and full-text search.

**Why hybrid default**: Removes the burden of choosing from the LLM. Most queries benefit from both signals. The LLM can still narrow to `semantic` or `fulltext` when it knows what it wants.

### 7. Single `tag_highlight` tool with `action` parameter

Instead of separate `add_tag_to_highlight` and `remove_tag_from_highlight` tools, use one tool with `action: Literal["add", "remove"]`.

**Why**: Operations are mirror-symmetric. One tool with an action param is easier for the LLM to discover and reduces tool count. Pattern validated by MCP tool reviewer.

### 8. Config via pydantic-settings matching mcp-siyuan

```python
class Settings(BaseSettings):
    readwise_token: SecretStr           # X-Access-Token for Readwise API
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    mcp_api_key: str = ""               # Bearer token for MCP Portal auth
    readwise_base_url: str = "https://readwise.io"
```

**Why SecretStr for token**: Prevents accidental logging of credentials. Same pattern as mcp-siyuan's `siyuan_token`.

### 9. Docker: python:3.12-slim, non-root user, health check

Standard Dockerfile matching mcp-siyuan:
- `python:3.12-slim` base
- `pip install --no-cache-dir .` (no dev deps in image)
- Non-root `mcp` user
- Health check hitting `/mcp` endpoint
- Internal port 8000

### 10. Komodo stack deployment

`komodo.toml` matching mcp-siyuan pattern:
- Git-based deployment from `CaseyRo/mcp-readwise`
- Environment variables: `READWISE_TOKEN`, `MCP_API_KEY`, public URL
- Tags: `["mcp"]`
- Server: `ubuntu-smurf-mirror`

## Risks / Trade-offs

**[Readwise API rate limits]** The Readwise API has undocumented rate limits. With 15 tools, aggressive LLM usage could hit them.
-> Mitigation: Centralized exponential backoff in `client.py`. Return clear error messages so the LLM can wait and retry.

**[Book metadata caching for joined responses]** Fetching book details for every highlight search adds latency and API calls.
-> Mitigation: In-memory book metadata cache in the client (LRU, 15-minute TTL). Books change rarely. Cache miss only on first access.

**[Breaking change for existing users]** Anyone using the current Node.js server will need to reconfigure entirely.
-> Mitigation: This server has minimal external users (internal CDIT use). Document the migration clearly in README.

**[Reader API (v3) may have different auth or rate limits]** The Reader API is newer and may behave differently.
-> Mitigation: Use the same `X-Access-Token` header (confirmed by Readwise docs). Add separate error handling for v3-specific errors in client.

**[Full TypeScript removal loses git history context]** Deleting all TS files makes blame/history harder.
-> Mitigation: Git history is preserved. The old code is simple enough that no one will need to reference it after migration.

## Migration Plan

1. Create the full Python package structure alongside existing Node.js code
2. Implement and test the Python server locally
3. Remove all Node.js files (`src/`, `package.json`, `tsconfig.json`, etc.)
4. Update Docker files (new `Dockerfile`, `compose.yaml`, remove old)
5. Create `komodo.toml` for Komodo deployment
6. Update Cloudflare MCP Portal configuration
7. Deploy and verify via Cloudflare Portal
8. Update README and create SiYuan standards doc

**Rollback**: Revert to the previous git commit. The Node.js server can be restored from git history at any point.
