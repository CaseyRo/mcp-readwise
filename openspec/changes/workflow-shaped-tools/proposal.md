## Why

The mcp-readwise server currently exposes 17 tools that mirror the Readwise REST API one-to-one (`list_books`, `list_documents`, `list_highlights`, …). An audit traced the actual jobs-to-be-done — orient on recent reading, draft from highlights, surface interest patterns — and found only 2 of 5 top intents complete in a single tool call. Empirical inspection of the live corpus then exposed deeper problems with our first redesign:

- **Tags are nearly empty** (`list_tags` returns 1 entry; tag-based aggregations are noise on this corpus, and likely on most).
- **User notes are rare** (~3% of highlights), so any feature gated on "annotated content" finds nothing.
- **The book/article temporal split was a proxy.** What the user actually wants to weight is *engagement* per source — and engagement is detectable from existing API fields without needing tags or notes.
- **A v2/v3 asymmetry runs through the data.** v2 carries every highlighted source (going back 10 years for this corpus); v3 carries every Reader-era document (post-2022). They overlap but aren't identical. Pre-Reader books with deep highlight histories (Sapiens, Meditations, McKinsey Mind, etc.) are invisible to v3-only logic, but they're the user's actual canon.

The redesign collapses the surface around a single load-bearing concept — **per-source engagement** — and lets the books/articles temporal asymmetry, the saved-vs-finished status, and the patterns analytics all fall out as derived views of one cached index.

## What Changes

### Read surface (collapsed to 2 tools, 0 resources, 0 prompts)

- **NEW** `reading_status(window_days=7, week_offset=0) → ReadingStatus` — a single rich snapshot covering everything the user needs to orient on their reading. Returns `this_window` (finished / in_progress / saved_only / top_engaged), `evergreen_top` (high-intensity sources, all-time, recency-removed), `current_top` (high-engagement sources, last 30d), `junk_drawer` (saved cold, never advanced, age > 30d), and `signal_density` (tags_per_hl, notes_per_hl, sources_count, year_span). Replaces the workflow that was `get_reading_activity` + `reading_pulse` prompt + `weekly_reflection` prompt + `interest_compass` prompt.
- **NEW** `writing_material(topic=None, source=None, min_engagement=0.7, limit=30) → WritingMaterial` — composable bundle for drafting. Either source-first (provide `source` as `BookId | DocId | TitleSearch`) or topic-first (provide `topic`). Filters by engagement floor instead of editorial `lens`. Replaces `get_source_with_highlights` + `find_highlights_for_writing` + `writing_seeds` prompt.

### Engagement scoring (new internal primitive, exposed as model fields)

- **NEW** `EngagementScore` derived per source: a vector of `raw` (full ranking score), `intensity` (engagement without recency — for evergreen ranking), `recency` (time-decay component), `return_strength` (re-engagement signal). Plus `base_layer: Literal["saved_cold", "saved_warm", "reading", "finished_no_hl", "highlighted", "legacy"]` and `is_legacy: bool`. Computed from existing API data; no new auth or endpoints.
- **NEW** Engagement index — a TTL-cached primitive (default 30 minutes) that joins v2 books with v3 documents and computes `EngagementScore` per source. Both new tools read from this index; building it costs ~1–3 seconds cold against the live API for a 150-source corpus.

### Hygiene

- Add derived `reading_status` field on `ReaderDocument` (now superseded by base_layer on `EngagementScore`, but kept for direct-doc consumers; threshold lowered from 0.95 to 0.9, with `location="archive"` as authoritative-finished).
- Standardize `note` (singular) on every MCP-facing parameter; translate to `notes` internally.
- Expand the `_book_cache` in `client.py` to carry `source` (kindle/reader/ibooks/...), `num_highlights`, and `category` — needed for legacy detection and density scoring.

### BREAKING

- Remove every public-facing read primitive from the MCP surface: `list_books`, `get_book`, `list_documents`, `list_highlights`, `get_highlight`, `search_highlights`, `export_highlights`. They live on inside `client.py` as building blocks for the new tools but are not registered as MCP tools. Justification: the two new tools cover all observed intents; the primitives forced fan-out and prompt-side stitching that the engagement index now does server-side.
- The version bump is `v0.4.0` (BREAKING removals + additive new tools).

The public read surface goes from 7 endpoint-shaped tools to 2 engagement-shaped tools. Write tools and tag tools (`save_url`, `create_highlight`, `update_highlight`, `delete_highlight`, `update_progress`, `create_tag`, `delete_tag`, `tag_highlight`, `list_tags`) remain unchanged. Total: 11 tools, down from 17.

## Capabilities

### New Capabilities

- `engagement-scoring`: A per-source engagement model derived from existing v2/v3 API data — no new auth, no new endpoints. Defines the join between v2 books and v3 documents, the scoring formula (base layer + density + recency + annotation + return signal), the legacy bucket (v2-only sources from pre-Reader era), and the vector `EngagementScore` exposed on every `Source` model. Forms the load-bearing primitive that both `reading-status` and `writing-material` build on.
- `reading-status`: A single tool that returns a structured snapshot of the user's relationship with their library — recent activity, evergreen interests, current attention, junk drawer, and signal density. Designed to be invoked once and produce narrative-quality answers to "what have I been reading," "what am I into," and "what should I clear from my queue" without further round-trips.
- `writing-material`: A single tool that bundles the inputs an LLM needs to draft from Readwise content. Source-first (`source=...`) returns a single source's metadata + summary + highlights. Topic-first (`topic=...`) returns highlights matching the topic, grouped by source, filtered by engagement floor. Engagement-aware filtering replaces the editorial `lens` parameter from earlier drafts.

### Modified Capabilities

None. `openspec/specs/` is empty — this is the first capability spec set in the repo.

## Impact

- **Code**: Two new tool modules under `mcp_readwise/tools/`; one new internal module (`mcp_readwise/engagement.py` or similar) for the index + scoring; expanded `_book_cache` in `client.py`; new Pydantic models for `EngagementScore`, `Source`, `ReadingStatus`, `WritingMaterial`. Existing read-side tool modules (`books.py`, `highlights.py`, `reader.py`, `export.py`) keep their client functions but lose their `@mcp.tool` registrations.
- **APIs (Readwise)**: Cold-start cost of building the engagement index is ~1–3 seconds against the live API (paginate v2 books + v3 documents). TTL of 30 minutes bounds steady-state cost. No new auth scope.
- **Dependencies**: FastMCP 3.2.4 already installed — no new top-level deps.
- **Clients**: The MCP API key, transport, and `/health` contract are unchanged. The BREAKING removal of read primitives means LLM callers that explicitly invoked `list_books` etc. need to migrate to `reading_status` / `writing_material`. For the user's own usage this is acceptable; there are no third-party callers.
- **Docs**: README tool list, `/health` `tools` count, and any "how to use this MCP" notes need rewriting around the two-tool surface.
