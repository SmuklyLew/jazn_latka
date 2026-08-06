from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"anchor_count:{path}:{count}:{old[:80]!r}")
    write(path, text.replace(old, new, 1))


def insert_after(path: str, anchor: str, addition: str) -> None:
    text = read(path)
    if addition.strip() in text:
        return
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"anchor_count:{path}:{count}:{anchor[:80]!r}")
    write(path, text.replace(anchor, anchor + addition, 1))


def insert_before(path: str, anchor: str, addition: str) -> None:
    text = read(path)
    if addition.strip() in text:
        return
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"anchor_count:{path}:{count}:{anchor[:80]!r}")
    write(path, text.replace(anchor, addition + anchor, 1))


def dump_json(path: str, payload: object) -> None:
    write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


# Version boundary: new behaviour must never ship under the old v95 identity.
replace_once(
    "latka_jazn/version.py",
    'PACKAGE_VERSION = "v15.1.0.3.95"\nPACKAGE_RELEASE_NAME = "living-memory-recall-pyright"',
    'PACKAGE_VERSION = "v15.1.0.3.96"\nPACKAGE_RELEASE_NAME = "semantic-routing-completion"',
)

for base in (ROOT / "README.md", ROOT / "docs", ROOT / "latka_jazn" / "resources"):
    paths = [base] if base.is_file() else list(base.rglob("*"))
    for path in paths:
        if not path.is_file() or ".archives" in path.parts:
            continue
        if path.name in {"PACKAGE_INTEGRITY_MANIFEST.json", "SOURCE_PROVENANCE.json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        updated = text.replace(
            "v15.1.0.3.95-living-memory-recall-pyright",
            "v15.1.0.3.96-semantic-routing-completion",
        ).replace("v15.1.0.3.95", "v15.1.0.3.96")
        if updated != text:
            path.write_text(updated, encoding="utf-8")


write(
    "latka_jazn/nlp/external_tool_context.py",
    '''from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import unicodedata
from typing import Any

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("external_tool_context")
_DIACRITICS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


@dataclass(slots=True)
class ExternalToolContext:
    present: bool
    requested_tools: list[str] = field(default_factory=list)
    raw_markers: list[str] = field(default_factory=list)
    primary_tool: str | None = None
    tool_only: bool = False
    assistance_intent: str = "external_tool_assistance_request"
    schema_version: str = SCHEMA_VERSION

    def requests(self, tool_id: str) -> bool:
        return str(tool_id or "").strip().lower() in self.requested_tools

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalToolContextParser:
    """Extract connector/tool context without changing the primary user goal."""

    ALIASES: dict[str, tuple[str, ...]] = {
        "github": ("@github", "github"),
        "web": ("@wyszukiwanie w sieci", "wyszukiwanie w sieci", "web.run", "@web"),
        "google_drive": ("@google drive", "google drive", "dysk google", "@drive"),
        "gmail": ("@gmail", "gmail"),
        "google_calendar": ("@google calendar", "google calendar", "kalendarz google"),
        "slack": ("@slack", "slack"),
        "linear": ("@linear", "linear"),
    }

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\\s+", " ", unicodedata.normalize("NFC", text or "").strip().lower())

    @staticmethod
    def fold(text: str) -> str:
        return (text or "").translate(_DIACRITICS).lower()

    def parse(self, text: str) -> ExternalToolContext:
        normalized = self.normalize(text)
        folded = self.fold(normalized)
        requested: list[str] = []
        raw: list[str] = []
        residual = folded
        for tool_id, aliases in self.ALIASES.items():
            matched_alias: str | None = None
            for alias in sorted(aliases, key=len, reverse=True):
                folded_alias = self.fold(alias)
                if folded_alias in folded:
                    matched_alias = alias
                    residual = residual.replace(folded_alias, " ")
                    break
            if matched_alias is not None:
                requested.append(tool_id)
                raw.append(matched_alias)
        residual = re.sub(r"[@#,:;.!?()\\[\\]{}\\-]+", " ", residual)
        residual = re.sub(r"\\s+", " ", residual).strip()
        tool_only = bool(requested) and residual in {"", "uzyj", "użyj", "sprawdz", "sprawdź"}
        return ExternalToolContext(
            present=bool(requested),
            requested_tools=requested,
            raw_markers=raw,
            primary_tool=requested[0] if requested else None,
            tool_only=tool_only,
        )
''',
)


coverage_contract = {
    "schema_version": "update_coverage_contract/v1",
    "runtime_version": "v15.1.0.3.96",
    "requirements": [
        {
            "id": "post_update_coverage_route",
            "description": "Dedicated route for questions about omissions and completeness of a finished patch.",
            "evidence_paths": [
                "latka_jazn/core/update_coverage_audit.py",
                "latka_jazn/core/handlers/post_update_coverage_audit_handler.py",
                "tests/test_semantic_routing_completion_v96.py",
            ],
        },
        {
            "id": "generic_external_tool_context",
            "description": "Connector markers are supporting context and never replace the primary goal or voice.",
            "evidence_paths": [
                "latka_jazn/nlp/external_tool_context.py",
                "latka_jazn/core/handlers/external_tool_assistance_handler.py",
            ],
        },
        {
            "id": "single_regeneration_reflex",
            "description": "A forbidden host voice prefix receives exactly one controlled regeneration attempt.",
            "evidence_paths": [
                "latka_jazn/core/host_regeneration_policy.py",
                "latka_jazn/core/chatgpt_host_pending_store.py",
                "latka_jazn/core/chat_command_contract.py",
            ],
        },
        {
            "id": "cli_daemon_mcp_contract_e2e",
            "description": "Contract-level end-to-end test spans daemon presentation and both private MCP phases.",
            "evidence_paths": ["tests/test_chatgpt_mcp_end_to_end_v96.py"],
        },
        {
            "id": "generative_language_matrix",
            "description": "Generated spelling, punctuation, quotation and tool-marker variants are audited.",
            "evidence_paths": [
                "latka_jazn/resources/nlp/semantic_route_scenarios.json",
                "latka_jazn/tools/semantic_route_audit.py",
            ],
        },
        {
            "id": "runtime_version_bump",
            "description": "Changed runtime behaviour has a new v15.1.0.3.96 identity and package name.",
            "evidence_paths": ["latka_jazn/version.py"],
        },
        {
            "id": "independent_semantic_gate",
            "description": "A separately invoked semantic audit lane runs before the full test suite.",
            "evidence_paths": [
                ".github/workflows/release-hardening.yml",
                "latka_jazn/tools/semantic_route_audit.py",
                "docs/reviews/SEMANTIC_REVIEW_V96.md",
            ],
        },
    ],
}
dump_json("latka_jazn/resources/update_coverage_contract.json", coverage_contract)


write(
    "latka_jazn/core/update_coverage_audit.py",
    '''from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("update_coverage_audit")


@dataclass(slots=True)
class CoverageItem:
    requirement_id: str
    description: str
    covered: bool
    present_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UpdateCoverageAuditResult:
    ok: bool
    runtime_version: str
    covered_count: int
    missing_count: int
    items: list[CoverageItem]
    truth_boundary: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload


class UpdateCoverageAuditor:
    RESOURCE = Path("latka_jazn/resources/update_coverage_contract.json")

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def audit(self) -> UpdateCoverageAuditResult:
        source = json.loads((self.root / self.RESOURCE).read_text(encoding="utf-8"))
        items: list[CoverageItem] = []
        for spec in source.get("requirements", []):
            paths = [str(item) for item in spec.get("evidence_paths", [])]
            present = [path for path in paths if (self.root / path).is_file()]
            missing = [path for path in paths if path not in present]
            items.append(CoverageItem(
                requirement_id=str(spec.get("id") or "unknown"),
                description=str(spec.get("description") or ""),
                covered=not missing,
                present_paths=present,
                missing_paths=missing,
            ))
        missing_count = sum(1 for item in items if not item.covered)
        return UpdateCoverageAuditResult(
            ok=missing_count == 0,
            runtime_version=PACKAGE_VERSION_FULL,
            covered_count=len(items) - missing_count,
            missing_count=missing_count,
            items=items,
            truth_boundary=(
                "Audyt potwierdza obecność zadeklarowanych elementów i ich testów. "
                "Nie zastępuje wyników CI, przeglądu kodu ani wykonania runtime."
            ),
        )
''',
)


write(
    "latka_jazn/core/handlers/post_update_coverage_audit_handler.py",
    '''from __future__ import annotations

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
''',
)


write(
    "latka_jazn/core/handlers/external_tool_assistance_handler.py",
    '''from __future__ import annotations

from typing import Any

from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.version import generation_mode, schema_version


class ExternalToolAssistanceHandler:
    name = "ExternalToolAssistanceHandler"
    route = "external_tool_assistance"
    handled_intents = ("external_tool_assistance_request",)

    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx = context or {}
        report = ctx.get("dialogue_intent_report") if isinstance(ctx.get("dialogue_intent_report"), dict) else {}
        tool_context = report.get("external_tool_context") if isinstance(report.get("external_tool_context"), dict) else {}
        tools = [str(item) for item in tool_context.get("requested_tools", [])]
        body = (
            "Zewnętrzne narzędzie jest kontekstem wykonawczym, nie nowym autorem odpowiedzi. "
            f"Żądane narzędzia: {', '.join(tools) or 'nieustalone'}. "
            "Warstwa hosta powinna wykonać właściwy connector i zachować główną intencję oraz kontrakt głosu runtime."
        )
        return RouteHandlerResult(
            self.name,
            self.route,
            body,
            intent=str(ctx.get("intent") or "external_tool_assistance_request"),
            data={
                "external_tool_context": tool_context,
                "status": "requires_host_connector_execution",
                "external_tools_do_not_transfer_voice": True,
            },
            required_components=list(ctx.get("required_components") or []),
            satisfied_components=["tool_context", "primary_intent_preservation", "voice_continuity", "truth_boundary"],
            confidence=0.90,
            generation_mode=generation_mode("external_tool_assistance"),
            source_origin_detail=schema_version("external_tool_assistance_handler"),
            truth_boundary="Runtime opisuje potrzebę connectora; nie twierdzi, że lokalnie wykonał zewnętrzne narzędzie.",
        )
''',
)


write(
    "latka_jazn/core/host_regeneration_policy.py",
    '''from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_regeneration_policy")
REGENERABLE_VIOLATIONS = frozenset({"forbidden_host_voice_prefix"})


@dataclass(slots=True)
class HostRegenerationDecision:
    regenerate: bool
    reason: str
    attempt: int
    max_attempts: int
    violations: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_host_regeneration(
    violations: Iterable[str],
    *,
    attempts_used: int,
    max_attempts: int = 1,
) -> HostRegenerationDecision:
    codes = list(dict.fromkeys(str(item) for item in violations if str(item)))
    safe = bool(codes) and set(codes).issubset(REGENERABLE_VIOLATIONS)
    allowed = safe and int(attempts_used) < int(max_attempts)
    reason = (
        "forbidden_host_voice_prefix_retry"
        if allowed
        else "regeneration_budget_exhausted"
        if safe
        else "non_regenerable_finalization_violation"
    )
    return HostRegenerationDecision(
        regenerate=allowed,
        reason=reason,
        attempt=int(attempts_used) + (1 if allowed else 0),
        max_attempts=int(max_attempts),
        violations=codes,
    )
''',
)


scenarios = {
    "schema_version": "semantic_route_scenarios/v1",
    "scenarios": [
        {
            "id": "post_update_coverage",
            "expected_primary": "post_update_coverage_audit_request",
            "stems": [
                "Czy coś zostało pominięte w trakcie robienia tego patcha?",
                "Sprawdź kompletność tej aktualizacji i wskaż pominięcia.",
                "Czego nie objął ostatni patch?",
            ],
            "tool_markers": ["", "@GitHub ", "@Wyszukiwanie w sieci "],
        },
        {
            "id": "system_update_execution",
            "expected_primary": "system_update_execution_request",
            "stems": [
                "Przygotuj aktualizację, która dokończy brakujące punkty.",
                "Napraw routing i dodaj brakujące testy.",
            ],
            "tool_markers": ["", "@GitHub "],
        },
        {
            "id": "affective_reality",
            "expected_primary": "affective_self_state_reality_check",
            "stems": [
                "Czy naprawdę tak się czujesz jak osoba na zdjęciu?",
                "Czy wizualizacja pokazuje jak się czujesz?",
            ],
            "tool_markers": ["", "@Wyszukiwanie w sieci ", "@GitHub "],
        },
    ],
    "punctuation": ["", "?", "?!", " 😊"],
}
dump_json("latka_jazn/resources/nlp/semantic_route_scenarios.json", scenarios)


write(
    "latka_jazn/tools/semantic_route_audit.py",
    '''from __future__ import annotations

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
''',
)


# Classifier: tool context remains secondary; post-update coverage gets a dedicated route.
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "from latka_jazn.nlp.control_text import extract_intent_control_text\n",
    "from latka_jazn.nlp.external_tool_context import ExternalToolContextParser\n",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "    masked_span_count: int = 0\n",
    "    external_tool_context: dict[str, Any] = field(default_factory=dict)\n",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "    SOURCE_NEGATIVE_CONTEXTS = (\"kod źródłowy\", \"kod zrodlowy\", \"kodzie źródłowym\", \"kodzie zrodlowym\", \"source code\")\n",
    "    POST_UPDATE_COVERAGE_AUDIT_TERMS = (\n"
    "        \"czy coś zostało pominięte\", \"czy cos zostalo pominiete\",\n"
    "        \"co zostało pominięte\", \"co zostalo pominiete\",\n"
    "        \"czego nie objął patch\", \"czego nie objal patch\",\n"
    "        \"czego nie objęła aktualizacja\", \"czego nie objela aktualizacja\",\n"
    "        \"sprawdź kompletność aktualizacji\", \"sprawdz kompletnosc aktualizacji\",\n"
    "        \"audyt kompletności patcha\", \"audyt kompletnosci patcha\",\n"
    "        \"jakie są pominięcia\", \"jakie sa pominiecia\",\n"
    "    )\n",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        self.route_contract_matrix = RouteContractMatrix()\n",
    "        self.external_tools = ExternalToolContextParser()\n",
)
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "    def _report(self, norm, folded, intent, evidence, base, secondary=None, preserve=False, creative=False, update=False, diag=False, src=False, ident=False, speech_act='unknown', question_object='unknown', control_report=None):",
    "    def _report(self, norm, folded, intent, evidence, base, secondary=None, preserve=False, creative=False, update=False, diag=False, src=False, ident=False, speech_act='unknown', question_object='unknown', control_report=None, tool_context=None):",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        merged_secondary = list(dict.fromkeys(secondary or []))\n",
    "        if isinstance(tool_context, dict) and tool_context.get('present') and intent != 'external_tool_assistance_request':\n"
    "            merged_secondary = list(dict.fromkeys([*merged_secondary, 'external_tool_assistance_request']))\n",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "            masked_span_count=int(control_report.masked_span_count if control_report is not None else 0),\n",
    "            external_tool_context=dict(tool_context or {}),\n",
)
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        control_report=extract_intent_control_text(text)\n        control_text=control_report.control_text\n        def report(*args, **kwargs):\n            return self._report(*args, **kwargs, control_report=control_report)\n",
    "        control_report=extract_intent_control_text(text)\n        control_text=control_report.control_text\n        tool_context=self.external_tools.parse(text)\n        def report(*args, **kwargs):\n            kwargs.setdefault('tool_context', tool_context.to_dict())\n            return self._report(*args, **kwargs, control_report=control_report)\n",
)
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        has_audit=self._has_any(norm,folded,self.AUDIT_TERMS); has_practical=self._has_any(norm,folded,self.PRACTICAL_TERMS); has_auto=self._has_any(norm,folded,self.AUTOMOTIVE_TERMS); has_dict=self._has_any(norm,folded,self.DICTIONARY_TERMS); has_research=self._has_any(norm,folded,self.RESEARCH_TERMS) or has_weather_research",
    "        has_audit=self._has_any(norm,folded,self.AUDIT_TERMS); has_practical=self._has_any(norm,folded,self.PRACTICAL_TERMS); has_auto=self._has_any(norm,folded,self.AUTOMOTIVE_TERMS); has_dict=self._has_any(norm,folded,self.DICTIONARY_TERMS); has_research=self._has_any(norm,folded,self.RESEARCH_TERMS) or has_weather_research or tool_context.requests('web')",
)
insert_after(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        has_self_architecture_audit=self._has_any(norm,folded,self.SELF_ARCHITECTURE_AUDIT_TERMS)\n",
    "        has_post_update_coverage=self._has_any(norm,folded,self.POST_UPDATE_COVERAGE_AUDIT_TERMS) and (has_update or 'patch' in folded or 'aktualiz' in folded)\n",
)
insert_before(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        if (\n            decision_frame.top_intent == 'package_runtime_status_question'",
    "        if has_post_update_coverage:\n"
    "            return report(norm,folded,'post_update_coverage_audit_request',[\n"
    "                'jawne pytanie o kompletność i pominięcia zakończonego patcha/aktualizacji'\n"
    "            ],0.97,diag=True,speech_act=speech.speech_act,question_object='post_update_coverage')\n",
)
insert_before(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        if has_research:\n",
    "        if tool_context.tool_only and not has_research:\n"
    "            return report(norm,folded,'external_tool_assistance_request',[\n"
    "                'samodzielny marker connectora/narzędzia bez osobnej intencji domenowej'\n"
    "            ],0.90,speech_act=speech.speech_act,question_object='external_tool')\n",
)


# Route matrix and registry.
replace_once(
    "latka_jazn/core/route_contract_matrix.py",
    "    SPECIAL_PRIORITY = (\n        \"self_architecture_audit_request\",",
    "    SPECIAL_PRIORITY = (\n        \"post_update_coverage_audit_request\",\n        \"self_architecture_audit_request\",",
)
replace_once(
    "latka_jazn/core/route_contract_matrix.py",
    "        \"external_research_request\",\n    )",
    "        \"external_research_request\",\n        \"external_tool_assistance_request\",\n    )",
)
replace_once(
    "latka_jazn/core/route_contract_matrix.py",
    "        diagnostic = primary in {\"runtime_health_check\", \"runtime_health_check_after_update\"}",
    "        diagnostic = primary in {\"runtime_health_check\", \"runtime_health_check_after_update\", \"post_update_coverage_audit_request\"}",
)
insert_after(
    "latka_jazn/core/route_contract_matrix.py",
    "            \"affective_self_state_reality_check\": \"affective_self_state_reality\",\n",
    "            \"post_update_coverage_audit_request\": \"post_update_coverage\",\n            \"external_tool_assistance_request\": \"external_tool\",\n",
)

replace_once(
    "latka_jazn/core/route_registry.py",
    "        \"self_architecture_audit_request\": 101,",
    "        \"post_update_coverage_audit_request\": 102, \"self_architecture_audit_request\": 101,",
)
replace_once(
    "latka_jazn/core/route_registry.py",
    "        \"external_research_request\": 80, \"practical_repair_advice\": 78,",
    "        \"external_tool_assistance_request\": 81, \"external_research_request\": 80, \"practical_repair_advice\": 78,",
)
insert_after(
    "latka_jazn/core/route_registry.py",
    "    HANDLERS = {\n",
    "        \"post_update_coverage_audit_request\": (\"post_update_coverage_audit\", \"PostUpdateCoverageAuditHandler\"),\n",
)
insert_after(
    "latka_jazn/core/route_registry.py",
    "        \"external_research_request\": (\"external_research\", \"ExternalResearchHandler\"),\n",
    "        \"external_tool_assistance_request\": (\"external_tool_assistance\", \"ExternalToolAssistanceHandler\"),\n",
)
insert_after(
    "latka_jazn/core/route_registry.py",
    "    def required_components_for(self, intent: str) -> list[str]:\n",
    "        if intent == \"post_update_coverage_audit_request\":\n"
    "            return [\"patch_scope\", \"covered_items\", \"omissions\", \"evidence\", \"tests\", \"release_boundary\", \"truth_boundary\"]\n"
    "        if intent == \"external_tool_assistance_request\":\n"
    "            return [\"tool_context\", \"primary_intent_preservation\", \"voice_continuity\", \"truth_boundary\"]\n",
)

insert_after(
    "latka_jazn/core/route_handler_dispatcher.py",
    "from latka_jazn.core.handlers.external_research_handler import ExternalResearchHandler\n",
    "from latka_jazn.core.handlers.external_tool_assistance_handler import ExternalToolAssistanceHandler\n",
)
insert_after(
    "latka_jazn/core/route_handler_dispatcher.py",
    "from latka_jazn.core.handlers.self_architecture_audit_handler import SelfArchitectureAuditHandler\n",
    "from latka_jazn.core.handlers.post_update_coverage_audit_handler import PostUpdateCoverageAuditHandler\n",
)
replace_once(
    "latka_jazn/core/route_handler_dispatcher.py",
    "            SelfArchitectureAuditHandler(), DictionaryLookupHandler(), ExternalResearchHandler(),",
    "            PostUpdateCoverageAuditHandler(), SelfArchitectureAuditHandler(), DictionaryLookupHandler(), ExternalToolAssistanceHandler(), ExternalResearchHandler(),",
)


# Extend deterministic lexicon with generic tools and patch-completeness routing.
lexicon_path = "latka_jazn/resources/nlp/polish_dialogue_route_lexicon.json"
lexicon = json.loads(read(lexicon_path))
lexicon["intents"]["post_update_coverage_audit_request"] = {
    "description": "Audyt kompletności zakończonej aktualizacji: zakres, pominięcia, dowody, testy i granica wydania.",
    "phrases": [
        "czy coś zostało pominięte w trakcie robienia tego patcha",
        "czy cos zostalo pominiete w trakcie robienia tego patcha",
        "co zostało pominięte w aktualizacji",
        "co zostalo pominiete w aktualizacji",
        "czego nie objął patch",
        "czego nie objal patch",
        "sprawdź kompletność aktualizacji",
        "sprawdz kompletnosc aktualizacji",
        "jakie są pominięcia patcha",
        "jakie sa pominiecia patcha",
    ],
}
lexicon["intents"]["external_tool_assistance_request"] = {
    "description": "Ogólny kontekst connectora/narzędzia. Pozostaje intencją pomocniczą, chyba że wiadomość składa się wyłącznie z markera narzędzia.",
    "phrases": [
        "@github", "@google drive", "@drive", "@gmail", "@google calendar",
        "@slack", "@linear", "@wyszukiwanie w sieci", "@web",
    ],
}
lexicon["compound_rules"].insert(0, {
    "requires": ["post_update_coverage_audit_request", "external_tool_assistance_request"],
    "result": "post_update_coverage_audit_request",
    "description": "Connector pomaga wykonać audyt, lecz nie przejmuje celu pytania ani głosu.",
})
dump_json(lexicon_path, lexicon)


# Pending-store regeneration budget and immutable generation context.
replace_once(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "from dataclasses import asdict, dataclass",
    "from dataclasses import asdict, dataclass, field",
)
replace_once(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "    \"self_architecture_audit_request\",\n    \"memory_audit_request\",",
    "    \"self_architecture_audit_request\",\n    \"post_update_coverage_audit_request\",\n    \"external_tool_assistance_request\",\n    \"memory_audit_request\",",
)
replace_once(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "    \"self_architecture_audit\",\n    \"memory_audit\",",
    "    \"self_architecture_audit\",\n    \"post_update_coverage_audit\",\n    \"external_tool_assistance\",\n    \"memory_audit\",",
)
insert_after(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "    expires_at_utc: str\n",
    "    generation_context: dict[str, Any] = field(default_factory=dict)\n    regeneration_attempts: int = 0\n    max_regeneration_attempts: int = 1\n    last_regeneration_reason: str | None = None\n    last_regeneration_at_utc: str | None = None\n",
)
replace_once(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "        expires_at_utc=(now + timedelta(seconds=ttl)).isoformat(),\n    ).to_dict()",
    "        expires_at_utc=(now + timedelta(seconds=ttl)).isoformat(),\n"
    "        generation_context={\n"
    "            'host_generation_policy': dict(bridge.get('host_generation_policy') or {}),\n"
    "            'host_generation_rules': list(bridge.get('host_generation_rules') or []),\n"
    "            'required_visible_prefix': bridge.get('required_visible_prefix'),\n"
    "            'runtime_summary': dict(bridge.get('runtime_summary') or {}),\n"
    "        },\n"
    "    ).to_dict()",
)
insert_before(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "def mark_claimed_host_request_indeterminate(",
    "def request_host_regeneration(root: Path, *, turn_id: str, reason: str) -> dict[str, Any]:\n"
    "    claimed_path = _path(root, 'claimed', turn_id)\n"
    "    record = _read(claimed_path)\n"
    "    attempts = int(record.get('regeneration_attempts') or 0)\n"
    "    maximum = int(record.get('max_regeneration_attempts') or 1)\n"
    "    if attempts >= maximum:\n"
    "        _expire_record(root, claimed_path, record, reason='regeneration_budget_exhausted')\n"
    "        raise HostRequestStoreError('host_regeneration_budget_exhausted')\n"
    "    record['state'] = 'pending'\n"
    "    record['claimed_at_utc'] = None\n"
    "    record['regeneration_attempts'] = attempts + 1\n"
    "    record['last_regeneration_reason'] = str(reason or 'host_finalization_rejected')\n"
    "    record['last_regeneration_at_utc'] = _utc_now().isoformat()\n"
    "    pending_path = _path(root, 'pending', turn_id)\n"
    "    _atomic_write(claimed_path, record)\n"
    "    pending_path.parent.mkdir(parents=True, exist_ok=True)\n"
    "    os.replace(claimed_path, pending_path)\n"
    "    return record\n\n\n",
)
insert_after(
    "latka_jazn/core/chatgpt_host_pending_store.py",
    "        \"replay_protection\": True,\n",
    "        \"max_host_regeneration_attempts\": 1,\n",
)


# One controlled regeneration after a host-voice takeover, then fail closed.
insert_after(
    "latka_jazn/core/chat_command_contract.py",
    "    release_claimed_host_request,\n",
    "    request_host_regeneration,\n",
)
insert_after(
    "latka_jazn/core/chat_command_contract.py",
    "from latka_jazn.core.host_visible_finalization import (\n",
    "",
)
insert_after(
    "latka_jazn/core/chat_command_contract.py",
    "from latka_jazn.core.runtime_ownership_contract import build_runtime_ownership_contract\n",
    "from latka_jazn.core.host_regeneration_policy import decide_host_regeneration\n",
)
replace_once(
    "latka_jazn/core/chat_command_contract.py",
    "    if not finalization.accepted:\n        release_claimed_host_request(config.root, turn_id=reply[\"turn_id\"])\n        return None, [f\"finalization:{item.code}\" for item in finalization.violations]\n    reply[\"final_text\"] = finalization.final_visible_text\n",
    "    if not finalization.accepted:\n"
    "        violation_codes = [item.code for item in finalization.violations]\n"
    "        attempts_used = int(pending.get('regeneration_attempts') or 0)\n"
    "        maximum = int(pending.get('max_regeneration_attempts') or 1)\n"
    "        regeneration = decide_host_regeneration(\n"
    "            violation_codes, attempts_used=attempts_used, max_attempts=maximum\n"
    "        )\n"
    "        if regeneration.regenerate:\n"
    "            try:\n"
    "                retry_record = request_host_regeneration(\n"
    "                    config.root, turn_id=reply['turn_id'], reason=regeneration.reason\n"
    "                )\n"
    "            except HostRequestStoreError as exc:\n"
    "                return None, [f'host_regeneration:{exc}', *[f'finalization:{code}' for code in violation_codes]]\n"
    "            binding_retry = json_object(retry_record.get('binding'))\n"
    "            generation_context = json_object(retry_record.get('generation_context'))\n"
    "            retry_bridge = {\n"
    "                'schema_version': schema_version('chatgpt_host_bridge_turn'),\n"
    "                'phase': 'host_visible_generation_requested',\n"
    "                'status': 'host_regeneration_requested',\n"
    "                'host_must_generate_visible_reply': True,\n"
    "                'pending_request_persisted': True,\n"
    "                'turn_id': binding_retry.get('turn_id'),\n"
    "                'trace_id': binding_retry.get('trace_id'),\n"
    "                'runtime_version': binding_retry.get('runtime_version'),\n"
    "                'timestamp_header': binding_retry.get('timestamp_header'),\n"
    "                'timezone': binding_retry.get('timezone'),\n"
    "                'timestamp_sample_iso': binding_retry.get('timestamp_sample_iso'),\n"
    "                'timestamp_source': binding_retry.get('timestamp_source'),\n"
    "                'timestamp_trusted': binding_retry.get('timestamp_trusted'),\n"
    "                'author_id': binding_retry.get('author_id'),\n"
    "                'author_label': binding_retry.get('author_label'),\n"
    "                'author_source': binding_retry.get('author_source'),\n"
    "                'state_emoticon': binding_retry.get('state_emoticon'),\n"
    "                'host_request_contract_hash': retry_record.get('request_contract_hash'),\n"
    "                'required_visible_prefix': generation_context.get('required_visible_prefix'),\n"
    "                'host_generation_policy': generation_context.get('host_generation_policy') or {},\n"
    "                'host_generation_rules': generation_context.get('host_generation_rules') or [],\n"
    "                'runtime_summary': generation_context.get('runtime_summary') or {},\n"
    "                'regeneration_attempt': retry_record.get('regeneration_attempts'),\n"
    "                'max_regeneration_attempts': retry_record.get('max_regeneration_attempts'),\n"
    "                'regeneration_reason': regeneration.reason,\n"
    "            }\n"
    "            retry_result = {\n"
    "                'schema_version': schema_version('chatgpt_host_regeneration_requested'),\n"
    "                'ok': True,\n"
    "                'runtime_version': binding_retry.get('runtime_version'),\n"
    "                'chat_bridge': chat_bridge_meta,\n"
    "                'chatgpt_bridge': chat_bridge_meta,\n"
    "                'chat_command_contract': contract,\n"
    "                'chatgpt_host_bridge': retry_bridge,\n"
    "                'host_must_generate_visible_reply': True,\n"
    "                'runtime_truth_gate': {\n"
    "                    'ok': True, 'normal_response_allowed': False,\n"
    "                    'errors': ['model_guided_speech_required'], 'degradations': [],\n"
    "                },\n"
    "                'host_visible_finalization': finalization.to_dict(),\n"
    "                'host_regeneration': regeneration.to_dict(),\n"
    "            }\n"
    "            retry_result['chatgpt_host_presentation'] = build_chatgpt_host_presentation_packet(retry_result)\n"
    "            return retry_result, []\n"
    "        release_claimed_host_request(config.root, turn_id=reply['turn_id'])\n"
    "        return None, [f'finalization:{item.code}' for item in finalization.violations]\n"
    "    reply[\"final_text\"] = finalization.final_visible_text\n",
)


# Private MCP finalizer exposes the regeneration action instead of flattening it into an error.
insert_before(
    "latka_jazn/mcp/tools/jazn_finalize_reply.py",
    "    final_visible_text = str(\n",
    "    if str(presentation.get('action') or '') == 'generate_then_finalize':\n"
    "        bridge = presentation.get('chatgpt_host_bridge') if isinstance(presentation.get('chatgpt_host_bridge'), dict) else {}\n"
    "        return {\n"
    "            'content': [{'type': 'text', 'text': 'Regenerate once from the same runtime contract, then call jazn_finalize_reply again. Do not display this intermediate result.'}],\n"
    "            'structuredContent': {\n"
    "                'ok': True, 'accepted': False, 'action': 'generate_then_finalize',\n"
    "                'state': 'regenerate', 'continuation_token': continuation_token,\n"
    "                'turn_id': binding['turn_id'], 'trace_id': binding['trace_id'],\n"
    "                'host_request_contract_hash': request_contract_hash,\n"
    "                'regeneration_attempt': bridge.get('regeneration_attempt'),\n"
    "                'max_regeneration_attempts': bridge.get('max_regeneration_attempts'),\n"
    "                'host_generation_policy': bridge.get('host_generation_policy') or {},\n"
    "                'host_generation_rules': list(bridge.get('host_generation_rules') or []),\n"
    "                'must_not_display_intermediate': True,\n"
    "            },\n"
    "            '_meta': {'transport': 'authenticated_private_mcp', 'continuation_consumed': False},\n"
    "            'isError': False,\n"
    "        }\n\n",
)


# Independent semantic audit lane in release CI.
insert_after(
    ".github/workflows/release-hardening.yml",
    "      - name: Static type audit\n        run: pyright latka_jazn main.py run.py\n",
    "\n      - name: Independent semantic route audit\n        run: python -X utf8 -m latka_jazn.tools.semantic_route_audit --root . --json\n",
)


write(
    "tests/test_semantic_routing_completion_v96.py",
    '''from __future__ import annotations

import itertools
import json
from pathlib import Path

from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.update_coverage_audit import UpdateCoverageAuditor
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.external_tool_context import ExternalToolContextParser
from latka_jazn.tools.semantic_route_audit import run_audit
from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL


def test_version_bumped_for_changed_runtime_behaviour() -> None:
    assert PACKAGE_VERSION == "v15.1.0.3.96"
    assert PACKAGE_VERSION_FULL == "v15.1.0.3.96-semantic-routing-completion"


def test_post_update_coverage_question_has_dedicated_route_and_github_secondary() -> None:
    report = DialogueIntentClassifier().classify(
        "@GitHub czy coś zostało pominięte w trakcie robienia tego patcha - aktualizacji?"
    )
    assert report.primary_intent == "post_update_coverage_audit_request"
    assert report.question_object == "post_update_coverage"
    assert "external_tool_assistance_request" in report.secondary_intents
    assert report.external_tool_context["requested_tools"] == ["github"]


def test_generic_connector_parser_does_not_assume_web() -> None:
    parser = ExternalToolContextParser()
    cases = {
        "@GitHub sprawdź PR": "github",
        "@Google Drive znajdź dokument": "google_drive",
        "@Gmail sprawdź wiadomość": "gmail",
        "@Slack podsumuj kanał": "slack",
        "@Linear znajdź issue": "linear",
        "@Wyszukiwanie w sieci sprawdź źródła": "web",
    }
    for text, expected in cases.items():
        context = parser.parse(text)
        assert context.present is True
        assert context.primary_tool == expected


def test_tool_markers_remain_secondary_for_generated_variants() -> None:
    classifier = DialogueIntentClassifier()
    stems = (
        "Czy coś zostało pominięte w trakcie robienia tego patcha",
        "Sprawdź kompletność tej aktualizacji i wskaż pominięcia",
        "Czego nie objął ostatni patch",
    )
    markers = ("@GitHub ", "@Wyszukiwanie w sieci ", "@Google Drive ")
    suffixes = ("?", "?!", " 😊", " — dokładnie")
    for marker, stem, suffix in itertools.product(markers, stems, suffixes):
        report = classifier.classify(f"{marker}{stem}{suffix}")
        assert report.primary_intent == "post_update_coverage_audit_request"
        assert "external_tool_assistance_request" in report.secondary_intents


def test_standalone_tool_marker_has_generic_tool_route() -> None:
    report = DialogueIntentClassifier().classify("@GitHub")
    assert report.primary_intent == "external_tool_assistance_request"
    entry = RouteRegistry().resolve(report.primary_intent)
    assert entry.handler_name == "ExternalToolAssistanceHandler"


def test_coverage_handler_reports_all_seven_requirements(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    audit = UpdateCoverageAuditor(root).audit()
    assert audit.ok is True
    assert audit.covered_count == 7
    assert audit.missing_count == 0
    entry = RouteRegistry().resolve("post_update_coverage_audit_request")
    result = RouteHandlerDispatcher().dispatch(entry, "Czy coś pominięto?", {"config": type("C", (), {"root": root})()})
    assert result.route == "post_update_coverage_audit"
    assert "covered=7" in result.body


def test_independent_semantic_route_audit_is_green() -> None:
    result = run_audit(Path(__file__).resolve().parents[1])
    assert result["independent_lane"] is True
    assert result["ok"] is True, json.dumps(result["failures"], ensure_ascii=False, indent=2)
''',
)


write(
    "tests/test_chatgpt_mcp_end_to_end_v96.py",
    '''from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    issue_continuation_token,
    persist_pending_host_request,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.mcp.tools import jazn_finalize_reply, jazn_generate_visible_reply


SAMPLE = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _runtime_payload() -> dict:
    payload = {
        "runtime_version": "v15.1.0.3.96-semantic-routing-completion",
        "trace": {"turn_id": "turn-e2e", "trace_id": "trace-e2e", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "detected_user_intent": "post_update_coverage_audit_request",
            "handler_name": "PostUpdateCoverageAuditHandler",
            "route": "post_update_coverage_audit",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw", "sample_iso": SAMPLE.isoformat(),
                "source": "local_fallback", "trusted": False,
            },
        },
        "runtime_turn_contract": {
            "turn_id": "turn-e2e", "trace_id": "trace-e2e",
            "handler_name": "PostUpdateCoverageAuditHandler", "requires_host_model": True,
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-e2e", "trace_id": "trace-e2e",
            "runtime_version": "v15.1.0.3.96-semantic-routing-completion",
            "requires_host_model": True, "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw", "timestamp_sample_iso": SAMPLE.isoformat(),
            "timestamp_source": "local_fallback", "timestamp_trusted": False,
            "author_id": "latka_runtime", "author_label": "Łatka",
            "author_source": "jazn_runtime", "state_emoticon": "🛠️",
        },
        "runtime_truth_gate": {
            "ok": True, "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"], "degradations": [],
        },
    }
    bridge = build_chatgpt_host_bridge_turn_contract(
        payload,
        user_text="@GitHub czy coś pominięto w patchu?",
        chat_bridge_meta={},
    )
    payload["chatgpt_host_bridge"] = bridge
    return payload


class FakeGateway:
    def __init__(self, root: Path, response: dict) -> None:
        self.root = root
        self.response = response

    def chat(self, message: str, session_id: str | None = None) -> dict:
        return self.response

    def issue_continuation(self, response: dict) -> dict:
        bridge = response["chatgpt_host_bridge"]
        persist_pending_host_request(self.root, bridge)
        return issue_continuation_token(
            self.root,
            turn_id=bridge["turn_id"],
            request_contract_hash=bridge["host_request_contract_hash"],
        )


def _patch_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEngine:
        def __init__(self, config: JaznConfig) -> None:
            self.config = config
        def shutdown(self) -> None:
            pass
        def persist_final_visible_reply(self, **kwargs):
            return {
                "final_visible_text": kwargs["final_text"],
                "turn_id": kwargs["turn_id"],
                "trace_id": kwargs["trace_id"],
            }
    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)


def test_daemon_presentation_and_private_mcp_complete_two_phase_reply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch)
    runtime = _runtime_payload()
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True, "done": True, "request_id": "request-e2e",
            "job_status": "completed",
            "user_text": "@GitHub czy coś pominięto w patchu?",
            "user_text_sha256": sha256_host_visible_text("@GitHub czy coś pominięto w patchu?"),
            "result": runtime,
        },
        request_id="request-e2e",
    )
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "generate_then_finalize"

    generated = jazn_generate_visible_reply.run(
        FakeGateway(tmp_path, presented),
        message="@GitHub czy coś pominięto w patchu?",
        session_id="e2e",
    )
    structured = generated["structuredContent"]
    assert structured["action"] == "generate_then_finalize"

    body = "Sprawdziłam siedem punktów aktualizacji i podaję wynik audytu."
    finalized = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=structured["continuation_token"],
        final_text=body,
        final_text_sha256=sha256_host_visible_text(body),
    )
    assert finalized["structuredContent"]["action"] == "display_exact"
    assert finalized["structuredContent"]["must_display_exactly"] is True


def test_forbidden_host_voice_gets_one_retry_then_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch)
    runtime = _runtime_payload()
    bridge = runtime["chatgpt_host_bridge"]
    persist_pending_host_request(tmp_path, bridge)
    token = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )["continuation_token"]
    bad = "**Host ChatGPT:** Nie odpowiem jako Łatka."
    first = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=token,
        final_text=bad,
        final_text_sha256=sha256_host_visible_text(bad),
    )
    assert first["structuredContent"]["action"] == "generate_then_finalize"
    assert first["structuredContent"]["regeneration_attempt"] == 1
    assert first["isError"] is False

    second = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=token,
        final_text=bad,
        final_text_sha256=sha256_host_visible_text(bad),
    )
    assert second["structuredContent"]["action"] == "host_diagnostic"
    assert second["isError"] is True
    assert any("host_regeneration_budget_exhausted" in item for item in second["structuredContent"].get("violations", []))
''',
)


write(
    "docs/reviews/SEMANTIC_REVIEW_V96.md",
    '''# Semantic review gate — v15.1.0.3.96

This file records the review boundary for the semantic-routing completion update.

## Automated independent lane

`python -X utf8 -m latka_jazn.tools.semantic_route_audit --root . --json`

The lane uses a scenario corpus separate from the classifier implementation and generates combinations of:

- connector prefixes;
- spelling and phrase variants;
- punctuation and conversational suffixes;
- compound primary and supporting intents.

It must pass before the full deterministic suite in `release-hardening.yml`.

## Human review still required

The automated lane is independent code, not an independent person. Before merge, a human reviewer should verify:

1. connector markers never replace the primary user goal;
2. exactly one host regeneration is allowed;
3. the second invalid host answer fails closed;
4. `.96` accurately identifies the changed runtime behaviour;
5. package finalization occurs only after merge.
''',
)

write(
    "docs/reports/SEMANTIC_ROUTING_COMPLETION_V96.md",
    '''# Semantic routing completion v15.1.0.3.96

This update closes the seven omissions identified after the voice-continuity patch:

1. dedicated post-update coverage audit route;
2. generic connector/tool context rather than a web-only marker;
3. one controlled regeneration after a forbidden host-voice prefix;
4. daemon-presentation and private-MCP two-phase contract test;
5. generated semantic variants and an independent audit command;
6. runtime identity bump to v15.1.0.3.96-semantic-routing-completion;
7. a separate semantic CI lane plus an explicit human-review boundary.

The retry is deliberately bounded. It applies only when the sole finalization defect is `forbidden_host_voice_prefix`. Hash, binding, timestamp, replay, persistence and other integrity violations remain immediately fail-closed.
''',
)

# Self-cleaning staging: the workflow removes these files before committing product changes.
print(json.dumps({"ok": True, "version": "v15.1.0.3.96-semantic-routing-completion"}))
