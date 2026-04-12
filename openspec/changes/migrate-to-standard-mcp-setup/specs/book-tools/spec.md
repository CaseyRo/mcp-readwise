## ADDED Requirements

### Requirement: List books with category and annotation filters
The system SHALL provide a `list_books` tool that accepts optional filters: `category` (Literal: `books`, `articles`, `tweets`, `podcasts`, `supplementals`), `source` (string), `num_highlights_gte` (int, minimum highlight count), `updated_after` (ISO 8601), `page` (default 1), `limit` (1-100, default 50). Results SHALL use the standard pagination envelope.

#### Scenario: List all books
- **WHEN** the LLM calls `list_books` with no filters
- **THEN** the system returns the first 50 books with `title`, `author`, `category`, `source`, `num_highlights`, `cover_image_url`, `source_url`, plus `total` and `next_page`

#### Scenario: Filter by category and annotation density
- **WHEN** the LLM calls `list_books` with `category="books"` and `num_highlights_gte=10`
- **THEN** only books (not articles/tweets/etc.) with at least 10 highlights are returned

#### Scenario: Filter by source
- **WHEN** the LLM calls `list_books` with `source="kindle"`
- **THEN** only books imported from Kindle are returned

### Requirement: Get book by ID
The system SHALL provide a `get_book` tool that accepts `book_id` (int) and returns the full book object including `title`, `author`, `category`, `source`, `num_highlights`, `cover_image_url`, `source_url`, `created_at`, `updated_at`.

#### Scenario: Retrieve specific book
- **WHEN** the LLM calls `get_book` with `book_id=12345`
- **THEN** the system returns the complete book metadata object
