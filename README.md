# mcp-readwise

MCP server for [Readwise](https://readwise.io) built on [FastMCP](https://github.com/prefecthq/fastmcp). Two engagement-aware read tools (`reading_status`, `writing_material`) plus the standard write surface — 14 tools total.

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
| `save_markdown` | Save a markdown blob to Reader as rendered HTML with `category="epub"` UI hint. Synchronous; returns `ReaderDocument`. See "Three ways to save owned markdown" below. |
| `save_markdown_as_epub` | Render markdown to a real EPUB 3 via pandoc (with CDIT brand styling) and email it to your Readwise Library address through a Resend SMTP relay. **Async** — returns `EpubSendResult` after SMTP delivery; document materializes in Reader in 1–5 minutes. Use `verify_epub_received` to confirm. Requires three env vars. |
| `verify_epub_received` | Confirm a `save_markdown_as_epub` send has landed in Reader. Pass `title` and `accepted_at` from the send result. Returns `VerifyResult` with time-aware retry guidance. |
| `update_progress` | Update reading progress (0.0–1.0) |

### Tags

| Tool | Description |
|------|-------------|
| `list_tags` | List all user-created custom tags |
| `create_tag` | Create a new tag |
| `delete_tag` | Delete a tag by ID |
| `tag_highlight` | Add or remove a tag on a highlight |

## Three ways to save owned content into Reader

| Want | Use | Sync/Async | Fidelity | Setup cost |
|------|-----|------------|----------|------------|
| Save a URL (Readwise fetches & parses) | `save_url` | sync | HTML article | none |
| Save your markdown as HTML with epub-UX hint | `save_markdown` | sync | HTML with `category="epub"` | none |
| Save your markdown as a real EPUB book | `save_markdown_as_epub` | **async** (1–5 min) | True EPUB 3 with TOC, chapter nav, CDIT brand styling | requires Resend + library email setup |

The Readwise Reader API has no file-upload endpoint (confirmed against the v3 API and their own official CLI). Real EPUB ingestion exists only via the email-to-library mechanism, which `save_markdown_as_epub` automates through Resend SMTP.

### save_markdown (HTML path)

`save_url` is for URLs Readwise fetches and parses. `save_markdown` is for content you already have as markdown — notes, drafts, distilled summaries — that you want sitting in Reader's queue with the long-form reader UX, but where you don't need the full EPUB experience (TOC, chapter nav, e-reader export).

1. Parses optional YAML frontmatter for metadata
2. Renders the body to clean HTML (`extra`, `sane_lists`, `smarty` extensions — tables, footnotes, fenced code, smart quotes)
3. POSTs to `/api/v3/save/` with `html=...`, `should_clean_html=false`, and `category="epub"` by default
4. Returns the resulting `ReaderDocument` synchronously

**Synthetic URL**: Reader requires a `url` field. The tool generates `https://mcp-readwise.local/md/<sha1(title + body[:512])[:16]>` so re-uploading identical content updates the same Reader entry. Filter Reader queries by this host prefix to find tool-uploaded content.

### save_markdown_as_epub (real EPUB path)

![EPUB rendered by save_markdown_as_epub, opened in Readwise Reader. The CDIT brand stylesheet survives Reader's renderer: Strong Blue H1 underlines, Inter typography, the mint-rail "Note" preface block from the frontmatter `note:` field, and Reader's own TOC sidebar listing the auto-generated chapters.](docs/screenshots/v0.6.0-epub-in-reader.png)

For when you want the content to actually be a book in Reader — TOC, chapter navigation, EPUB export to Kobo/Boox/Kindle. Renders the markdown through pandoc with the **CDIT brand stylesheet** (palette + typography baked in from cdit-works.de — see "Brand stylesheet" below) and emails the resulting EPUB as an attachment to your Readwise Library email through Resend SMTP.

**Setup** — three env vars required (server boots without them; other 13 tools keep working):

```bash
# Your custom Readwise Library email — find at:
# read.readwise.io → Account → Personalize email addresses
# This address is a bearer credential; rotate via Readwise if it leaks.
READWISE_LIBRARY_EMAIL=casey-personal@library.readwise.io

# Resend API key (used as SMTP password). From resend.com → API Keys.
RESEND_API_KEY=re_…

# Verified sender domain registered in Resend. Resend will reject sends
# from unverified domains.
# Must be on a verified Resend domain. For this project: cdit-dev.de.
EPUB_FROM_ADDRESS=mcp-readwise@cdit-dev.de
```

**Two-step flow** (chain `save_markdown_as_epub` → `verify_epub_received`):

```
save_markdown_as_epub(markdown=…) → EpubSendResult(title, accepted_at, …)
# wait 1–2 minutes
verify_epub_received(title=…, since=…) → VerifyResult(found=True, document=…)
```

The tool's docstring leads with the async contract loudly — LLM agents reading the schema before calling know not to tell the human "done" until `verify_epub_received` confirms ingest.

**Idempotency**: pass `idempotency_key="some-stable-string"` (e.g. SHA-256 of title+body, or a workflow ID). The EPUB's `dc:identifier` becomes `epub-key-<key>`, so retries with the same key collapse into one Library entry instead of duplicating. Omit for one-shot semantics (fresh UUID per call).

**Pandoc in the image**: the Docker image bakes in `pandoc` (~150MB) for EPUB generation. The cost is accepted as the price of admission for real EPUB output.

### Frontmatter (both tools)

```markdown
---
title: My Note
author: Casey
summary: A brief description.
tags: [research, draft]
note: Context from the author.
published_date: 2026-05-11
image_url: https://example.com/cover.jpg
---
# Body starts here

Content with **markdown** features.
```

**Title resolution** (first non-empty wins): explicit `title=` param → frontmatter `title:` → first `# H1` in body → `"Untitled"`. The same precedence applies to other fields (without the H1 fallback).

### Brand stylesheet

The EPUB output uses a hand-tuned CSS shipped at `mcp_readwise/assets/epub/cdit-style.css`, with the CDIT palette from cdit-works.de:

- Carbon `#272f38` (body text), Cloud Dancer `#f0eee9` (page background)
- Strong Blue `#1f5da0` (links, chapter underline), Mint `#5cc6c3` (blockquote rail)
- Inter weight 400 / 700 / 800 embedded as static woff2 subsets (latin + latin-ext, ~170KB)
- Heading typography deliberately diverges from the website: chapter heads use Inter weight 800 with tracking `-0.02em`, not League Gothic — condensed display fonts become fatiguing across long-form chapter breaks
- `body { line-height: 1.7; text-align: left; hyphens: auto; }` tuned for sustained reading rather than screen UI

To customize: fork `cdit-style.css` and override the brand variables. The CSS file is intentionally a first-class editable asset, not generated Python.

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
