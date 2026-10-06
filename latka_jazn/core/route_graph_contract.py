from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _classifier_literal_intents(root: Path) -> set[str]:
    path = root / "latka_jazn" / "nlp" / "dialogue_intent_classifier.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    intents: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "report":
            continue
        if len(node.args) < 3:
            continue
        intent_node = node.args[2]
        if isinstance(intent_node, ast.Constant) and isinstance(intent_node.value, str):
            intents.add(intent_node.value)
    return intents


def audit_route_graph(root: Path | None = None) -> dict[str, Any]:
    resolved_root = Path(root or _default_root()).resolve()
    registry = RouteRegistry()
    dispatcher = RouteHandlerDispatcher()

    literal_intents = _classifier_literal_intents(resolved_root)
    registered_intents = set(registry.HANDLERS)

    unresolved_intents = sorted(literal_intents - registered_intents)
    routes_without_handlers: list[dict[str, str]] = []
    required_components_without_owner: list[dict[str, Any]] = []

    referenced_handler_names: set[str] = set()
    handlers_by_route: dict[str, set[str]] = {}

    for intent, (route, handler_name) in registry.HANDLERS.items():
        referenced_handler_names.add(handler_name)
        handlers_by_route.setdefault(route, set()).add(handler_name)
        handler_exists = (
            handler_name in dispatcher.handlers_by_name
            or route in dispatcher.handlers_by_route
        )
        if not handler_exists:
            routes_without_handlers.append(
                {
                    "intent": intent,
                    "route": route,
                    "handler_name": handler_name,
                }
            )
            required = registry.required_components_for(intent)
            if required:
                required_components_without_owner.append(
                    {
                        "intent": intent,
                        "route": route,
                        "handler_name": handler_name,
                        "required_components": list(required),
                    }
                )

    compatibility_allowlist = {"FallbackHandler"}
    unreachable_handlers = sorted(
        set(dispatcher.handlers_by_name)
        - referenced_handler_names
        - compatibility_allowlist
    )

    duplicate_canonical_owners = [
        {"route": route, "handler_names": sorted(handler_names)}
        for route, handler_names in sorted(handlers_by_route.items())
        if len(handler_names) > 1
    ]

    anonymous_fallbacks = [
        {
            "intent": intent,
            "route": route,
            "handler_name": handler_name,
        }
        for intent, (route, handler_name) in registry.HANDLERS.items()
        if route == "fallback" or handler_name == "FallbackHandler"
    ]

    failures = {
        "unresolved_intents": unresolved_intents,
        "routes_without_handlers": routes_without_handlers,
        "unreachable_handlers": unreachable_handlers,
        "required_components_without_owner": required_components_without_owner,
        "duplicate_canonical_owners": duplicate_canonical_owners,
        "anonymous_fallbacks": anonymous_fallbacks,
    }
    ok = not any(bool(value) for value in failures.values())

    return {
        "schema_version": "route_graph_audit/v1",
        "ok": ok,
        "root": str(resolved_root),
        "classifier_literal_intent_count": len(literal_intents),
        "registered_intent_count": len(registered_intents),
        "handler_count": len(dispatcher.handlers_by_name),
        "route_count": len(dispatcher.handlers_by_route),
        "compatibility_allowlist": sorted(compatibility_allowlist),
        **failures,
    }
