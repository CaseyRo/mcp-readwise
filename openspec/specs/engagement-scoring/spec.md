# engagement-scoring Specification

## Purpose

Define the in-memory engagement index that joins Readwise v2 books with Readwise Reader v3 documents and computes a decomposable per-source `EngagementScore` (raw / intensity / recency / return_strength + base_layer + flags). This capability provides the scoring foundation consumed by the `reading_status` and `writing_material` workflow-shaped tools.

## Requirements

### Requirement: v2/v3 source join

The system SHALL maintain an in-memory engagement index that joins every Readwise v2 book with its corresponding Readwise Reader v3 document (when one exists), so that per-source engagement signals can be computed from both APIs in a single pass.

#### Scenario: Reader-imported source with ULID source_url

- **WHEN** a v2 book carries `source="reader"` and `source_url` of the form `private://read/<ULID>`
- **THEN** the index SHALL extract the ULID and look up the matching v3 document by `id`
- **AND** the resulting `Source` SHALL carry both v2 highlight metadata and v3 location/progress

#### Scenario: Reader-imported source with public URL

- **WHEN** a v2 book carries `source="reader"` and `source_url` is a public `http(s)://` URL
- **THEN** the index SHALL look up the matching v3 document by `source_url` equality
- **AND** the resulting `Source` SHALL carry both v2 and v3 metadata

#### Scenario: Legacy source (Kindle/iBooks/etc.)

- **WHEN** a v2 book carries `source` not equal to `"reader"` (e.g. `"kindle"`, `"ibooks"`, `"instapaper"`)
- **THEN** the index SHALL NOT attempt a v3 lookup
- **AND** the resulting `Source` SHALL be flagged `is_legacy=True`

#### Scenario: Reader-imported source with no v3 match

- **WHEN** a v2 book carries `source="reader"` but no v3 document matches by ULID or URL
- **THEN** the source SHALL be flagged `is_legacy=True` (treated as legacy for scoring)

#### Scenario: v3 document with no v2 entry (saved-but-not-highlighted)

- **WHEN** a v3 document exists with no corresponding v2 book (no highlights yet)
- **THEN** the index SHALL include the document as a `Source` with `is_legacy=False` and no `num_highlights`

### Requirement: Engagement score is a vector

Every `Source` produced by the engagement index SHALL carry an `EngagementScore` with the fields `raw: float`, `intensity: float`, `recency: float`, `return_strength: float`, `base_layer: Literal["saved_cold", "saved_warm", "reading", "finished_no_hl", "highlighted", "legacy"]`, and `flags: list[str]` (e.g. `"junk_drawer_candidate"`, `"multi_era_return"`).

#### Scenario: Score components are decomposable

- **WHEN** a `Source` is returned from any tool
- **THEN** `EngagementScore.raw` SHALL equal `intensity + recency + return_strength` (within floating-point tolerance) so the consumer can verify and recompose

#### Scenario: Different views rank by different components

- **WHEN** a tool ranks sources for `current_top` (recent attention)
- **THEN** the ranking SHALL use `EngagementScore.raw`

- **WHEN** a tool ranks sources for `evergreen_top` (durable interest)
- **THEN** the ranking SHALL use `EngagementScore.intensity` (recency removed)

### Requirement: Base-layer derivation rules

The system SHALL determine `base_layer` for every source by applying these rules in order, taking the first applicable layer:

1. If the source is v2-only or has no v3 match (legacy detection per v2/v3 join) → `"legacy"` (legacy detection takes precedence; v2-only highlights score on the legacy track)
2. If the source has any non-discarded highlight → `"highlighted"` (overrides v3 progress/location for Reader-era sources)
3. If `v3.location == "archive"` OR `v3.reading_progress >= 0.9` → `"finished_no_hl"`
4. If `0 < v3.reading_progress < 0.9` → `"reading"`
5. If `v3.location == "later"` AND `v3.reading_progress == 0` → `"saved_warm"`
6. Otherwise (`v3.location` in `{"new", "feed"}`, progress=0, no highlights) → `"saved_cold"`

#### Scenario: Highlights override v3 progress

- **WHEN** a source has 2 highlights but `v3.reading_progress == 0`
- **THEN** `base_layer` SHALL equal `"highlighted"`

#### Scenario: Archive overrides progress for finished detection

- **WHEN** `v3.location == "archive"` and `v3.reading_progress == 0` and no highlights
- **THEN** `base_layer` SHALL equal `"finished_no_hl"`

#### Scenario: Legacy with highlights still gets legacy base

- **WHEN** a v2 book has `source="kindle"` and has 25 highlights
- **THEN** `base_layer` SHALL equal `"legacy"` (not `"highlighted"`) — legacy detection takes precedence

### Requirement: Engagement score formula

The `raw` engagement score SHALL be computed as `base + density + recency + annotation + return_signal` per the formula. Highlights with `is_discard=True` SHALL be excluded from the highlighted base-layer trigger and from density counts.

| Component | Condition | Value |
|---|---|---|
| base | `base_layer == "highlighted"` | 0.70 |
| base | `base_layer == "finished_no_hl"` | 0.50 |
| base | `base_layer == "reading"` | 0.30 |
| base | `base_layer == "saved_warm"` | 0.15 |
| base | `base_layer == "saved_cold"` | 0.10 |
| base | `base_layer == "legacy"` | 0.40 |
| density (highlighted or legacy only; counts non-discarded) | `num_highlights` 1–2 | +0.10 |
| density (highlighted or legacy only; counts non-discarded) | `num_highlights` 3–9 | +0.30 |
| density (highlighted or legacy only; counts non-discarded) | `num_highlights` 10–29 | +0.50 |
| density (highlighted or legacy only; counts non-discarded) | `num_highlights` 30+ | +0.70 |
| recency | `max(highlighted_at)` within 30 days | +0.20 |
| recency | `max(highlighted_at)` older than 5 years | −0.10 |
| recency | otherwise | 0.00 |
| annotation | ≥1 highlight has a non-structural user note | +0.30 |
| annotation | ≥1 highlight has a non-denylisted user-applied tag | +0.10 |
| annotation | ≥1 highlight has `is_favorite=True` | +0.20 |
| return_signal | highlight timestamps form clusters with gap > 2 years | +0.30 |
| return_signal | Reader v3 `last_opened_at` within 30d AND `first_opened_at` older than 90d | +0.20 |

The score SHALL NOT be capped — it ranks, it is not a percentage. Multiple return_signal contributions stack additively.

#### Scenario: Reader article, recent, modest highlights

- **WHEN** a source has `base_layer="highlighted"`, 3 highlights, last highlight within 30 days, no notes, no tags, no return cluster
- **THEN** `raw` SHALL equal `0.70 + 0.30 + 0.20 + 0.00 + 0.00 = 1.20`

#### Scenario: Legacy book, deep engagement, old

- **WHEN** a source has `base_layer="legacy"`, 25 highlights, last highlight 5+ years ago, no notes, no tags, no return cluster
- **THEN** `raw` SHALL equal `0.40 + 0.50 − 0.10 + 0.00 + 0.00 = 0.80`

#### Scenario: Cold inbox

- **WHEN** a source has `base_layer="saved_cold"`, no highlights, no annotation, no return
- **THEN** `raw` SHALL equal `0.10`

#### Scenario: intensity excludes recency and return

- **WHEN** computing `EngagementScore.intensity` for the legacy book scenario above
- **THEN** `intensity` SHALL equal `base + density + annotation = 0.40 + 0.50 + 0.00 = 0.90`

### Requirement: Return signal detection

The system SHALL detect two distinct return signals and combine them into `return_strength`:

1. **Multi-era timestamp cluster:** When a source's highlights, sorted by `highlighted_at`, contain at least one consecutive pair with a gap greater than 2 years, the source SHALL gain +0.30 and carry the `"multi_era_return"` flag.
2. **Reader-era re-open:** When a Reader v3 document has `last_opened_at` within the last 30 days AND `first_opened_at` older than 90 days, the source SHALL gain +0.20 and carry the `"reader_return"` flag. This signal SHALL be skipped for sources without v3 data (legacy sources).

Both signals SHALL stack additively into `return_strength`.

#### Scenario: Single-era highlights, never reopened

- **WHEN** all of a source's highlights occur within a 12-month window AND no v3 reopen pattern applies
- **THEN** `return_strength` SHALL be 0.00 and the source SHALL NOT carry any return flag

#### Scenario: Multi-era highlights only

- **WHEN** a source has highlights from 2018 and additional highlights from 2024 (gap > 2 years)
- **AND** no v3 reopen pattern applies
- **THEN** `return_strength` SHALL be +0.30
- **AND** the source's flags SHALL include `"multi_era_return"`

#### Scenario: Reader-era reopen only

- **WHEN** a v3 document has `first_opened_at` 6 months ago and `last_opened_at` yesterday
- **AND** highlights span only a 2-month window
- **THEN** `return_strength` SHALL be +0.20
- **AND** the source's flags SHALL include `"reader_return"`

#### Scenario: Both signals stack

- **WHEN** a source has multi-era highlights AND a recent Reader reopen
- **THEN** `return_strength` SHALL be +0.50 and both flags SHALL be present

### Requirement: Tag denylist for annotation bonus

The annotation bonus for tags SHALL exclude tags that match a configurable denylist of structural / auto-generated tag names. The default denylist SHALL include heading markers (`h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `.h1`, `.h2`), the literal `"discard"`, single-character tags, and common color names (`orange`, `blue`, `red`, `green`, `yellow`, `purple`).

#### Scenario: Denylisted tag does not earn annotation bonus

- **WHEN** the only tag on a source's highlights is `"h1"`
- **THEN** the annotation tag bonus SHALL be 0.00

#### Scenario: Non-denylisted tag earns annotation bonus

- **WHEN** a source has at least one highlight tagged `"productivity"` (not in denylist)
- **THEN** the annotation tag bonus SHALL be +0.10

#### Scenario: Configurable denylist

- **WHEN** `ENGAGEMENT_TAG_DENYLIST` config is set to a custom list
- **THEN** the system SHALL use the configured denylist instead of the default

### Requirement: Index caching with TTL

The system SHALL cache the engagement index in memory with a default TTL of 30 minutes (configurable via `ENGAGEMENT_INDEX_TTL_SECONDS`). Tool calls within the TTL window SHALL be served from cache without re-paginating the Readwise APIs.

#### Scenario: Cache hit within TTL

- **WHEN** `reading_status` is invoked twice within 30 minutes
- **THEN** the second invocation SHALL be served from the cached index without making v2/v3 API calls

#### Scenario: Cache miss after TTL

- **WHEN** `reading_status` is invoked after the TTL has elapsed
- **THEN** the index SHALL be rebuilt from fresh v2 and v3 paginations

### Requirement: Junk drawer detection

A `Source` SHALL carry the flag `"junk_drawer_candidate"` when all of the following hold: `base_layer in {"saved_cold", "saved_warm"}`, no highlights, and the source's `saved_at` timestamp from Reader v3 is older than 30 days. (Falls back to `created_at` when `saved_at` is unavailable.)

#### Scenario: Recently saved article, untouched

- **WHEN** an article has `location="later"`, `progress=0`, no highlights, and was saved 5 days ago
- **THEN** the source SHALL NOT carry `"junk_drawer_candidate"` (within the 30-day grace window)

#### Scenario: Old saved article, untouched

- **WHEN** an article has `location="later"`, `progress=0`, no highlights, and was saved 90 days ago
- **THEN** the source SHALL carry `"junk_drawer_candidate"`
