"""Concurrent diagnostics keep one read and preserve mutation exclusion."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from urllib.error import URLError
import pytest
from tools.jazn_run_studio.core import Controller, Settings, StudioError
from tools.jazn_run_studio.workbench_theme import workbench_colors

@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "latka_jazn").mkdir()
    for name in ("run.py", "main.py", "latka_jazn/version.py"):
        (tmp_path / name).touch()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace_runtime"))
    c = Controller(tmp_path, Settings())
    yield c
    c.close()

def test_rapid_clicks_launch_one_read(core, monkeypatch):
    launches = []
    monkeypatch.setattr(core, "_launch", lambda job, argv, timeout: launches.append(job))
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: core.start_action("status"), range(40)))
    assert all(job is jobs[0] for job in jobs)
    assert len(launches) == 1
    with pytest.raises(StudioError):
        core._reserve("status")

def test_batch_waits_for_existing_status_and_keeps_failure(core, monkeypatch):
    status = core._reserve("status")
    batch = core.run_batch(("status",))
    assert not batch.done.wait(0.05)
    status.state, status.error = "failed", "invalid_status_json"
    status.done.set()
    assert batch.done.wait(3)
    assert batch.state == "failed" and batch.error == "failed_step:status"
    assert core.jobs["status"] is status

def test_cancel_batch_does_not_cancel_shared_read(core):
    status = core._reserve("status")
    batch = core.run_batch(("status",))
    batch.cancel.set()
    assert batch.done.wait(3) and batch.state == "stopped"
    assert not status.cancel.is_set()
    status.done.set()

def test_lifecycle_mutations_still_exclude_each_other(core, monkeypatch):
    monkeypatch.setattr(core, "_launch", lambda *args: None)
    core.start_action("start")
    for name in ("start", "restart", "stop"):
        with pytest.raises(StudioError):
            core.start_action(name)

def test_mcp_diagnostic_uses_selected_local_port(core):
    core.settings = Settings(mcp_port="19080")
    command = core.command("mcp")
    assert command[command.index("--url") + 1] == "http://127.0.0.1:19080/mcp"

def test_probe_unavailable_is_failed_and_safe(core, monkeypatch):
    from tools.jazn_run_studio import probes
    def unavailable(*args):
        raise URLError("secret=private-endpoint-error")
    monkeypatch.setattr(probes, "ollama", unavailable)
    job = core.probe("ollama")
    assert job.done.wait(3)
    assert job.state == "failed" and job.error == "URLError"
    assert "private-endpoint-error" not in str(core.report())

def test_duplicate_probe_shares_observation(core, monkeypatch):
    from tools.jazn_run_studio import probes
    release = threading.Event()
    def slow(*args):
        release.wait(3)
        return {"models": [], "generation_verified": False}
    monkeypatch.setattr(probes, "ollama", slow)
    job = core.probe("ollama")
    try:
        assert core.probe("ollama") is job
    finally:
        release.set()
    assert job.done.wait(3)

def test_violet_night_text_and_control_contrast():
    c = workbench_colors(Settings().theme, Settings().accent)
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))
    def ratio(a, b):
        x, y = sorted((luminance(a), luminance(b)))
        return (y + 0.05) / (x + 0.05)
    for background in (c.background, c.sidebar, c.surface, c.hover):
        assert ratio(c.text, background) >= 4.5
        assert ratio(c.muted, background) >= 4.5
        assert ratio(c.border, background) >= 3
    assert ratio(c.selected_text, c.accent) >= 4.5
