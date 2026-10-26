"""Acceptance profile v2: durable settings, repeatable session, strict live adoption."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from latka_jazn.core.acceptance_layout import (
    acceptance_environment,
    resolve_acceptance_layout,
    validate_resumed_daemon,
)
from tools.jazn_run_studio.core import (
    Settings,
    load_settings,
    save_settings,
    settings_path,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    return tmp_path


def test_profile_session_reused_without_autostart_or_prod_writes(home: Path) -> None:
    root = home / "feature"
    root.mkdir()
    with acceptance_environment(root) as first:
        assert first.operator.is_relative_to(home / ".jazn")
        assert os.environ["JAZN_MEMORY_MODE"] == "off"
        assert os.environ["JAZN_STUDIO_ACCEPTANCE_PROFILE"] == "isolated"
        assert not first.runtime.exists()
        marker = first.runtime / "JAZN_ACTIVE_RUNTIME.json"
        assert not marker.exists()
    with acceptance_environment(root) as second:
        assert second.runtime == first.runtime
        assert second.memory == first.memory
        assert second.operator == first.operator
        assert not marker.exists()
    assert "JAZN_STUDIO_ACCEPTANCE_PROFILE" not in os.environ
    assert not (root / "workspace_runtime").exists()


def test_two_roots_use_disjoint_acceptance_sessions(home: Path) -> None:
    a = home / "systemA"
    b = home / "systemB"
    a.mkdir()
    b.mkdir()
    with acceptance_environment(a) as left:
        with acceptance_environment(b) as right:
            assert left.runtime != right.runtime
            assert left.operator != right.operator
            assert left.memory != right.memory


@pytest.mark.parametrize("key,value", (
    ("session_id", "not-a-uuid"),
    ("system_root", "/someone-else/system"),
    ("runtime_version", "incompatible-version"),
))
def test_corrupt_profile_refuses_reuse(home: Path, key: str, value: str) -> None:
    root = home / "feature"
    root.mkdir()
    with acceptance_environment(root) as layout:
        profile = layout.operator / "acceptance_profile.json"
    content = json.loads(profile.read_text(encoding="utf-8"))
    content[key] = value
    profile.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="Niezgodny"):
        with acceptance_environment(root):
            pass


def test_persistent_studio_settings_live_outside_runtime(home: Path) -> None:
    root = home / "feature"
    root.mkdir()
    with acceptance_environment(root) as layout:
        selected = settings_path(root)
        assert selected == layout.operator / "jazn_run_studio" / "settings.json"
        settings = Settings(
            daemon_url="http://127.0.0.1:8796",
            mcp_port="8081",
            runtime_profile="off",
        )
        saved_digest = save_settings(root, settings, None)
        loaded, digest = load_settings(root)
        assert digest == saved_digest
        assert loaded.daemon_url == "http://127.0.0.1:8796"
        assert loaded.mcp_port == "8081"
        assert not (root / "jazn_system_config.json").exists()
        assert not (root / "workspace_runtime").exists()
    with acceptance_environment(root) as next_layout:
        assert next_layout == layout
        loaded, _ = load_settings(root)
        assert loaded.mcp_port == "8081"


def test_resume_with_marker_rejects_unverified_identity(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = home / "feature"
    root.mkdir()
    with acceptance_environment(root) as layout:
        layout.runtime.mkdir(parents=True)
        (layout.runtime / "JAZN_ACTIVE_RUNTIME.json").write_text("{}", encoding="utf-8")
        from latka_jazn.core import runtime_daemon
        monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *args, **kwargs: {
            "active_state": "inactive",
            "process_identity_confirmed": False,
        })
        with pytest.raises(ValueError, match="Odmowa wznowienia"):
            validate_resumed_daemon(layout, "http://127.0.0.1:8796")


def test_resume_with_marker_requires_all_trust_gates(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = home / "feature"
    root.mkdir()
    with acceptance_environment(root) as layout:
        layout.runtime.mkdir(parents=True)
        (layout.runtime / "JAZN_ACTIVE_RUNTIME.json").write_text("{}", encoding="utf-8")
        from latka_jazn.core import runtime_daemon
        expected = {
            "active_state": "active_trusted",
            "process_identity_confirmed": True,
            "endpoint_identity_matches": True,
            "endpoint_heartbeat_fresh": True,
            "package_integrity_verified": True,
            "source_provenance_verified": True,
        }
        seen = []
        def status(*args: object, **kwargs: object) -> dict[str, object]:
            seen.append(kwargs)
            return expected
        monkeypatch.setattr(runtime_daemon, "status_daemon", status)
        validate_resumed_daemon(layout, "http://127.0.0.1:8796")
        assert seen[0]["port"] == 8796


def test_no_profile_override_for_normal_studio(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = home / "jazn_latka_master"
    root.mkdir()
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)
    monkeypatch.delenv("JAZN_OPERATOR_STATE_ROOT", raising=False)
    assert settings_path(root) == root / "workspace_runtime" / "jazn_run_studio" / "settings.json"
