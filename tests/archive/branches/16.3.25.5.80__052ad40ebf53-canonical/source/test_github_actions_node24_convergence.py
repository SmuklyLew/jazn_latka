from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from latka_jazn.tools.javascript_runtime import inspect_javascript_runtime, parse_node_version


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
JAVASCRIPT_ROOT = ROOT / "tools" / "javascript"
CHECKOUT_NODE24_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_NODE24_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
SETUP_NODE_NODE24_SHA = "820762786026740c76f36085b0efc47a31fe5020"
STALE_NODE20_SHAS = {
    "34e114876b0b11c390a56381ad16ebd13914f8d5",
    "a26af69be951a213d495a4c3e4e4022e16d87065",
    "49933ea5288caeca8642d1e84afbd3f7d6820020",
}


def _all_active_workflow_text() -> str:
    paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert len(paths) >= 11
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_all_active_github_actions_pass_fail_closed_node24_audit() -> None:
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(ROOT / "tools" / "github_actions_node24_audit.py"),
        "--root",
        str(ROOT),
        "--json",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["workflow_count"] >= 11
    assert payload["findings"] == []


def test_node20_action_pins_are_absent_and_node24_pins_are_present() -> None:
    text = _all_active_workflow_text()
    assert CHECKOUT_NODE24_SHA in text
    assert SETUP_PYTHON_NODE24_SHA in text
    assert SETUP_NODE_NODE24_SHA in text
    for stale in STALE_NODE20_SHAS:
        assert stale not in text
    assert "node20" not in text.lower()


def test_javascript_tooling_is_locked_private_esm_and_node24_scoped() -> None:
    package = json.loads((JAVASCRIPT_ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((JAVASCRIPT_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    probe = (JAVASCRIPT_ROOT / "jazn_node24_probe.mjs").read_text(encoding="utf-8")

    assert package["private"] is True
    assert package["type"] == "module"
    assert package["version"] == "16.3.25.5.30"
    assert package["engines"]["node"] == ">=24 <25"
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["version"] == package["version"]
    assert lock["packages"][""]["engines"] == package["engines"]
    assert "import.meta.url" in probe
    assert "major === 24" in probe
    assert "await Promise.resolve" in probe


def test_python_runtime_probe_keeps_javascript_optional() -> None:
    assert parse_node_version("v24.20.0") == (24, 20, 0)
    assert parse_node_version("24.0.1") == (24, 0, 1)
    assert parse_node_version("not-node") is None

    missing = inspect_javascript_runtime("/__jazn_missing_node__/node")
    assert missing["ok"] is False
    assert missing["available"] is False
    assert missing["minimum_node_major"] == 24
    assert missing["ci_node_major"] == 24


def test_repository_text_policy_covers_node_install_state_and_esm_eol() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "project" / "REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md").read_text(
        encoding="utf-8"
    )
    codex = (ROOT / "AGENTS.codex.md").read_text(encoding="utf-8")

    assert "node_modules/" in gitignore
    assert "*.mjs    text eol=lf" in attributes
    assert "Node.js 24 LTS" in policy
    assert "npm ci" in policy
    assert "JavaScript jest opcjonalną capability" in codex
    assert "github_actions_node24_audit.py" in codex
