from __future__ import annotations

from pathlib import Path
import tomllib


def test_pyright_excludes_mutable_workspace_runtime_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = set(config["tool"]["pyright"]["exclude"])
    ignored = set(config["tool"]["pyright"]["ignore"])

    assert "workspace_runtime" in excluded
    assert "**/workspace_runtime/**" in excluded

    assert "workspace_runtime" in ignored
    assert "**/workspace_runtime/**" in ignored
