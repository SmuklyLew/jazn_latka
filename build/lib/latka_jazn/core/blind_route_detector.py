from __future__ import annotations

from typing import Any, Iterable, Mapping

from latka_jazn.core.turn_diagnostics import (
    BlindRouteFinding,
    DiagnosticSeverity,
    FallbackDecision,
    TurnStage,
)


class BlindRouteDetector:
    """Detect incomplete route/handler/validation paths without inferring user intent.

    The detector consumes already-produced runtime evidence. It never classifies
    natural language and never chooses a replacement route.
    """

    def detect(
        self,
        *,
        intent: str | None,
        route: str | None,
        handler_name: str | None,
        required_components: Iterable[str] = (),
        satisfied_components: Iterable[str] = (),
        missing_components: Iterable[str] = (),
        dispatch_report: Mapping[str, Any] | None = None,
        validation: Mapping[str, Any] | None = None,
        fallback: FallbackDecision | Mapping[str, Any] | None = None,
    ) -> tuple[BlindRouteFinding, ...]:
        findings: list[BlindRouteFinding] = []
        dispatch = dict(dispatch_report or {})
        validator = dict(validation or {})
        required = {str(item) for item in required_components if str(item).strip()}
        satisfied = {str(item) for item in satisfied_components if str(item).strip()}
        missing = {str(item) for item in missing_components if str(item).strip()}

        if not str(intent or "").strip():
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_INTENT_MISSING",
                    stage=TurnStage.ROUTING,
                    component="DialogueIntentClassifier",
                )
            )
        if not str(route or "").strip():
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_ROUTE_MISSING",
                    stage=TurnStage.ROUTING,
                    component="RouteRegistry",
                )
            )
        if not str(handler_name or "").strip():
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_HANDLER_MISSING",
                    stage=TurnStage.HANDLER,
                    component="RouteHandlerDispatcher",
                )
            )

        dispatch_status = str(dispatch.get("status") or "").strip()
        if dispatch_status and dispatch_status != "ok":
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_HANDLER_DISPATCH_DEGRADED",
                    stage=TurnStage.HANDLER,
                    component="RouteHandlerDispatcher",
                    severity=DiagnosticSeverity.WARNING,
                    attributes={
                        "dispatch_status": dispatch_status,
                        "requested_handler": dispatch.get("requested_handler"),
                        "selected_handler": dispatch.get("selected_handler"),
                    },
                )
            )

        effective_missing = set(missing)
        if required and satisfied:
            effective_missing.update(required - satisfied)
        if effective_missing:
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_REQUIRED_COMPONENT_MISSING",
                    stage=TurnStage.VALIDATION,
                    component="RuntimeAnswerValidator",
                    attributes={"missing_components": sorted(effective_missing)},
                )
            )

        accepted = validator.get("accepted")
        mismatch_reason = str(validator.get("mismatch_reason") or "").strip()
        checks = [
            str(item)
            for item in validator.get("checks") or []
            if str(item).strip()
        ]
        validator_missing = [
            str(item)
            for item in validator.get("missing_required_components") or []
            if str(item).strip()
        ]
        if accepted is False and not mismatch_reason and not checks and not validator_missing:
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_VALIDATION_REJECTED_WITHOUT_REASON",
                    stage=TurnStage.VALIDATION,
                    component="RuntimeAnswerValidator",
                )
            )

        fallback_payload: Mapping[str, Any] | None
        if isinstance(fallback, FallbackDecision):
            fallback_payload = fallback.to_dict()
        elif isinstance(fallback, Mapping):
            fallback_payload = fallback
        else:
            fallback_payload = None

        route_is_fallback = str(route or "").strip() == "fallback"
        dispatch_degraded = bool(dispatch_status and dispatch_status != "ok")
        if (route_is_fallback or dispatch_degraded) and not fallback_payload:
            findings.append(
                BlindRouteFinding.build(
                    code="BLIND_ROUTE_ANONYMOUS_FALLBACK",
                    stage=TurnStage.RECOVERY,
                    component="BlindRouteDetector",
                    attributes={
                        "route": route,
                        "dispatch_status": dispatch_status or None,
                    },
                )
            )

        return tuple(findings)
