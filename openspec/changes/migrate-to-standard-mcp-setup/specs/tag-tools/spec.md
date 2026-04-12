## ADDED Requirements

### Requirement: List all tags
The system SHALL provide a `list_tags` tool that returns all tags with their `id` and `name`. No pagination required (tag lists are typically small).

#### Scenario: Retrieve all tags
- **WHEN** the LLM calls `list_tags`
- **THEN** the system returns all tags as a list of `{"id": int, "name": str}` objects

### Requirement: Create tag
The system SHALL provide a `create_tag` tool that accepts `name` (string, required) and returns the created tag object with `id` and `name`.

#### Scenario: Create new tag
- **WHEN** the LLM calls `create_tag` with `name="must-revisit"`
- **THEN** the system creates the tag and returns `{"id": 456, "name": "must-revisit"}`

### Requirement: Delete tag
The system SHALL provide a `delete_tag` tool that accepts `tag_id` (int, required) and returns a deletion confirmation.

#### Scenario: Delete existing tag
- **WHEN** the LLM calls `delete_tag` with `tag_id=456`
- **THEN** the system deletes the tag and returns `{"deleted": true, "id": 456}`

### Requirement: Add or remove tag on highlight
The system SHALL provide a `tag_highlight` tool that accepts `highlight_id` (int), `tag` (string), and `action` (Literal: `add`, `remove`). When `action` is `add`, the tag SHALL be created if it does not exist. The tool SHALL return the updated highlight's tag list.

#### Scenario: Add tag to highlight
- **WHEN** the LLM calls `tag_highlight` with `highlight_id=98765`, `tag="key-insight"`, `action="add"`
- **THEN** the system adds the tag (creating it if needed) and returns the highlight's updated tag list

#### Scenario: Remove tag from highlight
- **WHEN** the LLM calls `tag_highlight` with `highlight_id=98765`, `tag="key-insight"`, `action="remove"`
- **THEN** the system removes the tag from the highlight and returns the updated tag list
