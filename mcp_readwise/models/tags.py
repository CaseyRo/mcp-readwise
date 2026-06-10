"""Pydantic models for tag responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TagResult(BaseModel):
    # Hardened per the mcp-zernio guard: extra="allow" + optional error so a
    # future error-shaped element still validates against the published schema.
    model_config = ConfigDict(extra="allow")

    id: int = 0
    name: str = ""
    error: Optional[str] = None
