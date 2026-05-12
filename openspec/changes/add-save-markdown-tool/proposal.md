## Why

Readwise Reader is the user's long-form reading queue. Today, the only way to push handwritten content into it is the email-to-Reader fallback or the browser extension on rendered HTML — both manual, neither composable from agents. The user routinely produces markdown (notes, drafts, briefings, distilled web reading) that would benefit from sitting in the Reader queue alongside saved articles, but there's no programmatic path for "I have this markdown blob, put it in Reader and give me back the document URL."

The original framing of this work imagined a folder-watcher service converting `.md` → `.epub` and uploading the EPUB. An API audit before implementation surfaced two facts that reshape the design:

1. **Readwise Reader has no file upload endpoint.** `POST /api/v3/save/` accepts `url` or `html` — no multipart, no EPUB. The full EPUB path was a dead end.
2. **The `category` field controls the Reader UX**, not the file format. Posting clean HTML with `category="epub"` yields the long-form chapter-style reader view; posting it with `category="article"` yields the article view. The "make it feel like a book" goal is settled by one field, not by producing an actual EPUB.

This collapses the original three-component vision (folder + pandoc + uploader) into a single MCP tool. The folder-watcher remains valid as a *separate downstream service* that would call this tool — but it's out of scope for mcp-readwise and out of scope for this change.

## What Changes

### New tool (additive — no breaking changes)

- **NEW** `save_markdown(markdown: str, title=None, author=None, summary=None, tags=None, location="new", category="epub", published_date=None, note=None) → ReaderDocument`
  - Accepts a markdown string. Parses YAML frontmatter if present.
  - Renders markdown → clean HTML via the `markdown` library with the `extra`, `footnotes`, `sane_lists`, `tables`, `smarty` extensions.
  - Title resolution chain: explicit param > frontmatter `title` > first `# H1` in the markdown body > `"Untitled"`.
  - Author, summary, tags, published_date follow the same explicit > frontmatter chain.
  - Generates a stable synthetic URL: `https://mcp-readwise.local/md/<sha1[:16]>` derived from `(title, body[:512])` so re-uploads of the same content produce the same URL — Reader will then update-in-place rather than duplicate.
  - POSTs to `/api/v3/save/` with `should_clean_html=False` to preserve our rendered structure, and the resolved metadata.
  - Returns the `ReaderDocument` for the newly created (or updated) Reader entry — same shape as `save_url`.

### Dependencies

- Add `markdown>=3.7` (Apache 2.0, pure-Python; the standard markdown renderer) to `pyproject.toml`.
- No frontmatter library — implement a 20-line YAML-or-plain frontmatter parser inline. The frontmatter we need to parse is constrained (scalar fields only); pulling `python-frontmatter` + `PyYAML` to handle a known-shape parse is overkill.

### Hygiene

- `/health` `tools` count goes from 11 → 12.
- Bump `__version__` and `pyproject.toml` version to `0.5.0` (additive minor — no breaking removal of read primitives this time).
- README gets a `save_markdown` section under "Tools" with an example payload.

## Capabilities

### New Capabilities

- **`save-markdown`**: A single tool that turns a markdown blob into a Readwise Reader document with full frontmatter support, stable synthetic URLs for idempotent re-upload, and `category="epub"` defaulting for the long-form reader UX. Encapsulates the markdown → HTML render, metadata resolution, and Reader API call in one tool call — no fan-out, no temp files, no filesystem dependency.

### Modified Capabilities

None.

## Impact

- **Code**: One new tool module (`mcp_readwise/tools/markdown.py`), one new helper module (`mcp_readwise/markdown_render.py`) for the render + frontmatter + URL hash logic, server.py registration, README update.
- **Dependencies**: `markdown>=3.7` added. No system packages required (no pandoc).
- **APIs (Readwise)**: One additional `POST /api/v3/save/` call per invocation. No new auth scope, no new endpoints.
- **Container**: Image size unchanged (`markdown` is ~150KB pure-Python).
- **Clients**: Purely additive — existing 11 tools unchanged. The `save_url` tool stays put; `save_markdown` is its sibling for owned content.
- **Out of scope**: Folder watcher, pandoc, real EPUB generation, MD file path inputs (string content only for now), batch uploads. All can layer on later without modifying this tool.
