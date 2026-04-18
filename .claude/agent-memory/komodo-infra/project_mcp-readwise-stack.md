---
name: mcp-readwise Komodo stack
description: Deployment config for the git-mcp-readwise stack on ubuntu-smurf-mirror
type: project
---

Stack `git-mcp-readwise` deployed on ubuntu-smurf-mirror (100.118.241.89) via Komodo. Source: github.com/CaseyRo/mcp-readwise, branch main, file_paths: compose.yaml.

**Why:** Replaces the older `readwise-mcp-server-werkstatt` stack on werkstatt-1 with a git-tracked, auto-pull stack on ubuntu-smurf-mirror behind Cloudflare MCP Portal.

**How to apply:** When referencing the mcp-readwise service, use `git-mcp-readwise` (ubuntu-smurf-mirror) — not the older werkstatt-1 stack. Port mapping is 8010:8000. Public URL: https://mcp-readwise.cdit-dev.de/mcp.

Komodo variables used:
- `READWISE_TOKEN` (secret) — Readwise API token from 1Password "terminal access/MCP Readwise API Key"
- `MCP_READWISE_API_KEY` (secret) — bearer token for Cloudflare MCP Portal auth

Stack environment injects: READWISE_TOKEN, MCP_API_KEY (from MCP_READWISE_API_KEY), MCP_READWISE_PUBLIC_URL.
