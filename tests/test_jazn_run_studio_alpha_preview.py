"""Preflight must not execute commands or disclose raw argument values."""
import argparse
import pytest
from tools.jazn_run_studio.studio_worker import commands, preview_command, preview_fingerprint, argv_for


def schema():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    child = parser.add_subparsers(dest="command", required=True).add_parser("save")
    child.add_argument("--target", required=True)
    return commands(parser)[0]


def test_preview_preserves_only_safe_metadata():
    command = schema()
    spec = {"path": command["path"], "values": {"0": "/private/export.sqlite"}}
    result = preview_command(command, spec)
    assert result["execution_performed"] is False
    assert result["requires_confirmation"] is True
    assert result["fingerprint"] == preview_fingerprint(spec)
    assert "/private" not in str(result)


def test_edit_requires_a_new_preview():
    command = schema()
    first = {"path": command["path"], "values": {"0": "first.db"}}
    second = {"path": command["path"], "values": {"0": "second.db"}}
    assert preview_fingerprint(first) != preview_fingerprint(second)


def test_unknown_args_wrong_path_and_oversize_are_rejected():
    command = schema()
    for bad in [
        {"path": ["wrong"], "values": {"0": "ok"}},
        {"path": command["path"], "values": {"unknown": "x"}},
        {"path": command["path"], "values": {"0": "x" * 100000}},
        {"path": command["path"], "values": {}, "extra": True},
    ]:
        with pytest.raises(ValueError):
            preview_command(command, bad)
    with pytest.raises(ValueError):
        argv_for(command, {})
