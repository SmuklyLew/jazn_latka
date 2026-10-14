from __future__ import annotations

from io import BytesIO, TextIOWrapper

from tools import mcp_conformance_runner


def test_mcp_runner_unicode_logs_work_on_windows_cp1252(monkeypatch) -> None:
    output = BytesIO()
    stdout = TextIOWrapper(output, encoding="cp1252", write_through=True)
    monkeypatch.setattr(mcp_conformance_runner.sys, "stdout", stdout)
    mcp_conformance_runner._configure_unicode_console()
    stdout.write("Błąd: Jaźń — niezrealizowany wynik ⏳")
    stdout.flush()
    assert stdout.encoding.lower().replace("-", "") == "utf8"
    assert "Jaźń" in output.getvalue().decode("utf-8")
