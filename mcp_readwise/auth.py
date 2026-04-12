"""Bearer token authentication for the MCP server."""

import hmac

from fastmcp.server.auth import AccessToken, TokenVerifier


class BearerTokenVerifier(TokenVerifier):
    """Verify a static bearer token (API key) using timing-safe comparison."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token, self._api_key):
            return AccessToken(token=token, client_id="bearer", scopes=[])
        return None
