"""Pydantic models for book/source responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int = 0
    title: str = ""
    author: str = ""
    category: str = ""
    source: str = ""
    num_highlights: int = 0
    cover_image_url: str = ""
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    error: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class BookListResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[BookResult] = Field(default_factory=list)
    total: int = 0
    next_page: Optional[int] = None
    error: Optional[str] = None
