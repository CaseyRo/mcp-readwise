## ADDED Requirements

### Requirement: Single-call snapshot of reading state

The system SHALL provide a `reading_status` tool that returns a `ReadingStatus` response containing a structured snapshot of the user's relationship with their library. The snapshot SHALL include: `this_window` (recent activity grouped by status), `evergreen_top` (high-intensity sources, all-time, recency-removed), `current_top` (high-engagement sources, last 30 days), `junk_drawer` (saved cold sources older than 30 days, with count and examples), and `signal_density` (corpus shape signals: tags-per-highlight, notes-per-highlight, sources_count, year_span).

#### Scenario: Default invocation populates every section

- **WHEN** `reading_status()` is invoked with no arguments
- **THEN** the response SHALL contain populated `this_window`, `evergreen_top`, `current_top`, `junk_drawer`, and `signal_density` fields
- **AND** every `Source` in the response SHALL carry an `EngagementScore` and `is_legacy: bool`

#### Scenario: Empty corpus

- **WHEN** the user has no books, documents, or highlights
- **THEN** the response SHALL contain empty lists for `evergreen_top` and `current_top`, zeroed counts in `junk_drawer`, and zeroed values in `signal_density` — without raising an error

### Requirement: Time-windowed activity in `this_window`

`this_window` SHALL contain four lists — `finished`, `in_progress`, `saved_only`, `top_engaged` — populated from sources whose most recent activity falls inside the configured window. The window SHALL default to 7 days, overridable via `window_days: int` parameter, and shiftable into the past via `week_offset: int` (default 0; `-1` means the previous 7-day window, etc.).

#### Scenario: Default 7-day window

- **WHEN** `reading_status()` is invoked with default arguments
- **THEN** `this_window.finished` SHALL contain sources whose `base_layer` indicates finished AND whose most recent activity is within the last 7 days
- **AND** `this_window.in_progress` SHALL contain sources with active reading inside the window
- **AND** `this_window.saved_only` SHALL contain sources newly saved in the window with no further activity

#### Scenario: Past week via week_offset

- **WHEN** `reading_status(week_offset=-1)` is invoked
- **THEN** `this_window` SHALL be populated from activity 7–14 days ago

#### Scenario: Top-engaged in the window

- **WHEN** the window contains 50 active sources
- **THEN** `this_window.top_engaged` SHALL contain at most 10 sources, ranked by `EngagementScore.raw`

### Requirement: Evergreen vs current ranking

`evergreen_top` SHALL be ranked by `EngagementScore.intensity` (no recency component) and capped at 10 entries. `current_top` SHALL be ranked by `EngagementScore.raw` (recency-weighted) over sources active in the last 30 days, also capped at 10 entries.

#### Scenario: Legacy book dominates evergreen

- **WHEN** the corpus contains a legacy book with intensity 0.90 and a recent article with intensity 0.80
- **THEN** the legacy book SHALL appear higher in `evergreen_top` than the recent article

#### Scenario: Recent article dominates current

- **WHEN** the corpus contains a recent article with raw 1.20 and a legacy book with raw 0.80
- **THEN** the recent article SHALL appear higher in `current_top` than the legacy book

#### Scenario: Source older than 30 days excluded from current

- **WHEN** a source's most recent highlight is 60 days ago
- **THEN** that source SHALL NOT appear in `current_top` regardless of its engagement score

### Requirement: Junk drawer surfaces unprocessed material

`junk_drawer` SHALL contain a `count` field (integer total) and an `examples` list (up to 5 sources, sorted by saved-age descending) drawn from sources with the `"junk_drawer_candidate"` flag.

#### Scenario: Many junk-drawer sources

- **WHEN** the corpus has 23 sources flagged as junk-drawer candidates
- **THEN** `junk_drawer.count` SHALL equal 23
- **AND** `junk_drawer.examples` SHALL contain 5 sources, sorted by oldest saved first

#### Scenario: No junk-drawer sources

- **WHEN** no sources match the junk-drawer criteria
- **THEN** `junk_drawer.count` SHALL equal 0
- **AND** `junk_drawer.examples` SHALL be an empty list

### Requirement: Signal density summary

`signal_density` SHALL contain `tags_per_highlight: float`, `notes_per_highlight: float`, `sources_count: int`, `total_highlights: int`, and `year_span: int` (the number of years between the oldest and newest highlight in the corpus). The system SHALL NOT pre-bake a maturity label; the consumer (LLM or other client) frames the corpus from these raw numbers.

#### Scenario: Year span across decade-old corpus

- **WHEN** the oldest highlight is from 2016 and newest from 2026
- **THEN** `signal_density.year_span` SHALL equal `10` (within rounding)

#### Scenario: Sparse-tag corpus

- **WHEN** the corpus has 730 highlights and only 5 tag occurrences across all of them
- **THEN** `signal_density.tags_per_highlight` SHALL be approximately `0.007` (5 / 730)

#### Scenario: Empty corpus does not crash

- **WHEN** the corpus has zero highlights
- **THEN** `signal_density.tags_per_highlight` and `notes_per_highlight` SHALL equal `0.0` (not raise a divide-by-zero error)
- **AND** `year_span` SHALL equal `0`

### Requirement: Derived `reading_status` field on `ReaderDocument`

The system SHALL expose a derived `reading_status` field on every `ReaderDocument` returned by direct lookup with one of three values — `"finished"`, `"in_progress"`, `"saved_only"` — computed by these rules in order:

1. `location == "archive"` → `"finished"`
2. `reading_progress >= 0.9` → `"finished"`
3. `0 < reading_progress < 0.9` → `"in_progress"`
4. otherwise → `"saved_only"`

#### Scenario: Archive overrides progress

- **WHEN** a document has `location="archive"` and `reading_progress=0.0`
- **THEN** `reading_status` SHALL equal `"finished"`

#### Scenario: PDF reaching 0.9

- **WHEN** a document has `reading_progress=0.92`
- **THEN** `reading_status` SHALL equal `"finished"`

#### Scenario: Partially read

- **WHEN** a document has `reading_progress=0.5`
- **THEN** `reading_status` SHALL equal `"in_progress"`

#### Scenario: Never opened

- **WHEN** a document has `reading_progress=0.0` and `location="new"` or `"later"`
- **THEN** `reading_status` SHALL equal `"saved_only"`
