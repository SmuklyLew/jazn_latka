"""TPA endpoint selection survives the existing queue's environment isolation."""
import sys
import tempfile

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_engine import TPARunner


def test_queue_records_endpoint_before_preflight_and_passes_it_to_live_child(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    runner = TPARunner(root, sys.executable)
    pending = []
    monkeypatch.setattr(runner, "_io", lambda operation, done: pending.append((operation, done)))
    runner.start_selection(("ollama-two-turns",), execution="live", model="synthetic:latest",
                           api_base="http://127.0.0.1:11534/")
    assert runner.report is not None
    assert runner.report["environment"]["ollama_api_base"] == "http://127.0.0.1:11534"
    assert len(pending) == 1
    # Commit the actual initial manifest without launching preflight/imports.
    operation, _done = pending[0]
    operation()
    runner.probe = {"ok": True}
    runner.availability = {"ollama-two-turns": {"ready": True}}
    launched = []
    monkeypatch.setattr(runner, "_save_then", lambda done: done())
    monkeypatch.setattr(runner, "_launch_durable", lambda args, *_a, **_kw: launched.append(args))
    temporary = tempfile.TemporaryDirectory(dir=tmp_path)
    with temporary:
        runner.temp = temporary
        runner._next()
        assert len(launched) == 1
        args = launched[0]
        assert args[args.index("--ollama-api-base") + 1] == "http://127.0.0.1:11534"
        assert runner.report["results"][0]["command"] == [sys.executable, *args]
    runner.temp = None
    runner.active = False
    runner.deleteLater()
    app.processEvents()
