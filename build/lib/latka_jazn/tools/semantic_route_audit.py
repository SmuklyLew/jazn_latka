from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("semantic_route_audit")


def run_audit(root: Path) -> dict[str, Any]:
    source = json.loads((root / "latka_jazn/resources/nlp/semantic_route_scenarios.json").read_text(encoding="utf-8"))
    classifier = DialogueIntentClassifier()
    failures: list[dict[str, str]] = []
    checked = 0
    for scenario in source.get("scenarios", []):
        expected = str(scenario["expected_primary"])
        for marker, stem, suffix in itertools.product(
            scenario.get("tool_markers", [""]),
            scenario.get("stems", []),
            source.get("punctuation", [""]),
        ):
            text = f"{marker}{stem}{suffix}".strip()
            report = classifier.classify(text)
            checked += 1
            if report.primary_intent != expected:
                failures.append({
                    "scenario": str(scenario.get("id") or "unknown"),
                    "text": text,
                    "expected": expected,
                    "actual": report.primary_intent,
                })
            if marker.strip() and "external_tool_assistance_request" not in report.secondary_intents:
                failures.append({
                    "scenario": str(scenario.get("id") or "unknown"),
                    "text": text,
                    "expected": "secondary:external_tool_assistance_request",
                    "actual": ",".join(report.secondary_intents),
                })
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": PACKAGE_VERSION_FULL,
        "ok": not failures,
        "checked": checked,
        "failure_count": len(failures),
        "failures": failures,
        "independent_lane": True,
        "truth_boundary": "Oddzielny korpus scenariuszy sprawdza routing; nie jest ludzkim review ani dowodem świadomości.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_audit(Path(args.root).resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic-route-audit ok={result['ok']} checked={result['checked']} failures={result['failure_count']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
