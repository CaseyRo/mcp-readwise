"""Pydantic models for highlight responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class HighlightResult(BaseModel):
    id: int
    text: str = ""
    note: str = ""
    tags: list[str] = []
    book_id: int = 0
    book_title: str = ""
    book_author: str = ""
    source_url: str = ""
    highlighted_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class HighlightListResult(BaseModel):
    results: list[HighlightResult]
    total: int
    next_page: Optional[int] = None


class ExportResult(BaseModel):
    results: list[dict]
    next_cursor: Optional[str] = None
