"""Configuration loaded from environment variables."""

from __future__ import annotations

import logging
import warnings
from typing import Any, Literal

from pydantic import SecretStr, field_validator, model_validator
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
    mcp_api_key: SecretStr = SecretStr("")

    # Engagement index
    engagement_index_ttl_seconds: int = 1800  # 30 minutes
    engagement_tag_denylist: str = ""  # comma-separated; empty = use defaults

    # EPUB sender (save_markdown_as_epub) — lazy validation; empty defaults
    # let the rest of the server boot without these set.
    readwise_library_email: str = ""
    resend_api_key: SecretStr = SecretStr("")
    epub_from_address: str = ""
    smtp_host: str = "smtp.resend.com"
    smtp_port: int = 587
    epub_lang: str = "en"
    # 20 MiB ceiling. Readwise email-ingest caps at 30 MB total email size;
    # base64 encoding inflates binary by ~33% and MIME adds ~1 MB overhead, so
    # 20 MiB raw EPUB ≈ 27.4 MB on the wire — fits with margin. Resend's own
    # cap is 40 MB, so Readwise is the binding constraint.
    epub_max_bytes: int = 20_971_520

    model_config = {"env_prefix": "", "case_sensitive": False}

    @property
    def epub_sender_configured(self) -> bool:
        """True only when all three required EPUB-sender fields are set."""
        return bool(
            self.readwise_library_email
            and self.resend_api_key.get_secret_value()
            and self.epub_from_address
        )

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

    @model_validator(mode="after")
    def require_api_key_for_http(self) -> "Settings":
        if self.transport == "http" and not self.mcp_api_key.get_secret_value():
            raise ValueError(
                "MCP_API_KEY is required when TRANSPORT=http. "
                "Set the MCP_API_KEY environment variable."
            )
        return self

    def model_post_init(self, __context: Any) -> None:
        if not self.readwise_token.get_secret_value():
            warnings.warn(
                "READWISE_TOKEN is not set. API calls to Readwise will fail.",
                stacklevel=2,
            )


settings = Settings()
