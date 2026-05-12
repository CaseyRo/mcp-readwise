## ADDED Requirements

### Requirement: List Reader documents with filters
The system SHALL provide a `list_documents` tool that accepts optional filters: `location` (Literal: `new`, `later`, `shortlist`, `archive`, `feed`), `category` (Literal: `article`, `email`, `rss`, `highlight`, `note`, `pdf`, `epub`, `tweet`, `video`), `updated_after` (ISO 8601), `page` (default 1), `limit` (1-100, default 50). Results SHALL use the standard pagination envelope.

#### Scenario: List inbox documents
- **WHEN** the LLM calls `list_documents` with `location="new"`
- **THEN** the system returns documents in the Reader inbox with `id`, `title`, `author`, `source_url`, `category`, `location`, `reading_progress`, `word_count`, `created_at`

#### Scenario: List all articles
- **WHEN** the LLM calls `list_documents` with `category="article"`
- **THEN** only articles (not PDFs, emails, etc.) are returned across all locations

### Requirement: Get Reader document by ID
The system SHALL provide a `get_document` tool that accepts `document_id` (string) and returns the full document including `title`, `author`, `source_url`, `content` (full HTML or text), `summary`, `reading_progress`, `location`, `tags`, `created_at`, `updated_at`.

#### Scenario: Retrieve document with full content
- **WHEN** the LLM calls `get_document` with `document_id="abc123"`
- **THEN** the system returns the complete document object including its full content

### Requirement: Save URL to Reader
The system SHALL provide a `save_url` tool that accepts `url` (string, required), and optional `title`, `tags` (list), `location` (Literal: `new`, `later`, `shortlist`, `archive`, default `new`), `notes` (string). The tool SHALL return the created document object.

#### Scenario: Save article to inbox
- **WHEN** the LLM calls `save_url` with `url="https://example.com/article"`
- **THEN** the system saves the URL to Reader's inbox and returns the created document with auto-fetched `title`, `author`, etc.

#### Scenario: Save URL with tags and location
- **WHEN** the LLM calls `save_url` with `url="https://example.com/paper"`, `tags=["research"]`, `location="shortlist"`, `notes="Recommended by colleague"`
- **THEN** the system saves the URL to the shortlist with tags and notes attached

### Requirement: Update reading progress
The system SHALL provide an `update_progress` tool that accepts `document_id` (string) and `reading_progress` (float, 0.0 to 1.0). The tool SHALL return the updated document object.

#### Scenario: Mark document as half-read
- **WHEN** the LLM calls `update_progress` with `document_id="abc123"` and `reading_progress=0.5`
- **THEN** the system updates the reading position to 50% and returns the updated document

#### Scenario: Mark document as finished
- **WHEN** the LLM calls `update_progress` with `document_id="abc123"` and `reading_progress=1.0`
- **THEN** the system marks the document as fully read
