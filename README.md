# mcp-readwise

MCP server for [Readwise](https://readwise.io) built on [FastMCP](https://github.com/prefecthq/fastmcp). Provides 17 tools covering highlights, books, tags, Reader documents, and bulk export.

## Installation

```bash
uv sync
```

Or with pip:

```bash
pip install .
```

## Configuration

Set the following environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `READWISE_TOKEN` | Yes | - | Readwise API access token |
| `TRANSPORT` | No | `stdio` | Transport mode: `stdio` or `http` |
| `HOST` | No | `127.0.0.1` | HTTP server host |
| `PORT` | No | `8000` | HTTP server port |
| `MCP_API_KEY` | No | - | Bearer token for MCP Portal auth |
| `READWISE_BASE_URL` | No | `https://readwise.io` | Readwise API base URL |

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

### Highlights

| Tool | Description |
|------|-------------|
| `search_highlights` | Search using semantic, full-text, or hybrid mode |
| `list_highlights` | List with filters (book, tag, date) and pagination |
| `get_highlight` | Get by ID with book metadata |
| `create_highlight` | Create on a book with optional note/tags |
| `update_highlight` | Update text or note |
| `delete_highlight` | Delete by ID |
| `export_highlights` | Bulk export with cursor pagination |

### Books

| Tool | Description |
|------|-------------|
| `list_books` | List with category/source/annotation filters |
| `get_book` | Get by ID |

### Tags

| Tool | Description |
|------|-------------|
| `list_tags` | List all tags |
| `create_tag` | Create a new tag |
| `delete_tag` | Delete by ID |
| `tag_highlight` | Add or remove a tag on a highlight |

### Reader

| Tool | Description |
|------|-------------|
| `list_documents` | List Reader docs with location/category filters |
| `get_document` | Get by ID with full content |
| `save_url` | Save a URL to Reader |
| `update_progress` | Update reading progress (0.0-1.0) |

## Project Structure

```
mcp_readwise/
  server.py      # FastMCP app, tool registration, entry point
  config.py      # pydantic-settings configuration
  client.py      # Centralized httpx client (auth, retries, rate limits)
  auth.py        # Bearer token verifier for MCP Portal
  models/        # Pydantic response models
  tools/         # Tool functions by domain
```

## Deployment

Deployed via Komodo to `ubuntu-smurf-mirror`, accessible through Cloudflare MCP Portal at `mcp-readwise.cdit-dev.de`.

## License

MIT
