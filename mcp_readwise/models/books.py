"""Pydantic models for book/source responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BookResult(BaseModel):
    id: int
    title: str
    author: str = ""
    category: str = ""
    source: str = ""
    num_highlights: int = 0
    cover_image_url: str = ""
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""


class BookListResult(BaseModel):
    results: list[BookResult]
    total: int
    next_page: Optional[int] = None
