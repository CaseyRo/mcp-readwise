"""Pydantic models for the writing_material tool."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp_readwise.models.source import Source


class HighlightInMaterial(BaseModel):
    """A highlight enriched with the context an LLM needs to draft from it."""

    model_config = ConfigDict(extra="allow")

    id: int = 0
    text: str = ""
    note: str = ""
    tags: list[str] = Field(default_factory=list)
    highlighted_at: str = ""
    is_favorite: bool = False
    book_id: Optional[int] = None
    book_title: str = ""
    book_author: str = ""
    error: Optional[str] = None

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

    model_config = ConfigDict(extra="allow")

    sources: list[Source] = Field(default_factory=list)
    highlights: list[HighlightInMaterial] = Field(default_factory=list)
    grouped_by_source: dict[str, list[HighlightInMaterial]] = Field(default_factory=dict)
    summary: str = ""
    has_notes: bool = False
    has_legacy: bool = False
    has_more: bool = False
    total_highlights: int = 0
    error: Optional[str] = None
