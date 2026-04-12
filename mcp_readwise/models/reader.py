"""Pydantic models for Reader document responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class ReaderDocument(BaseModel):
    id: str
    title: str = ""
    author: str = ""
    source_url: str = ""
    category: str = ""
    location: str = ""
    reading_progress: float = 0.0
    word_count: int = 0
    summary: str = ""
    content: str = ""
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class ReaderListResult(BaseModel):
    results: list[ReaderDocument]
    total: int
    next_page: Optional[int] = None
