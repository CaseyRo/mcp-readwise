"""Pydantic models for the engagement-aware Source abstraction.

A `Source` unifies a Readwise v2 book with its corresponding Reader v3 document
(when one exists), and carries an `EngagementScore` derived from both.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


BaseLayer = Literal[
    "saved_cold",
    "saved_warm",
    "reading",
    "finished_no_hl",
    "highlighted",
    "legacy",
]


class EngagementScore(BaseModel):
    """Vector engagement score per source.

    The components are decomposable: `raw == intensity + recency + return_strength`
    (within floating-point tolerance). Different views of the corpus rank by
    different components — `current_top` ranks by `raw` (recency-weighted);
    `evergreen_top` ranks by `intensity` (recency removed).
    """

    model_config = ConfigDict(extra="allow")

    raw: float = 0.0
    intensity: float = 0.0
    recency: float = 0.0
    return_strength: float = 0.0
    base_layer: BaseLayer = "saved_cold"
    flags: list[str] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v


class Source(BaseModel):
    """A unified source — v2 book metadata + v3 document metadata + engagement.

    Either `book_id` or `document_id` (or both) is populated. `is_legacy=True`
    indicates a v2-only source (pre-Reader-era Kindle/iBooks/etc imports or
    Reader-era ingestions from non-Reader sources).
    """

    model_config = ConfigDict(extra="allow")

    # Identifiers — at least one populated
    book_id: Optional[int] = None
    document_id: Optional[str] = None

    # Display metadata
    title: str = ""
    author: str = ""
    source_url: str = ""
    category: str = ""

    # v2 signals
    num_highlights: int = 0
    source_field: str = ""  # "reader" | "kindle" | "ibooks" | ...

    # v3 signals (None when no v3 join)
    location: Optional[str] = None
    reading_progress: Optional[float] = None
    saved_at: Optional[str] = None
    first_opened_at: Optional[str] = None
    last_opened_at: Optional[str] = None
    last_moved_at: Optional[str] = None

    # Highlight aggregates (populated by the engagement module)
    last_highlighted_at: Optional[str] = None
    has_user_note: bool = False
    has_user_tag: bool = False
    has_favorite: bool = False

    # Engagement
    engagement: EngagementScore = Field(default_factory=EngagementScore)
    is_legacy: bool = False
    legacy_recency: Optional[Literal["cold", "warm"]] = None
    error: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        # Allow None for explicitly Optional fields; coerce others to default.
        field = cls.model_fields.get(info.field_name)
        if v is None and field is not None:
            annotation = str(field.annotation)
            if "Optional" in annotation or "None" in annotation:
                return v
            if field.default is not None:
                return field.default
        return v
