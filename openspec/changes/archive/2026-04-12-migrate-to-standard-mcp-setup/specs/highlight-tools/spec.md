## ADDED Requirements

### Requirement: Search highlights with hybrid, semantic, or full-text modes
The system SHALL provide a `search_highlights` tool that accepts a `query` string and a `search_type` parameter with values `semantic`, `fulltext`, or `hybrid` (default: `hybrid`). The tool SHALL support optional filters: `book_id`, `tags` (list), and `limit` (1-100, default 20). Results SHALL include book title, author, and source URL inline with each highlight.

#### Scenario: Hybrid search with default parameters
- **WHEN** the LLM calls `search_highlights` with `query="habit formation"`
- **THEN** the system returns up to 20 highlights matching semantically and by full-text, each including `book_title`, `book_author`, `source_url`, `text`, `note`, `tags`, and `id`

#### Scenario: Filtered search by book
- **WHEN** the LLM calls `search_highlights` with `query="key insight"` and `book_id=12345`
- **THEN** only highlights from that specific book are returned

#### Scenario: Semantic-only search
- **WHEN** the LLM calls `search_highlights` with `query="productivity systems"` and `search_type="semantic"`
- **THEN** the system uses only vector search, no full-text matching

### Requirement: List highlights with pagination and filters
The system SHALL provide a `list_highlights` tool that returns highlights filtered by optional `book_id`, `tag`, `updated_after` (ISO 8601), with `page` (default 1) and `limit` (1-100, default 50). Results SHALL use the standard pagination envelope with `results`, `total`, and `next_page`.

#### Scenario: List all highlights paginated
- **WHEN** the LLM calls `list_highlights` with no filters
- **THEN** the system returns the first 50 highlights with `total` count and `next_page` if more exist

#### Scenario: Filter by tag and date
- **WHEN** the LLM calls `list_highlights` with `tag="important"` and `updated_after="2024-01-01"`
- **THEN** only highlights tagged "important" and updated after that date are returned

### Requirement: Get highlight by ID
The system SHALL provide a `get_highlight` tool that accepts a `highlight_id` (int) and returns the full highlight with joined book metadata.

#### Scenario: Retrieve specific highlight
- **WHEN** the LLM calls `get_highlight` with `highlight_id=98765`
- **THEN** the system returns the highlight including `text`, `note`, `tags`, `book_title`, `book_author`, `source_url`, `created_at`, `updated_at`

### Requirement: Create highlight
The system SHALL provide a `create_highlight` tool that accepts `text` (required), `book_id` (required), `note` (optional), and `tags` (optional list). The tool SHALL return the full created highlight object.

#### Scenario: Create highlight with note
- **WHEN** the LLM calls `create_highlight` with `text="The key to success..."`, `book_id=123`, `note="Important insight"`
- **THEN** the system creates the highlight and returns the complete object including generated `id` and timestamps

### Requirement: Update highlight
The system SHALL provide an `update_highlight` tool that accepts `highlight_id` (required) and optional fields `text`, `note`. The tool SHALL return the full updated highlight object.

#### Scenario: Update highlight note
- **WHEN** the LLM calls `update_highlight` with `highlight_id=98765` and `note="Revised note"`
- **THEN** the system updates only the note field and returns the complete updated highlight

### Requirement: Delete highlight
The system SHALL provide a `delete_highlight` tool that accepts `highlight_id` (required) and returns a confirmation with the deleted highlight's ID.

#### Scenario: Delete existing highlight
- **WHEN** the LLM calls `delete_highlight` with `highlight_id=98765`
- **THEN** the system deletes the highlight and returns `{"deleted": true, "id": 98765}`

### Requirement: Export highlights in bulk with cursor pagination
The system SHALL provide an `export_highlights` tool that accepts optional `updated_after` (ISO 8601), `book_ids` (list of int), and `cursor` (string). Results SHALL use cursor-based pagination with `results`, `next_cursor`. Each result SHALL include full highlight text with book metadata attached.

#### Scenario: Initial export
- **WHEN** the LLM calls `export_highlights` with no parameters
- **THEN** the system returns the first page of exported highlights with `next_cursor` if more pages exist

#### Scenario: Continued export with cursor
- **WHEN** the LLM calls `export_highlights` with `cursor="abc123"`
- **THEN** the system returns the next page of results starting from that cursor position
