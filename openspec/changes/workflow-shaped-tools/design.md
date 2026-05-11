## Context

mcp-readwise today is a thin Python/FastMCP 3.2.4 wrapper over the Readwise v2 (books/highlights) and v3 (Reader documents) REST APIs. 17 tools, mostly endpoint-shaped. Tests live under `tests/` with `pytest-httpx`-based mocks. The internal `client.py` already does partial book-metadata caching (256-entry LRU on title/author/url) and centralizes auth, retry, and 429 backoff.

An audit traced jobs-to-be-done and found endpoint-shaped tools force LLM-side fan-out. A first redesign proposed three workflow-shaped tools, four prompts, and one resource — but empirical inspection of the live corpus then showed:

- **Tags are essentially absent** for this user (1 tag from `list_tags`, scattered structural tags inline).
- **Notes are ~3% of highlights**, breaking any feature gated on "annotated content."
- **The book/article temporal split was a proxy** for engagement intensity; the underlying signal was always per-source engagement.
- **v2 carries 10 years of highlight history**; v3 only Reader-era (post-2022). Pre-Reader books with deep highlight histories — the user's actual canon — are invisible to v3-only logic.
- **The v2 `source_url` field carries a join key.** For Reader-imported items it's `private://read/<ULID>` where the ULID matches the v3 document_id, or a public URL that matches v3's `source_url`. The join is a hash lookup, not a search.

This redesign collapses the surface around per-source engagement and lets temporal/category/status views fall out as derived rankings of one cached index.

`openspec/specs/` is empty — every capability is `ADDED`.

## Goals / Non-Goals

**Goals:**
- Replace the read primitives with two engagement-shaped tools that absorb every observed intent.
- Build a TTL-cached engagement index that joins v2/v3 once and serves both tools.
- Make the legacy bucket (pre-Reader books) first-class: visible, flagged, scored on a density-aware floor.
- Expose engagement as a vector (`raw` / `intensity` / `recency` / `return_strength`) so different ranking views (current vs evergreen vs return) draw on the right component.
- Reduce the public surface from 17 to 11 tools while increasing what each one does.

**Non-Goals:**
- Not rewriting the Readwise client transport, auth, or retry behavior; those are sound.
- Not introducing FastMCP prompts or resources in v1. The rich return shapes carry the editorial structure that prompts would have provided. Resources add a third reader of the same data.
- Not exposing word-count-normalized highlight density. Books over-rank slightly vs articles in absolute density; that's accurate, not distortion.
- Not building per-tag analytics. Tags are too sparse to be a primary pivot.
- Not designing for multi-user or multi-tenant. This is a single-user MCP server.

## Decisions

### D1: Per-source engagement is the load-bearing primitive

Both new tools read from one cached `engagement_index: dict[SourceId, Source]` where each `Source` carries the joined v2 + v3 metadata plus an `EngagementScore` vector. Building the index requires paginating v2 books (~2 pages for this corpus) and v3 documents (~5–10 pages), joining them, and scoring each source. Cold cost ~1–3s; TTL 30 minutes.

**Alternatives considered:**
- *Two independent caches, one per tool.* Rejected — duplicates work, drifts over time.
- *No cache, recompute per call.* Rejected — every call would burn 5–10 API requests.

### D2: The v2/v3 join uses two hash indices, no fuzzy matching

```python
# Build phase — once per cache miss
v2_books = await collect_all("/api/v2/books/")    # ~2 pages
v3_docs  = await collect_all("/api/v3/list/")     # ~5–10 pages

by_ulid = {d.id: d for d in v3_docs}
by_url  = {d.source_url: d for d in v3_docs if d.source_url}

# Match phase — for each v2 book
def find_v3(book) -> Optional[Doc]:
    if book.source != "reader":
        return None  # legacy — no v3 entry expected
    if book.source_url.startswith("private://read/"):
        ulid = book.source_url.rsplit("/", 1)[-1]
        return by_ulid.get(ulid)
    return by_url.get(book.source_url)
```

Source field on v2 books distinguishes Reader-imported from legacy (kindle/ibooks/instapaper/manual). The current `_book_cache` in `client.py` doesn't expose `source` — needs expansion. ULID extraction is a string split; URL match is a dict lookup. No fuzzy matching, no per-item HTTP calls.

### D3: The engagement formula is a layered sum, vector output

```
engagement(source) = base_layer + density + recency + annotation + return_signal

base_layer (mutually exclusive — first match wins, in priority order):
  legacy             0.40   v2 only, no v3 join (highest priority — v2-only
                            highlights score on the legacy track regardless of
                            density, since they lack Reader-era engagement signal)
  highlighted        0.70   any non-discarded highlight present (Reader-era;
                            overrides v3 progress)
  finished_no_hl     0.50   v3.location="archive" OR progress >= 0.9
  reading            0.30   v3.progress in (0, 0.9), no highlights
  saved_warm         0.15   v3.location="later", progress=0
  saved_cold         0.10   v3.location in {"new", "feed"}, progress=0

density (only if highlighted or legacy; counts non-discarded highlights):
  num_hl  1–2     +0.10
  num_hl  3–9     +0.30
  num_hl 10–29    +0.50
  num_hl  30+     +0.70

recency (max(highlighted_at) across the source's highlights):
  within  30d     +0.20
  within   1y      0.00
  older than 5y   −0.10

annotation:
  any non-structural user note         +0.30
  any user-applied tag (post-denylist)  +0.10
  any highlight with is_favorite=True   +0.20

return_signal (sum across signals):
  highlight timestamps form clusters with gap > 2 years   +0.30   ("multi_era_return" flag)
  Reader v3 last_opened_at within 30d AND first_opened_at > 90d ago   +0.20   ("reader_return" flag)
```

**Spike finding (task 9.1) folded in:** Reader v3 documents expose `first_opened_at` and `last_opened_at`. The v2 highlights API exposes no review history. The v3 fields give us a Reader-era return signal that the timestamp-cluster signal alone (which requires multi-year gaps) cannot capture for sources from 2022 onward. Both signals stack into `return_strength`.

**Spike finding (task 9.3) folded in:** `is_favorite` is a boolean on each highlight (not a tag string). It's a stronger explicit annotation than user-applied custom tags. Treat it as its own annotation bonus. `is_discard=True` highlights are excluded from base_layer (highlighted) and from density count — the user has explicitly demoted them.

The score is exposed as a vector to support different ranking views:
- `raw` = full sum (used by `current_top`)
- `intensity` = base_layer + density + annotation (no recency, used by `evergreen_top`)
- `recency` = recency component alone
- `return_strength` = return_signal alone

**Why a vector, not a single float:** different views (current vs evergreen vs return) want to weight components differently. A single float bakes in one ranking; a vector lets the consumer pick. The cost of carrying 4 floats per source is trivial.

**The load-bearing rule:** *Highlights override v3 location/progress.* If a source has any highlight, base_layer = `highlighted` regardless of what v3 says about progress. Reader bugs and import edge cases sometimes leave progress unsynced on highlighted documents; the highlight presence is the stronger signal.

**Alternatives considered:**
- *Single float score.* Rejected — loses ranking flexibility for the analytical views.
- *Word-count-normalized density.* Rejected for v1 — adds complexity for marginal accuracy gain. Books should rank above articles per source, and density-by-count produces that without normalization.
- *No legacy bucket, only Reader-era.* Rejected — would silence 16+ deeply-engaged sources from the user's actual canon.

### D4: Legacy bucket is first-class, density-aware, never invisible

Pre-Reader-era books and Reader-era Kindle imports are the user's foundational reading. Hiding them would make `evergreen_top` vapid (article-only, AI-only). Detection: v2 entry exists, no v3 join (either `source != "reader"` or no matching ULID/URL).

Legacy items get `base_layer="legacy"` (0.40 floor), full density bonus, full recency tweak. They typically score 0.6–1.1 — competitive with Reader-era engaged items, dominant in `evergreen_top` (intensity-only ranking).

Every `Source` model carries `is_legacy: bool` and an optional `legacy_recency: Literal["cold", "warm"] | None` so the LLM can narrate "absorbed in your Kindle era" vs "engaged via Kindle this year." The earlier proposal's `core / recent / cooled` temporal layer collapses into this — recency comes from `highlighted_at`, "core" is high intensity, "cooled" is high intensity + low recency.

### D5: Drop the resource

`readwise://patterns` was justified earlier as cached corpus-level analytics. With the engagement index serving both tools, a separate resource adds a third reader of the same data with no new signal. Practical client behavior consumes resources via tool calls anyway. `reading_status` returns the same patterns as fields (`evergreen_top`, `current_top`, `signal_density`).

**Alternatives considered:**
- *Keep the resource with a longer TTL.* Rejected — micro-optimization, not architectural.
- *Promote the resource and drop a tool.* Rejected — the parameterized snapshot (window, week_offset) doesn't fit the resource read model.

### D6: Drop prompts in v1

The earlier `reading_pulse`, `interest_compass`, `writing_seeds`, `weekly_reflection` prompts each existed to wrap thin tool data in editorial framing. With richly named return shapes (`junk_drawer`, `evergreen_top`, `signal_density`), the LLM produces the narrative directly. If real usage shows narrative quality is uneven, prompts can be added later without changing the tool contracts — the editorial layer is additive.

**Alternatives considered:**
- *Ship one prompt to anchor the four use cases.* Rejected — adds surface for marginal benefit. The fields self-document.

### D7: Remove read primitives from the MCP surface entirely

Earlier draft demoted `list_books`, `list_documents`, etc. with "advanced — prefer X" docstrings. Empirical reality: this is the user's own MCP server, single user, no external callers. Demoted tools clutter the surface and tempt LLMs to use them. Remove `@mcp.tool` registration; keep the client functions for internal use by the new tools.

This is the primary BREAKING change. Affected reads: `list_books`, `get_book`, `list_documents`, `list_highlights`, `get_highlight`, `search_highlights`, `export_highlights`. All write tools and tag tools stay registered.

If a real escape-hatch case appears, add the specific primitive back in a follow-up. Don't pre-pay for a hypothetical.

### D8: `reading_status` field on `ReaderDocument` — kept, threshold revised

`reading_status: Literal["finished", "in_progress", "saved_only"]` is now a derived field for direct-doc consumers (the Reader v3 path). The engagement index carries the richer `base_layer` enum, but for `ReaderDocument` returned by direct lookup we keep the simpler 3-value enum.

Revised threshold (from earlier 0.95 to 0.9), with `location="archive"` as authoritative:
- `location == "archive"` → `"finished"` regardless of progress
- `reading_progress >= 0.9` → `"finished"`
- `0 < reading_progress < 0.9` → `"in_progress"`
- `reading_progress == 0` → `"saved_only"`

The 0.9 threshold catches PDFs that top out at 0.9 because of footers; the archive-as-authoritative rule respects user intent (archiving is a deliberate "done" action in Reader).

### D9: Tag denylist for annotation bonus

Observed tags in this corpus include `"orange"`, `"favorite"`, `"discard"`, `"h1"`, `".h1"`. Some user-applied (color, favorite); some structural (h1 from epub TOC). Programmatically distinguishing them is imperfect. v1 denylist:

```
{"h1", "h2", "h3", "h4", "h5", "h6", ".h1", ".h2", "discard"}
plus single-character tags
plus tags matching color names (orange, blue, red, green, yellow, purple)
```

This is conservative — some legitimate user tags ("orange" might be a deliberate marker) get filtered. Acceptable tradeoff: false negatives mean the bonus is missed; false positives would inflate scores. Tunable in config (`ENGAGEMENT_TAG_DENYLIST`).

### D10: TTL on the engagement index

Default 30 minutes via `ENGAGEMENT_INDEX_TTL_SECONDS`. Rationale: the corpus changes slowly between conversation sessions; 30 minutes covers the typical interactive window. For a "fresh" view the user can wait or restart the server.

**Alternatives considered:**
- *Longer TTL (4h).* Rejected — conversations within a few hours can include just-saved items the user wants reflected.
- *No TTL, recompute per call.* Rejected — wastes 5–10 API calls per tool invocation.
- *Manual invalidation tool.* Rejected for v1 — adds surface without proven need.

### D11: Two-tool surface, no cross-tool dependencies

`reading_status` and `writing_material` both read from the engagement index but don't call each other. Each is independently useful. The shared module (`mcp_readwise/engagement.py`) holds the index, the scoring function, and the v2/v3 join. Tools depend on this module; nothing depends on tools.

## Risks / Trade-offs

- **Cold-start latency on the engagement index** → 1–3s for a 150-source corpus, longer for larger libraries. Mitigation: TTL caching means cold cost is paid once per 30 minutes. If the cold call exceeds 5s for any user, scope the index build to last 365 days as a follow-up.
- **The v2/v3 join can miss matches when URLs differ trivially** (query params, redirects). Mitigation: ULID-based join handles Reader-imported items unambiguously; URL match is a fallback. Misses degrade to "treated as legacy," which is non-fatal — the source still scores, just on the legacy floor.
- **The 0.9 finished threshold misclassifies PDFs that legitimately reach 0.95+.** Mitigation: `archive` location is authoritative-finished, so users who manually archive get correct status regardless of progress.
- **The structural-tag denylist is heuristic.** A user who deliberately tags items "h1" or "orange" loses the annotation bonus. Acceptable cost; tunable in config.
- **Removing read primitives breaks any external caller.** No external callers exist for this single-user server. If one appears, add back the specific primitive needed.
- **Vector engagement scores are more for the LLM to reason about** than a single float. Mitigation: rich naming (`raw`, `intensity`, `recency`, `return_strength`) plus docstring guidance — "use `intensity` for evergreen, `raw` for current."
- **Highlight count caps at the v2 paging limit (100/page).** A book with 500 highlights surfaces correctly only if we paginate the highlights endpoint when needed; for the engagement score, only `num_highlights` (already on v2 books endpoint) matters, so this isn't a blocker for scoring — only for `writing_material` returning all highlights from a high-highlight source.

## Migration Plan

This server is consumed by the user's own Claude/MCP clients. No third-party callers.

1. Implement the engagement module + new tools + model changes behind tests.
2. Remove `@mcp.tool` registrations on the read primitives. Keep their client functions.
3. Update `/health` `tools` count.
4. Bump version to `v0.4.0`. CHANGELOG flags the BREAKING read primitive removal.
5. Update README around the two-tool surface.
6. Push to main; Komodo webhook auto-rebuilds on `ubuntu-smurf-mirror`.
7. Smoke test: `/health` reports the new tool count; `mcp inspector` lists `reading_status` and `writing_material`; an actual `reading_status()` call returns a populated snapshot in <5s cold.
8. Rollback: revert the merge commit; the previous container image is in the host's Docker cache.

## Resolved Decisions (formerly Open Questions)

1. **`reading_status` `sections` parameter — DEFERRED.** Ship full snapshot only. The full response is a few hundred tokens; lean-mode is over-engineering until proven necessary. Add the parameter in v0.4.1 if real usage shows context cost is a problem.

2. **`writing_material` default `min_engagement = 0.7` — KEPT.** Floor of 0.7 corresponds to "any highlighted source." This is the right default for writing material — only sources where the user has actual quotes to draw from. Callers can lower the floor explicitly when they want to include lightly-engaged legacy items or finished-but-unhighlighted articles.

3. **Daily Review / `last_seen_at` — SPIKE BEFORE SEALING FORMULA.** Promote the API probe from a follow-up to a pre-implementation task. Spend ~10 minutes hitting Readwise endpoints (and reading the v2 docs) to see if any per-highlight `last_seen_at`, `times_reviewed`, or Daily Review history is exposed. If yes, fold into `return_strength` before locking the formula. If no, ship without it; the multi-era timestamp clustering already covers "you came back" reasonably well.

4. **`writing_material` highlight limits — SPLIT BY PATH.** Source-first calls return up to 200 highlights (capped for safety, not arbitrary 30). Topic-first calls default to 30 across sources. Different defaults match different intents — "give me this whole book" vs "give me the top results across sources." Updated in `specs/writing-material/spec.md`.

5. **`signal_density.corpus_maturity` label — DROPPED.** Don't pre-bake a maturity label. Return the raw signals (`sources_count`, `year_span`, `total_highlights`, `tags_per_highlight`, `notes_per_highlight`) and let the LLM frame appropriately. A 145-source / 10-year corpus would have been mislabeled "emerging" by simple count thresholds; better to expose the numbers and trust narrative judgment than to bake a misclassifying opinion into the response. Removed from `specs/reading-status/spec.md`.
