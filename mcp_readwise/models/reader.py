"""Pydantic models for Reader document responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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


class ReaderListResult(BaseModel):
    results: list[ReaderDocument]
    total: int
    next_page: Optional[int] = None
