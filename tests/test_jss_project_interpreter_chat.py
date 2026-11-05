"""Chat connect, resume and final validation use the selected ROOT interpreter."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import chat
from tools.jazn_run_studio.core import Controller, Settings, StudioError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    (tmp_path / ".settings").mkdir()
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text('PACKAGE_VERSION="test"')
    (tmp_path / "main.py").write_text("# test")
    (tmp_path / "run.py").write_text("# test")
    venv = tmp_path / ".venv"
    local = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    local.parent.mkdir(parents=True)
    local.write_bytes(b"test fixture, not executed")
    (venv / "pyvenv.cfg").write_text("include-system-site-packages=false\n")
    core = Controller(tmp_path, Settings(model="demo"))
    return chat.ChatClient(core), local


def test_connect_and_resume_select_project_interpreter(client):
    transport, local = client
    assert transport.connection_command()[0] == str(local)
    assert transport.resume_command("request-one")[0] == str(local)


def test_validator_uses_project_interpreter(client, monkeypatch):
    transport, local = client
    commands = []

    def validate(argv, **kwargs):
        commands.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"accepted": False}).encode())

    monkeypatch.setattr(chat, "run", validate)
    transport.pending = "request-one"
    transport.receive({})
    assert commands[0][0][0] == str(local)
    assert commands[0][1]["cwd"] == transport.core.root
    assert transport.pending == "request-one"
    assert transport._awaiting_gui_ack is None


def test_operator_override_wins_in_chat(client):
    transport, _local = client
    transport.core.settings = Settings(python=sys.executable, model="demo")
    assert transport.connection_command()[0] == sys.executable
    assert transport.resume_command("request-one")[0] == sys.executable


def test_environment_override_wins_in_chat(client, monkeypatch):
    transport, _local = client
    monkeypatch.setenv("JAZN_STUDIO_PYTHON", sys.executable)
    assert transport.connection_command()[0] == sys.executable


def test_broken_project_environment_cannot_fall_back_in_chat(client):
    transport, local = client
    local.unlink()
    with pytest.raises(StudioError, match="interpretera"):
        transport.connection_command()
    with pytest.raises(StudioError, match="interpretera"):
        transport.resume_command("request-one")
    assert transport.job is None


def test_validator_refuses_broken_environment_before_launch(client, monkeypatch):
    transport, local = client
    local.unlink()
    transport.pending = "request-one"

    def unexpected(*args, **kwargs):
        pytest.fail("Validator launched with an unselected interpreter")

    monkeypatch.setattr(chat, "run", unexpected)
    with pytest.raises(StudioError, match="interpretera"):
        transport.receive({})
    assert transport.pending == "request-one"
