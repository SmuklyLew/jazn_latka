from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from latka_jazn.tools import runtime_console


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_console_is_loopback_only() -> None:
    with pytest.raises(runtime_console.RuntimeConsoleError, match="loopback_only"):
        runtime_console.RuntimeConsoleConfig(
            root=ROOT,
            host="0.0.0.0",
        ).normalized()


def test_runtime_console_overview_is_bounded_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_console.diagnostics,
        "status_payload",
        lambda *_args, **_kwargs: {
            "runtime_version": "test-runtime",
            "operational_state": "active_ready",
            "process_ok": True,
            "runtime_core_ready": True,
            "system_fully_ready": True,
            "capability_readiness": {
                "memory_search_ready": True,
                "memory_search_status": "ready",
                "legacy_memory_search_ready": False,
                "continuity_ready": True,
                "nlp_core_ready": True,
                "nlp_enhanced_ready": False,
                "nlp_enhanced_status": "optional_unavailable",
                "rest_scheduler_ready": True,
                "rest_scheduler_running": True,
                "rest_scheduler_status": "ready",
            },
            "transactional_memory": {
                "ready": True,
                "path": "/private/memory.sqlite3",
            },
            "chatgpt_visible_turn_readiness": {
                "scope": "per_turn",
                "status": "accepted_final_required_per_turn",
                "ready": None,
                "accepted_visible_turn_required": True,
                "daemon_liveness_sufficient": False,
            },
            "system_readiness_profile": {
                "profile": "interactive_live_voice",
                "system_fully_ready": True,
            },
            "daemon": {
                "active_state": "active_trusted",
                "endpoint_reachable": True,
                "pid_alive": True,
                "pid": 42,
                "secret": "must-not-leak",
            },
            "root": "/private/runtime/root",
        },
    )
    payload = runtime_console.build_overview_snapshot(ROOT)
    encoded = json.dumps(payload)
    assert payload["runtime"]["active_state"] == "active_trusted"
    assert payload["visible_turn"]["daemon_liveness_sufficient"] is False
    assert "must-not-leak" not in encoded
    assert "/private/memory.sqlite3" not in encoded
    assert "/private/runtime/root" not in encoded


def test_runtime_console_serves_strict_headers_and_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_console,
        "build_live_snapshot",
        lambda *_args, **_kwargs: {
            "schema_version": "test/v1",
            "kind": "live",
            "runtime_version": "test",
            "runtime": {
                "active_state": "active_trusted",
                "endpoint_reachable": True,
            },
        },
    )
    config = runtime_console.RuntimeConsoleConfig(root=ROOT, port=0)
    server = runtime_console.RuntimeConsoleServer(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(server.server_port)
        request = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "Jaźń Runtime Console" in body
            assert response.headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"

        mutation = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/live",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(mutation, timeout=5)
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_runtime_console_assets_avoid_inline_script_and_dom_html_injection() -> None:
    assets = ROOT / "latka_jazn" / "resources" / "runtime_console"
    index = (assets / "index.html").read_text(encoding="utf-8")
    app = (assets / "app.mjs").read_text(encoding="utf-8")
    assert '<script type="module" src="/app.mjs"></script>' in index
    assert "<script>" not in index
    assert "innerHTML" not in app
    assert "textContent" in app


def test_runtime_console_assets_are_in_system_package_profile() -> None:
    assets = ROOT / "latka_jazn" / "resources" / "runtime_console"
    expected = {"index.html", "styles.css", "model.mjs", "app.mjs"}
    assert expected == {path.name for path in assets.iterdir() if path.is_file()}

    profiles = json.loads(
        (ROOT / "latka_jazn" / "resources" / "zip_package_profiles.json").read_text(
            encoding="utf-8"
        )
    )
    system = next(item for item in profiles["profiles"] if item["name"] == "system")
    assert "latka_jazn/**" in system["includes"]
    assert not any(
        entry == "latka_jazn/resources/runtime_console/**"
        for entry in system.get("excludes", [])
    )


def test_runtime_console_cli_parser_is_explicit() -> None:
    from latka_jazn.cli import build_parser

    ns = build_parser().parse_args(
        [
            "runtime-console",
            "--host",
            "127.0.0.1",
            "--port",
            "9001",
            "--daemon-port",
            "8787",
            "--open-browser",
        ]
    )
    assert ns.command == "runtime-console"
    assert ns.host == "127.0.0.1"
    assert ns.port == 9001
    assert ns.daemon_port == 8787
    assert ns.open_browser is True
