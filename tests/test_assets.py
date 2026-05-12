"""Tests for the EPUB brand assets shipped with the package."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def _assets_dir() -> Path:
    return Path(str(files("mcp_readwise").joinpath("assets/epub")))


class TestCditStyleCss:
    def test_brand_colors_present(self):
        css = (_assets_dir() / "cdit-style.css").read_text(encoding="utf-8")
        # Carbon, Cloud Dancer, Strong Blue, Mint
        assert "#272f38" in css
        assert "#f0eee9" in css
        assert "#1f5da0" in css
        assert "#5cc6c3" in css

    def test_no_league_gothic_in_body_selectors(self):
        css = (_assets_dir() / "cdit-style.css").read_text(encoding="utf-8")
        # League Gothic must not appear in font-family declarations.
        # It may appear in a comment block at the top of the file (explaining
        # the deliberate omission), but never in a real CSS rule.
        # Strip comments before checking.
        import re
        css_no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        assert "League Gothic" not in css_no_comments

    def test_body_long_form_tuning(self):
        css = (_assets_dir() / "cdit-style.css").read_text(encoding="utf-8")
        # Long-form-tuned body rules
        assert "line-height: 1.7" in css
        assert "text-align: left" in css
        assert "hyphens: auto" in css

    def test_headings_use_inter_not_league_gothic(self):
        css = (_assets_dir() / "cdit-style.css").read_text(encoding="utf-8")
        # The h1, h2, h3 block should reference Inter
        # Find the rule starting "h1, h2, h3"
        idx = css.find("h1, h2, h3")
        assert idx > 0
        # Read the next 500 chars (the rule block)
        block = css[idx : idx + 500]
        assert '"Inter"' in block
        assert "League Gothic" not in block


class TestFontAssets:
    def test_six_inter_static_subsets_exist(self):
        fonts_dir = _assets_dir() / "fonts"
        expected = {
            "inter-400-latin.woff2",
            "inter-400-latin-ext.woff2",
            "inter-700-latin.woff2",
            "inter-700-latin-ext.woff2",
            "inter-800-latin.woff2",
            "inter-800-latin-ext.woff2",
        }
        present = {p.name for p in fonts_dir.glob("*.woff2")}
        assert expected.issubset(present), f"missing: {expected - present}"

    def test_no_inter_variable_woff2(self):
        fonts_dir = _assets_dir() / "fonts"
        names = [p.name.lower() for p in fonts_dir.iterdir()]
        # Variable axis files typically have "variable" or "wght-normal" in the name.
        # The static fontsource files we ship are named inter-{weight}-{subset}.woff2.
        # No file should mention "variable" or contain a multi-weight axis indicator.
        assert not any("variable" in n for n in names)
        assert not any("wght" in n and "normal" in n for n in names)

    def test_no_league_gothic_fonts_in_body_assets(self):
        fonts_dir = _assets_dir() / "fonts"
        names = [p.name.lower() for p in fonts_dir.iterdir()]
        assert not any(n.startswith("league-gothic") for n in names)
        assert not any("leaguegothic" in n for n in names)

    def test_no_jetbrains_mono_fonts_in_body_assets(self):
        fonts_dir = _assets_dir() / "fonts"
        names = [p.name.lower() for p in fonts_dir.iterdir()]
        assert not any(n.startswith("jetbrains-mono") for n in names)
        assert not any("jetbrainsmono" in n for n in names)

    def test_total_font_payload_under_200kb(self):
        """Sanity check on the embedded font cost. Our estimate was ~110–140KB;
        latin-ext pushes us to ~170KB. Cap at 200KB to catch surprise growth."""
        fonts_dir = _assets_dir() / "fonts"
        total = sum(p.stat().st_size for p in fonts_dir.glob("*.woff2"))
        assert total < 200_000, f"font payload {total} bytes exceeds 200KB cap"
