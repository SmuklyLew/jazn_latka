from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_system_package_profile_contains_standalone_chatgpt_bootstrap() -> None:
    payload = json.loads(
        (ROOT / "latka_jazn" / "resources" / "zip_package_profiles.json").read_text(
            encoding="utf-8"
        )
    )
    profiles = {item["name"]: item for item in payload["profiles"]}

    assert "CHATGPT_BOOTSTRAP.py" in profiles["system"]["includes"]
    assert "CHATGPT_BOOTSTRAP.py" in profiles["github_source_safe"]["includes"]


def test_chatgpt_project_loader_is_thin_and_exposes_no_operator_recovery() -> None:
    path = ROOT / "docs" / "runtime" / "CHATGPT_PROJECT_INSTRUCTIONS.txt"
    text = path.read_text(encoding="utf-8")

    assert len(text) <= 5000
    assert "host_executor_unavailable" in text
    assert "CHATGPT_BOOTSTRAP.py" in text
    assert "materialized_operator_ready" in text
    assert "surowe `extractall()` bez walidacji jest zabronione" in text
    assert "run.py host-preflight --json" in text
    assert "run.py doctor --json" in text
    assert "run.py start" in text
    assert "run.py status --json" in text
