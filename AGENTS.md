# AGENTS.md

## Project Overview
- **mcp-readwise**: Python FastMCP server providing MCP access to Readwise highlights, books, tags, and Reader documents
- **Tech Stack**: Python 3.12, FastMCP 3.x, httpx, Pydantic, pydantic-settings
- **Deployment**: Docker (python:3.12-slim) -> Komodo -> Cloudflare MCP Portal

## Project Structure
```
mcp_readwise/
  server.py      # FastMCP app, tool registration, main()
  config.py      # Settings via pydantic-settings
  client.py      # Centralized httpx client (auth, retries, rate limits)
  auth.py        # BearerTokenVerifier for MCP Portal
  models/        # Pydantic response models (highlights, books, tags, reader)
  tools/         # Tool functions by domain (highlights, books, tags, reader, export)
```

## Conventions
- Tool names: snake_case, no server prefix (Cloudflare Portal namespaces automatically)
- All tools are async functions
- Response models join book metadata into highlight responses
- List tools return pagination envelopes with `total` and `next_page`/`next_cursor`
- Literal types for all categorical parameters
- Upper-bounded limits on all paginated queries (max 100)

## Development
```bash
READWISE_TOKEN=your_token uv run mcp-readwise          # stdio mode
READWISE_TOKEN=your_token TRANSPORT=http uv run mcp-readwise  # HTTP mode
```

## Testing
```bash
uv run pytest
```

## Docker
```bash
docker compose up -d    # requires READWISE_TOKEN in .env
```

## API Endpoints
- Readwise v2 API (readwise.io/api/v2/) — highlights, books, tags, export
- Readwise Reader v3 API (readwise.io/api/v3/) — Reader documents
- Auth: `Authorization: Token <READWISE_TOKEN>` header on all requests
