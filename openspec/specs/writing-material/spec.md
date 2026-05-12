# writing-material Specification

## Purpose

Provide a single composable `writing_material` MCP tool that returns the inputs an LLM needs to draft from Readwise content — either source-first (one source, up to 200 highlights) or topic-first (up to 30 highlights across sources). Uses the `engagement-scoring` capability's `EngagementScore.raw` as the quality floor and exposes `has_notes` / `has_legacy` convenience flags.

## Requirements

### Requirement: Single composable tool for writing input

The system SHALL provide a `writing_material` tool that returns a `WritingMaterial` response containing the inputs an LLM needs to draft from Readwise content. The tool SHALL accept either `source` (source-first) or `topic` (topic-first), an optional `min_engagement: float` floor (default 0.7), and an optional `limit: int`. Exactly one of `source` or `topic` SHALL be provided. The default `limit` SHALL differ by path: `200` for source-first (return everything in a single source, capped for safety), `30` for topic-first (top results across multiple sources).

#### Scenario: Source-first invocation returns up to 200 highlights by default

- **WHEN** `writing_material(source=BookId(12345))` is invoked with no explicit `limit`
- **THEN** the response SHALL contain that single source's metadata (`Source` model with engagement), Reader summary (if available), and up to 200 highlights with their `note` fields, tags, and `highlighted_at` timestamps

#### Scenario: Topic-first invocation defaults to 30 across sources

- **WHEN** `writing_material(topic="compound interest")` is invoked with no explicit `limit`
- **THEN** the response SHALL contain up to 30 highlights matching the topic, grouped by source under `grouped_by_source`
- **AND** the response SHALL contain `sources` (deduplicated list of source titles represented)

#### Scenario: Source has more than 200 highlights

- **WHEN** the requested source has 500 highlights and `limit` is not specified
- **THEN** the response SHALL contain 200 highlights (the safety cap)
- **AND** the response SHALL include a flag or count indicating that the source has more highlights than were returned

#### Scenario: Both source and topic provided

- **WHEN** the tool is invoked with both `source` and `topic`
- **THEN** the tool SHALL raise a validation error indicating exactly one is required

#### Scenario: Neither source nor topic provided

- **WHEN** the tool is invoked with neither argument
- **THEN** the tool SHALL raise a validation error

### Requirement: Source identifier accepts three forms

When `source` is provided, it SHALL accept one of: a `BookId` (integer, v2 book id), a `DocId` (string, v3 document UUID), or a `TitleSearch` (string, fuzzy title match). The tool SHALL route to the correct lookup path based on which form is supplied.

#### Scenario: BookId integer

- **WHEN** `source=BookId(60028133)`
- **THEN** the tool SHALL look up the v2 book and join with v3 document if available

#### Scenario: DocId string

- **WHEN** `source=DocId("01kq6xmbv7922ranv0p1qa214m")`
- **THEN** the tool SHALL look up the v3 document and join with v2 book if highlights exist

#### Scenario: TitleSearch with single match

- **WHEN** `source=TitleSearch("Antifragile")` matches exactly one source in the engagement index
- **THEN** the tool SHALL return that source's bundle

#### Scenario: TitleSearch with multiple matches

- **WHEN** `source=TitleSearch("AI")` matches multiple sources
- **THEN** the tool SHALL raise an error listing the candidate matches with their IDs so the caller can disambiguate

### Requirement: Engagement floor as the filter

When `topic` is provided, the response SHALL only include highlights from sources whose `EngagementScore.raw >= min_engagement`. The default floor SHALL be 0.7 (the threshold for `"highlighted"` base layer).

#### Scenario: Default floor 0.7 excludes saved-only

- **WHEN** `writing_material(topic="x")` is invoked with default `min_engagement=0.7`
- **THEN** the response SHALL NOT include highlights from sources with `base_layer in {"saved_cold", "saved_warm", "reading"}`

#### Scenario: Lowered floor includes legacy

- **WHEN** `writing_material(topic="x", min_engagement=0.4)` is invoked
- **THEN** sources with `base_layer="legacy"` and engagement ≥0.4 SHALL be eligible for inclusion

#### Scenario: Floor too high to match

- **WHEN** `min_engagement` is set above any source's engagement (e.g. `min_engagement=10.0`)
- **THEN** the response SHALL contain an empty highlight list rather than raising an error

### Requirement: Grouping by source for topic queries

For topic-first invocations, the response SHALL include a `grouped_by_source: dict[str, list[Highlight]]` mapping (where the key is the source title) and a `sources: list[Source]` (the distinct sources represented, in score order).

#### Scenario: Multiple sources match

- **WHEN** `writing_material(topic="stoicism")` returns highlights from three different books
- **THEN** `grouped_by_source` SHALL contain three keys, one per book
- **AND** `sources` SHALL contain three `Source` entries

#### Scenario: Single source matches

- **WHEN** `writing_material(topic="x")` returns highlights from only one source
- **THEN** `grouped_by_source` SHALL contain exactly one key
- **AND** `sources` SHALL contain exactly one entry

### Requirement: Convenience flags on the response

Every `WritingMaterial` response SHALL include `has_notes: bool` (true if any returned highlight has a non-empty `note`) and `has_legacy: bool` (true if any returned `Source` is `is_legacy=True`).

#### Scenario: At least one note

- **WHEN** any returned highlight has a non-empty `note` field
- **THEN** `has_notes` SHALL be `True`

#### Scenario: No notes anywhere

- **WHEN** every returned highlight has an empty or null `note` field
- **THEN** `has_notes` SHALL be `False`

#### Scenario: Legacy source represented

- **WHEN** any returned `Source` has `is_legacy=True`
- **THEN** `has_legacy` SHALL be `True` (signaling that some material comes from pre-Reader-era sources)
