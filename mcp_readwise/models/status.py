"""Pydantic models for the reading_status snapshot."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from mcp_readwise.models.source import Source


class ThisWindow(BaseModel):
    """Recent activity within the configured window, bucketed by status."""

    finished: list[Source] = []
    in_progress: list[Source] = []
    saved_only: list[Source] = []
    top_engaged: list[Source] = []

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            return []
        return v


class JunkDrawer(BaseModel):
    """Saved-but-untouched sources older than the grace window."""

    count: int = 0
    examples: list[Source] = []

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class SignalDensity(BaseModel):
    """Corpus-shape signals — raw numbers, no pre-baked maturity label."""

    sources_count: int = 0
    total_highlights: int = 0
    tags_per_highlight: float = 0.0
    notes_per_highlight: float = 0.0
    year_span: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class ReadingStatus(BaseModel):
    """Single-call snapshot of the user's relationship with their library."""

    this_window: ThisWindow = ThisWindow()
    evergreen_top: list[Source] = []
    current_top: list[Source] = []
    junk_drawer: JunkDrawer = JunkDrawer()
    signal_density: SignalDensity = SignalDensity()
    window_days: int = 7
    week_offset: int = 0
