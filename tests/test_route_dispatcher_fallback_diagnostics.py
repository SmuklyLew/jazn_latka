from __future__ import annotations

from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistryEntry


class _ExplodingHandler:
    name = "ExplodingHandler"
    route = "explode"
    handled_intents = ("explode_intent",)

    def handle(self, text: str, context: dict) -> RouteHandlerResult:
        raise RuntimeError("boom")


def test_dispatcher_marks_unresolved_handler_as_typed_fallback() -> None:
    dispatcher = RouteHandlerDispatcher()
    entry = RouteRegistryEntry(
        intent="missing_intent",
        route="missing_route",
        handler_name="MissingHandler",
        priority=1,
    )

    result = dispatcher.dispatch(entry, "test", {})
    fallback = result.data["fallback_decision"]
    report = result.data["dispatch_report"]

    assert fallback["kind"] == "RECOVERABLE_FALLBACK"
    assert fallback["reason_code"] == "ROUTE_HANDLER_UNRESOLVED"
    assert fallback["from_route"] == "missing_route"
    assert fallback["to_route"] == "fallback"
    assert report["status"] == "fallback_selected"


def test_dispatcher_preserves_handler_exception_as_typed_fallback() -> None:
    dispatcher = RouteHandlerDispatcher()
    exploding = _ExplodingHandler()
    dispatcher.handlers_by_name[exploding.name] = exploding
    dispatcher.handlers_by_route[exploding.route] = exploding
    entry = RouteRegistryEntry(
        intent="explode_intent",
        route=exploding.route,
        handler_name=exploding.name,
        priority=1,
    )

    result = dispatcher.dispatch(entry, "test", {})
    fallback = result.data["fallback_decision"]
    report = result.data["dispatch_report"]

    assert fallback["reason_code"] == "HANDLER_EXCEPTION"
    assert fallback["origin_stage"] == "HANDLER"
    assert report["status"] == "handler_error"
    assert result.errors[-1]["error_type"] == "RuntimeError"
    assert result.errors[-1]["reason_code"] == "HANDLER_EXCEPTION"
