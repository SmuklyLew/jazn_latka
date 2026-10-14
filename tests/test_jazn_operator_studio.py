from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.tools.jazn_studio import core


@pytest.fixture
def system(tmp_path: Path) -> Path:
    (tmp_path / "main.py").write_text("# central runtime entry\n")
    (tmp_path / "run.py").write_text("# thin launcher\n")
    package = tmp_path / "latka_jazn"
    package.mkdir()
    (package / "version.py").write_text('PACKAGE_VERSION="fixture"\n')
    return tmp_path


def test_studio_settings_roundtrip_and_compare_and_swap(system: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "workspace_runtime_path", lambda root: root / "workspace_runtime")
    default, original_hash = core.load_settings(system)
    assert original_hash is None
    assert default.cloudflare_url == "https://jazn-runtime.jazn-lakta.workers.dev"
    path = core.write_settings(system, core.StudioSettings(
        refresh_seconds=45, timeout_seconds=11), expected_sha256=original_hash)
    assert path.parent.name == "jazn_studio"
    first, first_hash = core.load_settings(system)
    assert first.refresh_seconds == 45
    assert first.timeout_seconds == 11
    assert first_hash is not None
    assert core.settings_snapshot(system)[0] == first
    with pytest.raises(core.StudioError, match="changed on disk"):
        core.write_settings(system, first, expected_sha256=None)
    path2 = core.write_settings(system, core.StudioSettings(refresh_seconds=60), expected_sha256=first_hash)
    assert path2 == path
    assert core.load_settings(system)[0].refresh_seconds == 60


@pytest.mark.parametrize("payload", [
    {"cloudflare_url": "http://jazn-runtime.jazn-lakta.workers.dev"},
    {"cloudflare_url": "https://user:pass@jazn-runtime.jazn-lakta.workers.dev"},
    {"cloudflare_url": "https://127.0.0.1"},
    {"cloudflare_url": "https://example.com"},
    {"cloudflare_url": "https://a.workers.dev/credentials"},
    {"cloudflare_url": "https://a.workers.dev?token=leak"},
    {"local_mcp_url": "http://0.0.0.0:8080/mcp"},
    {"local_mcp_url": "http://127.0.0.1:8787/mcp"},
    {"refresh_seconds": 1},
    {"refresh_seconds": True},
    {"timeout_seconds": 100},
    {"arbitrary_env": "OPENAI_API_KEY=x"},
    {"show_details": "false"},
])
def test_bad_or_secret_bearing_operator_settings_are_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(core.StudioError):
        core.StudioSettings.validate(payload)


def test_settings_schema_and_duplicate_keys_fail_closed(system: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "workspace_runtime_path", lambda root: root / "workspace_runtime")
    settings = system / "workspace_runtime" / "jazn_studio" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"schema":"jazn_operator_studio/v1","refresh_seconds":20,"refresh_seconds":25}')
    with pytest.raises(core.StudioError, match="Duplicate"):
        core.load_settings(system)
    settings.write_text('{"schema":"unexpected","refresh_seconds":20}')
    with pytest.raises(core.StudioError, match="Unsupported"):
        core.load_settings(system)


def test_studio_rejects_symlink_settings_directory(system: Path, tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "workspace_runtime_path", lambda root: root / "workspace_runtime")
    workspace = system / "workspace_runtime"
    workspace.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    try:
        (workspace / "jazn_studio").symlink_to(other, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink privilege unavailable")
    with pytest.raises(core.StudioError, match="symlink"):
        core.load_settings(system)


def test_diagnostics_run_only_known_canonical_commands(system: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    def mock_invoke(args: list[str], **_kw: Any) -> dict[str, Any]:
        calls.append(args)
        return {"ok": True, "result": {"conversation_ready": True}}
    monkeypatch.setattr(core, "_invoke", mock_invoke)
    result = core.run_diagnostic(system, "status")
    assert result["ok"] is True
    assert calls[0][-2:] == ["status", "--json"]
    assert calls[0][-3].endswith("run.py")
    with pytest.raises(core.StudioError):
        core.run_diagnostic(system, 'status; rm -rf memory')


def test_http_probes_do_not_follow_nonapproved_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(core.StudioError):
        core.probe_http("http://127.0.0.1:8787/status")
    with pytest.raises(core.StudioError):
        core.probe_http("https://jazn-runtime.jazn-lakta.workers.dev/mcp")
    with pytest.raises(core.StudioError):
        core.probe_http("https://user:pass@jazn-runtime.jazn-lakta.workers.dev/healthz")

    class Response:
        status = 200
        def __enter__(self) -> "Response":
            return self
        def __exit__(self, *args: Any) -> None:
            return None
        def read(self, count: int) -> bytes:
            assert count <= 32_768
            return b'{"status":"ready","ready":true,"token":"PRIVATE"}'
    requests: list[Any] = []
    def fake_open(req: Any, *, timeout: int) -> Response:
        requests.append(req)
        return Response()
    monkeypatch.setattr(core, "urlopen", fake_open)
    result = core.probe_http("http://127.0.0.1:8080/readyz")
    assert result["ok"] is True
    assert result["status"]["ready"] is True
    assert "token" not in json.dumps(result)
    assert len(requests) == 1


def test_git_update_readiness_requires_clean_fast_forward_master(system: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    def git(_root: Path, *args: str, **_kw: Any) -> tuple[int, str]:
        values = {
            ("rev-parse", "--is-inside-work-tree"): (0, "true"),
            ("branch", "--show-current"): (0, "master"),
            ("rev-parse", "--short", "HEAD"): (0, "abc123"),
            ("status", "--porcelain", "--untracked-files=normal"): (0, ""),
            ("rev-list", "--left-right", "--count", "HEAD...origin/master"): (0, "2\t0"),
            ("merge-base", "--is-ancestor", "HEAD", "origin/master"): (0, ""),
        }
        return values.get(args, (1, ""))
    monkeypatch.setattr(core, "_git", git)
    plan = core.update_plan(system)
    assert plan["apply_allowed"] is True
    assert plan["behind"] == 2
    with pytest.raises(core.StudioError, match="backup"):
        core.apply_fast_forward(system)
    monkeypatch.setattr(core, "_is_listening", lambda port: True)
    with pytest.raises(core.StudioError, match="Stop"):
        core.apply_fast_forward(system, acknowledged_backup=True)


def test_no_automatic_merge_on_dirty_checkout(system: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_git(_root: Path, *args: str, **_kw: Any) -> tuple[int, str]:
        known = {
            ("rev-parse", "--is-inside-work-tree"): (0, "true"),
            ("branch", "--show-current"): (0, "master"),
            ("rev-parse", "--short", "HEAD"): (0, "abc"),
            ("status", "--porcelain", "--untracked-files=normal"): (0, " M latka_jazn/mcp/http_gateway.py"),
            ("rev-list", "--left-right", "--count", "HEAD...origin/master"): (0, "1\t0"),
            ("merge-base", "--is-ancestor", "HEAD", "origin/master"): (0, ""),
        }
        return known.get(args, (1, ""))
    monkeypatch.setattr(core, "_git", fake_git)
    monkeypatch.setattr(core, "_is_listening", lambda port: False)
    assert core.update_plan(system)["reason"] == "dirty_worktree"
    with pytest.raises(core.StudioError, match="dirty_worktree"):
        core.apply_fast_forward(system, acknowledged_backup=True)


def test_existing_studios_are_delegated_not_reimplemented(system: Path) -> None:
    tools = system / "tools"
    tools.mkdir()
    for name in ("jazn_config_studio.py", "jazn_tests_studio.py", "jazn_memory_studio.py"):
        (tools / name).write_text("# canonical\n")
    for name in ("configuration", "tests", "memory"):
        command = core.safe_launcher(system, name)
        assert command[0]
        assert command[-1].endswith(".py")
    with pytest.raises(core.StudioError):
        core.safe_launcher(system, "unknown")


def test_operator_snapshot_does_not_assume_pid_proves_runtime(system: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "workspace_runtime_path", lambda root: root / "workspace_runtime")
    result = core.studio_snapshot(system)
    assert result["schema"] == core.SCHEMA
    assert result["read_only"] is True
    assert "runtime_ready" not in result
    assert "memory" not in result
