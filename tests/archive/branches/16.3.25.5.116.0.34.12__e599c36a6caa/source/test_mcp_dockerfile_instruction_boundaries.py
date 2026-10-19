from __future__ import annotations

"""Guard Dockerfile instruction boundaries for the MCP gateway container."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_dockerfile_ends_with_separate_valid_instructions() -> None:
    dockerfile = (ROOT / "deploy/chatgpt_mcp/Dockerfile").read_text(encoding="utf-8")
    assert "\\n" not in dockerfile
    lines = [line for line in dockerfile.splitlines() if line.strip()]
    assert lines[-2] == "STOPSIGNAL SIGTERM"
    assert lines[-1] == 'ENTRYPOINT ["python", "-X", "utf8", "-m", "latka_jazn.mcp.deployment"]'
