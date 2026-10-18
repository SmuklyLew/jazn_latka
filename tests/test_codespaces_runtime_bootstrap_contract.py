"""Regression contract for a manual, private GitHub Codespaces bootstrap."""

from __future__ import annotations

import json
from pathlib import Path


def test_codespaces_devcontainer_is_manual_and_fail_closed() -> None:
    repo = Path(__file__).resolve().parents[1]
    configuration = json.loads(
        (repo / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
    )
    assert configuration["workspaceFolder"] == "/workspaces/jazn_latka"
    assert configuration["forwardPorts"] == []
    assert configuration["portsAttributes"]["8080"]["onAutoForward"] == "ignore"
    assert configuration["portsAttributes"]["8080"]["protocol"] == "http"
    for command in ("postStartCommand", "postAttachCommand", "initializeCommand"):
        assert command not in configuration
    setup = configuration["postCreateCommand"]
    assert "workspace_runtime/codespaces-venv" in setup
    assert ".[mcp-http]" in setup
    assert "run.py --version" in setup
    assert "run.py start" not in setup
    assert "mcp-http --loopback-dev" not in setup
    assert "OPENAI_API_KEY" not in json.dumps(configuration)
