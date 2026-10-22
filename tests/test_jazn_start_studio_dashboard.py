"""Deterministic Studio 0.3 dashboard contracts, independent of display and daemons."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.jazn_start_studio import StudioCore, safe_line
from tools.jazn_start_studio_dashboard import (
    summarize_daemon, summarize_memory, summarize_mcp, summarize_ollama,
    read_health, HealthItem,
)


def status_fixture() -> dict:
    return {
        "runtime_version": "16.3.25.5.116.0.34.38",
        "daemon": {
            "active_state": "active_trusted",
            "endpoint_identity_matches": True,
            "endpoint_heartbeat_fresh": True,
            "endpoint_reachable": True,
            "marker": {
                "runtime_version_full": "16.3.25.5.116.0.34.31",
                "daemon_chat_jobs": {"pid": 27504},
            },
        },
        "capability_readiness": {
            "full_autobiographical_recall_ready": False,
            "continuity_ready": False,
        },
        "capability_matrix": {
            "components": {"remote_transport": {"available": False}}
        },
    }


class StatusPresentationTests(unittest.TestCase):
    def test_daemon_verified_with_version_mismatch(self):
        result = summarize_daemon(status_fixture())
        self.assertEqual(result.state, "ready")
        self.assertIn("PID 27504", result.detail)
        self.assertIn("wersje różne", result.detail)

    def test_open_endpoint_without_identity_is_not_ready(self):
        data = status_fixture()
        data["daemon"]["endpoint_identity_matches"] = False
        self.assertEqual(summarize_daemon(data).state, "warning")

    def test_missing_evidence_is_unknown(self):
        self.assertEqual(summarize_daemon({"daemon": {}}).state, "unknown")
        self.assertEqual(summarize_memory({}).state, "unknown")
        self.assertEqual(summarize_mcp({}).state, "unknown")

    def test_memory_degraded_not_marked_ready(self):
        self.assertEqual(summarize_memory(status_fixture()).state, "warning")

    def test_mcp_local_transport_not_host_turn(self):
        data = status_fixture()
        self.assertEqual(summarize_mcp(data).state, "unknown")
        data["capability_matrix"]["components"]["remote_transport"]["available"] = True
        result = summarize_mcp(data)
        self.assertEqual(result.state, "warning")
        self.assertIn("tura niezweryfikowana", result.detail)

    def test_ollama_needs_api_json_model_list(self):
        self.assertEqual(summarize_ollama({"models": [{"name": "gemma3:latest"}]}).state, "ready")
        self.assertEqual(summarize_ollama({"models": []}).state, "warning")
        self.assertEqual(summarize_ollama({"something": True}).state, "unknown")

    def test_json_boolean_must_not_be_redacted(self):
        self.assertEqual(safe_line('"requires_api_key": false,'), '"requires_api_key": false,')
        self.assertEqual(safe_line('"normal_runtime_requires_openai_api_key": true,'),
                         '"normal_runtime_requires_openai_api_key": true,')
        self.assertNotIn("supersecrettoken", safe_line('"identity_token": "supersecrettoken"'))

    def test_block_duplicate_process_as_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = StudioCore(Path(tmp), sys.executable, "ollama", "gemma3:latest")
            with patch("tools.jazn_start_studio.is_local_port_open", return_value=True):
                core.start("jazn_start")
                core.start("ollama_serve")
            self.assertIn("pominięto", core.states["jazn_start"].status)
            self.assertIn("pominięto", core.states["ollama_serve"].status)
            self.assertEqual(core.active(), [])

    def test_health_reads_status_but_no_tk_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run.py").write_text("# stub\n", encoding="utf-8")
            core = StudioCore(root, sys.executable, "ollama", "gemma3:latest")
            class Proc:
                returncode = 0
                stdout = json.dumps(status_fixture())
            class Response:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *unused):
                    return False
                def read(self, _size):
                    return b'{"models":[{"name":"gemma3:latest"}]}'
            with patch("tools.jazn_start_studio_dashboard.subprocess.run", return_value=Proc()) as run, \
                 patch("tools.jazn_start_studio_dashboard.urlopen", return_value=Response()):
                report = read_health(core)
            self.assertEqual([x.state for x in report.items],
                             ["ready", "ready", "warning", "unknown"])
            argv = run.call_args.args[0]
            self.assertEqual(argv[-2:], ["status", "--json"])


if __name__ == "__main__":
    unittest.main()
