"""Markdown → EPUB rendering via pandoc.

Builds a metadata YAML block, optionally fetches a cover image, then invokes
pandoc with the CDIT brand stylesheet and embedded Inter font subsets.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import uuid
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import httpx
import pypandoc

from mcp_readwise.config import settings

logger = logging.getLogger(__name__)

_PANDOC_MIN_VERSION = (3, 0)
_COVER_FETCH_TIMEOUT = 10.0
_FILENAME_MAX_LEN = 80
_FILENAME_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")
_NOTE_PREFACE_TEMPLATE = (
    '<div class="mcp-note">\n{note}\n</div>\n\n'
)


class EpubGenerationError(RuntimeError):
    """Raised when pandoc fails to produce an EPUB."""


class EpubTooLargeError(RuntimeError):
    """Raised when generated EPUB exceeds the configured size ceiling."""


_pandoc_check_done = False
_pandoc_ok = False


def _pandoc_available() -> bool:
    """Check pandoc binary presence + minimum version. Result cached."""
    global _pandoc_check_done, _pandoc_ok
    if _pandoc_check_done:
        return _pandoc_ok
    _pandoc_check_done = True
    try:
        version_str = pypandoc.get_pandoc_version()
        parts = tuple(int(p) for p in version_str.split(".")[:2])
        _pandoc_ok = parts >= _PANDOC_MIN_VERSION
        if not _pandoc_ok:
            logger.warning(
                "pandoc %s is below minimum %s",
                version_str,
                ".".join(str(p) for p in _PANDOC_MIN_VERSION),
            )
    except (OSError, ValueError) as exc:
        logger.warning("pandoc not available: %s", exc)
        _pandoc_ok = False
    return _pandoc_ok


def _safe_filename(title: str) -> str:
    """Slugify a title into a safe ASCII filename ending in `.epub`."""
    ascii_only = title.encode("ascii", errors="ignore").decode("ascii")
    slug = _FILENAME_SLUG_RE.sub("-", ascii_only).strip("-").lower()
    if not slug:
        slug = "document"
    if len(slug) > _FILENAME_MAX_LEN:
        slug = slug[:_FILENAME_MAX_LEN].rstrip("-")
    return f"{slug}.epub"


def _yaml_escape(value: str) -> str:
    """Minimal YAML scalar escape for double-quoted strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_metadata_yaml(
    metadata: dict[str, Any],
    idempotency_key: str | None,
) -> tuple[str, str]:
    """Produce pandoc YAML metadata + the identifier scheme used.

    Returns (yaml_str, identifier_scheme). When `idempotency_key` is provided,
    the dc:identifier becomes `epub-key-<key>` with scheme
    `x-mcp-readwise-idempotency`; otherwise a fresh uuid4 with scheme `uuid`.
    """
    if idempotency_key:
        identifier_value = f"epub-key-{idempotency_key}"
        identifier_scheme = "x-mcp-readwise-idempotency"
    else:
        identifier_value = str(uuid.uuid4())
        identifier_scheme = "uuid"

    lines = ["---"]
    title = metadata.get("title", "Untitled")
    lines.append(f'title: "{_yaml_escape(title)}"')

    creator = metadata.get("author") or "Casey Romkes"
    lines.append(f'creator: "{_yaml_escape(creator)}"')

    lines.append(f"lang: {settings.epub_lang}")

    if metadata.get("published_date"):
        lines.append(f'date: "{_yaml_escape(metadata["published_date"])}"')

    lines.append('publisher: "CDiT Works"')

    lines.append("identifier:")
    lines.append(f"  - scheme: {identifier_scheme}")
    lines.append(f'    text: "{identifier_value}"')

    description_parts = []
    if metadata.get("summary"):
        description_parts.append(metadata["summary"])
    if metadata.get("note"):
        description_parts.append(metadata["note"])
    if description_parts:
        joined = " — ".join(description_parts)
        lines.append(f'description: "{_yaml_escape(joined)}"')

    tags = metadata.get("tags") or []
    if tags:
        lines.append("subject:")
        for tag in tags:
            lines.append(f'  - "{_yaml_escape(str(tag))}"')

    lines.append("---\n")
    return "\n".join(lines), identifier_scheme


async def _resolve_cover(cover_image_url: str | None) -> Path | None:
    """Download a cover image to a temp file. Returns None on any failure.

    Failure modes (all → None, never raise): timeout, non-200 status,
    non-image content-type, IO error. The send proceeds without a cover.
    """
    if not cover_image_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=_COVER_FETCH_TIMEOUT) as client:
            resp = await client.get(cover_image_url, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(
                    "Cover fetch %s returned %d", cover_image_url, resp.status_code
                )
                return None
            ctype = resp.headers.get("content-type", "").lower()
            if not ctype.startswith("image/"):
                logger.warning(
                    "Cover fetch %s returned non-image content-type %s",
                    cover_image_url,
                    ctype,
                )
                return None
            ext = ctype.split("/")[-1].split(";")[0].strip() or "jpg"
            if ext not in ("jpeg", "jpg", "png", "gif", "webp"):
                ext = "jpg"
            ext = "jpg" if ext == "jpeg" else ext
            fd = tempfile.NamedTemporaryFile(
                suffix=f".{ext}", delete=False
            )
            fd.write(resp.content)
            fd.close()
            return Path(fd.name)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Cover fetch %s failed: %s", cover_image_url, exc)
        return None


def _prepend_note_preface(markdown: str, note: str | None) -> str:
    """Inline an HTML note block at the top of the markdown body.

    Pandoc passes raw HTML through to EPUB output, so the `.mcp-note` div
    lands styled by the brand stylesheet.
    """
    if not note:
        return markdown
    block = _NOTE_PREFACE_TEMPLATE.format(note=note)
    return block + markdown


def _assets_dir() -> Path:
    """Resolve the packaged assets directory on disk.

    Uses importlib.resources so this works from an installed wheel.
    """
    resource = files("mcp_readwise").joinpath("assets/epub")
    # We need a real on-disk path because pandoc reads --css from the filesystem.
    # as_file returns a context-manager-like object; for our use case the assets
    # are flat files in the package, so the resource path resolves directly.
    with as_file(resource) as path:
        return Path(path)


async def render_epub(
    markdown: str,
    metadata: dict[str, Any],
    cover_path: Path | None,
    idempotency_key: str | None,
) -> tuple[bytes, str]:
    """Render markdown to an EPUB 3 binary via pandoc.

    Returns (epub_bytes, identifier_scheme). Raises EpubGenerationError on
    pandoc failure, EpubTooLargeError if the result exceeds the size ceiling.
    """
    if not _pandoc_available():
        raise EpubGenerationError(
            "pandoc is not installed or below minimum version 3.0"
        )

    yaml_str, identifier_scheme = _build_metadata_yaml(metadata, idempotency_key)
    body = _prepend_note_preface(markdown, metadata.get("note"))

    assets = _assets_dir()
    css_path = assets / "cdit-style.css"

    extra_args = [
        f"--css={css_path}",
        "--standalone",
        "--toc",
        "--toc-depth=2",
    ]

    fonts_dir = assets / "fonts"
    for woff2 in sorted(fonts_dir.glob("*.woff2")):
        extra_args.append(f"--epub-embed-font={woff2}")

    if cover_path is not None:
        extra_args.append(f"--epub-cover-image={cover_path}")

    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w", delete=False, encoding="utf-8"
    ) as meta_fd:
        meta_fd.write(yaml_str)
        meta_path = meta_fd.name
    extra_args.append(f"--metadata-file={meta_path}")

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as out_fd:
        out_path = out_fd.name

    try:
        await asyncio.to_thread(
            pypandoc.convert_text,
            body,
            to="epub3",
            format="markdown",
            extra_args=extra_args,
            outputfile=out_path,
        )
    except RuntimeError as exc:
        stderr = str(exc)[:500]
        raise EpubGenerationError(f"pandoc failed: {stderr}") from exc
    finally:
        Path(meta_path).unlink(missing_ok=True)

    epub_bytes = Path(out_path).read_bytes()
    Path(out_path).unlink(missing_ok=True)

    size = len(epub_bytes)
    if size > settings.epub_max_bytes:
        raise EpubTooLargeError(
            f"EPUB is {size} bytes; ceiling is {settings.epub_max_bytes}"
        )

    return epub_bytes, identifier_scheme
