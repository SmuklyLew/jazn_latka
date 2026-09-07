from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run_preflight(tmp_path: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    contract = tmp_path / "host-preflight.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "host-preflight", "--input", str(contract), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _degraded_executor_payload() -> list[dict[str, object]]:
    return [
        {
            "surface": "python_tool",
            "process_created": False,
            "error_class": "ClientError",
            "alternative_surface_available": True,
        },
        {
            "surface": "terminal",
            "process_created": True,
            "command_completed": True,
            "returncode": 0,
            "filesystem_probe_succeeded": True,
        },
    ]


def test_run_py_host_preflight_reports_degraded_but_usable_host(tmp_path: Path) -> None:
    completed = _run_preflight(
        tmp_path,
        {
            "executor_observations": _degraded_executor_payload(),
            "package_required": False,
        },
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["gate_passed"] is True
    assert result["environment_state"] == "degraded"
    assert result["filesystem_state"] == "observed"
    assert result["runtime_state"] == "unverified"
    assert result["canonical_resume_entrypoint"] == "run.py"


def test_run_py_host_preflight_blocks_stable_truncated_attachment(tmp_path: Path) -> None:
    part = tmp_path / "package.zip.004"
    part.write_bytes(b"partial")
    expected_sha = hashlib.sha256(b"x" * 32).hexdigest()

    completed = _run_preflight(
        tmp_path,
        {
            "executor_observations": _degraded_executor_payload(),
            "package_required": True,
            "attachments": [
                {
                    "path": str(part),
                    "expected_size_bytes": 32,
                    "expected_sha256": expected_sha,
                }
            ],
        },
    )

    assert completed.returncode == 3, completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["gate_passed"] is False
    assert result["environment_state"] == "degraded"
    assert result["filesystem_state"] == "observed"
    assert result["package_state"] == "incomplete"
    assert result["reason_code"] == "attachment_package_incomplete"
    assert result["attachments"][0]["state"] == "incomplete"
