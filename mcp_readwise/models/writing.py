"""Pydantic models for the writing_material tool."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator

from mcp_readwise.models.source import Source


class HighlightInMaterial(BaseModel):
    """A highlight enriched with the context an LLM needs to draft from it."""

    id: int
    text: str = ""
    note: str = ""
    tags: list[str] = []
    highlighted_at: str = ""
    is_favorite: bool = False
    book_id: Optional[int] = None
    book_title: str = ""
    book_author: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            if field is not None:
                annotation = str(field.annotation)
                if "Optional" in annotation or "None" in annotation:
                    return v
                if field.default is not None:
                    return field.default
        return v


class WritingMaterial(BaseModel):
    """Bundle of highlights + sources for drafting from Readwise content.

    Source-first invocation: one entry in `sources`, all highlights from
    that source in `highlights` (and `grouped_by_source[source.title]`),
    with `summary` populated from the Reader v3 document if available.

    Topic-first invocation: multiple entries in `sources`, highlights
    aggregated, also surfaced via `grouped_by_source`. `summary` empty.
    """

    sources: list[Source] = []
    highlights: list[HighlightInMaterial] = []
    grouped_by_source: dict[str, list[HighlightInMaterial]] = {}
    summary: str = ""
    has_notes: bool = False
    has_legacy: bool = False
    has_more: bool = False
    total_highlights: int = 0
