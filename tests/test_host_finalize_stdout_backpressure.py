from __future__ import annotations

import io
import json

from latka_jazn.cli_commands import host


def test_host_finalize_json_survives_transient_nonblocking_stdout(monkeypatch):
    payload = {"accepted": True, "final_visible_text": "Łatka " + "x" * 100000}
    sink = bytearray()
    call_count = 0

    class Pipe:
        encoding = "utf-8"

        def fileno(self):
            return 41

    def intermittent_write(fd, data):
        nonlocal call_count
        assert fd == 41
        call_count += 1
        if call_count in (1, 3):
            raise BlockingIOError(11, "host pipe temporarily full")
        n = min(len(data), 900)
        sink.extend(data[:n])
        return n

    monkeypatch.setattr(host.sys, "stdout", Pipe())
    monkeypatch.setattr(host.os, "write", intermittent_write)
    monkeypatch.setattr(host.time, "sleep", lambda _: None)
    host._emit_json_stdout(payload)
    assert call_count > 100
    assert json.loads(sink.decode("utf-8")) == payload


def test_host_finalize_json_supports_text_only_capture(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(host.sys, "stdout", stream)
    host._emit_json_stdout({"accepted": False, "error_code": "gate_closed"})
    assert json.loads(stream.getvalue()) == {
        "accepted": False, "error_code": "gate_closed"
    }
