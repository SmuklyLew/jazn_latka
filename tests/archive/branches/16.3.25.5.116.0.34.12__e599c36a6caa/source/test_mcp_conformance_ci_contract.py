from __future__ import annotations

from pathlib import Path


def test_official_mcp_conformance_installs_test_dependencies_before_contract_gate() -> None:
    yaml = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mcp-conformance.yml").read_text(encoding="utf-8")
    assert 'python -m pip install -e ".[mcp-http]" pytest' in yaml
    assert "python -X utf8 -m pytest" in yaml
    assert "tests/test_mcp_task_protocol_authorization.py" in yaml
    assert '--requirements", "2026-07-28"' in (
        Path(__file__).resolve().parents[1] / "tools" / "mcp_conformance_runner.py"
    ).read_text(encoding="utf-8")
