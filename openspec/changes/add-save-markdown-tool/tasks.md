## 1. Dependencies

- [ ] 1.1 Add `markdown>=3.7` to `pyproject.toml` dependencies
- [ ] 1.2 Run `uv lock` to refresh `uv.lock`

## 2. Markdown render + frontmatter helper

- [ ] 2.1 Create `mcp_readwise/markdown_render.py`
- [ ] 2.2 Implement `parse_frontmatter(text: str) -> tuple[dict, str]` — inline YAML-subset parser (scalar strings + list-of-strings only)
- [ ] 2.3 Implement `extract_first_h1(body: str) -> str | None` — first `^# (.+)$` on first 50 lines
- [ ] 2.4 Implement `render_markdown(body: str) -> str` — `markdown.Markdown(extensions=['extra', 'sane_lists', 'smarty'])`
- [ ] 2.5 Implement `synthetic_url(title: str, body: str) -> str` — `https://mcp-readwise.local/md/<sha1(title + body[:512])[:16]>`
- [ ] 2.6 Implement `resolve_metadata(markdown_text, explicit_title, explicit_author, ...) -> tuple[dict, str]` — title resolution chain returning (metadata, html)

## 3. save_markdown tool

- [ ] 3.1 Create `mcp_readwise/tools/markdown.py`
- [ ] 3.2 Implement `save_markdown(markdown, title, author, summary, tags, location, category, published_date, note) -> ReaderDocument`
- [ ] 3.3 Use Literal types: `category` from documented Reader categories; `location` from save_url set
- [ ] 3.4 POST to `/api/v3/save/` with `should_clean_html=False`
- [ ] 3.5 Map response to `ReaderDocument` (reuse the shape from `save_url`)

## 4. Server wiring

- [ ] 4.1 Register `save_markdown` in `server.py` next to `save_url`
- [ ] 4.2 Update `/health` `tools` count from 11 to 12

## 5. Tests

- [ ] 5.1 `tests/test_markdown_render.py` — frontmatter parse (valid, missing, malformed, list-of-strings)
- [ ] 5.2 Frontmatter parse — body-starts-with-`---`-but-no-second-fence falls back to whole body
- [ ] 5.3 H1 extraction — finds first H1, ignores deeper headings, returns None on no H1
- [ ] 5.4 Title resolution chain — explicit > frontmatter > H1 > "Untitled" (4 cases)
- [ ] 5.5 Synthetic URL — stable for same input, different for different title or body
- [ ] 5.6 HTML render — table, footnote, fenced code, smarty quote
- [ ] 5.7 `tests/test_save_markdown.py` — happy path with mocked Reader API, asserts payload includes html, category, title, synthetic url
- [ ] 5.8 Test — frontmatter tags merge with explicit tags param (explicit takes precedence on conflict)
- [ ] 5.9 Test — explicit title overrides frontmatter title

## 6. Docs

- [ ] 6.1 README: add `save_markdown` to tools list with example payload
- [ ] 6.2 README: document frontmatter format and supported fields
- [ ] 6.3 README: note that this is for owned content; `save_url` remains for URLs

## 7. Release

- [ ] 7.1 Bump version to `0.5.0` in `pyproject.toml` and `mcp_readwise/__init__.py`
- [ ] 7.2 `uv run pytest` clean
- [ ] 7.3 `uv run ruff check` clean
- [ ] 7.4 Manual smoke test against live Readwise (stdio mode, local) — verify document appears in Reader with correct category
