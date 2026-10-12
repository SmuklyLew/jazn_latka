from __future__ import annotations

from pathlib import Path
from typing import Any

from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.core.update_coverage_audit import UpdateCoverageAuditor
from latka_jazn.version import generation_mode, schema_version


class PostUpdateCoverageAuditHandler:
    name = "PostUpdateCoverageAuditHandler"
    route = "post_update_coverage_audit"
    handled_intents = ("post_update_coverage_audit_request",)

    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx = context or {}
        config = ctx.get("config")
        root = Path(getattr(config, "root", "."))
        audit = UpdateCoverageAuditor(root).audit()
        report = audit.to_dict()
        lines = [
            f"Audyt kompletności aktualizacji: covered={audit.covered_count}, missing={audit.missing_count}.",
        ]
        for item in audit.items:
            state = "OK" if item.covered else "BRAK"
            lines.append(f"- {state} {item.requirement_id}: {item.description}")
            if item.missing_paths:
                lines.append(f"  Brakujące dowody: {', '.join(item.missing_paths)}")
        lines.append(f"Granica prawdy: {audit.truth_boundary}")
        return RouteHandlerResult(
            self.name,
            self.route,
            "\n".join(lines),
            intent=str(ctx.get("intent") or "post_update_coverage_audit_request"),
            data={"update_coverage_audit": report, "preserve_handler_body": True},
            required_components=list(ctx.get("required_components") or []),
            satisfied_components=[
                "patch_scope", "covered_items", "omissions", "evidence", "tests",
                "release_boundary", "truth_boundary",
            ],
            confidence=0.98,
            generation_mode=generation_mode("post_update_coverage_audit"),
            source_origin_detail=schema_version("post_update_coverage_audit_handler"),
            truth_boundary=audit.truth_boundary,
        )
