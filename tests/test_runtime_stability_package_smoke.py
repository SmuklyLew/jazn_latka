from __future__ import annotations

from pathlib import Path
import json

from latka_jazn import cli
from latka_jazn.tools import release_readiness
from latka_jazn.tools.source_provenance import SourceProvenanceError
from latka_jazn.tools.package_export import forbidden_package_reason


def test_package_smoke_does_not_reference_missing_external_script() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "tools/release_readiness_v15.py" not in source
    assert "build_release_readiness_report" in source


def test_package_smoke_json_is_one_document_and_preserves_exit_code(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        release_readiness,
        "build_release_readiness_report",
        lambda root, profile="system": {
            "schema_version": "test/v1", "ok": False, "exit_code": 1,
            "profile": profile, "root": str(root), "checks": [],
        },
    )
    code = cli.main(["package-smoke", "--root", str(tmp_path), "--profile", "system", "--json"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == ""
    assert json.loads(captured.out)["exit_code"] == 1


def test_incomplete_package_is_configuration_error(tmp_path: Path) -> None:
    report = release_readiness.build_release_readiness_report(tmp_path, profile="system")
    assert report["ok"] is False
    assert report["exit_code"] == 2


def test_system_profile_does_not_require_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(release_readiness, "verify_package_integrity_manifest", lambda _root: {"ok": False, "configuration_error": True, "errors": []})
    report = release_readiness.build_release_readiness_report(tmp_path, profile="system")
    assert not any(item["name"] == "memory_wake_state" for item in report["checks"])


def test_release_check_runner_handles_text_input_and_closed_input(
    tmp_path: Path,
) -> None:
    with_input = release_readiness._run(
        tmp_path,
        "-c",
        "import sys; print(sys.stdin.read())",
        input_text="payload",
    )
    without_input = release_readiness._run(
        tmp_path,
        "-c",
        "import sys; print(sys.stdin.read())",
    )

    assert with_input["returncode"] == 0
    assert with_input["stdout"].strip() == "payload"
    assert without_input["returncode"] == 0
    assert without_input["stdout"].strip() == ""


def test_backups_are_forbidden_export_paths() -> None:
    assert forbidden_package_reason("backups/pre-change/working-tree.patch") is not None


def test_release_profile_reports_dirty_worktree_as_policy_failure(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        release_readiness,
        "verify_package_integrity_manifest",
        lambda _root: {"ok": False, "configuration_error": False, "errors": [{"code": "sha256_mismatch"}]},
    )

    def reject_dirty(_root, _destination):
        raise SourceProvenanceError("release provenance requires a clean working tree")

    monkeypatch.setattr(release_readiness, "create_release_staging", reject_dirty)
    monkeypatch.setattr(
        release_readiness,
        "read_source_provenance",
        lambda *_args, **_kwargs: type("Status", (), {"to_dict": lambda self: {"status": "invalid"}})(),
    )
    report = release_readiness.build_release_readiness_report(tmp_path, profile="release")
    staging = next(item for item in report["checks"] if item["name"] == "profile_staging")
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert staging["error_code"] == "dirty_worktree"


def _chat_result(payload: dict, *, returncode: int = 0, suffix: str = "") -> dict:
    return {
        "returncode": returncode,
        "stdout": json.dumps(payload, ensure_ascii=False) + "\n" + suffix,
        "stderr": "",
    }


def test_chat_integrity_check_retries_transient_missing_consensus(monkeypatch, tmp_path: Path) -> None:
    responses = iter([
        _chat_result({"final_visible_text": "Działam.", "final_visible_integrity_consensus": {}}),
        _chat_result({
            "final_visible_text": "Działam.",
            "final_visible_integrity_consensus": {"valid": True, "mismatch": False},
        }),
    ])
    monkeypatch.setattr(release_readiness, "_run", lambda *_args, **_kwargs: next(responses))

    result = release_readiness._run_chat_integrity_check(tmp_path)

    assert result["ok"] is True
    assert result["attempt_count"] == 2
    assert result["retry_used"] is True
    assert result["attempts"][0]["consensus"] == {}
    assert result["consensus"]["valid"] is True


def test_chat_integrity_check_selects_payload_before_trailing_json_noise(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "final_visible_text": "Działam.",
        "final_visible_integrity_consensus": {"valid": True, "mismatch": False},
    }
    response = _chat_result(payload, suffix=json.dumps({"kind": "diagnostic_noise"}) + "\n")
    monkeypatch.setattr(release_readiness, "_run", lambda *_args, **_kwargs: response)

    result = release_readiness._run_chat_integrity_check(tmp_path)

    assert result["ok"] is True
    assert result["attempt_count"] == 1
    assert result["retry_used"] is False


def test_chat_integrity_check_does_not_mask_explicit_integrity_mismatch(monkeypatch, tmp_path: Path) -> None:
    response = _chat_result({
        "final_visible_text": "Działam.",
        "final_visible_integrity_consensus": {"valid": False, "mismatch": True},
    })
    calls = 0

    def run_once(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return response

    monkeypatch.setattr(release_readiness, "_run", run_once)

    result = release_readiness._run_chat_integrity_check(tmp_path)

    assert result["ok"] is False
    assert result["attempt_count"] == 1
    assert result["retry_used"] is False
    assert calls == 1

def test_inactive_status_snapshot_is_a_valid_smoke_observation() -> None:
    payload = {
        "ok": False,
        "daemon": {
            "active_state": "inactive",
            "endpoint_probe_performed": False,
            "observation_state": "endpoint_not_probed",
        },
    }
    assert release_readiness._inactive_snapshot_contract_ok({"returncode": 1}, payload) is True
    assert release_readiness._inactive_snapshot_contract_ok({"returncode": 0}, payload) is False
    assert release_readiness._inactive_snapshot_contract_ok({"returncode": 1}, None) is False
