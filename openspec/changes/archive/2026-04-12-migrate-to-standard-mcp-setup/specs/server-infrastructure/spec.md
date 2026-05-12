## ADDED Requirements

### Requirement: FastMCP server with HTTP and stdio transport
The system SHALL instantiate a `FastMCP` server named `"mcp-readwise"` that supports both `stdio` and `http` transport modes, selectable via the `TRANSPORT` environment variable (default: `stdio`). In HTTP mode, the server SHALL bind to the configured `HOST` and `PORT`.

#### Scenario: Start in HTTP mode
- **WHEN** `TRANSPORT=http` is set in the environment
- **THEN** the server starts listening on `HOST:PORT` (default `127.0.0.1:8000`) with the FastMCP HTTP transport

#### Scenario: Start in stdio mode
- **WHEN** `TRANSPORT` is not set or set to `stdio`
- **THEN** the server starts in stdio mode for direct MCP client connections

### Requirement: Configuration via pydantic-settings
The system SHALL use a `Settings` class extending `pydantic_settings.BaseSettings` with the following fields: `readwise_token` (SecretStr, required), `transport` (Literal stdio/http, default stdio), `host` (str, default 127.0.0.1), `port` (int, default 8000), `mcp_api_key` (str, default empty), `readwise_base_url` (str, default https://readwise.io). All fields SHALL be configurable via environment variables.

#### Scenario: Token loaded from environment
- **WHEN** `READWISE_TOKEN` is set in the environment
- **THEN** the `Settings` instance loads it as a `SecretStr` that is redacted in logs and repr

#### Scenario: Missing token warning
- **WHEN** `READWISE_TOKEN` is not set
- **THEN** the system raises a warning at startup (API calls will fail)

### Requirement: Centralized async HTTP client with retries and rate-limit backoff
The system SHALL provide a `ReadwiseClient` class wrapping `httpx.AsyncClient` that handles: base URL routing (v2 for highlights/books/tags, v3 for Reader), `X-Access-Token` header injection, exponential backoff on HTTP 429 responses, up to 3 retries on transient errors (5xx, timeouts), and connection pooling.

#### Scenario: Rate limit handling
- **WHEN** the Readwise API returns HTTP 429
- **THEN** the client waits with exponential backoff and retries, returning a clear error message to the LLM if retries are exhausted

#### Scenario: Transient error retry
- **WHEN** the Readwise API returns HTTP 503
- **THEN** the client retries up to 3 times with backoff before returning an error

#### Scenario: V2 vs V3 routing
- **WHEN** a tool calls `client.get("/api/v2/highlights")`
- **THEN** the client routes to `readwise.io/api/v2/highlights` with the access token header
- **WHEN** a tool calls `client.get("/api/v3/list/")`
- **THEN** the client routes to `readwise.io/api/v3/list/` with the access token header

### Requirement: Bearer token authentication for MCP Portal
The system SHALL support optional bearer token authentication via `MCP_API_KEY` environment variable. When set, all MCP requests MUST include a valid `Authorization: Bearer <token>` header. When not set, authentication is disabled (for local development).

#### Scenario: Valid bearer token
- **WHEN** `MCP_API_KEY` is set and a request includes `Authorization: Bearer <matching-token>`
- **THEN** the request is processed normally

#### Scenario: Missing or invalid token
- **WHEN** `MCP_API_KEY` is set and a request has no token or a wrong token
- **THEN** the server returns HTTP 401 Unauthorized

#### Scenario: Auth disabled
- **WHEN** `MCP_API_KEY` is not set (empty string)
- **THEN** all requests are accepted without authentication

### Requirement: Pydantic response models for all tool outputs
The system SHALL define Pydantic `BaseModel` classes for all tool return types. Every highlight response model SHALL include joined book metadata (`book_title`, `book_author`, `source_url`). All list results SHALL use a pagination envelope with `results`, `total`, and `next_page` or `next_cursor`. Models SHALL validate and constrain field lengths where appropriate.

#### Scenario: Highlight response includes book context
- **WHEN** any highlight tool returns results
- **THEN** each highlight object includes `book_title`, `book_author`, and `source_url` fields populated from the book metadata, not just `book_id`

#### Scenario: Paginated result envelope
- **WHEN** any list or search tool returns results
- **THEN** the response follows the structure `{"results": [...], "total": N, "next_page": int|null}` or `{"results": [...], "next_cursor": str|null}` for cursor-based pagination
