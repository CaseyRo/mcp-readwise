"""Pydantic models for tag responses."""

from __future__ import annotations


from pydantic import BaseModel, ConfigDict


class TagResult(BaseModel):
    # extra="allow": an upstream adding a field must not break clients.
    model_config = ConfigDict(extra="allow")

    id: int = 0
    name: str = ""
