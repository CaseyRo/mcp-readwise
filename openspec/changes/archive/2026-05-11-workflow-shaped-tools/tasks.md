## 1. Foundation: client cache + models

- [x] 1.1 Expanded `_book_cache` in `client.py` to carry `source`, `num_highlights`, `category`; bumped `_BOOK_CACHE_SIZE` to 512
- [x] 1.2 Added `reading_status` derivation on `ReaderDocument` via `@model_validator(mode='after')` (archive override; 0.9 threshold). Also added `saved_at`, `first_opened_at`, `last_opened_at`, `last_moved_at` fields per spike findings
- [x] 1.3 Added `Source` Pydantic model in `mcp_readwise/models/source.py` with engagement, is_legacy, legacy_recency, flags
- [x] 1.4 Added `EngagementScore` Pydantic model with raw/intensity/recency/return_strength vector + base_layer + flags
- [x] 1.5 Renamed `notes` → `note` on `save_url`; internal translation to `notes` for v3 endpoint
- [x] 1.6 Tests in `tests/test_models.py` cover all four reading_status branches plus PDF-at-0.9, archive-with-progress, etc. — 11 tests passing
- [x] 1.7 (additional) Added `is_favorite` and `is_discard` boolean fields to `HighlightResult` (spike 9.3 finding)

## 2. Engagement: index module

- [x] 2.1 Created `mcp_readwise/engagement.py` with `_IndexCache` dataclass holding the merged `dict[SourceId, Source]` and a TTL timestamp
- [x] 2.2 Implemented `build_index()` paginating `/api/v2/export/` (books with highlights inline) + `/api/v3/list/` (Reader docs); built `by_ulid` and `by_url` indices; joined each v2 book with its v3 doc (or marked legacy); emitted `Source` records
- [x] 2.3 Sequential pagination via existing `client._request` retry/backoff (429 handling reused, no parallel fan-out)
- [x] 2.4 Implemented `extract_ulid(source_url)` parsing `private://read/<ULID>` (strict regex; returns None on misses)
- [x] 2.5 Implemented TTL caching with `ENGAGEMENT_INDEX_TTL_SECONDS` config (default 1800 / 30 min), asyncio.Lock for concurrent safety
- [x] 2.6 Tests: ULID extraction with 6 input variants
- [x] 2.7 Tests: build_index against mocked v2/v3 — Reader-imported, legacy, v3-only branches all asserted
- [x] 2.8 Tests: cache hit on repeat call within TTL; rebuild after TTL expiry; force_refresh

## 3. Engagement: scoring formula

- [x] 3.1 `compute_base_layer` per design D3 (legacy first, then highlighted overrides v3 progress)
- [x] 3.2 `compute_density` from non-discarded highlight count, gated on highlighted/legacy base
- [x] 3.3 `compute_recency` from `max(highlighted_at)` vs now (30d / 1y / 5y bands)
- [x] 3.4 `compute_annotation` — note (+0.30) + non-denylisted tag (+0.10) + is_favorite (+0.20)
- [x] 3.5 `compute_return_signal` — multi-era cluster detection (>2yr gap → +0.30) AND Reader-era reopen (`last_opened_at` within 30d AND `first_opened_at` >90d ago → +0.20); flags stack
- [x] 3.6 `compute_engagement` assembles the vector (raw, intensity, recency, return_strength) + flags including `junk_drawer_candidate`
- [x] 3.7 Default tag denylist (h1–h6, .h1–.h6, discard, favorite, single-char, color names); configurable via `ENGAGEMENT_TAG_DENYLIST`
- [x] 3.8 Tests: spec scenarios — Reader article 1.20, legacy book 0.80, cold inbox 0.10, intensity decomposition
- [x] 3.9 Tests: multi-era return for 2018+2024 cluster; not detected for single-era; both signals stack
- [x] 3.10 Tests: tag denylist filters structural tags; legitimate user tags earn +0.10
- [x] 3.11 Tests: junk_drawer_candidate flag set/not set per saved_at age

## 4. Tool: reading_status

- [x] 4.1 `ReadingStatus` model in `mcp_readwise/models/status.py` with `this_window`, `evergreen_top`, `current_top`, `junk_drawer`, `signal_density`, `window_days`, `week_offset`
- [x] 4.2 `ThisWindow`, `JunkDrawer`, `SignalDensity` sub-models
- [x] 4.3 `reading_status(window_days=7, week_offset=0)` builds each section from the engagement index
- [x] 4.4 `evergreen_top` ranked by `EngagementScore.intensity`, capped at 10
- [x] 4.5 `current_top` ranked by `EngagementScore.raw` over sources active in last 30d, capped at 10
- [x] 4.6 `junk_drawer.examples` — up to 5 sources with `junk_drawer_candidate` flag, oldest saved first
- [x] 4.7 `signal_density` — sources_count / total_highlights / tags_per_highlight / notes_per_highlight / year_span (no maturity label per Q5 decision)
- [x] 4.8 Registered `reading_status` in `server.py` via `mcp.tool(...)`
- [x] 4.9 Tests in `tests/test_status.py` — default invocation, empty corpus, intensity-vs-raw ranking, top-N caps, junk_drawer, decade-span signal_density
- [x] 4.10 Tests: signal_density year_span across 10-year corpus

## 5. Tool: writing_material

- [x] 5.1 `WritingMaterial` model in `mcp_readwise/models/writing.py` with `sources`, `highlights`, `grouped_by_source`, `summary`, `has_notes`, `has_legacy`, `has_more`, `total_highlights`
- [x] 5.2 Flat-kwarg discriminated source: `book_id` / `document_id` / `title_search` / `topic` (one-of validation)
- [x] 5.3 `writing_material(...)` with split defaults — 200 source-first, 30 topic-first
- [x] 5.4 Source-first path: lookup by id; for `title_search`, case-insensitive contains-match against engagement index titles, error on multiple with candidate list
- [x] 5.5 Topic-first path: existing semantic search via `/api/mcp/highlights`, filter by `min_engagement` against the engagement index, group by source
- [x] 5.6 Computed `has_notes`, `has_legacy`, `has_more`, `total_highlights` on response
- [x] 5.7 Registered `writing_material` in `server.py` via `mcp.tool(...)`
- [x] 5.8 Tests in `tests/test_writing.py` — neither/multiple args raise, BookId/DocId/TitleSearch single/ambiguous/missing, engagement floor filtering, has_legacy flag, default-limits split

## 6. Hygiene: BREAKING — remove read primitives from MCP surface

- [x] 6.1 Removed `@mcp.tool` registration for `list_books`, `get_book`, `list_documents`, `get_document`, `list_highlights`, `get_highlight`, `search_highlights`, `export_highlights` (client functions remain in their tool modules for internal/test use)
- [x] 6.2 README header documents v0.4.0 as BREAKING; commit message will repeat the call-out (no separate CHANGELOG.md created — repo uses commit-message convention)
- [x] 6.3 Verified internal callers — only `engagement.py` calls `client.get/post` directly; the new tools call `engagement.get_index` and the writing tool also calls `client.get` for highlights pagination

## 7. Wire-up & observability

- [x] 7.1 `/health` `tools` count updated to 11
- [x] 7.2 `/health` exposes `engagement_index` block with `built`, `built_at`, `age_seconds`, `source_count`, `ttl_seconds`
- [x] 7.3 Build identifier baking unchanged — Dockerfile still bakes git commit and the resolution path is untouched

## 8. Docs & release

- [x] 8.1 Rewrote README around the two-tool surface; documented removed primitives; updated config table with engagement vars
- [x] 8.2 Added "How the engagement score works" section explaining the formula at a high level
- [x] 8.3 Linked README to `design.md` for the full formula
- [x] 8.4 Bumped version to `0.4.0` in `pyproject.toml` and `mcp_readwise/__init__.py`
- [x] 8.5 Full test suite (110 tests) green; ruff clean
- [x] 8.6 Pushed to main (`d50bf81` → `0774d94` → `8a8363a`); auto-deploy chain fixed mid-ship — discovered webhook URL was on wrong path (`/webhook/*` instead of v2's `/listener/github/stack/...`), GitHub webhook URL corrected, secret rotated atomically on both sides. Auto-deploy now functional. Stack: `git-mcp-readwise-mini` on `ubuntu-smurf-mini`.
- [x] 8.7 Smoke test passed: `/health` reports `version: "0.4.0"`, `tools: 11`, fresh container uptime. 11 tools verified by name (reading_status, writing_material + 9 write/util). Cold-call rate-limit issue surfaced and fixed in flight via `0774d94` (Retry-After support + separate 429 retry budget). Known pre-existing issue not blocking: Komodo isn't injecting `GIT_COMMIT` build arg, so `/health.git_commit` shows `"unknown"`.

## 9. Pre-implementation spike (COMPLETE — findings folded into design D3)

- [x] 9.1 Probed Readwise API. **Finding:** v2 highlights expose no `last_seen_at`/`times_reviewed`. v3 Reader docs DO expose `first_opened_at` and `last_opened_at` — folded into `return_strength` for Reader-era sources. v2 `/api/v2/review/` endpoint exists but only returns today's session, no history.
- [x] 9.2 v3 page count not measurable today (token expired); earlier probes show several hundred docs across locations. 5–10 pages estimate stands; build scopes conservatively.
- [x] 9.3 **Finding:** `list_tags` returns user-created custom tags only. Inline `favorite`/`discard` tags are derived from `is_favorite`/`is_discard` booleans on highlights; `h1`/`h2` are imported from epub TOC structure. Not a bug. Adjusted design: use `is_favorite` boolean as a first-class annotation signal (+0.20), keep tag denylist for the auto-derived inline strings.
