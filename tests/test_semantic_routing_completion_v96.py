from __future__ import annotations

import itertools
import json
from pathlib import Path

from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.update_coverage_audit import UpdateCoverageAuditor
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.external_tool_context import ExternalToolContextParser
from latka_jazn.tools.semantic_route_audit import run_audit
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION, PACKAGE_VERSION_FULL


def test_semantic_routing_completion_release_contract_tracks_current_version() -> None:
    assert PACKAGE_VERSION_FULL.startswith(PACKAGE_VERSION)
    assert PACKAGE_VERSION_FULL == f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}"

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
