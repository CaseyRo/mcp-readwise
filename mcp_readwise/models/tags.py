"""Pydantic models for tag responses."""

from __future__ import annotations

from pydantic import BaseModel


class TagResult(BaseModel):
    id: int
    name: str
