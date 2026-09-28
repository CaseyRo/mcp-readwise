"""__version__ comes from APP_VERSION or package metadata, never a literal."""

import importlib
from importlib.metadata import version

import mcp_readwise


def test_version_from_metadata(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert importlib.reload(mcp_readwise).__version__ == version("mcp-readwise")


def test_app_version_env_wins(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    assert importlib.reload(mcp_readwise).__version__ == "9.9.9"
    monkeypatch.delenv("APP_VERSION")
    importlib.reload(mcp_readwise)
