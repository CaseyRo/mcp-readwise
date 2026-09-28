"""Pydantic models for highlight responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HighlightResult(BaseModel):
    # extra="allow": an upstream adding a field must not break clients.
    model_config = ConfigDict(extra="allow")

    id: int = 0
    text: str = ""
    note: str = ""
    tags: list[str] = Field(default_factory=list)
    book_id: int = 0
    book_title: str = ""
    book_author: str = ""
    source_url: str = ""
    highlighted_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    # First-class booleans (separate from tags per Readwise v2 docs)
    is_favorite: bool = False
    is_discard: bool = False

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class HighlightListResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[HighlightResult] = Field(default_factory=list)
    total: int = 0
    next_page: Optional[int] = None


class DeletionResult(BaseModel):
    """Uniform confirmation for irreversible delete tools.

    `deleted` is always True on success (the underlying API raises on
    failure before this is constructed); `id` echoes the removed entity's
    identifier so the caller can confirm which record was destroyed.
    """

    model_config = ConfigDict(extra="allow")

    deleted: bool = True
    id: int = 0


class ExportResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[dict] = Field(default_factory=list)
    next_cursor: Optional[str] = None

    @field_validator("next_cursor", mode="before")
    @classmethod
    def coerce_cursor_to_str(cls, v):
        if v is not None:
            return str(v)
        return v
