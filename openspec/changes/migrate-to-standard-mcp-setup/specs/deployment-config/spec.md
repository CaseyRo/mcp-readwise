## ADDED Requirements

### Requirement: Dockerfile using python:3.12-slim with non-root user
The system SHALL provide a `Dockerfile` based on `python:3.12-slim` that copies `pyproject.toml`, `README.md`, and `mcp_readwise/` into `/app`, installs the package via `pip install --no-cache-dir .`, creates a non-root `mcp` user, exposes port 8000, and includes a health check.

#### Scenario: Build and run container
- **WHEN** `docker build .` is run
- **THEN** the image builds successfully with only production dependencies and runs as the `mcp` user

#### Scenario: Health check passes
- **WHEN** the container is running
- **THEN** the Docker health check hits the `/mcp` endpoint and reports healthy

### Requirement: compose.yaml with standard environment variables
The system SHALL provide a `compose.yaml` file that defines a `mcp-readwise` service with: `TRANSPORT=http`, `HOST=0.0.0.0`, `READWISE_TOKEN` from env, `MCP_API_KEY` from env, `FASTMCP_HOME=/data/fastmcp`, port mapping to internal 8000, memory limit of 512m, and a `fastmcp-data` volume.

#### Scenario: Start with docker compose
- **WHEN** `docker compose up` is run with `READWISE_TOKEN` and `MCP_API_KEY` in the environment
- **THEN** the server starts on the mapped port with HTTP transport and bearer auth enabled

### Requirement: Komodo stack configuration
The system SHALL provide a `komodo.toml` file that defines a stack named `git-mcp-readwise` with: server `ubuntu-smurf-mirror`, git provider `github.com`, repo `CaseyRo/mcp-readwise`, branch `main`, environment variables for `READWISE_TOKEN`, `MCP_API_KEY`, and public URL, and tags `["mcp"]`.

#### Scenario: Deploy via Komodo
- **WHEN** Komodo deploys the stack
- **THEN** it pulls from the GitHub repo, builds the Docker image, and starts the service with the configured environment variables

### Requirement: Cloudflare MCP Portal integration
The system SHALL be reachable via the Cloudflare MCP Portal at a public URL (e.g., `mcp-readwise.cdit-dev.de`). The portal handles TLS termination and forwards requests to the Komodo-deployed service. Authentication is handled by the `MCP_API_KEY` bearer token.

#### Scenario: External access via portal
- **WHEN** a Claude Desktop or MCP client connects to `https://mcp-readwise.cdit-dev.de/mcp`
- **THEN** the portal forwards the request to the internal service and returns the response
