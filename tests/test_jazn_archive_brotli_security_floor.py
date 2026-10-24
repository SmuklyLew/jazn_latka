"""The optional archive wheelhouse must resolve a fixed Brotli decoder."""
from __future__ import annotations

from pathlib import Path
import tomllib


def test_archive_optional_dependencies_require_patched_brotli() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    archive = project["project"]["optional-dependencies"]["archive"]
    assert "Brotli>=1.2.1,<2" in archive
    assert "py7zr>=1.1.3,<2" in archive
