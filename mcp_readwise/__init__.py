"""MCP server for Readwise."""

import os
from importlib.metadata import PackageNotFoundError, version

try:
    # Releases are git tags; the image carries the tag as APP_VERSION.
    __version__ = os.environ.get("APP_VERSION") or version("mcp-readwise")
except PackageNotFoundError:
    __version__ = "unknown"
