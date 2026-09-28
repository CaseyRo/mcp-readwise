# mcp-readwise

MCP server for [Readwise](https://readwise.io) and Readwise Reader, built on [FastMCP](https://github.com/prefecthq/fastmcp). Engagement-aware reads, the few write tools the official Readwise connector lacks, and one thing you can't easily do anywhere else: **turn a markdown blob into a real, brand-styled EPUB and have it land in your Reader Library a minute later.**

It is for Readwise users who work with Claude or another MCP client and want their reading history, engagement signals and long-form drafts to flow into Reader without copy and paste. It is designed to run next to the official Readwise connector, not to replace it.

10 tools, 2 prompts, 6 resources. Python 3.11+, FastMCP 4. Runs over stdio for a local client or as an HTTP server in Docker.

## Scope: what this server adds over the official connector

The official claude.ai Readwise connector covers Reader search/list/create/move/tags, highlight CRUD and highlight tags, highlight vector search and daily review. Use it for those. This server keeps only what the connector lacks:

- **EPUB delivery** — `save_markdown_as_epub` + `verify_epub_received` (real EPUB 3 via the email-to-library path).
- **Branded render** — `save_markdown` (frontmatter + CDIT-styled HTML).
- **Engagement-scored reads** — `reading_status`, `writing_material`.
- **Reading progress** — `update_progress`.
- **By-URL lookup** — `reader_get_by_url` (canonicalized exact source-URL match; the connector has no URL filter).
- **v2 tag management** — `create_tag` / `delete_tag`, plus `list_tags` as the only source of the v2 tag ids `delete_tag` needs.

## Why this exists

The most common source of "long markdown that needs a reading home" in 2026 is **research output from Claude, OpenAI, and other agent loops**. Deep-research mode produces 3000–8000 word briefs in a single tool turn. They arrive as markdown in a chat window, and they shouldn't stay there — they want chapter navigation, a TOC sidebar, downloadable export to a Kobo / Boox / Kindle, and most often **the Readwise iOS and iPad apps**, which are quietly the best long-form reading and highlighting clients on those devices.

This MCP server is the transporter for that markdown into Reader. An agent calls `save_markdown_as_epub`, the EPUB appears in your Library a minute later, and the chat window is no longer your reading place.

## The niche-but-nice part: markdown → real EPUB in Reader

![EPUB rendered by save_markdown_as_epub, opened in Readwise Reader. The CDIT brand stylesheet survives Reader's renderer: Strong Blue H1 underlines, Inter typography, the mint-rail "Note" preface block from the frontmatter `note:` field, and Reader's own TOC sidebar listing the auto-generated chapters.](docs/screenshots/v0.6.0-epub-in-reader.png)

Readwise's Reader API has no file-upload endpoint — I verified this against their v3 docs *and* their own official CLI, which doesn't expose one either. The closest thing the API offers is "save URL" or "save HTML." Neither produces a true EPUB in Reader, which is the format with proper chapter nav, TOC, and downloadable export to Kobo / Boox / Kindle.

The one path that *does* produce a real EPUB is the email-to-library mechanism: every Reader account has a `<custom>@library.readwise.io` address that accepts EPUB attachments and ingests them properly. So `save_markdown_as_epub` automates that path:

```
markdown blob → pandoc renders to EPUB 3 (with CDIT brand styling)
             → aiosmtplib delivers via Resend SMTP
             → email lands at <custom>@library.readwise.io
             → Readwise ingest pipeline picks it up (1–5 min)
             → real EPUB appears in Library
```

The tool returns immediately after SMTP delivery — the ingest is async by nature. A companion tool `verify_epub_received` polls Reader to confirm the document landed, with time-aware retry guidance baked into the response so an LLM caller knows when to retry vs. when to surface a failure.

### Setup

Three environment variables, all required (the server still boots without them — only `save_markdown_as_epub` refuses to run; every other tool, including `verify_epub_received`, works normally):

```bash
# Your custom Readwise Library email
# Find at: read.readwise.io → Account → Personalize email addresses
# Bearer credential — rotate via Readwise if it leaks.
READWISE_LIBRARY_EMAIL=your-name@library.readwise.io

# Resend API key, used as SMTP password (username is literal "resend")
RESEND_API_KEY=re_…

# Verified sender registered in Resend
EPUB_FROM_ADDRESS=reader@example.com
```

### Calling it

```python
# From any MCP client (Claude, agents, scripts):
result = save_markdown_as_epub(
    markdown="""---
    title: Q2 Planning Brief
    author: Casey
    tags: [planning, brief]
    note: Context for the team — read this before Thursday's call.
    ---
    # Background
    ...
    """,
    idempotency_key="brief-2026-q2-v1",  # optional — collapses retry duplicates
)
# → EpubSendResult(title=..., accepted_at=..., recipient=...,
#                  identifier_scheme="x-mcp-readwise-idempotency", ...)

# Wait 1–2 minutes, then:
verify = verify_epub_received(title=result.title, since=result.accepted_at)
# → VerifyResult(found=True, document=ReaderDocument(...),
#                note="Found in Reader Library.")
```

The docstring leads with the async contract loudly so LLM agents reading the schema know not to tell the human "done" until `verify_epub_received` confirms.

### Brand stylesheet (CDIT)

EPUB output is styled by a hand-tuned CSS at `mcp_readwise/assets/epub/cdit-style.css`, inheriting the palette from [cdit-works.de](https://cdit-works.de):

- Carbon `#272f38` (body text), Cloud Dancer `#f0eee9` (page background)
- Strong Blue `#1f5da0` (links, H1 underline), Mint `#5cc6c3` (blockquote rail, Note preface)
- Inter weights 400 / 700 / 800 embedded as static woff2 subsets (latin + latin-ext, ~170KB)
- Headings deliberately diverge from the website's display face: chapter heads use Inter weight 800 with tracking `-0.02em`, **not** League Gothic — condensed display fonts fatigue across long-form chapter breaks
- `body { line-height: 1.7; text-align: left; hyphens: auto; }` tuned for sustained reading

To customize, fork the CSS file. It's a first-class editable asset, not generated from Python.

### Frontmatter

Both `save_markdown` and `save_markdown_as_epub` accept YAML frontmatter for self-describing markdown:

```markdown
---
title: My Note
author: Casey
summary: A brief description.
tags: [research, draft]
note: Context for the reader.
published_date: 2026-05-11
image_url: https://example.com/cover.jpg
---
# Body starts here

Content with **markdown** features — tables, footnotes, fenced code, smart quotes
all render properly through the `extra` + `sane_lists` + `smarty` extensions.
```

**Title resolution** (first non-empty wins): explicit `title=` param → frontmatter `title:` → first `# H1` in body → `"Untitled"`. Same precedence for other fields (without the H1 fallback).

### Limits

- EPUB ceiling: **20 MiB raw binary** (Readwise's email ingest caps at 30 MB; base64 inflates ~33%, MIME adds ~1 MB, so 20 MiB fits with margin). Larger EPUBs raise `EpubTooLargeError` before SMTP.
- Pandoc binary in the Docker image: ~150 MB. Accepted cost.
- Inline images in markdown must use absolute HTTPS URLs — pandoc fetches them at build time; relative paths don't resolve.

## The other 8 tools

### Read (engagement-aware)

These two collapsed an earlier 7-tool read surface into intent-shaped calls. They're built on a per-source **engagement score** that joins Readwise v2 books with their Reader v3 documents, so books and articles, finished and saved, recent and legacy, all sit on one comparable axis.

| Tool | Description |
|------|-------------|
| `reading_status` | Single-call snapshot — recent activity, evergreen top, current attention, junk drawer, signal density. Accepts `window_days` (default 7) and `week_offset` (default 0). |
| `writing_material` | Bundle highlights for drafting. Source-first (`book_id` / `document_id` / `title_search`) or topic-first (`topic`). Filters by `min_engagement` floor (default 0.7). |

### Read (direct Reader lookup)

This bypasses the engagement cache to look up a document anywhere in the Reader library (e.g. archived docs the cache doesn't surface).

| Tool | Description |
|------|-------------|
| `reader_get_by_url` | Look up a single Reader document by its source URL. |

### Write

| Tool | Description |
|------|-------------|
| `save_markdown` | Save a markdown blob to Reader as rendered HTML with `category="epub"` UI hint. Synchronous, returns `ReaderDocument`. Use this for lightweight notes you don't need as a real EPUB. |
| `save_markdown_as_epub` | The real-EPUB-via-email path described above. Async, returns `EpubSendResult`. |
| `verify_epub_received` | Confirm a `save_markdown_as_epub` send has landed. Time-aware retry guidance in the response `note`. |
| `update_progress` | Update reading progress (0.0–1.0). |

### Tags

| Tool | Description |
|------|-------------|
| `list_tags` | List user-created custom tags (with the ids `delete_tag` needs). |
| `create_tag` / `delete_tag` | Tag create/delete. |

### Ways to save your own content into Reader

| You want | Use | Sync / Async | Fidelity | Setup |
|---|---|---|---|---|
| Save a URL (Readwise fetches & parses) | official connector `reader_create_document` | sync | HTML article | none |
| Save markdown as HTML with epub-UX hint | `save_markdown` | sync | HTML with `category="epub"` | none |
| Save markdown as a real EPUB book | `save_markdown_as_epub` | **async** (1–5 min) | true EPUB 3 with TOC, chapter nav, brand styling | three env vars |

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- A Readwise access token ([get one](https://readwise.io/access_token))
- [Pandoc](https://pandoc.org), only for `save_markdown_as_epub` (included in the Docker image)
- For the EPUB path: an SMTP account (Resend by default) with a verified sender address

## Installation and running

```bash
git clone https://github.com/CaseyRo/mcp-readwise.git
cd mcp-readwise
uv sync

# stdio (default), for a local MCP client
READWISE_TOKEN=... uv run mcp-readwise

# streamable HTTP on HOST:PORT, path /mcp
READWISE_TOKEN=... MCP_API_KEY=... TRANSPORT=http uv run mcp-readwise
```

For local development install Pandoc with your package manager (for example `brew install pandoc`). The other tools work without it.

### Docker

```bash
cp .env.example .env   # fill in the values
docker compose up -d --build
```

`compose.yaml` builds the image from source, runs with `TRANSPORT=http` and publishes the server on host port 8010. `GIT_COMMIT` and `APP_VERSION` can be passed as build args so `/health` reports the running build.

## Configuration

All settings are environment variables (see `.env.example`).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `READWISE_TOKEN` | Yes | (empty) | Readwise API access token |
| `MCP_API_KEY` | When `TRANSPORT=http` | (empty) | Bearer token clients must send; the server refuses to start in HTTP mode without it |
| `TRANSPORT` | No | `stdio` | `stdio` or `http` |
| `HOST` | No | `127.0.0.1` | HTTP bind address |
| `PORT` | No | `8000` | HTTP port |
| `READWISE_BASE_URL` | No | `https://readwise.io` | Readwise API base URL |
| `ENGAGEMENT_INDEX_TTL_SECONDS` | No | `14400` | TTL for the engagement index cache (4 hours) |
| `ENGAGEMENT_TAG_DENYLIST` | No | (built-in) | Comma-separated tags excluded from the annotation bonus |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| **EPUB sender (optional, but all three required together)** ||||
| `READWISE_LIBRARY_EMAIL` | Only for `save_markdown_as_epub` | (empty) | Your `<custom>@library.readwise.io` |
| `RESEND_API_KEY` | Only for `save_markdown_as_epub` | (empty) | SMTP password (Resend API key by default) |
| `EPUB_FROM_ADDRESS` | Only for `save_markdown_as_epub` | (empty) | Verified sender address |
| `SMTP_HOST` | No | `smtp.resend.com` | Override to use Postmark, SES, etc. |
| `SMTP_PORT` | No | `587` | |
| `EPUB_LANG` | No | `en` | EPUB OPF `dc:language` metadata |
| `EPUB_MAX_BYTES` | No | `20971520` | 20 MiB ceiling before send |
| **Build metadata (optional)** ||||
| `GIT_COMMIT` | No | `unknown` | Commit reported by `/health` |
| `APP_VERSION` | No | package version | Release version reported by `/health` |

## Authentication

In stdio mode there is no server-side auth; the client that starts the process owns it. In HTTP mode every request to `/mcp` must carry `Authorization: Bearer <MCP_API_KEY>`. The key is compared in constant time. Put the server behind TLS (a reverse proxy or tunnel) before exposing it beyond localhost, and keep `MCP_API_KEY` and `READWISE_TOKEN` out of version control.

## Health endpoint

```
GET /health
```

Returns build identifier, git commit, uptime, registered tool count, engagement index status, and the `epub_sender` configured flags (without ever exposing the API key or library email in plaintext).

```json
{
  "status": "healthy",
  "version": "0.7.0",
  "build": "0.7.0+6ec5b6b",
  "tools": 10,
  "engagement_index": { "built": true, "source_count": 152, "age_seconds": 312 },
  "epub_sender": {
    "configured": true,
    "smtp_host": "smtp.resend.com",
    "smtp_port": 587,
    "from_address": "reader@example.com",
    "library_email_set": true
  }
}
```

## How the engagement score works

Every source — book or article, Reader-imported or legacy Kindle — gets a vector engagement score with four components:

- **`raw`** ranks "current attention" (recency-weighted overall score)
- **`intensity`** ranks "evergreen interests" (recency removed; pure depth)
- **`recency`** small modifier from how recently the source was last highlighted
- **`return_strength`** captures multi-year highlight clusters and recent Reader re-opens

Computed from a layered sum of:

1. **Base layer** — `legacy` (v2-only Kindle/iBooks book), `highlighted`, `finished_no_hl`, `reading`, `saved_warm`, `saved_cold`
2. **Density** — non-discarded highlight count
3. **Recency** — last-highlight age, banded (30d / 1y / 5y)
4. **Annotation** — does any highlight carry a user note, a non-structural tag, or `is_favorite`?
5. **Return signal** — multi-year highlight clusters AND/OR Reader-era reopens

See `openspec/changes/archive/2026-05-11-workflow-shaped-tools/design.md` for the full formula and decision rationale.

## Project structure

```
mcp_readwise/
  server.py             # FastMCP app, tool registration, /health
  config.py             # pydantic-settings configuration
  client.py             # Centralized httpx client (auth, retries, rate limits)
  auth.py               # Bearer token verifier for MCP Portal
  engagement.py         # The engagement index + scoring formula
  markdown_render.py    # Frontmatter parser + Markdown → HTML helper
  epub_render.py        # Pandoc wrapper + EPUB metadata builder
  smtp_client.py        # Async SMTP transport (aiosmtplib)
  assets/epub/          # CDIT brand stylesheet + embedded Inter woff2 subsets
  models/               # Pydantic response models
  tools/
    status.py, writing.py             # Engagement-aware reads
    markdown.py                       # save_markdown (HTML path)
    epub_sender.py, epub_verifier.py  # Real-EPUB-via-email path
    reader.py, tags.py                # Progress, by-URL lookup, v2 tags
```

## Telemetry

A vendored `usage.py` middleware writes one JSON line per tool call to stderr: server, tool, duration, outcome and protocol. Tool arguments are never logged. Tool failures are raised as `ToolError`, so clients receive a proper MCP error.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

CI (`.github/workflows/ci.yml`) runs the same lint and tests as the required `test` check. `main` is branch-protected, so changes land through a pull request. A separate security workflow runs dependency audits.

## Releases

Releases are tag-only. After a merge to `main`, `.github/workflows/release.yml` runs the tests and `pip-audit`, then pushes the next `vX.Y.Z` tag. Nothing is committed back to the branch and there are no version-bump commits; the git tag is the version. Deployments build the image from source.

## Support

If this server saves you time, you can [buy me a coffee](https://buymeacoffee.com/caseyberlin).

## License

MIT, see [LICENSE](LICENSE).
