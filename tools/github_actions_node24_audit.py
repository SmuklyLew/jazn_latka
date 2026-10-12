from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence


EXPECTED_ACTION_SHAS: dict[str, str] = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",  # v7.0.1, node24
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",  # v7.0.0, node24
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",  # v7.0.0, node24
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",  # v7.0.1, node24
    "actions/download-artifact": "37930b1c2abaa49bbe596cd826c3c89aef350131",  # audited node24 pin
    "actions/dependency-review-action": "a1d282b36b6f3519aa1f3fc636f609c47dddb294",  # audited node24 pin
    "actions/attest": "1e69f48acb82d1966a394da916b4c1698aa569d6",  # audited node24 pin
}

FORBIDDEN_NODE20_ACTION_SHAS = frozenset(
    {
        "34e114876b0b11c390a56381ad16ebd13914f8d5",  # checkout v4 line
        "a26af69be951a213d495a4c3e4e4022e16d87065",  # setup-python v5 line
        "49933ea5288caeca8642d1e84afbd3f7d6820020",  # setup-node v4 line
    }
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)


def audit_workflows(root: Path) -> dict[str, Any]:
    workflow_root = root / ".github" / "workflows"
    findings: list[dict[str, str]] = []
    observed: dict[str, set[str]] = {}
    workflows = sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml"))

    if not workflows:
        findings.append({"path": str(workflow_root), "reason": "no_active_workflows"})

    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if "node20" in text.lower():
            findings.append({"path": path.as_posix(), "reason": "literal_node20_runtime"})

        for reference in _USES_RE.findall(text):
            if reference.startswith("./"):
                continue
            if "@" not in reference:
                findings.append(
                    {"path": path.as_posix(), "reference": reference, "reason": "unversioned_external_action"}
                )
                continue
            action, sha = reference.rsplit("@", 1)
            observed.setdefault(action, set()).add(sha)
            if sha in FORBIDDEN_NODE20_ACTION_SHAS:
                findings.append(
                    {"path": path.as_posix(), "reference": reference, "reason": "forbidden_node20_action_pin"}
                )
                continue
            if not _SHA_RE.fullmatch(sha):
                findings.append(
                    {"path": path.as_posix(), "reference": reference, "reason": "action_not_pinned_to_full_sha"}
                )
                continue
            expected = EXPECTED_ACTION_SHAS.get(action)
            if expected is None:
                findings.append(
                    {"path": path.as_posix(), "reference": reference, "reason": "unreviewed_external_action"}
                )
            elif sha != expected:
                findings.append(
                    {
                        "path": path.as_posix(),
                        "reference": reference,
                        "reason": "action_sha_differs_from_audited_node24_pin",
                        "expected": f"{action}@{expected}",
                    }
                )

    return {
        "ok": not findings,
        "workflow_count": len(workflows),
        "audited_actions": {name: sorted(values) for name, values in sorted(observed.items())},
        "expected_action_shas": dict(sorted(EXPECTED_ACTION_SHAS.items())),
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    payload = audit_workflows(args.root.resolve())
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        state = "OK" if payload["ok"] else "FAIL"
        print(f"GitHub Actions Node24 audit: {state}; workflows={payload['workflow_count']}")
        for finding in payload["findings"]:
            print(json.dumps(finding, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
