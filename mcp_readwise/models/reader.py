"""Pydantic models for Reader document responses."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReadingStatus = Literal["finished", "in_progress", "saved_only"]


class ReaderDocument(BaseModel):
    # extra="allow" + optional error keep BOTH the success and any error-shaped
    # payload valid against the published output_schema (mcp-zernio guard).
    model_config = ConfigDict(extra="allow")

    id: str = ""
    title: str = ""
    author: str = ""
    source_url: str = ""
    category: str = ""
    location: str = ""
    reading_progress: float = 0.0
    word_count: int = 0
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    # Reader v3 engagement fields
    saved_at: str = ""
    first_opened_at: str = ""
    last_opened_at: str = ""
    last_moved_at: str = ""
    # Derived
    reading_status: ReadingStatus = "saved_only"
    error: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def none_to_default(cls, v, info):
        if v is None:
            field = cls.model_fields.get(info.field_name)
            return field.default if field and field.default is not None else v
        return v

    @model_validator(mode="after")
    def derive_reading_status(self) -> "ReaderDocument":
        """Derive reading_status from location and reading_progress.

        Rules (in order):
        1. location == "archive" → "finished" (archive implies user marked done)
        2. reading_progress >= 0.9 → "finished" (PDFs often top out at 0.9)
        3. 0 < reading_progress < 0.9 → "in_progress"
        4. otherwise (progress = 0, location in {new, later, feed, ...}) → "saved_only"
        """
        if self.location == "archive":
            self.reading_status = "finished"
        elif self.reading_progress >= 0.9:
            self.reading_status = "finished"
        elif self.reading_progress > 0:
            self.reading_status = "in_progress"
        else:
            self.reading_status = "saved_only"
        return self


class ReaderListResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[ReaderDocument] = Field(default_factory=list)
    total: int = 0
    next_page: Optional[int] = None
    error: Optional[str] = None


class ReaderListPage(BaseModel):
    """Cursor-paginated page of Reader documents.

    Mirrors the Reader v3 list endpoint shape: `nextPageCursor` is an opaque
    string (or null) returned by the API. Pass it back as `page_cursor` to
    fetch the next page. Distinct from `ReaderListResult` so the internal
    `list_documents` callers aren't broken by changing the pagination model.
    """

    model_config = ConfigDict(extra="allow")

    results: list[ReaderDocument] = Field(default_factory=list)
    count: int = 0
    next_cursor: Optional[str] = None
    error: Optional[str] = None
