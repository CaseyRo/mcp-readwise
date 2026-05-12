"""Tests for the EPUB render module."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_readwise.epub_render import (
    EpubGenerationError,
    EpubTooLargeError,
    _build_metadata_yaml,
    _resolve_cover,
    _safe_filename,
    render_epub,
)


class TestBuildMetadataYaml:
    def test_uuid_identifier_when_no_key(self):
        yaml, scheme = _build_metadata_yaml({"title": "T"}, None)
        assert scheme == "uuid"
        match = re.search(r'text: "([0-9a-f-]{36})"', yaml)
        assert match is not None
        # Valid uuid4 format
        assert len(match.group(1).split("-")) == 5

    def test_fresh_uuid_per_call(self):
        a, _ = _build_metadata_yaml({"title": "T"}, None)
        b, _ = _build_metadata_yaml({"title": "T"}, None)
        a_id = re.search(r'text: "([^"]+)"', a).group(1)
        b_id = re.search(r'text: "([^"]+)"', b).group(1)
        assert a_id != b_id

    def test_idempotency_key_produces_stable_identifier(self):
        yaml_a, scheme_a = _build_metadata_yaml({"title": "T"}, "my-key")
        yaml_b, scheme_b = _build_metadata_yaml({"title": "T"}, "my-key")
        assert scheme_a == "x-mcp-readwise-idempotency"
        assert scheme_b == "x-mcp-readwise-idempotency"
        id_a = re.search(r'text: "([^"]+)"', yaml_a).group(1)
        id_b = re.search(r'text: "([^"]+)"', yaml_b).group(1)
        assert id_a == id_b == "epub-key-my-key"

    def test_metadata_fields_included(self):
        yaml, _ = _build_metadata_yaml(
            {
                "title": "My Title",
                "author": "Casey",
                "summary": "A summary.",
                "tags": ["a", "b"],
                "published_date": "2026-05-12",
            },
            None,
        )
        assert 'title: "My Title"' in yaml
        assert 'creator: "Casey"' in yaml
        assert 'date: "2026-05-12"' in yaml
        assert '"a"' in yaml and '"b"' in yaml
        assert 'publisher: "CDiT Works"' in yaml

    def test_note_appended_to_description(self):
        yaml, _ = _build_metadata_yaml(
            {"title": "T", "summary": "S", "note": "N"},
            None,
        )
        # Both summary and note end up in description
        assert 'description: "S — N"' in yaml

    def test_yaml_escape_handles_quotes(self):
        yaml, _ = _build_metadata_yaml(
            {"title": 'Has "quotes" inside'},
            None,
        )
        assert r'title: "Has \"quotes\" inside"' in yaml


class TestSafeFilename:
    def test_basic_slug(self):
        assert _safe_filename("My Document") == "my-document.epub"

    def test_strips_non_ascii(self):
        # German umlauts are stripped (ascii ignore), then the remaining gap
        # between words collapses through the slug regex.
        assert _safe_filename("Über Müller") == "ber-mller.epub"

    def test_collapses_special_characters(self):
        assert _safe_filename("a/b\\c:d*e") == "a-b-c-d-e.epub"

    def test_max_length_cap(self):
        long_title = "x" * 200
        result = _safe_filename(long_title)
        # 80-char slug + ".epub"
        assert len(result) <= 85
        assert result.endswith(".epub")

    def test_fallback_when_empty(self):
        assert _safe_filename("***") == "document.epub"
        assert _safe_filename("") == "document.epub"


class TestResolveCover:
    @pytest.mark.asyncio
    async def test_none_url_returns_none(self):
        result = await _resolve_cover(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_image_download(self, tmp_path, monkeypatch):
        # Mock httpx response
        class FakeResp:
            status_code = 200
            content = b"\x89PNG\r\n\x1a\nfakebody"
            headers = {"content-type": "image/png"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, follow_redirects=True):
                return FakeResp()

        monkeypatch.setattr("mcp_readwise.epub_render.httpx.AsyncClient", FakeClient)
        result = await _resolve_cover("https://example.com/cover.png")
        assert result is not None
        assert result.exists()
        assert result.suffix == ".png"
        # Cleanup
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self, monkeypatch):
        class FakeResp:
            status_code = 404
            content = b""
            headers = {"content-type": "image/png"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, follow_redirects=True):
                return FakeResp()

        monkeypatch.setattr("mcp_readwise.epub_render.httpx.AsyncClient", FakeClient)
        result = await _resolve_cover("https://example.com/missing.png")
        assert result is None

    @pytest.mark.asyncio
    async def test_non_image_content_type_returns_none(self, monkeypatch):
        class FakeResp:
            status_code = 200
            content = b"<html>"
            headers = {"content-type": "text/html"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, follow_redirects=True):
                return FakeResp()

        monkeypatch.setattr("mcp_readwise.epub_render.httpx.AsyncClient", FakeClient)
        result = await _resolve_cover("https://example.com/page.html")
        assert result is None


class TestRenderEpub:
    @pytest.mark.asyncio
    async def test_pandoc_invocation_args_include_css_and_metadata(self, monkeypatch):
        captured = {}

        def fake_convert_text(text, to, format, extra_args, outputfile):
            captured["text"] = text
            captured["to"] = to
            captured["extra_args"] = extra_args
            # Write a tiny stub EPUB so the size check passes
            Path(outputfile).write_bytes(b"PK\x03\x04stub-epub-bytes")

        monkeypatch.setattr(
            "mcp_readwise.epub_render.pypandoc.convert_text", fake_convert_text
        )
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: True
        )

        epub_bytes, scheme = await render_epub(
            "# Hello\n\nBody.",
            {"title": "Hello", "tags": []},
            None,
            None,
        )

        assert epub_bytes.startswith(b"PK\x03\x04")
        assert scheme == "uuid"
        assert any(a.startswith("--css=") for a in captured["extra_args"])
        assert any(a.startswith("--metadata-file=") for a in captured["extra_args"])
        # Cover NOT passed when cover_path is None
        assert not any(a.startswith("--epub-cover-image=") for a in captured["extra_args"])

    @pytest.mark.asyncio
    async def test_pandoc_invocation_includes_cover_when_provided(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        def fake_convert_text(text, to, format, extra_args, outputfile):
            captured["extra_args"] = extra_args
            Path(outputfile).write_bytes(b"PK\x03\x04stub")

        monkeypatch.setattr(
            "mcp_readwise.epub_render.pypandoc.convert_text", fake_convert_text
        )
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: True
        )

        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

        await render_epub("# T\n\nBody.", {"title": "T", "tags": []}, cover, None)

        assert any(
            a == f"--epub-cover-image={cover}" for a in captured["extra_args"]
        )

    @pytest.mark.asyncio
    async def test_pandoc_invocation_embeds_fonts(self, monkeypatch):
        captured = {}

        def fake_convert_text(text, to, format, extra_args, outputfile):
            captured["extra_args"] = extra_args
            Path(outputfile).write_bytes(b"PK\x03\x04stub")

        monkeypatch.setattr(
            "mcp_readwise.epub_render.pypandoc.convert_text", fake_convert_text
        )
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: True
        )

        await render_epub("# T", {"title": "T", "tags": []}, None, None)

        font_args = [
            a for a in captured["extra_args"] if a.startswith("--epub-embed-font=")
        ]
        # Six Inter woff2 files (400/700/800 × latin/latin-ext)
        assert len(font_args) == 6
        joined = " ".join(font_args)
        assert "inter-400-latin.woff2" in joined
        assert "inter-800-latin-ext.woff2" in joined

    @pytest.mark.asyncio
    async def test_oversize_raises(self, monkeypatch):
        def fake_convert_text(text, to, format, extra_args, outputfile):
            # Write 25 MiB to blow the 20 MiB ceiling
            Path(outputfile).write_bytes(b"x" * (25 * 1024 * 1024))

        monkeypatch.setattr(
            "mcp_readwise.epub_render.pypandoc.convert_text", fake_convert_text
        )
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: True
        )

        with pytest.raises(EpubTooLargeError):
            await render_epub("# T", {"title": "T", "tags": []}, None, None)

    @pytest.mark.asyncio
    async def test_pandoc_unavailable_raises(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: False
        )
        with pytest.raises(EpubGenerationError):
            await render_epub("# T", {"title": "T", "tags": []}, None, None)

    @pytest.mark.asyncio
    async def test_pandoc_runtime_error_wrapped(self, monkeypatch):
        def fake_convert_text(text, to, format, extra_args, outputfile):
            raise RuntimeError("pandoc died horribly")

        monkeypatch.setattr(
            "mcp_readwise.epub_render.pypandoc.convert_text", fake_convert_text
        )
        monkeypatch.setattr(
            "mcp_readwise.epub_render._pandoc_available", lambda: True
        )

        with pytest.raises(EpubGenerationError, match="pandoc failed"):
            await render_epub("# T", {"title": "T", "tags": []}, None, None)
