"""Pydantic models for the reading_status snapshot."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp_readwise.models.source import Source


class ThisWindow(BaseModel):
    """Recent activity within the configured window, bucketed by status."""

    model_config = ConfigDict(extra="allow")

    finished: list[Source] = Field(default_factory=list)
    in_progress: list[Source] = Field(default_factory=list)
    saved_only: list[Source] = Field(default_factory=list)
    top_engaged: list[Source] = Field(default_factory=list)
    error: Optional[str] = None

    @field_validator("finished", "in_progress", "saved_only", "top_engaged", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            return []
        return v


class JunkDrawer(BaseModel):
    """Saved-but-untouched sources older than the grace window."""

    model_config = ConfigDict(extra="allow")

    count: int = 0
    examples: list[Source] = Field(default_factory=list)
    error: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class SignalDensity(BaseModel):
    """Corpus-shape signals — raw numbers, no pre-baked maturity label."""

    model_config = ConfigDict(extra="allow")

    sources_count: int = 0
    total_highlights: int = 0
    tags_per_highlight: float = 0.0
    notes_per_highlight: float = 0.0
    year_span: int = 0
    error: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class ReadingStatus(BaseModel):
    """Single-call snapshot of the user's relationship with their library."""

    model_config = ConfigDict(extra="allow")

    this_window: ThisWindow = Field(default_factory=ThisWindow)
    evergreen_top: list[Source] = Field(default_factory=list)
    current_top: list[Source] = Field(default_factory=list)
    junk_drawer: JunkDrawer = Field(default_factory=JunkDrawer)
    signal_density: SignalDensity = Field(default_factory=SignalDensity)
    window_days: int = 7
    week_offset: int = 0
    error: Optional[str] = None
