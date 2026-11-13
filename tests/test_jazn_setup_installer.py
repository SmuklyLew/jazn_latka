"""Tests for the portable operator installer; no network, live daemon or MEMORY."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools import jazn_setup as setup


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "SYSTEM"
    root.mkdir()
    for name in ("run.py", "main.py", "AGENTS.md"):
        (root / name).write_text("# fixture\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nrequires-python=">=3.12"\ndependencies=["tzdata>=2024.1", "packaging>=24.2,<27"]\n',
        encoding="utf-8",
    )
    profiles = root / "latka_jazn/resources/dependencies/profiles.json"
    profiles.parent.mkdir(parents=True)
    profiles.write_text(json.dumps({"profiles": {
        "core": {}, "run-studio": {}, "mcp-http": {}, "polish-nlp": {},
        "test-evidence": {}, "all": {},
    }}), encoding="utf-8")
    monkeypatch.setattr(setup, "ROOT", root)
    return root


def test_doctor_read_only_without_any_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup, "_managed_status", lambda _root: {"ready": False, "status": "missing"})
    result = setup.execute(setup.build_parser().parse_args(["doctor"]))
    assert result["mode"] == "doctor"
    assert result["local_venv"]["state"] == "missing"
    assert not (root / ".venv").exists()
    assert not (root / "workspace_runtime").exists()
    assert not (root / "memory").exists()


def test_unknown_profile_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _fixture(tmp_path, monkeypatch)
    with pytest.raises(setup.SetupError, match="Unsupported dependency profile"):
        setup.execute(setup.build_parser().parse_args(["install", "--profile", "../bad", "--yes"]))
    assert not (root / ".venv").exists()


def test_no_implicit_network_or_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup, "_target", lambda: {"release_wheelhouse_target_supported": True})
    monkeypatch.setattr(setup, "_managed_status", lambda _root: {"ready": False})
    with pytest.raises(setup.SetupError, match="No compatible verified offline wheelhouse"):
        setup.execute(setup.build_parser().parse_args(["install", "--yes"]))
    assert not (root / ".venv").exists()


def test_incomplete_venv_is_not_destroyed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _fixture(tmp_path, monkeypatch)
    venv = root / ".venv"
    venv.mkdir()
    sentinel = venv / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(setup.SetupError, match="never overwrite"):
        setup._create_venv(root)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_offline_install_uses_canonical_dependency_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    bundle = tmp_path / "verified-wheelhouse"
    bundle.mkdir()
    python = tmp_path / "env" / "python.exe"
    python.parent.mkdir()
    python.write_text("interpreter fixture", encoding="utf-8")
    monkeypatch.setattr(setup, "_target", lambda: {
        "release_wheelhouse_target_supported": True, "python": "3.14",
    })
    counts = {"status": 0}
    def managed(_root: Path) -> dict:
        counts["status"] += 1
        if counts["status"] == 1:
            return {"ready": False}
        return {"ready": True, "resolved_profiles": ["core", "run-studio"], "python_executable": str(python)}
    monkeypatch.setattr(setup, "_managed_status", managed)
    calls: list[tuple[str, tuple[str, ...]]] = []
    def studio(_root: Path, operation: str, *args: str, timeout: int = 1800) -> dict:
        calls.append((operation, args))
        if operation == "verify":
            return {"ok": True}
        if operation == "install":
            return {"ok": True, "python_executable": str(python), "state": "environment_ready",
                    "activation_marker_updated": True}
        raise AssertionError(f"unexpected command: {operation}")
    monkeypatch.setattr(setup, "_dependency_studio", studio)
    args = setup.build_parser().parse_args([
        "install", "--profile", "run-studio", "--bundle", str(bundle), "--yes",
    ])
    result = setup.execute(args)
    assert result["ok"] is True
    assert result["profiles"] == ["core", "run-studio"]
    assert [item[0] for item in calls] == ["verify", "install"]
    assert "--offline" in calls[-1][1]
    assert "--bundle" in calls[-1][1]
    assert not (root / ".venv").exists()


def test_reuse_managed_environment_without_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    python = tmp_path / "ready" / "python.exe"
    python.parent.mkdir()
    python.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(setup, "_target", lambda: {"release_wheelhouse_target_supported": True})
    monkeypatch.setattr(setup, "_managed_status", lambda _root: {
        "ready": True, "resolved_profiles": ["core"], "python_executable": str(python),
    })
    monkeypatch.setattr(setup, "_dependency_studio", lambda *_args, **_kwargs: pytest.fail("unexpected mutation"))
    result = setup.execute(setup.build_parser().parse_args(["install"]))
    assert result["state"] == "already_ready"
    assert result["python_executable"] == str(python)
    assert not (root / ".venv").exists()


def test_optional_profiles_must_not_reuse_core_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup, "_target", lambda: {"release_wheelhouse_target_supported": True})
    monkeypatch.setattr(setup, "_managed_status", lambda _root: {
        "ready": True, "resolved_profiles": ["core"], "python_executable": "unused",
    })
    with pytest.raises(setup.SetupError, match="No compatible verified offline wheelhouse"):
        setup.execute(setup.build_parser().parse_args(["install", "--profile", "mcp-http", "--yes"]))


def test_doctor_invalid_python_status_is_not_fabricated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _fixture(tmp_path, monkeypatch)
    venv = root / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home=elsewhere", encoding="utf-8")
    assert setup._probe_venv(root)["ready"] is False
    assert setup._probe_venv(root)["state"] == "incomplete"


def test_cli_returns_nonzero_for_unsupported_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup, "_target", lambda: {"release_wheelhouse_target_supported": False})
    assert setup.main(["install", "--yes", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_type"] == "SetupError"


def test_powershell_and_sh_preserve_installation_root() -> None:
    source_root = Path(__file__).resolve().parents[1]
    sh = (source_root / "setup.sh").read_text(encoding="utf-8")
    ps = (source_root / "setup.ps1").read_text(encoding="utf-8")
    assert 'dirname -- "$0"' in sh
    assert "Split-Path -Parent $MyInvocation.MyCommand.Path" in ps
    assert "pip install" not in sh and "pip install" not in ps
    assert "wizard" in ps
    assert "wizard" in (source_root / "tools/jazn_setup.py").read_text(encoding="utf-8")


def test_extend_uses_only_existing_root_venv_and_verified_wheelhouse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a mismatched previous activation marker cannot redirect setup."""
    root = _fixture(tmp_path, monkeypatch)
    bundle = tmp_path / "verified-wheelhouse"
    bundle.mkdir()
    python = setup._venv_python(root)
    python.parent.mkdir(parents=True)
    python.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(setup, "_probe_venv", lambda _root: {"ready": True})
    monkeypatch.setattr(setup, "_target", lambda: {
        "release_wheelhouse_target_supported": True, "python": "3.14",
    })
    calls = {"status": 0}
    def managed(_root):
        calls["status"] += 1
        if calls["status"] == 1:
            return {
                "ready": True, "resolved_profiles": ["core", "run-studio", "test-evidence"],
                "python_executable": str(tmp_path / "old-managed" / "python.exe"),
                "environment_root": str(tmp_path / "old-managed"),
            }
        return {
            "ready": True, "resolved_profiles": ["core", "run-studio", "test-evidence"],
            "python_executable": str(python),
            "environment_root": str(root / ".venv"),
        }
    monkeypatch.setattr(setup, "_managed_status", managed)
    operations = []
    def studio(_root, operation, *args, timeout=1800):
        operations.append((operation, args))
        if operation == "verify":
            return {"ok": True}
        if operation == "extend":
            return {"ok": True, "python_executable": str(python),
                    "state": "private_environment_extended", "activation_marker_updated": True}
        raise AssertionError(operation)
    monkeypatch.setattr(setup, "_dependency_studio", studio)
    result = setup.execute(setup.build_parser().parse_args([
        "extend", "--profile", "run-studio", "--profile", "test-evidence",
        "--bundle", str(bundle), "--yes",
    ]))
    assert result["ok"] is True and result["mode"] == "extend"
    assert result["python_executable"] == str(python)
    assert [item[0] for item in operations] == ["verify", "extend"]
    assert "--offline" in operations[-1][1]
    assert "--layout" not in operations[-1][1]
    assert str(python) in operations[-1][1]


def test_extend_refuses_missing_or_unverified_root_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup, "_target", lambda: {"release_wheelhouse_target_supported": True})
    monkeypatch.setattr(setup, "_managed_status", lambda _root: {"ready": False})
    with pytest.raises(setup.SetupError, match="verified ROOT/.venv"):
        setup.execute(setup.build_parser().parse_args(["extend", "--yes"]))


def test_first_run_jss_profiles_include_pytest_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First-run choice 3 produces Core + JSS + MCP + pytest in one venv."""
    import builtins
    from types import SimpleNamespace
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(setup.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    selections = iter(("3", ""))
    monkeypatch.setattr(builtins, "input", lambda *_args: next(selections))
    monkeypatch.setattr(setup, "_probe_venv", lambda _root: {"ready": False})
    monkeypatch.setattr(setup, "execute", lambda args: {
        "mode": args.mode, "profiles": args.profile, "online": args.online,
    })
    result = setup._wizard(setup.build_parser().parse_args(["wizard"]))
    assert result["mode"] == "install"
    assert result["profiles"] == ["core", "run-studio", "mcp-http", "test-evidence"]
    assert result["online"] is True
