"""Configuration loaded from environment variables."""

from __future__ import annotations

import logging
import warnings
from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Readwise API connection
    readwise_token: SecretStr = SecretStr("")
    readwise_base_url: str = "https://readwise.io"

    # Server transport
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000

    # Bearer token auth for MCP Portal
    mcp_api_key: str = ""

    model_config = {"env_prefix": "", "case_sensitive": False}

    @field_validator("readwise_base_url")
    @classmethod
    def validate_readwise_url(cls, v: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("READWISE_BASE_URL must use http or https scheme")
        if not parsed.hostname:
            raise ValueError("READWISE_BASE_URL must have a hostname")
        return v.rstrip("/")

    def model_post_init(self, __context: Any) -> None:
        if not self.readwise_token.get_secret_value():
            warnings.warn(
                "READWISE_TOKEN is not set. API calls to Readwise will fail.",
                stacklevel=2,
            )


settings = Settings()
