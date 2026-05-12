## Context

mcp-readwise (v0.4.0) currently exposes 11 tools — 2 engagement-shaped reads (`reading_status`, `writing_material`), 4 highlight write/update tools, 4 tag tools, and `save_url` + `update_progress` on the Reader side. The Reader API surface is entered exclusively through `save_url` (URL-based, Reader fetches and parses).

The user wants a parallel write path for content they already own as markdown: notes, drafts, distilled summaries, briefings. The desired UX is "MCP call in → Reader document URL out." No filesystem, no async pipeline, no folder watcher inside mcp-readwise itself.

A pre-implementation API audit found:

1. `POST /api/v3/save/` accepts:
   - `url` (required) — synthetic OK (`https://yourapp.com#document1` per docs)
   - `html` (optional) — pre-rendered content; when present, server uses it directly
   - `should_clean_html` (bool) — when `true`, server scrapes title/author/strips chrome; default behavior when omitted with an HTML payload
   - `category` (string) — `article | email | rss | highlight | note | pdf | epub | tweet | video`; controls Reader UI
   - `location`, `title`, `author`, `summary`, `published_date`, `image_url`, `tags`, `notes`, `saved_using`
2. No file upload endpoint exists. No multipart endpoint. The doc explicitly says "The Reader API just supports saving new documents to Reader and fetching your documents."
3. The `category="epub"` setting is what gives the long-form reader UX. Reader does not validate that the HTML actually came from a real EPUB.

## Goals / Non-Goals

**Goals:**
- Single MCP tool call: markdown in, ReaderDocument out.
- Frontmatter support for embedded metadata so the markdown blob is self-describing.
- Stable synthetic URL hashing so re-uploads of identical content collapse into one Reader entry rather than duplicating.
- Long-form reader UX by default (`category="epub"`).
- Zero new system dependencies (no pandoc binary).

**Non-Goals:**
- Not parsing or accepting `.md` file paths. The MCP tool takes a markdown string. Callers (folder watcher service, CLI, agent) handle file IO.
- Not converting to a real EPUB binary. The Reader API can't ingest one, so there's no point.
- Not supporting batch uploads. One markdown blob per call. Iteration is the caller's job.
- Not building a folder watcher / inotify service. That's a separate downstream component.
- Not supporting embedded images by reference (`![](./local.png)`). The Reader save API has `image_url` for a single cover image (handled via frontmatter) but inline images need absolute HTTP URLs in the source markdown. Validation of inline image URLs is the caller's responsibility.

## Decisions

### D1: Render via the `markdown` library, not pandoc

The original vision assumed pandoc → EPUB. With EPUB off the table, the only conversion needed is markdown → HTML. The `markdown` library (Python Software Foundation; pure-Python; ~150KB) covers everything the user writes:

- `extra` → tables, footnotes, definition lists, fenced code, abbreviations, attribute lists
- `sane_lists` → consistent list parsing
- `smarty` → typographic quotes / dashes
- `codehilite` (optional, behind a config flag) → server-side syntax highlighting

Pandoc would add a ~150MB system binary to the container and a `pypandoc` Python wrapper for marginal gain over what Reader's renderer does anyway after ingestion. Rejected.

**Alternatives considered:**
- `mistune` — faster, more permissive footnote handling. Rejected: `markdown` is the established Python markdown lib with the best documentation and is what most agents will recognize.
- Raw regex / hand-rolled. Rejected: footnotes alone are non-trivial, and we'd ship subtle parsing bugs.

### D2: Frontmatter parsing — inline, not via `python-frontmatter`

Frontmatter we care about is YAML-shaped but tightly constrained: `title: str`, `author: str`, `summary: str`, `tags: list[str]`, `published_date: ISO-8601`, `image_url: url`. No nested structures, no anchors, no flow-style edge cases.

A 30-line parser that:
1. Detects `---\n` at line 1
2. Reads until the second `---\n`
3. Parses `key: value` pairs, with `[...]` for list-of-strings and bare strings otherwise
4. Returns `(metadata_dict, body_str)`

…replaces a dependency on PyYAML (which `python-frontmatter` pulls in). PyYAML's full parser is overkill and has historically been a CVE source. Rejected.

If users provide invalid frontmatter, we fall back to treating the whole content as body — no error. The frontmatter parse is a convenience feature, not a contract.

### D3: Title resolution chain

Source order (first non-empty wins):
1. Explicit `title=` parameter
2. Frontmatter `title:` field
3. First `# H1` in the body (regex: `^# (.+)$` on first 50 lines, take first match, strip)
4. Literal `"Untitled"`

This matches user expectation: if I pass `title=`, you respect it; if my markdown has a frontmatter title or H1, you use it; otherwise don't fail.

Same chain applies to `author`, `summary`, `tags`, `published_date`, `image_url` (without the H1 fallback — H1 is title-only).

### D4: Synthetic URL — stable hash of (title, body[:512])

The Reader API requires a `url` field. For owned markdown there is no canonical URL. We could:

1. **Use a random UUID per call.** Every re-upload produces a new Reader document; duplicates pile up. Rejected.
2. **Use a hash of the full body.** Idempotent on identical content. But editing a typo and re-uploading produces a new doc. Reasonable middle ground; chosen.
3. **Use a caller-provided `source_url` parameter.** Adds a parameter most callers won't set sensibly. Deferred — can be added later without breaking the signature.

The chosen form: `https://mcp-readwise.local/md/<sha1(title + body[:512])[:16]>`. SHA1 (truncated, non-cryptographic use), 16 hex chars = ~10^19 namespace. Collisions are not a security concern; they'd produce update-in-place which is the desired behavior on near-identical content anyway.

The `mcp-readwise.local` host is intentionally non-routable — it's a marker, not a real URL. Readwise stores it as `source_url` on the resulting document; users can filter Reader queries by it to find tool-uploaded content.

### D5: `category="epub"` default; `should_clean_html=False` always

The category default is `epub` because the user's framing was "I want it to feel like a book in Reader." Callers can override (`category="article"` for a short note, `category="note"` for a snippet). The Literal type accepts the same set as `list_documents`.

`should_clean_html=False` is hard-coded — we've already produced clean structural HTML; letting Reader strip "chrome" risks losing legitimate content (footnote markers, code blocks, definition lists).

### D6: No HTML sanitization beyond what `markdown` produces

`markdown` does not execute JavaScript, does not pass through `<script>` by default (well, it depends on config; we explicitly do not enable raw HTML escaping). We use `safe_mode=False` (the default — preserves inline HTML the user wrote intentionally) but rely on Reader's own sanitization at ingest. If the user wants raw HTML in their markdown (e.g., `<details>`), it goes through.

**Risk accepted**: if a user pastes hostile markdown into this tool, Reader's ingest pipeline is the sanitizer. We are not in the security boundary here — the user controls both ends of the wire. If this tool were ever exposed to untrusted markdown input, we'd add `bleach` and an allowlist. Out of scope for v1.

### D7: Tool registration ordering

Register `save_markdown` next to `save_url` in `server.py` — they are siblings in semantic surface area. Update the `tools` count in `/health` from 11 to 12.

## Risks / Trade-offs

- **The synthetic URL collides for two genuinely different documents with the same title + first 512 chars.** Unlikely in practice; if it happens, the user re-uploads with a more distinct title or accepts that one will overwrite the other. Acceptable.
- **Reader's `category="epub"` UX might not feel exactly like a real EPUB.** It's the closest available — chapters from `<h2>`s, long-form view, no article-style header. If users report it's not enough, we'd need to escalate to the email-to-Reader path, which requires SMTP setup outside mcp-readwise. Documented as a known limitation.
- **Frontmatter ambiguity if a user's body legitimately starts with `---`.** Rare — almost always indicates intent. Inline parser only treats `---\n` at line 1 as frontmatter open; bodies that start with a horizontal rule should use `***` or `___` instead. Documented.
- **Markdown extensions add ~30ms render time on a 5000-word doc.** Negligible. Async-friendly: rendering happens before the awaited POST.

## Migration Plan

No migration. Purely additive. Existing callers continue to use `save_url` for URL-based content. New callers wanting to push owned content use `save_markdown`.

## Open Questions

None blocking. Future enhancements that don't affect this design:

- Should we accept a `source_url` parameter to override the synthetic URL (for callers who do have a canonical URL but want HTML rendered locally)? — additive, deferrable.
- Should we expose a separate `render_markdown` tool that returns HTML without saving, for inspection? — likely not; the user has the markdown source already.
- Image upload pipeline? — deferred; requires its own design conversation with Reader's image hosting (or external CDN).
