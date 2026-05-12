"""verify_epub_received — confirm a recently-sent EPUB has landed in Reader."""

from __future__ import annotations

from datetime import datetime, timezone

from mcp_readwise.models.epub import VerifyResult
from mcp_readwise.tools.reader import list_documents


def _elapsed_note(elapsed_seconds: float) -> str:
    """Time-aware retry guidance for the LLM caller when no match was found."""
    if elapsed_seconds < 60:
        return (
            "Too early — Readwise typically ingests within 1–5 minutes. "
            "Retry shortly."
        )
    if elapsed_seconds < 300:
        return "Not yet — ingest pending. Retry in 1–2 minutes."
    if elapsed_seconds < 900:
        return (
            "Late — Readwise ingest usually completes by 5 min. May have failed."
        )
    return (
        "Not found — check SMTP delivery (Resend dashboard) and library email."
    )


def _match(doc_title: str, target: str, fuzzy: bool) -> bool:
    if fuzzy:
        return target.lower() in doc_title.lower()
    return doc_title.strip().lower() == target.strip().lower()


async def verify_epub_received(
    title: str,
    since: str,
    fuzzy: bool = True,
) -> VerifyResult:
    """Confirm a recently-sent EPUB has landed in Readwise Reader's Library.

    Use after save_markdown_as_epub returns: pass `EpubSendResult.title`
    and `EpubSendResult.accepted_at` as `title` and `since` respectively.
    Returns `found=True` with the matching `ReaderDocument` once Readwise
    has ingested the email; otherwise `found=False` with time-aware
    retry guidance in `note`.

    Readwise's email-ingest pipeline typically completes within 1–5
    minutes. If the EPUB hasn't appeared after 15 minutes, the SMTP
    delivery probably failed silently — check the Resend dashboard and
    confirm `READWISE_LIBRARY_EMAIL` is correct.

    This tool does NOT require the EPUB-sender env vars (READWISE_LIBRARY_EMAIL,
    RESEND_API_KEY, EPUB_FROM_ADDRESS). It only needs READWISE_TOKEN,
    which the read-side tools already require.

    `fuzzy=True` (default) matches case-insensitive contains. Set
    `fuzzy=False` for exact (case-insensitive) title equality.
    """
    docs = await list_documents(
        category="epub",
        updated_after=since,
        limit=20,
    )

    for doc in docs.results:
        if _match(doc.title, title, fuzzy):
            return VerifyResult(
                found=True,
                document=doc,
                note="Found in Reader Library.",
            )

    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - since_dt).total_seconds()
    except (ValueError, TypeError):
        elapsed = 0.0

    return VerifyResult(
        found=False,
        document=None,
        note=_elapsed_note(elapsed),
    )
