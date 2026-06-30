"""save_markdown_as_epub — turn markdown into a real EPUB and email it to Readwise Library."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastmcp import Context

from mcp_readwise.config import settings
from mcp_readwise.epub_render import (
    _resolve_cover,
    _safe_filename,
    render_epub,
)
from mcp_readwise.markdown_render import parse_frontmatter, extract_first_h1
from mcp_readwise.models.epub import EpubSendResult
from mcp_readwise.smtp_client import send_epub

ReaderLocation = Literal["new", "later", "shortlist", "archive"]


class ConfigurationError(RuntimeError):
    """Raised when required EPUB-sender env vars are missing."""


_ASYNC_NOTE = (
    "Sent. The SMTP relay accepted the message for delivery — this is NOT "
    "confirmation it ingested into Readwise Reader. The document usually "
    "appears within 1–5 minutes; call verify_epub_received to confirm before "
    "telling the human it is available."
)


def _check_config() -> None:
    """Raise ConfigurationError listing missing env vars; never leak values."""
    missing = []
    if not settings.readwise_library_email:
        missing.append("READWISE_LIBRARY_EMAIL")
    if not settings.resend_api_key.get_secret_value():
        missing.append("RESEND_API_KEY")
    if not settings.epub_from_address:
        missing.append("EPUB_FROM_ADDRESS")
    if missing:
        raise ConfigurationError(
            "save_markdown_as_epub requires env vars: " + ", ".join(missing)
        )


async def save_markdown_as_epub(
    markdown: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[list[str]] = None,
    note: Optional[str] = None,
    cover_image_url: Optional[str] = None,
    published_date: Optional[str] = None,
    location: ReaderLocation = "new",
    idempotency_key: Optional[str] = None,
    ctx: Context | None = None,
) -> EpubSendResult:
    """ASYNC: Returns after SMTP delivery. Document appears in Reader in 1–5 minutes. Do not tell the human the document is available until verify_epub_received confirms it.

    REQUIRES env vars: READWISE_LIBRARY_EMAIL, RESEND_API_KEY, EPUB_FROM_ADDRESS.
    If unconfigured, raises ConfigurationError immediately.

    Renders markdown to a real EPUB 3 via pandoc with CDIT brand styling, then
    emails it as an attachment to the user's Readwise Library address through
    a Resend SMTP relay. Use this for owned content you want to read in
    Reader's true EPUB experience (TOC, chapter nav, EPUB export). For
    URL-based content use `save_url`; for lightweight HTML-as-epub-UX use
    `save_markdown` (synchronous, same-call ReaderDocument back).

    Frontmatter is supported (same parser as save_markdown). Explicit
    parameters override frontmatter; title falls back to first `# H1` and
    finally `"Untitled"`.

    `location` is accepted for parity with save_markdown but is
    informational-only: the email-to-library pipeline always places
    documents in the default Library state. Routing to later/shortlist/
    archive requires a follow-up move call after verify_epub_received
    confirms ingest. The value is echoed on EpubSendResult.location to
    make that follow-up chain explicit.

    `idempotency_key` is the retry-safe-dedup hook: pass a stable string
    (e.g. a SHA-256 of title+body, or a workflow identifier) and the
    EPUB's dc:identifier becomes `epub-key-<key>`. Two sends with the
    same key produce EPUBs Readwise treats as the same logical document,
    so an LLM agent retry won't create duplicate Library entries. Omit
    for one-shot semantics (fresh UUID per call).
    """
    _check_config()

    frontmatter, body = parse_frontmatter(markdown)

    resolved_title = (
        title
        or frontmatter.get("title")
        or extract_first_h1(body)
        or "Untitled"
    )
    resolved_author = author or frontmatter.get("author") or ""
    resolved_summary = summary or frontmatter.get("summary") or ""
    resolved_note = note if note is not None else frontmatter.get("note") or ""
    resolved_published = published_date or frontmatter.get("published_date") or ""
    resolved_cover = cover_image_url or frontmatter.get("image_url") or None

    if tags is not None:
        resolved_tags = list(tags)
    else:
        fm_tags = frontmatter.get("tags")
        resolved_tags = list(fm_tags) if isinstance(fm_tags, list) else []

    metadata = {
        "title": resolved_title,
        "author": resolved_author,
        "summary": resolved_summary,
        "note": resolved_note,
        "tags": resolved_tags,
        "published_date": resolved_published,
    }

    if ctx is not None:
        await ctx.info(f"Rendering EPUB: {resolved_title!r}")
        await ctx.report_progress(progress=0, total=3)

    cover_path = await _resolve_cover(resolved_cover)

    epub_bytes, identifier_scheme = await render_epub(
        body, metadata, cover_path, idempotency_key
    )

    filename = _safe_filename(resolved_title)
    body_text = (
        f"Auto-generated by mcp-readwise.\n\nTitle: {resolved_title}\n"
        f"Sent at: {datetime.now(timezone.utc).isoformat()}\n"
    )
    if ctx is not None:
        await ctx.info(
            f"Rendered {len(epub_bytes)} bytes; delivering to Readwise Library via SMTP"
        )
        await ctx.report_progress(progress=1, total=3)

    send_result = await send_epub(
        from_addr=settings.epub_from_address,
        to_addr=settings.readwise_library_email,
        subject=resolved_title,
        body_text=body_text,
        epub_bytes=epub_bytes,
        filename=filename,
    )

    if ctx is not None:
        await ctx.report_progress(progress=3, total=3)
        await ctx.info(
            "SMTP accepted. Reader ingest is async (1–5 min) — "
            "call verify_epub_received before reporting the document as available."
        )

    # send_epub raises on hard failure (auth, 5xx, refused recipient, retry
    # budget exhausted), so reaching here means the relay accepted the message.
    # That is delivery ACCEPTANCE, not Reader ingest — surface it as such
    # rather than a bare success=True that overclaims ingest (CDI-1311).
    return EpubSendResult(
        success=True,
        delivery_status="smtp_accepted",
        accepted_at=send_result.accepted_at,
        recipient=settings.readwise_library_email,
        message_id=send_result.message_id,
        file_size_bytes=len(epub_bytes),
        title=resolved_title,
        location=location,
        identifier_scheme=identifier_scheme,
        note=_ASYNC_NOTE,
    )
