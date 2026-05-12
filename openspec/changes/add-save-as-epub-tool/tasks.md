## 1. Dependencies & Dockerfile

- [x] 1.1 Add `pypandoc>=1.13` to `pyproject.toml` dependencies
- [x] 1.2 Add `aiosmtplib>=3.0` to `pyproject.toml` dependencies
- [x] 1.3 Run `uv lock` to refresh `uv.lock`
- [x] 1.4 Update `Dockerfile` to install pandoc via `apt-get install -y --no-install-recommends pandoc` in the runtime stage; verify image still builds
- [x] 1.5 Verify pandoc version in image is ≥3.0 (`pandoc --version`); pin a minimum in `epub_render.py` startup check — `_pandoc_available()` enforces `(3, 0)` minimum, cached

## 2. Configuration

- [x] 2.1 Add `readwise_library_email: str = ""` to `Settings` in `mcp_readwise/config.py`
- [x] 2.2 Add `resend_api_key: SecretStr = SecretStr("")` to `Settings`
- [x] 2.3 Add `epub_from_address: str = ""` to `Settings`
- [x] 2.4 Add `smtp_host: str = "smtp.resend.com"` and `smtp_port: int = 587` to `Settings`
- [x] 2.5 Add `epub_lang: str = "en"` and `epub_max_bytes: int = 20_971_520` (20 MiB, sized for Readwise's 30 MB ingest cap minus base64 inflation) to `Settings`
- [x] 2.6 Implement `Settings.epub_sender_configured` property returning `True` only when all three required fields are non-empty
- [x] 2.7 Update `.env.example` (if present) with the new vars and brief comments

## 3. Brand stylesheet + static font subsets

- [x] 3.1 Create `mcp_readwise/assets/epub/cdit-style.css` with the full CDIT palette (Carbon `#272f38`, Cloud Dancer `#f0eee9`, Strong Blue `#1f5da0`, Mint `#5cc6c3`)
- [x] 3.2 In CSS: set `body` line-height to `1.7`, `text-align: left`, `hyphens: auto` (long-form tuning)
- [x] 3.3 In CSS: set `h1`/`h2`/`h3` font-family to `Inter` (NOT League Gothic), `letter-spacing: -0.02em`, `line-height: 1.15`
- [x] 3.4 Confirm CSS uses hex colors (not OKLCH) for EPUB reader compatibility
- [x] 3.5 Confirm font-family stacks: `Inter` for body AND headings, `JetBrains Mono` for code, with sensible fallbacks; League Gothic appears in no body-context selector
- [x] 3.6 Generate static Inter woff2 subsets at `mcp_readwise/assets/epub/fonts/`: 6 files, 168KB total (latin + latin-ext × 400/700/800; latin-ext slightly pushes the estimate but covers German)
- [x] 3.7 Add `@font-face` rules in `cdit-style.css` referencing the static woff2 paths (relative within the EPUB), with `unicode-range` for latin vs latin-ext split
- [x] 3.8 Do NOT generate or embed League Gothic in body assets; do NOT embed JetBrains Mono
- [x] 3.9 Add `[tool.hatch.build.targets.wheel.artifacts]` entry so the assets directory (CSS + fonts) ships with the wheel (used `artifacts` glob rather than `force-include` to avoid duplicate entries)
- [x] 3.10 Verify all assets land in the built wheel via `uv build && unzip -l dist/*.whl | grep -E 'epub/(cdit-style|fonts/)'` — 7 entries, no dupes

## 4. EPUB render module

- [x] 4.1 Create `mcp_readwise/epub_render.py`
- [x] 4.2 Implement `_pandoc_available() -> bool` cached startup check
- [x] 4.3 Implement `_build_metadata_yaml(metadata: dict, idempotency_key: str | None) -> str` producing pandoc-compatible YAML; when `idempotency_key` is provided, identifier scheme is `x-mcp-readwise-idempotency` with value `epub-key-<key>`; otherwise scheme is `uuid` with a fresh `uuid4()`
- [x] 4.4 Implement `_resolve_cover(cover_image_url: str | None) -> Path | None` — async httpx fetch with 10s timeout, content-type validation, returns None on failure (logs warning, never raises)
- [x] 4.5 Implement `_safe_filename(title: str) -> str` — slugify title, ASCII-only, ≤80 chars, append `.epub`
- [x] 4.6 Implement `async render_epub(markdown: str, metadata: dict, cover_path: Path | None, idempotency_key: str | None) -> tuple[bytes, str]` returning (epub_bytes, identifier_scheme); wraps `pypandoc.convert_text(..., to="epub3", extra_args=[...])` in `asyncio.to_thread`
- [x] 4.7 Pass `--css=<asset path>`, `--metadata-file=<tmp yaml>`, optional `--epub-cover-image=<path>` to pandoc; reference embedded fonts via the asset directory (uses `--epub-embed-font` for each woff2)
- [x] 4.8 Enforce `EPUB_MAX_BYTES` ceiling — raise `EpubTooLargeError` if output exceeds
- [x] 4.9 Wrap pandoc errors in `EpubGenerationError` with trimmed stderr (≤500 chars)
- [x] 4.10 Optionally render a "Note" preface block from the resolved `note` value into the markdown body before pandoc invocation (so it appears as the first block in the EPUB) — uses `<div class="mcp-note">` styled by the brand sheet

## 5. SMTP transport module

- [x] 5.1 Create `mcp_readwise/smtp_client.py`
- [x] 5.2 Implement `_build_message(...)` using `email.message.EmailMessage`, attach EPUB with `Content-Type: application/epub+zip` and base64 encoding
- [x] 5.3 Implement `async send_epub(...)` using `aiosmtplib.send(..., start_tls=True)` with username `"resend"` and password from settings
- [x] 5.4 Implement retries on transient SMTP errors (4xx codes) with exponential backoff (1s then 4s) — total 3 attempts: initial + 2 retries
- [x] 5.5 Do not retry on auth/5xx errors; surface `SmtpDeliveryError` with server response
- [x] 5.6 Return `SendResult` dataclass with `message_id`, `accepted_at`, `server_response`

## 6. EpubSendResult + VerifyResult models

- [x] 6.1 Create `mcp_readwise/models/epub.py` with `EpubSendResult` Pydantic model (success, accepted_at, recipient, message_id, file_size_bytes, title, location, identifier_scheme, note) — recipient is FULL address, not masked
- [x] 6.2 In `mcp_readwise/models/epub.py` add `VerifyResult` Pydantic model (found: bool, document: Optional[ReaderDocument], note: str)
- [x] 6.3 Do NOT implement any recipient-masking helper — earlier draft removed per audit

## 7. save_markdown_as_epub tool

- [x] 7.1 Create `mcp_readwise/tools/epub_sender.py`
- [x] 7.2 Implement `save_markdown_as_epub(markdown, title, author, summary, tags, note, cover_image_url, published_date, location, idempotency_key) -> EpubSendResult` — `image_url` is a frontmatter-only key (extracted by `parse_frontmatter`), not an MCP-facing param
- [x] 7.3 Docstring leads with `ASYNC: Returns after SMTP delivery. Document appears in Reader in 1–5 minutes. Do not tell the human the document is available until verify_epub_received confirms it.` followed by `REQUIRES env vars: READWISE_LIBRARY_EMAIL, RESEND_API_KEY, EPUB_FROM_ADDRESS.`
- [x] 7.4 Docstring documents `location` as informational-only and `idempotency_key` as the retry-safe-dedup hook
- [x] 7.5 Validate config via `_check_config()`; raise `ConfigurationError` listing missing vars without leaking values
- [x] 7.6 Reuse `mcp_readwise.markdown_render.parse_frontmatter` to extract frontmatter (no HTML render — pandoc takes raw markdown)
- [x] 7.7 Apply title/author/summary/tags/note resolution chain (explicit > frontmatter > H1 for title only > default)
- [x] 7.8 Build metadata dict for pandoc YAML (title, creator, language, date, publisher="CDiT Works", subject, description, note)
- [x] 7.9 Call `render_epub(...)` with `idempotency_key`; receive `(epub_bytes, identifier_scheme)`; pandoc errors bubble up as `EpubGenerationError`/`EpubTooLargeError`
- [x] 7.10 Call `send_epub(...)`; SMTP errors bubble up as `SmtpDeliveryError`
- [x] 7.11 Return `EpubSendResult` with full (unmasked) recipient, `location` echoed, `identifier_scheme` from the render step, async-leading `note`

## 8. verify_epub_received tool

- [x] 8.1 Create `mcp_readwise/tools/epub_verifier.py`
- [x] 8.2 Implement `verify_epub_received(title: str, since: str, fuzzy: bool = True) -> VerifyResult`
- [x] 8.3 Internally call `mcp_readwise.tools.reader.list_documents(category="epub", updated_after=since, limit=20)`
- [x] 8.4 Match documents by title: case-insensitive `contains` when `fuzzy=True`, exact (case-insensitive) when `fuzzy=False`
- [x] 8.5 When match found, return `VerifyResult(found=True, document=match, note="Found in Reader Library.")`
- [x] 8.6 When no match, compute elapsed seconds since `since`; emit time-aware note per the 4-band table
- [x] 8.7 Docstring notes that this tool does NOT require epub-sender configuration — only READWISE_TOKEN

## 9. Server wiring

- [x] 9.1 Import `save_markdown_as_epub` and `verify_epub_received` in `mcp_readwise/server.py`
- [x] 9.2 Register both tools next to `save_markdown` via `mcp.tool(...)`
- [x] 9.3 Update `/health` `tools` count from 12 to 14
- [x] 9.4 Add `epub_sender` block to `/health` response with `configured`, `smtp_host`, `smtp_port`, `from_address`, `library_email_set` (boolean only; library email never plaintext in /health)
- [x] 9.5 Confirm boolean flags + `from_address` are the only config-derived values exposed in /health; `EpubSendResult.recipient` returns the full address (different surface, intentional)

## 10. Tests — render + transport

- [x] 10.1 `tests/test_epub_render.py` — metadata YAML generation with UUID identifier (no idempotency_key); fresh UUID per call
- [x] 10.2 `tests/test_epub_render.py` — metadata YAML with `idempotency_key="K"` produces scheme `x-mcp-readwise-idempotency` and value `epub-key-K`; two calls with same key produce identical identifiers
- [x] 10.3 `tests/test_epub_render.py` — safe filename slugification (umlauts, slashes, length cap)
- [x] 10.4 `tests/test_epub_render.py` — pandoc invocation with mocked `pypandoc.convert_text` (asserts `--css`, `--metadata-file` args are always present; `--epub-cover-image` IS passed when `cover_path` is provided, AND is NOT in the args list when `cover_path` is None — covers the default-text-cover branch)
- [x] 10.5 `tests/test_epub_render.py` — file-size ceiling raises `EpubTooLargeError`
- [x] 10.6 `tests/test_epub_render.py` — cover download failure returns None (no exception, logged warning); send proceeds
- [x] 10.7 `tests/test_smtp_client.py` — message construction: MIME structure, attachment Content-Type `application/epub+zip`, base64 encoding, filename header
- [x] 10.8 `tests/test_smtp_client.py` — retry once on 4xx, no retry on 5xx, all with mocked `aiosmtplib.SMTP`
- [x] 10.9 `tests/test_smtp_client.py` — auth failure (535) raises immediately, no retry

## 11. Tests — tools

- [x] 11.1 `tests/test_save_markdown_as_epub.py` — happy path: explicit title, frontmatter title, H1 fallback, Untitled fallback
- [x] 11.2 `tests/test_save_markdown_as_epub.py` — explicit params override frontmatter for author/summary/tags/note
- [x] 11.3 `tests/test_save_markdown_as_epub.py` — `note` parameter is forwarded to EPUB metadata description AND rendered as preface block (not silently dropped)
- [x] 11.3b `tests/test_save_markdown_as_epub.py` — frontmatter `note: "From the author."` (with no explicit `note=` param) resolves to `"From the author."` and is forwarded to EPUB metadata; covers spec scenario "Frontmatter note field populates when explicit note is absent"
- [x] 11.4 `tests/test_save_markdown_as_epub.py` — `idempotency_key` is forwarded to render; two identical calls produce same identifier; no key produces distinct UUIDs
- [x] 11.5 `tests/test_save_markdown_as_epub.py` — `location` parameter accepted, echoed in `EpubSendResult.location`, does NOT affect SMTP routing
- [x] 11.6 `tests/test_save_markdown_as_epub.py` — `ConfigurationError` raised when any required env var missing; error message names the missing var(s); secrets never appear in message
- [x] 11.7 `tests/test_save_markdown_as_epub.py` — `EpubSendResult.recipient` returns the FULL (unmasked) library email address
- [x] 11.8 `tests/test_save_markdown_as_epub.py` — `EpubSendResult.note` leads with the async contract
- [x] 11.9 `tests/test_save_markdown_as_epub.py` — `cover_image_url` param is downloaded and embedded; missing cover proceeds without error
- [x] 11.9b `tests/test_save_markdown_as_epub.py` — frontmatter `image_url: https://example.com/cover.jpg` (with no explicit `cover_image_url=` param) ALSO triggers the cover download path; covers spec scenario `Cover image URL is downloaded and embedded` for the frontmatter branch
- [x] 11.10 `tests/test_verify_epub_received.py` — found path: returns `VerifyResult(found=True, document=..., note="Found in Reader Library.")`
- [x] 11.11 `tests/test_verify_epub_received.py` — not-yet path: returns `found=False` with time-band-appropriate note (use `freezegun` or monkeypatch `datetime.now` to test each of the 4 elapsed bands)
- [x] 11.12 `tests/test_verify_epub_received.py` — fuzzy=True matches partial title; fuzzy=False requires exact case-insensitive equality
- [x] 11.13 `tests/test_verify_epub_received.py` — runs successfully without epub-sender env vars (only READWISE_TOKEN required)

## 12. Tests — docstring + assets

- [x] 12.1 `tests/test_save_markdown_as_epub.py` — docstring starts with literal `"ASYNC"` (uppercase)
- [x] 12.2 `tests/test_save_markdown_as_epub.py` — docstring contains all three env var names: `READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS`
- [x] 12.3 `tests/test_save_markdown_as_epub.py` — docstring contains a phrase directing the agent not to tell the human the document is available before verifying
- [x] 12.3b `tests/test_save_markdown_as_epub.py` — docstring includes wording that `location` is informational-only and that routing to sub-locations requires a follow-up move call after `verify_epub_received`; covers spec scenario "Docstring documents the informational-only nature"
- [x] 12.4 `tests/test_assets.py` — load `cdit-style.css` via `importlib.resources`; assert brand colors `#272f38`, `#f0eee9`, `#1f5da0`, `#5cc6c3` are all present
- [x] 12.5 `tests/test_assets.py` — assert the CSS does NOT contain the string `"League Gothic"` in any body selector (it should appear nowhere except in a comment, if anywhere)
- [x] 12.5b `tests/test_assets.py` — assert NO `league-gothic*` woff2 files exist in `mcp_readwise/assets/epub/fonts/` AND NO `jetbrains-mono*` woff2 files exist there; covers spec scenario "League Gothic and JetBrains Mono are not embedded in the EPUB body"
- [x] 12.6 `tests/test_assets.py` — assert `body { line-height: 1.7; text-align: left }` is present
- [x] 12.7 `tests/test_assets.py` — assert Inter static font subsets exist as files at expected paths (400/700/800 × latin/latin-ext)
- [x] 12.8 `tests/test_assets.py` — assert NO Inter Variable woff2 file is present

## 13. Documentation

- [x] 13.1 README: add `save_markdown_as_epub` and `verify_epub_received` rows to the Reader-write tools table; tool count goes to 14
- [x] 13.2 README: add a side-by-side decision table — when to use `save_url` vs `save_markdown` vs `save_markdown_as_epub` (sync vs async, URL vs owned HTML vs real EPUB, dedup behavior)
- [x] 13.3 README: document the 3 required env vars and where to get them (Resend dashboard, Readwise Library email settings); note that library email is a bearer credential
- [x] 13.4 README: document the CDIT brand stylesheet — what it inherits from cdit-works.de, the deliberate divergence on heading typography for long-form, how to override (fork the asset)
- [x] 13.5 README: note that `pandoc` is now baked into the Docker image (~150MB cost)
- [x] 13.6 README: document the `verify_epub_received` flow pattern: send, wait 1–2 min, verify, optionally retry

## 14. Release

- [x] 14.1 Bump version to `0.6.0` in `pyproject.toml` and `mcp_readwise/__init__.py`
- [x] 14.2 Run `uv lock` after version bump
- [x] 14.3 Run `uv run pytest` — full suite green (target: 200+ tests) — **233 tests passing** (was 156; +77 new across 4 new test files)
- [x] 14.4 Run `uv run ruff check` — clean
- [ ] 14.5 Manual smoke test in stdio mode: configure env vars locally with a Resend test key, send a real markdown, run `verify_epub_received` 1 min later; verify the EPUB lands in Readwise Library and the verify tool finds it
- [ ] 14.6 Manual visual check on the resulting EPUB in Readwise Reader: confirm Carbon text, Cloud Dancer background (where Reader doesn't force its own theme), Strong Blue links, Mint blockquote rail, headings set in Inter weight 800 (NOT condensed League Gothic), body line-height feels right at reading distance
- [ ] 14.7 Manual idempotency check: send same markdown twice with same `idempotency_key`; verify Readwise shows ONE entry, not two
- [ ] 14.8 Commit, push, verify Komodo auto-deploy and `/health.tools == 14`, `/health.epub_sender.configured == true`
