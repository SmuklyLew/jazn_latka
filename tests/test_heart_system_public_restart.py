"""Studio uses the actual public main.py restart grammar, not a legacy parser."""
from pathlib import Path
import pytest
from tools.jazn_run_studio.core import Controller, Settings

def test_selected_endpoint_reaches_central_restart_parser(tmp_path: Path, monkeypatch, capsys):
    (tmp_path / "latka_jazn").mkdir()
    for name in ("run.py", "main.py", "latka_jazn/version.py"):
        (tmp_path / name).touch()
    controller = Controller(tmp_path, Settings(daemon_url="http://127.0.0.1:19887"))
    import main
    from latka_jazn.core import runtime_lifecycle
    called = []
    monkeypatch.setattr(main, "_configure_stdio_utf8", lambda: None)
    def restart(config, **options):
        called.append(options)
        return {"ok": True, "test_only": True}
    monkeypatch.setattr(runtime_lifecycle, "restart_daemon", restart)
    assert main.main(controller.command("restart")[4:]) == 0
    assert called[0]["port"] == 19887 and called[0]["host"] == "127.0.0.1"
    assert '"ok": true' in capsys.readouterr().out

def test_real_child_exit_code_has_public_failure_reason(tmp_path: Path):
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").write_text("raise SystemExit(7)", encoding="utf-8")
    controller = Controller(tmp_path)
    job = controller.start_action("version")
    assert job.done.wait(10)
    assert job.state == "failed" and job.returncode == 7
    assert job.error == "process_exit:7"
