"""Pydantic models for book/source responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class BookResult(BaseModel):
    id: int
    title: str = ""
    author: str = ""
    category: str = ""
    source: str = ""
    num_highlights: int = 0
    cover_image_url: str = ""
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class BookListResult(BaseModel):
    results: list[BookResult]
    total: int
    next_page: Optional[int] = None
