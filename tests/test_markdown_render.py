"""Tests for the markdown render + frontmatter helpers."""

from __future__ import annotations

from mcp_readwise.markdown_render import (
    extract_first_h1,
    parse_frontmatter,
    render_markdown,
    resolve_metadata,
    synthetic_url,
)


class TestParseFrontmatter:
    def test_no_frontmatter(self):
        text = "# Just a body\n\nNo frontmatter."
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_scalar_fields(self):
        text = "---\ntitle: My Note\nauthor: Casey\n---\n# Body"
        meta, body = parse_frontmatter(text)
        assert meta == {"title": "My Note", "author": "Casey"}
        assert body == "# Body"

    def test_list_of_strings(self):
        text = "---\ntags: [research, draft, ideas]\n---\nBody"
        meta, body = parse_frontmatter(text)
        assert meta["tags"] == ["research", "draft", "ideas"]
        assert body == "Body"

    def test_quoted_values(self):
        text = '---\ntitle: "With: a colon"\nauthor: \'Single quoted\'\n---\nBody'
        meta, _ = parse_frontmatter(text)
        assert meta["title"] == "With: a colon"
        assert meta["author"] == "Single quoted"

    def test_no_closing_fence_falls_back_to_body(self):
        text = "---\ntitle: My Note\nauthor: Casey\n# Body"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_malformed_line_falls_back_to_body(self):
        text = "---\nthis is not a kv pair\n---\nBody"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_body_starts_with_dashes_but_no_open(self):
        # A horizontal rule in the body, not at line 1 — should not trigger
        text = "Some text\n\n---\n\nMore text"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_frontmatter_block(self):
        text = "---\n---\nBody"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == "Body"


class TestExtractFirstH1:
    def test_finds_first_h1(self):
        assert extract_first_h1("# Title\n\nbody") == "Title"

    def test_ignores_h2_and_deeper(self):
        assert extract_first_h1("## Subtitle\n\n# Title") == "Title"

    def test_none_when_no_h1(self):
        assert extract_first_h1("Just paragraph text.") is None

    def test_strips_trailing_whitespace(self):
        assert extract_first_h1("#   Spaced Title   ") == "Spaced Title"

    def test_only_scans_first_50_lines(self):
        body = ("blank\n" * 60) + "# Buried Title"
        assert extract_first_h1(body) is None


class TestRenderMarkdown:
    def test_simple_paragraph(self):
        html = render_markdown("Hello, world.")
        assert "<p>Hello, world." in html

    def test_table(self):
        md = "| h1 | h2 |\n|----|----|\n| a  | b  |\n"
        html = render_markdown(md)
        assert "<table>" in html
        assert "<th>h1</th>" in html
        assert "<td>a</td>" in html

    def test_footnote(self):
        md = "Body[^1]\n\n[^1]: A note."
        html = render_markdown(md)
        assert "footnote" in html.lower()
        assert "A note." in html

    def test_fenced_code_with_language(self):
        md = "```python\nprint('hi')\n```"
        html = render_markdown(md)
        assert "<code" in html
        assert "print(" in html


class TestSyntheticUrl:
    def test_stable_for_same_input(self):
        a = synthetic_url("Title", "body content")
        b = synthetic_url("Title", "body content")
        assert a == b

    def test_changes_with_title(self):
        a = synthetic_url("Title A", "body")
        b = synthetic_url("Title B", "body")
        assert a != b

    def test_changes_with_body(self):
        a = synthetic_url("Title", "body A")
        b = synthetic_url("Title", "body B")
        assert a != b

    def test_format(self):
        url = synthetic_url("x", "y")
        assert url.startswith("https://mcp-readwise.local/md/")
        suffix = url.rsplit("/", 1)[-1]
        assert len(suffix) == 16
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_only_first_512_chars_of_body_matter(self):
        prefix = "x" * 512
        a = synthetic_url("t", prefix + "tail-A")
        b = synthetic_url("t", prefix + "tail-B")
        assert a == b


class TestResolveMetadata:
    def test_explicit_title_wins(self):
        md = "---\ntitle: Frontmatter\n---\n# H1\nBody"
        meta, _, _ = resolve_metadata(md, title="Explicit")
        assert meta["title"] == "Explicit"

    def test_frontmatter_title_wins_over_h1(self):
        md = "---\ntitle: Frontmatter\n---\n# H1\nBody"
        meta, _, _ = resolve_metadata(md)
        assert meta["title"] == "Frontmatter"

    def test_h1_wins_when_no_frontmatter(self):
        md = "# From H1\n\nBody"
        meta, _, _ = resolve_metadata(md)
        assert meta["title"] == "From H1"

    def test_untitled_fallback(self):
        meta, _, _ = resolve_metadata("Just paragraph.")
        assert meta["title"] == "Untitled"

    def test_explicit_tags_replace_frontmatter_tags(self):
        md = "---\ntags: [fm-a, fm-b]\n---\nBody"
        meta, _, _ = resolve_metadata(md, tags=["explicit-only"])
        assert meta["tags"] == ["explicit-only"]

    def test_frontmatter_tags_when_no_explicit(self):
        md = "---\ntags: [a, b]\n---\nBody"
        meta, _, _ = resolve_metadata(md)
        assert meta["tags"] == ["a", "b"]

    def test_default_tags_empty(self):
        meta, _, _ = resolve_metadata("Body")
        assert meta["tags"] == []

    def test_html_rendered_from_body_not_frontmatter(self):
        md = "---\ntitle: T\n---\n# H1"
        _, html, body = resolve_metadata(md)
        assert "---" not in html
        assert body == "# H1"
        assert "<h1>H1</h1>" in html

    def test_published_date_from_frontmatter(self):
        md = "---\npublished_date: 2026-05-11\n---\nBody"
        meta, _, _ = resolve_metadata(md)
        assert meta["published_date"] == "2026-05-11"

    def test_explicit_published_date_overrides(self):
        md = "---\npublished_date: 2020-01-01\n---\nBody"
        meta, _, _ = resolve_metadata(md, published_date="2026-05-11")
        assert meta["published_date"] == "2026-05-11"
