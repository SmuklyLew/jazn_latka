"""P1: authenticated active-memory observation, redacted readiness, no activation."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from latka_jazn.core import active_memory_evidence as evidence
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.config import JaznConfig
from latka_jazn.tools.memory_rebuild_app import p1_active_memory_readiness as readiness
from latka_jazn.tools.memory_rebuild_app.p1_provenance_chain import PinnedMemoryArtifact
from latka_jazn.tools.memory_rebuild_app.p1_memory_provenance import _canonical


def _server(tmp_path: Path):
    from tests.test_runtime_daemon_security_contract import _Session
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=tmp_path),
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_Session,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path: str, token: str | None):
    headers = {daemon.DAEMON_AUTH_HEADER: token} if token else {}
    url = daemon.daemon_url("127.0.0.1", int(server.server_address[1]), path)
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3)


def test_evidence_endpoint_requires_auth_and_nonce(tmp_path: Path) -> None:
    server, thread = _server(tmp_path)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server, "/active-memory-evidence?nonce=" + "a"*32, None)
        assert exc.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server, "/active-memory-evidence?nonce=bad", server.auth_token)
        assert exc.value.code == 400
        assert b"invalid_evidence_nonce" in exc.value.read()
        with _get(server, "/active-memory-evidence?nonce=" + "a"*32, server.auth_token) as reply:
            payload = json.loads(reply.read())
        assert payload["schema_version"] == evidence.SCHEMA
        assert payload["nonce"] == "a"*32
        assert payload["proof"] == evidence._signature(
            {key: value for key, value in payload.items() if key != "proof"}, server.auth_token
        )
        assert payload["recall"]["state"] == "unverified"
        assert payload["continuity"]["state"] == "unverified"
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=3)


def test_missing_marker_fails_closed_without_files(tmp_path: Path) -> None:
    report = readiness.assess_active_memory_readiness(tmp_path)
    assert report["runtime_ready"] is False
    assert report["activation_preflight_passed"] is False
    assert report["activation_authorized"] is False
    assert report["memory_continuity_ready"] is None
    assert not list(tmp_path.iterdir())


def test_status_redacts_private_metadata_and_does_not_infer_recall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = {key: {"state": "verified", "issue": "/private/sensitive"} for key in evidence.CHECKS}
    monkeypatch.setattr(readiness, "collect_active_memory_evidence", lambda _: {
        "checks": checks, "observed_memory_path": "/private/sensitive.sqlite3",
        "database_metadata": {"secret": "never-print"},
    })
    report = readiness.assess_active_memory_readiness(tmp_path)
    assert report["runtime_ready"] is True
    assert report["memory_recall_ready"] is None
    assert report["activation_authorized"] is False
    assert "/private/" not in json.dumps(report)
    assert "never-print" not in json.dumps(report)


def test_independent_pin_still_cannot_grant_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "collect_active_memory_evidence", lambda _: {
        "checks": {key: {"state": "verified"} for key in evidence.CHECKS},
        "observed_memory_path": str(tmp_path / "synthetic.sqlite3"),
    })
    monkeypatch.setattr(readiness, "verify_provenance_chain", lambda *a, **kw: {"state": "verified"})
    report = readiness.assess_active_memory_readiness(
        tmp_path, pinned_reference=PinnedMemoryArtifact(tmp_path / "reference.sqlite3", "a"*64),
    )
    assert report["memory_provenance_verified"] is True
    assert report["activation_preflight_passed"] is False
    assert report["activation_authorized"] is False


def test_sqlite_blob_text_integer_and_real_cannot_hash_identically() -> None:
    assert _canonical("abc") != _canonical(b"abc")
    assert _canonical(1) != _canonical("1")
    assert _canonical(1.0) != _canonical(1)
