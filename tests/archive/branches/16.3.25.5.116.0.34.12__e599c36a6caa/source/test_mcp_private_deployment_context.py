from __future__ import annotations

"""Private deployment configuration must stay out of Git and Docker images."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_mcp_oauth_environment_file_is_excluded_from_all_build_contexts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "**/*.env" in dockerignore
    assert "**/*.env" in gitignore
    assert ".env" in dockerignore
    assert ".env" in gitignore
    assert (ROOT / "deploy/chatgpt_mcp/jazn-mcp.env.example").is_file()
