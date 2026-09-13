from __future__ import annotations

import argparse
import json
from typing import Sequence

from latka_jazn.bootstrap.chatgpt_host_preflight_attachments_parse import attachment_reports_from_payload
from latka_jazn.bootstrap.chatgpt_host_preflight_parse import (
    executor_observations_from_payload,
    json_object_from_file,
    optional_bool,
)
from latka_jazn.bootstrap.chatgpt_host_preflight_plan import plan_chatgpt_host_preflight


def run_host_preflight_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py host-preflight",
        description="Classify host execution surfaces, handoff outcomes, alternate routes, and attachment materialization.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", help="Optional JSON contract path or '-' for stdin")
    parser.add_argument("--json", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        payload = json_object_from_file(args.input) if args.input else {
            "package_required": False,
            "executor_observations": [{
                "surface": "current_local_python_process",
                "process_created": True,
                "command_completed": True,
                "returncode": 0,
                "filesystem_probe_succeeded": True,
            }],
            "attachments": [],
        }
        package_required = optional_bool(payload, "package_required", False)
        decision = plan_chatgpt_host_preflight(
            executor_observations_from_payload(payload),
            attachment_reports=attachment_reports_from_payload(payload),
            package_required=bool(package_required),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({
            "ok": False,
            "error_code": "invalid_host_preflight_input",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, ensure_ascii=False, indent=2 if args.json else None, sort_keys=True))
        return 2

    result = decision.to_dict()
    result["ok"] = True
    result["gate_passed"] = decision.bootstrap_allowed
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None, sort_keys=True))
    return 0 if decision.bootstrap_allowed else 3
