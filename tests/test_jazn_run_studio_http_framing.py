"""Malformed transport is an explicit failure and never a ready service."""
from __future__ import annotations

from http.client import IncompleteRead
from pathlib import Path

import pytest

from latka_jazn.mcp import chatgpt_bridge_probe as catalog
from tools.jazn_run_studio import probes
from tools.jazn_run_studio.core import Controller


class BrokenResponse:
    status = code = 200
    headers = {"Content-Type":"application/json"}
    def geturl(self): return "http://127.0.0.1:8080/mcp"
    def __enter__(self): return self
    def __exit__(self,*_args): return False
    def read(self,*_args): raise IncompleteRead(b"untrusted private response")


class BrokenOpener:
    def open(self,*_args,**_kwargs): return BrokenResponse()


def test_catalog_malformed_http_returns_structured_failure_without_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog.urllib.request,"build_opener",lambda *_a: BrokenOpener())
    report = catalog.probe_chatgpt_mcp_tool_catalog("http://127.0.0.1:8080/mcp")
    assert report["ok"] is False and report["tool_catalog_verified"] is False
    assert report["reason"] == "mcp_catalog_invalid_http_framing"
    assert "untrusted private response" not in str(report)


def test_service_framing_failure_finishes_failed_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path/"latka_jazn").mkdir()
    (tmp_path/"latka_jazn/version.py").touch()
    (tmp_path/"run.py").touch()
    (tmp_path/"main.py").touch()
    monkeypatch.setattr(probes,"build_opener",lambda *_a: BrokenOpener())
    core = Controller(tmp_path)
    job = core.probe("gateway")
    assert job.done.wait(5)
    assert job.state == "failed" and job.error == "ValueError"
    assert "untrusted private response" not in str(core.logs)
