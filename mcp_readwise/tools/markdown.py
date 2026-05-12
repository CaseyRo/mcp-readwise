"""save_markdown — convert markdown to Reader-ready HTML and save to Readwise."""

from __future__ import annotations

from typing import Literal, Optional

from mcp_readwise.client import client
from mcp_readwise.markdown_render import resolve_metadata, synthetic_url
from mcp_readwise.models.reader import ReaderDocument

ReaderCategory = Literal[
    "article", "email", "rss", "highlight", "note",
    "pdf", "epub", "tweet", "video",
]
ReaderLocation = Literal["new", "later", "shortlist", "archive"]


async def save_markdown(
    markdown: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[list[str]] = None,
    location: ReaderLocation = "new",
    category: ReaderCategory = "epub",
    published_date: Optional[str] = None,
    image_url: Optional[str] = None,
    note: Optional[str] = None,
) -> ReaderDocument:
    """Save a markdown document to Readwise Reader as rendered HTML (sync).

    For a real EPUB with TOC, chapter navigation, and downloadable EPUB
    export from Reader, use `save_markdown_as_epub` instead — this tool
    posts HTML with a `category="epub"` UI hint, which is lighter-weight
    but is not a true EPUB file.

    Use this for content you own — notes, drafts, distilled summaries,
    briefings — that you want to read in Reader's long-form view. For
    saving a public URL (where Reader fetches and parses), use `save_url`.

    The markdown body is rendered to clean HTML and posted to Reader with
    `should_clean_html=false` so the structure is preserved. The default
    `category="epub"` gives the chapter-style reader UX; override to
    `"article"`, `"note"`, etc. as appropriate.

    Frontmatter is supported. Begin the markdown with `---` to pass
    metadata inline:

        ---
        title: My Note
        author: Casey
        tags: [research, draft]
        summary: A brief note on something.
        ---
        # Body starts here

    Explicit parameters override frontmatter. If no title is provided
    via either, the first `# H1` in the body is used; otherwise the
    title falls back to "Untitled".

    The `source_url` of the resulting document is a synthetic stable hash
    of (title, body) — re-uploading identical content updates the same
    Reader entry instead of duplicating it.
    """
    metadata, html, body = resolve_metadata(
        markdown,
        title=title,
        author=author,
        summary=summary,
        tags=tags,
        published_date=published_date,
        image_url=image_url,
    )

    url = synthetic_url(metadata["title"], body)

    payload: dict = {
        "url": url,
        "html": html,
        "should_clean_html": False,
        "category": category,
        "location": location,
        "title": metadata["title"],
        "saved_using": "mcp-readwise",
    }
    if metadata["author"]:
        payload["author"] = metadata["author"]
    if metadata["summary"]:
        payload["summary"] = metadata["summary"]
    if metadata["tags"]:
        payload["tags"] = metadata["tags"]
    if metadata.get("published_date"):
        payload["published_date"] = metadata["published_date"]
    if metadata.get("image_url"):
        payload["image_url"] = metadata["image_url"]
    if note:
        payload["notes"] = note

    data = await client.post("/api/v3/save/", **payload)

    doc_tags = []
    if isinstance(data.get("tags"), dict):
        doc_tags = list(data["tags"].keys())
    elif isinstance(data.get("tags"), list):
        doc_tags = [
            t.get("name", t) if isinstance(t, dict) else str(t)
            for t in data["tags"]
        ]

    return ReaderDocument(
        id=str(data.get("id", "")),
        title=data.get("title", metadata["title"]),
        author=data.get("author", metadata["author"]),
        source_url=data.get("source_url", url),
        category=data.get("category", category),
        location=data.get("location", location),
        reading_progress=0.0,
        summary=data.get("summary", metadata["summary"]),
        tags=doc_tags or metadata["tags"],
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        saved_at=data.get("saved_at", ""),
    )
