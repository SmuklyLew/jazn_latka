from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from latka_jazn.core.dialogue_task_state import DialogueTaskStateResolver
from latka_jazn.core.operational_learning_memory import OperationalLearningMemory
from latka_jazn.core.reasoning_orchestrator import ReasoningOrchestrator
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.runtime_daemon import DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS
from latka_jazn.core.turn_timeout import (
    DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS,
    DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS,
)
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("cognitive_architecture_audit")

REQUIRED_FILES = (
    "latka_jazn/core/dialogue_task_state.py",
    "latka_jazn/core/reasoning_orchestrator.py",
    "latka_jazn/core/knowledge_fabric.py",
    "latka_jazn/core/operational_learning_memory.py",
    "latka_jazn/core/runtime_daemon.py",
    "latka_jazn/core/turn_timeout.py",
    "latka_jazn/memory/conversation_archive.py",
    "latka_jazn/memory/store.py",
    "latka_jazn/nlp/lexical_intelligence.py",
    "latka_jazn/resources/cognition/v154_architecture.json",
    "latka_jazn/resources/cognition/v154_dialogue_benchmark.json",
    "latka_jazn/resources/cognition/v154_operational_lessons.json",
    "latka_jazn/resources/nlp/v154_lexical_sources.json",
    "tests/test_dialogue_task_state_v154.py",
    "tests/test_reasoning_orchestrator_v154.py",
    "tests/test_knowledge_fabric_v154.py",
    "tests/test_lexical_intelligence_v154.py",
)


def _conversation_regressions(root: Path) -> list[dict[str, Any]]:
    benchmark_path = root / "latka_jazn/resources/cognition/v154_dialogue_benchmark.json"
    try:
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [{"id": "benchmark-load", "ok": False, "error": "benchmark_unavailable"}]
    raw_cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(raw_cases, list) or not raw_cases:
        return [{"id": "benchmark-empty", "ok": False, "error": "benchmark_empty"}]
    classifier = DialogueIntentClassifier()
    results: list[dict[str, Any]] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "")
        expected = str(raw.get("expected_intent") or "")
        previous_intent = str(raw.get("previous_intent") or "") or None
        previous_route = str(raw.get("previous_route") or "") or None
        previous_text = str(raw.get("previous_text") or "") or None
        task_state = None
        if bool(raw.get("active_task")) and previous_intent and previous_route:
            task_state = DialogueTaskStateResolver.derive_state(
                user_text=previous_text or "Aktywne zadanie",
                intent=previous_intent,
                route=previous_route,
                confidence=0.95,
            ).to_dict()
        actual = classifier.classify(
            text,
            previous_text=previous_text,
            previous_intent=previous_intent,
            previous_route=previous_route,
            previous_task_state=task_state,
        ).primary_intent
        results.append(
            {
                "id": str(raw.get("id") or "unnamed"),
                "text": text,
                "expected": expected,
                "actual": actual,
                "ok": expected == actual,
            }
        )
    return results


def run_audit(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    contextual_route = RouteRegistry().resolve("contextual_continuation_question")
    route_ok = contextual_route.route == "ordinary_dialogue" and contextual_route.handler_name == "OrdinaryDialogueHandler"
    reasoning = ReasoningOrchestrator().plan(
        user_text="Przygotuj pełną architekturę, wykonaj aktualizację i zweryfikuj brak regresji.",
        intent="system_update_execution_request",
        classifier_confidence=0.84,
        tool_available=True,
    )
    regressions = _conversation_regressions(root)
    lessons = OperationalLearningMemory.from_json_file(
        root / "latka_jazn/resources/cognition/v154_operational_lessons.json"
    )
    lesson_payload = lessons.to_dict()

    mixed_report = DialogueIntentClassifier().classify(
        "@Wyszukiwanie w sieci Przejrzyj wiarygodne źródła i napraw błędy, złe trasy oraz brakujące elementy systemu Jaźni."
    )
    negated_report = DialogueIntentClassifier().classify(
        "@Wyszukiwanie w sieci Nie zmieniaj kodu. Przejrzyj źródła i powiedz co poprawić."
    )
    dispatcher = RouteHandlerDispatcher()
    route_dispatch_missing = []
    for intent in RouteRegistry.HANDLERS:
        entry = RouteRegistry().resolve(intent)
        if entry.handler_name not in dispatcher.handlers_by_name and entry.route not in dispatcher.handlers_by_route:
            route_dispatch_missing.append(intent)

    checks = {
        "required_files": not missing,
        "contextual_continuation_route_safe": route_ok,
        "reasoning_verification_gate": reasoning.requires_verification,
        "reasoning_tool_gate": reasoning.requires_tools,
        "private_chain_of_thought_not_required": all("chain" not in step for step in reasoning.operational_steps),
        "conversation_regressions": bool(regressions) and all(item.get("ok") for item in regressions),
        "verified_operational_lessons": int(lesson_payload.get("verified_count") or 0) >= 2,
        "mixed_web_execution_route_safe": (
            mixed_report.primary_intent == "system_update_execution_request"
            and mixed_report.update_request is True
            and "external_research_request" in mixed_report.secondary_intents
        ),
        "negated_write_route_safe": (
            negated_report.primary_intent != "system_update_execution_request"
            and negated_report.update_request is False
        ),
        "route_dispatcher_complete": not route_dispatch_missing,
        "deadline_hierarchy_safe": (
            0 < DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS
            < DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS
            <= DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": PACKAGE_VERSION_FULL,
        "ok": all(checks.values()),
        "checks": checks,
        "missing_files": missing,
        "conversation_regressions": regressions,
        "routing_resilience": {
            "mixed_web_execution_primary": mixed_report.primary_intent,
            "mixed_web_execution_secondary": mixed_report.secondary_intents,
            "negated_write_primary": negated_report.primary_intent,
            "route_dispatch_missing": route_dispatch_missing,
        },
        "deadline_contract": {
            "runtime_turn_seconds": DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS,
            "daemon_chat_seconds": DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS,
            "deep_recall_seconds": DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS,
        },
        "reasoning_probe": reasoning.to_dict(),
        "operational_learning": {
            "lesson_count": lesson_payload.get("lesson_count"),
            "verified_count": lesson_payload.get("verified_count"),
        },
        "truth_boundary": "Audit validates source contracts and deterministic regression probes; it does not prove general intelligence or consciousness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_audit(Path(args.root))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("ok" if result["ok"] else "failed")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
