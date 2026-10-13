from __future__ import annotations

"""Fail-closed audit of active documentation and deploy/tool release identity.

Historical snapshots are not rewritten or mistaken for current state. This
script only validates current metadata and precise code-first documentation
anchors. No shell calls, network requests, imports of the live runtime or writes.
"""

import argparse
import json
from pathlib import Path
import re
from typing import Any

ACTIVE_DOCUMENT_MARKERS = {
    "docs/README.md": "**Wersja bieżąca:** dynamiczna — `latka_jazn/version.py`",
    "docs/plans/README.md": "**Wersja bieżąca:** dynamiczna — `latka_jazn/version.py`",
    "docs/plans/CURRENT_STEP.md": "**Wersja bieżąca:** dynamiczna — `latka_jazn/version.py`",
    "docs/project/CURRENT_STATE.md": "**Wersja bieżąca:** dynamiczna — `latka_jazn/version.py`",
    "docs/project/RELEASE_TIMELINE.md": "**Status:** `HISTORICAL_RELEASE_INDEX`",
    "docs/plans/PLAN_EXECUTION_HISTORY.md": "**Status:** `HISTORICAL_EXECUTION_INDEX`",
    "docs/runtime/TURN_FINALIZATION_CONTRACTS.md": "**Linia implementacji:** dynamiczna — `latka_jazn/version.py`",
}

REQUIRED_TOOL_NAMES = (
    "jazn_status", "jazn_generate_visible_reply", "jazn_resume_visible_reply", "jazn_finalize_reply",
)


def audit(root: Path, *, runtime_version: str | None = None) -> dict[str, Any]:
    root = Path(root)
    errors: list[str] = []
    scanned = []
    for relative, marker in ACTIVE_DOCUMENT_MARKERS.items():
        p = root / relative
        scanned.append(relative)
        if not p.is_file():
            errors.append(f"missing_active_document:{relative}")
            continue
        text = p.read_text(encoding="utf-8")
        if marker not in text[:3500]:
            errors.append(f"missing_dynamic_or_historical_marker:{relative}")
    if runtime_version is None:
        version_py = (root / "latka_jazn/version.py").read_text(encoding="utf-8")
        version = re.search(r'^PACKAGE_VERSION\s*=\s*"([^"]+)"', version_py, re.M)
        release = re.search(r'^PACKAGE_RELEASE_NAME\s*=\s*"([^"]+)"', version_py, re.M)
        if not version or not release:
            errors.append("version_py_identity_not_literal")
            runtime_version = None
        else:
            runtime_version = version.group(1) + "-" + release.group(1)
    dep = root / "deploy/chatgpt_mcp/deployment.contract.json"
    if dep.is_file():
        contract = json.loads(dep.read_text(encoding="utf-8"))
        if contract.get("runtime_version") != runtime_version:
            errors.append("deployment_runtime_version_mismatch")
    else:
        errors.append("deployment_contract_missing")
    tool_file = root / "latka_jazn/mcp/chatgpt_toolset.py"
    tool_text = tool_file.read_text(encoding="utf-8") if tool_file.is_file() else ""
    for name in REQUIRED_TOOL_NAMES:
        if f'"{name}"' not in tool_text:
            errors.append("required_tool_missing_in_code:" + name)
    evidence = root / "latka_jazn/resources/chatgpt_startup_evidence_contract.json"
    if evidence.is_file():
        declared = json.loads(evidence.read_text(encoding="utf-8"))
        if tuple(declared.get("required_current_message_tools", ())) != REQUIRED_TOOL_NAMES:
            errors.append("startup_evidence_toolset_mismatch")
    else:
        errors.append("startup_evidence_contract_missing")
    return {"ok": not errors, "errors": errors, "runtime_version": runtime_version, "scanned": scanned}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit current Jaźń docs and MCP metadata")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()
    result = audit(ns.root)
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("documentation/contract audit:", "PASS" if result["ok"] else "FAIL", result["errors"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
