"""Models for the EPUB sender + verifier tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from mcp_readwise.models.reader import ReaderDocument


class EpubSendResult(BaseModel):
    """Result of save_markdown_as_epub.

    `success=True` means the SMTP relay ACCEPTED the message for delivery —
    it is NOT a guarantee the document ingested into Readwise Reader. Reader
    ingest is asynchronous (typically 1–5 min) and cannot be confirmed at
    send time; confirm it separately with verify_epub_received. `success`
    therefore reflects delivery acceptance — the strongest signal detectable
    synchronously — not ingest. `delivery_status` carries the most specific
    terminal state known at return (`"smtp_accepted"`).

    `message_id` is the email's `Message-ID` header (searchable in the Resend
    dashboard), set deliberately by the sender — not a Resend-internal id.

    The recipient field is the FULL library email address — humans
    debugging silent-ingest failures need to verify the routing target.
    Library emails are bearer-credential-grade; rotate the address via
    Readwise settings if it leaks. The threat model deliberately does
    not include "transcript logs leak."
    """

    # extra="allow" + optional error keep BOTH the success and any error-shaped
    # payload valid against the published output_schema (mcp-zernio guard).
    model_config = ConfigDict(extra="allow")

    success: bool = False
    delivery_status: str = ""
    accepted_at: str = ""
    recipient: str = ""
    message_id: str = ""
    file_size_bytes: int = 0
    title: str = ""
    location: str = ""
    identifier_scheme: str = ""
    note: str = ""
    error: Optional[str] = None


class VerifyResult(BaseModel):
    """Result of verify_epub_received.

    `found=True` means a matching Reader document was located. `note`
    carries time-aware guidance for the LLM caller about whether to
    retry or surface a failure to the human.
    """

    model_config = ConfigDict(extra="allow")

    found: bool = False
    document: Optional[ReaderDocument] = None
    note: str = ""
    error: Optional[str] = None
