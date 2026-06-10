"""Guided-workflow prompts for the two signature multi-step jobs.

Registered onto the server via `register_prompts(mcp)` from server.py.

- publish_research_to_reader: the async EPUB pipeline
  (save_markdown_as_epub -> verify_epub_received -> optional move out of inbox).
- draft_from_highlights: the drafting pipeline
  (reading_status / writing_material -> compose).
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """Register all guided-workflow prompts onto the given FastMCP instance."""

    @mcp.prompt(
        name="publish_research_to_reader",
        title="Publish research markdown to Readwise Reader as an EPUB",
        description="Guided async EPUB pipeline: render+send, then verify before reporting done.",
    )
    def publish_research_to_reader(
        title: str,
        topic: Optional[str] = None,
    ) -> str:
        topic_line = (
            f"The document is about: {topic}.\n" if topic else ""
        )
        return (
            f"I want to publish a research document titled {title!r} to my "
            f"Readwise Reader library as a real EPUB.\n{topic_line}\n"
            "Follow this pipeline exactly, and do NOT tell me the document is "
            "available until verification confirms it:\n\n"
            "1. Call `save_markdown_as_epub` with the markdown body (use "
            "frontmatter or explicit args for title/author/tags). Pass a "
            "stable `idempotency_key` so a retry won't create a duplicate. "
            "It returns immediately after SMTP delivery — ingest is async.\n"
            "2. Take `EpubSendResult.title` and `EpubSendResult.accepted_at` "
            "and call `verify_epub_received(title=..., since=...)`. If "
            "`found` is False, wait per the `note` guidance and retry — "
            "Readwise typically ingests within 1–5 minutes.\n"
            "3. Once `found` is True, optionally move it out of the inbox: "
            "the EPUB always lands in the default Library state, so use "
            "`update_progress` or a follow-up to route it to later/shortlist/"
            "archive if I asked for that.\n"
            "4. Only then report the document as available, with its Reader "
            "document id.\n\n"
            "If `save_markdown_as_epub` raises ConfigurationError, the EPUB "
            "sender env vars are unset — tell me which ones are missing."
        )

    @mcp.prompt(
        name="draft_from_highlights",
        title="Draft a piece from my Readwise highlights on a topic",
        description="Guided drafting pipeline: orient via reading_status, gather via writing_material, then compose.",
    )
    def draft_from_highlights(
        topic: str,
        kind: str = "essay",
    ) -> str:
        return (
            f"Help me draft a {kind} about {topic!r} grounded in my own "
            "Readwise highlights and notes.\n\n"
            "Follow this pipeline:\n\n"
            "1. (Optional, for orientation) Call `reading_status` to see what "
            "I've been engaging with recently and which durable interests "
            "(`evergreen_top`) might connect to this topic.\n"
            "2. Call `writing_material(topic=...)` to pull the highlights, "
            "notes, and source bundle for the topic. If you already know the "
            "specific source, use `book_id` / `document_id` / `title_search` "
            "instead for the full single-source set. Lower `min_engagement` "
            "(e.g. 0.4) if the topic returns too little.\n"
            "3. Use the returned `highlights`, `grouped_by_source`, and "
            "`summary` as raw material. Prefer my own notes (where "
            "`has_notes` is true) as the spine of the argument; quote "
            "highlights sparingly and attribute them to their source.\n"
            "4. Draft the piece. Flag any place where I have a thin evidence "
            "base (few highlights, no notes) so I can decide whether to "
            "research more before publishing."
        )
