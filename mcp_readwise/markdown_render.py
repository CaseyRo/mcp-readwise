"""Markdown → HTML rendering, frontmatter parsing, and synthetic URL hashing.

The `save_markdown` tool composes these helpers; they are kept in a separate
module so they're trivially unit-testable without touching the MCP layer.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import markdown as md_lib

_FRONTMATTER_OPEN = "---\n"
_H1_PATTERN = re.compile(r"^# (.+)$", re.MULTILINE)
_FRONTMATTER_LIST = re.compile(r"^\[(.*)\]$")
_FRONTMATTER_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")

_SYNTHETIC_HOST = "https://mcp-readwise.local/md"
_HASH_BODY_PREFIX = 512
_HASH_LENGTH = 16

_MD_EXTENSIONS = ["extra", "sane_lists", "smarty"]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a YAML-subset frontmatter block from the head of `text`.

    Supports scalar string values and bracketed list-of-strings:
        title: My Note
        tags: [research, draft]

    On any parse failure (no opening fence, no closing fence, malformed line)
    returns `({}, text)` — the entire input is treated as body. Frontmatter is
    a convenience, not a contract.
    """
    if not text.startswith(_FRONTMATTER_OPEN):
        return {}, text

    rest = text[len(_FRONTMATTER_OPEN):]

    # Empty frontmatter block: opening fence immediately followed by closing fence.
    if rest.startswith("---\n"):
        return {}, rest[len("---\n"):]
    if rest == "---":
        return {}, ""

    closing_idx = rest.find("\n---\n")
    if closing_idx == -1:
        if rest.endswith("\n---"):
            closing_idx = len(rest) - len("\n---")
            body_start = len(text)
        else:
            return {}, text
    else:
        body_start = len(_FRONTMATTER_OPEN) + closing_idx + len("\n---\n")

    block = rest[:closing_idx]
    body = text[body_start:]

    metadata: dict[str, Any] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _FRONTMATTER_LINE.match(line)
        if not match:
            # Unparseable line → bail out, treat whole text as body.
            return {}, text
        key, value = match.group(1), match.group(2).strip()
        list_match = _FRONTMATTER_LIST.match(value)
        if list_match:
            inner = list_match.group(1).strip()
            items = [_strip_quotes(p.strip()) for p in inner.split(",") if p.strip()]
            metadata[key] = items
        else:
            metadata[key] = _strip_quotes(value)
    return metadata, body


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def extract_first_h1(body: str) -> str | None:
    """Return the first `# Heading` text in the first 50 lines, or None."""
    head = "\n".join(body.splitlines()[:50])
    match = _H1_PATTERN.search(head)
    if not match:
        return None
    return match.group(1).strip() or None


def render_markdown(body: str) -> str:
    """Render markdown to HTML with the standard extension set.

    A fresh Markdown instance is constructed per call because the parser
    holds state (reference defs, footnotes) between conversions.
    """
    md = md_lib.Markdown(extensions=_MD_EXTENSIONS, output_format="html")
    return md.convert(body)


def synthetic_url(title: str, body: str) -> str:
    """Stable synthetic URL for owned markdown content.

    SHA1 of `title + body[:512]`, truncated to 16 hex chars. The host is
    `mcp-readwise.local` — non-routable, a marker, not a real URL. Re-uploads
    of identical (title, leading body) produce the same URL, so Readwise will
    update-in-place rather than duplicate.
    """
    seed = (title + body[:_HASH_BODY_PREFIX]).encode("utf-8")
    digest = hashlib.sha1(seed, usedforsecurity=False).hexdigest()[:_HASH_LENGTH]
    return f"{_SYNTHETIC_HOST}/{digest}"


def resolve_metadata(
    markdown_text: str,
    *,
    title: str | None = None,
    author: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    published_date: str | None = None,
    image_url: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Run the full resolution pipeline.

    Returns `(metadata, html, body)` where:
      - metadata is the resolved fields (title, author, summary, tags, ...)
      - html is the rendered HTML (frontmatter stripped)
      - body is the post-frontmatter markdown source (for hash computation)

    Resolution order: explicit param > frontmatter > H1 (title only) > default.
    Tags are NOT merged; explicit replaces frontmatter to keep behavior
    predictable.
    """
    frontmatter, body = parse_frontmatter(markdown_text)

    resolved_title = (
        title
        or frontmatter.get("title")
        or extract_first_h1(body)
        or "Untitled"
    )
    resolved_author = author or frontmatter.get("author") or ""
    resolved_summary = summary or frontmatter.get("summary") or ""
    resolved_published = published_date or frontmatter.get("published_date") or None
    resolved_image = image_url or frontmatter.get("image_url") or None

    if tags is not None:
        resolved_tags = list(tags)
    else:
        fm_tags = frontmatter.get("tags")
        resolved_tags = list(fm_tags) if isinstance(fm_tags, list) else []

    html = render_markdown(body)

    metadata: dict[str, Any] = {
        "title": resolved_title,
        "author": resolved_author,
        "summary": resolved_summary,
        "tags": resolved_tags,
    }
    if resolved_published:
        metadata["published_date"] = resolved_published
    if resolved_image:
        metadata["image_url"] = resolved_image

    return metadata, html, body
