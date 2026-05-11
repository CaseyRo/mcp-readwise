# mcp-readwise

MCP server for [Readwise](https://readwise.io) built on [FastMCP](https://github.com/prefecthq/fastmcp). Two engagement-aware read tools (`reading_status`, `writing_material`) plus the standard write surface — 11 tools total.

## What's different in v0.4.0

The previous endpoint-shaped surface (17 tools mirroring Readwise's REST API) is gone. The new surface is intent-shaped and built on a per-source **engagement score** that joins your Readwise v2 books with their Reader v3 documents, so books and articles, finished and saved, recent and legacy, all sit on one comparable axis.

Two read tools cover everything:

- `reading_status` — orient on what you've been reading. Returns recent activity, top engaged sources, durable evergreen interests, current attention, items languishing in your "junk drawer," and corpus-shape stats. One call, no fan-out.
- `writing_material` — pull material for drafting. Source-first (give it a `book_id` / `document_id` / `title_search`) or topic-first (give it a `topic`). Filters by an engagement floor so you only see sources you've actually engaged with.

The legacy primitives (`list_books`, `list_highlights`, `search_highlights`, etc.) are no longer registered as MCP tools. Their client functions remain available internally for the engagement module.

## Installation

```bash
uv sync
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `READWISE_TOKEN` | Yes | - | Readwise API access token |
| `TRANSPORT` | No | `stdio` | Transport mode: `stdio` or `http` |
| `HOST` | No | `127.0.0.1` | HTTP server host |
| `PORT` | No | `8000` | HTTP server port |
| `MCP_API_KEY` | No | - | Bearer token for MCP Portal auth |
| `READWISE_BASE_URL` | No | `https://readwise.io` | Readwise API base URL |
| `ENGAGEMENT_INDEX_TTL_SECONDS` | No | `1800` | How long the engagement index is cached (default 30 min) |
| `ENGAGEMENT_TAG_DENYLIST` | No | (built-in) | Comma-separated tag names to exclude from the annotation bonus. Empty = use defaults (h1–h6, .h1, .h2, discard, favorite, color names) |

Get your Readwise access token at: https://readwise.io/access_token

## Usage

### Local (stdio)

```bash
READWISE_TOKEN=your_token uv run mcp-readwise
```

### HTTP mode

```bash
READWISE_TOKEN=your_token TRANSPORT=http uv run mcp-readwise
```

### Docker

```bash
cp .env.example .env  # Add your READWISE_TOKEN
docker compose up -d
```

## Available Tools

### Read (engagement-aware)

| Tool | Description |
|------|-------------|
| `reading_status` | Single-call snapshot — recent activity, evergreen top, current attention, junk drawer, signal density. Accepts `window_days` (default 7) and `week_offset` (default 0). |
| `writing_material` | Bundle highlights for drafting. Accepts exactly one of: `book_id`, `document_id`, `title_search`, `topic`. Filters by `min_engagement` (default 0.7). Source-first returns up to 200 highlights; topic-first returns up to 30 across multiple sources. |

### Write

| Tool | Description |
|------|-------------|
| `create_highlight` | Create a highlight on a book with optional `note` / tags |
| `update_highlight` | Update text or `note` |
| `delete_highlight` | Delete by ID |
| `save_url` | Save a URL to Reader (uses singular `note`) |
| `update_progress` | Update reading progress (0.0–1.0) |

### Tags

| Tool | Description |
|------|-------------|
| `list_tags` | List all user-created custom tags |
| `create_tag` | Create a new tag |
| `delete_tag` | Delete a tag by ID |
| `tag_highlight` | Add or remove a tag on a highlight |

## How the engagement score works (high level)

Every source — book or article, Reader-imported or legacy Kindle — gets a vector engagement score:

- **`raw`** ranks "current attention" (recency-weighted)
- **`intensity`** ranks "evergreen interests" (recency removed; pure depth)
- **`recency`** is a small tweak based on how recently the source was highlighted
- **`return_strength`** captures multi-year highlight clusters and recent Reader re-opens

The score is built from a layered sum of:

1. **Base layer** — what kind of engagement is this? `legacy` (v2-only Kindle/iBooks book), `highlighted` (Reader-era with any highlight), `finished_no_hl`, `reading`, `saved_warm`, `saved_cold`.
2. **Density** — how many highlights does this source have? More highlights = deeper engagement.
3. **Recency** — when was the last highlight? Within 30 days adds a bonus; older than 5 years subtracts a small amount.
4. **Annotation** — does any highlight carry a user note, a non-structural tag, or `is_favorite`?
5. **Return signal** — multi-year highlight clusters (you came back to this book years later) and Reader-era reopens (you opened this article today after first opening it months ago).

See `openspec/changes/workflow-shaped-tools/design.md` for the full formula and decision rationale.

## Health endpoint

```
GET /health
```

Returns build identifier, git commit, uptime, registered tool count, and engagement index status (last build time, source count, cache age).

## Project Structure

```
mcp_readwise/
  server.py        # FastMCP app, tool registration, /health
  config.py        # pydantic-settings configuration
  client.py        # Centralized httpx client (auth, retries, rate limits)
  auth.py          # Bearer token verifier for MCP Portal
  engagement.py    # The engagement index + scoring formula (load-bearing)
  models/
    source.py      # Source + EngagementScore (the unified model)
    status.py      # ReadingStatus + sub-models
    writing.py     # WritingMaterial + HighlightInMaterial
    reader.py      # ReaderDocument with derived reading_status
    books.py       # BookResult (used internally by engagement)
    highlights.py  # HighlightResult, ExportResult
    tags.py        # Tag models
  tools/
    status.py      # reading_status (registered MCP tool)
    writing.py     # writing_material (registered MCP tool)
    highlights.py  # CRUD + search (only CRUD registered as MCP tools)
    reader.py      # save_url, update_progress, etc.
    books.py       # list_books, get_book (internal, not MCP-registered)
    tags.py        # tag CRUD + tag_highlight
    export.py      # bulk export (internal, not MCP-registered)
```

## Deployment

Deployed via Komodo to `ubuntu-smurf-mirror`, accessible through Cloudflare MCP Portal at `mcp-readwise.cdit-dev.de`.

## License

MIT
