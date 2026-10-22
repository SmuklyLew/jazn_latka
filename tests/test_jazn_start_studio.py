"""Offline contract tests for the standalone operator Studio (no live Jaźń/Ollama)."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.jazn_start_studio import (  # noqa: E402
    StudioCore, STUDIO_VERSION, TASK_INDEX, TASKS, MAX_LOG_LINES,
    read_only_check, safe_line,
)


class StudioContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "main.py").write_text("# fixture\n", encoding="utf-8")
        (self.root / "run.py").write_text(
            "import sys\nprint('studio fixture', flush=True)\n", encoding="utf-8"
        )
        self.core = StudioCore(self.root, sys.executable, "ollama", "gemma3:latest")

    def test_profiles_are_unique_and_no_arbitrary_shell(self):
        self.assertEqual(len(TASKS), len(TASK_INDEX))
        self.assertNotIn("custom", [task.operation for task in TASKS])
        for key, task in TASK_INDEX.items():
            self.assertEqual(key, task.key)

    def test_root_check_is_readonly_not_runtime_proof(self):
        result = read_only_check(self.core)
        self.assertTrue(result["run_py_present"])
        self.assertTrue(result["main_py_present"])
        self.assertTrue(result["does_not_validate_runtime_turn"])
        self.assertIn("daemon_loopback_port_open_not_identity_proof", result)

    def test_profile_argv_direct_and_no_shell(self):
        cmd = self.core.command(TASK_INDEX["jazn_preflight"])
        self.assertEqual(cmd[:3], [sys.executable, "-X", "utf8"])
        self.assertEqual(cmd[-2:], ["host-preflight", "--json"])
        self.assertTrue(cmd[3].endswith("run.py"))

    def test_stop_unowned_does_not_touch_existing_service(self):
        # No process exists; stop must not probe, adopt, or kill a daemon.
        self.core.stop("jazn_status")
        self.assertIsNone(self.core.states["jazn_status"].proc)

    def test_cli_process_output_and_exit_are_reported(self):
        self.core.start("jazn_status")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.core.states["jazn_status"].status.startswith("zakończono"):
                break
            time.sleep(0.03)
        self.assertEqual(self.core.states["jazn_status"].status, "zakończono: OK")
        self.assertTrue(any("studio fixture" in line for line in self.core.logs["jazn_status"]))

    def test_stdout_secrets_are_redacted(self):
        self.core.emit("jazn_status", "INFO", "Authorization: Bearer top-secret-value")
        self.core.emit("jazn_status", "INFO", "api_key=abcdefghijk0123")
        combined = "\n".join(self.core.logs["jazn_status"])
        self.assertNotIn("top-secret-value", combined)
        self.assertNotIn("abcdefghijk0123", combined)

    def test_maximum_memory_log_history(self):
        for i in range(MAX_LOG_LINES + 17):
            self.core.emit("jazn_status", "INFO", str(i))
        self.assertEqual(len(self.core.logs["jazn_status"]), MAX_LOG_LINES)

    def test_mcp_receive_only_matching_request_id(self):
        inbox: queue.Queue[str] = queue.Queue()
        inbox.put(json.dumps({"jsonrpc": "2.0", "id": 8, "result": {}}) + "\n")
        inbox.put(json.dumps({"jsonrpc": "2.0", "id": 2,
                              "result": {"tools": []}}) + "\n")
        result = self.core._mcp_receive(inbox, 2, None, timeout=1)
        self.assertEqual(result["result"]["tools"], [])

    def test_mcp_non_json_rejected(self):
        inbox: queue.Queue[str] = queue.Queue()
        inbox.put("a plain log on stdout\n")
        with self.assertRaisesRegex(RuntimeError, "Non-JSON"):
            self.core._mcp_receive(inbox, 1, None, timeout=1)

    def test_mcp_deadline(self):
        with self.assertRaises(TimeoutError):
            self.core._mcp_receive(queue.Queue(), 1, None, timeout=0.02)


if __name__ == "__main__":
    unittest.main()
