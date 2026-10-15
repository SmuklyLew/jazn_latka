"""P0B/P4 operator benchmark controls, without private memory or network access."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.core.cognitive_development_evaluation import parse_labeled_cases


def test_operator_case_loader_rejects_duplicates_and_malformed_labels() -> None:
    """Malformed, repeated or oversized input must be rejected before routing."""
    example = {"name": "test-1", "utterance": "Czy Jaźń działa?",
               "expected": "runtime_health_check"}
    with pytest.raises(ValueError):
        parse_labeled_cases({"cases": [example, example]})
    with pytest.raises(ValueError):
        parse_labeled_cases({"cases": [{**example, "unexpected": "field"}]})
    with pytest.raises(ValueError):
        parse_labeled_cases({"cases": [{**example, "utterance": " "}]})
    with pytest.raises(ValueError):
        parse_labeled_cases({"cases": [{**example, "expected": " "}]})
    with pytest.raises(ValueError):
        parse_labeled_cases({"cases": [{**example, "previous_text": "x" * 3001}]})


def test_studio_bounded_operator_cases_report_without_source_echo(tmp_path: Path) -> None:
    """Studio reports counts and labels without printing the original prompt."""
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "test_cases.json"
    private_marker = "PRYWATNY_TEKST_DO_TESTU"
    path.write_text(json.dumps({"cases": [{
        "name": "case-1",
        "utterance": "Czy Jaźń działa? " + private_marker,
        "expected": "runtime_health_check",
    }]}), encoding="utf-8")
    command = [sys.executable, "-X", "utf8", str(root / "tools" / "jazn_studio.py"),
               "--root", str(root), "--cognitive-cases", str(path)]
    run = subprocess.run(command, cwd=root, capture_output=True, text=True,
                         check=False, timeout=45)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["origin"] == "operator_supplied_unverified"
    assert result["claim_of_generalization_allowed"] is False
    assert result["evaluated"] == 1
    assert private_marker not in run.stdout
