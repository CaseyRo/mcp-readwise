## ADDED Requirements

### Requirement: SiYuan documentation page for CDIT MCP server standards
The system SHALL create a documentation page in SiYuan (via `siyuan_create_document` or manual creation) that documents the standard patterns used across all CDIT MCP servers. The document SHALL cover: project structure, required dependencies, configuration patterns, authentication, Docker setup, Komodo deployment, Cloudflare Portal integration, and tool design principles.

#### Scenario: Document covers project structure
- **WHEN** a developer reads the standards doc
- **THEN** they find the standard package layout: `mcp_<name>/` with `server.py`, `config.py`, `client.py`, `auth.py`, `models/`, `tools/`, plus `pyproject.toml`, `compose.yaml`, `Dockerfile`, `komodo.toml`

#### Scenario: Document covers tool naming conventions
- **WHEN** a developer reads the tool design section
- **THEN** they find: snake_case function names without server prefix, Literal types for all enums, pagination envelopes on lists, joined context in responses, sensible defaults, upper-bounded limits

#### Scenario: Document covers deployment pipeline
- **WHEN** a developer reads the deployment section
- **THEN** they find the full pipeline: local dev (stdio) -> Docker (HTTP) -> Komodo stack (git deploy) -> Cloudflare MCP Portal (external HTTPS with bearer auth)

### Requirement: Standards doc references real server examples
The document SHALL reference concrete examples from existing servers (mcp-siyuan, mcp-readwise, mcp-klartext, mcp-things) for each pattern, including file paths and key code snippets.

#### Scenario: Config pattern with real example
- **WHEN** the doc explains the config pattern
- **THEN** it shows the actual `Settings` class from mcp-siyuan or mcp-readwise with `pydantic-settings`, `SecretStr`, and field validators
