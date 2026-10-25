from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from latka_jazn.core.route_graph_contract import audit_route_graph


def run_audit(root: Path | None = None) -> dict:
    return audit_route_graph(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Jaźń intent -> route -> handler graph without executing a turn.",
        allow_abbrev=False,
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_audit(Path(args.root))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "route_graph_audit "
            f"ok={result['ok']} "
            f"intents={result['registered_intent_count']} "
            f"handlers={result['handler_count']}"
        )
        for key in (
            "unresolved_intents",
            "routes_without_handlers",
            "unreachable_handlers",
            "required_components_without_owner",
            "duplicate_canonical_owners",
            "anonymous_fallbacks",
        ):
            values = result.get(key) or []
            if values:
                print(f"{key}: {values}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
