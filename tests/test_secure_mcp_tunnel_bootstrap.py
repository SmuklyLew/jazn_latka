from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core.daemon_autostart import DaemonEnsureResult
from latka_jazn.mcp import tunnel_bootstrap


def _ensure_result(active_root: Path, *, ok: bool = True, identity: bool = True) -> DaemonEnsureResult:
    return DaemonEnsureResult(
        ok=ok,
        ensured=ok,
        active_state="active_trusted" if ok else "inactive",
        reason="daemon_already_active" if ok else "daemon_start_failed",
        decision={"reason": "explicit_ensure_daemon"},
        selected_transport="persistent_daemon" if ok else "host_diagnostic",
        fallback_reason="daemon_reused" if ok else "daemon_start_required_failed",
        requested_runtime_root=str(active_root),
        resolved_active_root=str(active_root),
        daemon_endpoint_root=str(active_root),
        daemon_identity_verified=identity,
        daemon_pid=321 if ok else None,
        daemon_reused=ok,
    )


def test_ensure_tunnel_runtime_reuses_verified_active_subject_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = tmp_path / "requested"
    active = tmp_path / "active"
    requested.mkdir()
    active.mkdir()
    captured: dict[str, Any] = {}

    def fake_ensure(config: Any, **kwargs: Any) -> DaemonEnsureResult:
        captured["config_root"] = Path(config.root)
        captured["kwargs"] = kwargs
        return _ensure_result(active)

    monkeypatch.setattr(tunnel_bootstrap, "ensure_daemon_for_runtime_turn", fake_ensure)

    resolved, ensured = tunnel_bootstrap.ensure_tunnel_runtime(requested)

    assert resolved == active.resolve()
    assert ensured.daemon_identity_verified is True
    assert captured["config_root"] == requested.resolve()
    assert captured["kwargs"]["command"] == "secure_mcp_tunnel"
    assert captured["kwargs"]["explicit_ensure"] is True


def test_ensure_tunnel_runtime_fails_closed_without_daemon_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setattr(
        tunnel_bootstrap,
        "ensure_daemon_for_runtime_turn",
        lambda *_args, **_kwargs: _ensure_result(root, identity=False),
    )

    with pytest.raises(tunnel_bootstrap.TunnelBootstrapError, match="daemon_identity_not_verified"):
        tunnel_bootstrap.ensure_tunnel_runtime(root)


def test_main_delegates_protocol_to_existing_mcp_server_only_after_runtime_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    ensured = _ensure_result(root)
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        tunnel_bootstrap,
        "ensure_tunnel_runtime",
        lambda *_args, **_kwargs: (root.resolve(), ensured),
    )

    class FakeServer:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def serve_stdio(self) -> int:
            captured["served"] = True
            return 0

    monkeypatch.setattr(tunnel_bootstrap, "JaznMcpServer", FakeServer)

    assert tunnel_bootstrap.main(["--root", str(root)]) == 0
    io = capsys.readouterr()

    assert io.out == ""
    assert "secure_mcp_tunnel_runtime_ready" in io.err
    assert captured["root"] == root.resolve()
    assert captured["daemon_url"] == tunnel_bootstrap.DEFAULT_DAEMON_URL
    assert captured["trust_stdio_parent"] is True
    assert captured["served"] is True


def test_main_never_starts_mcp_protocol_after_failed_runtime_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setattr(
        tunnel_bootstrap,
        "ensure_tunnel_runtime",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            tunnel_bootstrap.TunnelBootstrapError("daemon_identity_not_verified")
        ),
    )
    monkeypatch.setattr(
        tunnel_bootstrap,
        "JaznMcpServer",
        lambda **_kwargs: pytest.fail("MCP server must not start after bootstrap failure"),
    )

    assert tunnel_bootstrap.main(["--root", str(root)]) == 78
    io = capsys.readouterr()
    assert io.out == ""
    assert "secure_mcp_tunnel_bootstrap_failed" in io.err
    assert "daemon_identity_not_verified" in io.err
