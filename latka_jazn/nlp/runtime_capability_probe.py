from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Literal

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.local_resource_paths import installed_provider_names, stanza_model_dir
from latka_jazn.nlp.nlp_capability_audit import NLPCapabilityAudit
from latka_jazn.nlp_reasoning.adapters.stanza_provider_adapter import StanzaReasoningAdapter
from latka_jazn.nlp_reasoning.pipeline import PolishReasoningPipeline
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("nlp_runtime_capability_probe")
CORPUS_SCHEMA_VERSION = "jazn_polish_nlp_capability_probe_corpus/v1"
CORPUS_RELATIVE_PATH = Path("latka_jazn/resources/nlp/polish_capability_probe_corpus.json")
ProbeMode = Literal["fast", "deep"]
StanzaAdapterFactory = Callable[[Path], Any]


@dataclass(slots=True)
class NLPCorpusCaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    observed_primary_intent: str | None = None
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NLPRuntimeCapabilityReport:
    schema_version: str
    mode: ProbeMode
    status: str
    core_probe_executed: bool
    core_ready: bool
    enhanced_probe_requested: bool
    enhanced_probe_executed: bool
    enhanced_ready: bool
    corpus_path: str
    corpus_case_count: int
    corpus_passed_count: int
    corpus_failures: list[dict[str, Any]]
    static_audit: dict[str, Any]
    stanza: dict[str, Any]
    truth_boundary: str = (
        "core_ready dowodzi wyłącznie wykonania deterministycznego smoke/probe na syntetycznym korpusie. "
        "enhanced_ready wymaga wykonanego deep probe lokalnego pipeline Stanza z provisioned polskimi modelami. "
        "Obecność modułu, plików albo find_spec() sama nie jest dowodem gotowości i probe nigdy nie pobiera modeli."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_corpus(root: Path) -> tuple[Path, list[dict[str, Any]]]:
    path = (root / CORPUS_RELATIVE_PATH).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError("nlp_capability_probe_corpus_schema_mismatch")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("nlp_capability_probe_corpus_empty")
    normalized: list[dict[str, Any]] = []
    for item in cases:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip() or not str(item.get("text") or "").strip():
            raise ValueError("nlp_capability_probe_corpus_invalid_case")
        expect = item.get("expect")
        if not isinstance(expect, dict):
            raise ValueError("nlp_capability_probe_corpus_invalid_expectation")
        normalized.append(item)
    return path, normalized


def _contains_all(observed: Any, expected: Any) -> bool:
    if not isinstance(observed, list) or not isinstance(expected, list):
        return False
    return set(str(value) for value in expected).issubset(str(value) for value in observed)


def _probe_core(root: Path, cases: list[dict[str, Any]]) -> list[NLPCorpusCaseResult]:
    classifier = DialogueIntentClassifier()
    pipeline = PolishReasoningPipeline(root, use_optional_providers=False)
    results: list[NLPCorpusCaseResult] = []
    for case in cases:
        text = str(case["text"])
        expected = dict(case["expect"])
        failures: list[str] = []
        dialogue = classifier.classify(text)
        reasoning = pipeline.analyse(text)

        for field_name in ("primary_intent", "update_request", "diagnostic_request", "compound"):
            if field_name in expected and getattr(dialogue, field_name) != expected[field_name]:
                failures.append(
                    f"{field_name}:expected={expected[field_name]!r}:observed={getattr(dialogue, field_name)!r}"
                )
        for expected_key, observed_name in (
            ("question_components_contains", "question_components"),
            ("negated_actions_contains", "negated_actions"),
        ):
            if expected_key in expected and not _contains_all(getattr(dialogue, observed_name), expected[expected_key]):
                failures.append(
                    f"{observed_name}:missing_expected={expected[expected_key]!r}:observed={getattr(dialogue, observed_name)!r}"
                )

        if reasoning.source_text != text:
            failures.append("reasoning_source_text_changed")
        if not reasoning.normalized_text.strip():
            failures.append("reasoning_normalized_text_empty")
        if not reasoning.tokens:
            failures.append("reasoning_tokens_empty")
        if not reasoning.token_analyses:
            failures.append("reasoning_token_analysis_empty")
        if not reasoning.provider_statuses:
            failures.append("reasoning_provider_status_missing")

        results.append(
            NLPCorpusCaseResult(
                case_id=str(case["id"]),
                passed=not failures,
                failures=failures,
                observed_primary_intent=dialogue.primary_intent,
                token_count=len(reasoning.tokens),
            )
        )
    return results


def _default_stanza_adapter_factory(root: Path) -> StanzaReasoningAdapter:
    return StanzaReasoningAdapter(root=root)


def _probe_stanza(
    root: Path,
    *,
    adapter_factory: StanzaAdapterFactory,
) -> tuple[bool, dict[str, Any]]:
    module_found = importlib.util.find_spec("stanza") is not None
    model_dir = stanza_model_dir(root)
    resources_found = (model_dir / "resources.json").is_file() and (model_dir / "pl").is_dir()
    manifest_claim = "stanza-pl" in installed_provider_names(root)
    base: dict[str, Any] = {
        "provider": "stanza-pl",
        "module_found": module_found,
        "resources_found": resources_found,
        "install_manifest_claim": manifest_claim,
        "model_dir": str(model_dir),
        "pipeline_call_performed": False,
        "available": False,
        "annotation_count": 0,
    }
    try:
        adapter = adapter_factory(root)
        status = adapter.status
        status_dict = status.to_dict() if hasattr(status, "to_dict") else {
            "provider": getattr(status, "provider", "stanza-pl"),
            "available": bool(getattr(status, "available", False)),
            "reason": getattr(status, "reason", None),
        }
        base["adapter_status"] = status_dict
        provider = adapter.provider
        analysis = provider.analyse_text(
            "Zażółć gęślą jaźń, a system sprawdzi zależności składniowe.",
            include_ner=False,
        )
        base["pipeline_call_performed"] = True
        base["analysis_error"] = getattr(analysis, "error", None)
        base["processors"] = list(getattr(analysis, "processors", []) or [])
        annotations = [
            token
            for sentence in (getattr(analysis, "sentences", []) or [])
            for token in sentence
        ]
        valid_annotations = [
            token
            for token in annotations
            if str(getattr(token, "text", "")).strip()
            and str(getattr(token, "lemma", "")).strip()
            and str(getattr(token, "upos", "")).strip()
            and str(getattr(token, "deprel", "")).strip()
        ]
        base["annotation_count"] = len(annotations)
        base["valid_annotation_count"] = len(valid_annotations)
        base["available"] = bool(getattr(analysis, "available", False))
        ready = bool(base["available"] and annotations and len(valid_annotations) == len(annotations))
        if ready:
            base["status"] = "ready"
        elif not manifest_claim:
            base["status"] = "stanza_not_provisioned_in_install_manifest"
        elif not module_found:
            base["status"] = "stanza_module_unavailable"
        elif not resources_found:
            base["status"] = "stanza_polish_models_unavailable"
        else:
            base["status"] = "stanza_execution_failed"
        return ready, base
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
        base.update(
            {
                "status": "stanza_probe_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return False, base


def probe_nlp_runtime_capability(
    root: str | Path,
    *,
    mode: ProbeMode = "fast",
    stanza_adapter_factory: StanzaAdapterFactory | None = None,
) -> NLPRuntimeCapabilityReport:
    root_path = Path(root).expanduser().resolve()
    if mode not in {"fast", "deep"}:
        raise ValueError(f"unsupported_nlp_probe_mode:{mode}")

    corpus_path, cases = _load_corpus(root_path)
    core_results = _probe_core(root_path, cases)
    core_ready = bool(core_results and all(item.passed for item in core_results))
    static = NLPCapabilityAudit(root_path).audit().to_dict()
    failed = [item.to_dict() for item in core_results if not item.passed]

    enhanced_requested = mode == "deep"
    enhanced_executed = False
    enhanced_ready = False
    stanza: dict[str, Any]
    if enhanced_requested:
        enhanced_executed = True
        enhanced_ready, stanza = _probe_stanza(
            root_path,
            adapter_factory=stanza_adapter_factory or _default_stanza_adapter_factory,
        )
        enhanced_ready = bool(core_ready and enhanced_ready)
    else:
        stanza = {
            "provider": "stanza-pl",
            "status": "deep_probe_not_requested",
            "pipeline_call_performed": False,
            "available": False,
        }

    if not core_ready:
        status = "core_probe_failed"
    elif not enhanced_requested:
        status = "core_ready_enhanced_probe_not_requested"
    elif enhanced_ready:
        status = "enhanced_ready"
    else:
        status = str(stanza.get("status") or "enhanced_probe_not_ready")

    return NLPRuntimeCapabilityReport(
        schema_version=SCHEMA_VERSION,
        mode=mode,
        status=status,
        core_probe_executed=True,
        core_ready=core_ready,
        enhanced_probe_requested=enhanced_requested,
        enhanced_probe_executed=enhanced_executed,
        enhanced_ready=enhanced_ready,
        corpus_path=str(corpus_path),
        corpus_case_count=len(core_results),
        corpus_passed_count=sum(1 for item in core_results if item.passed),
        corpus_failures=failed,
        static_audit={
            "ready_layers": list(static.get("ready_layers") or []),
            "partial_layers": list(static.get("partial_layers") or []),
            "unavailable_optional_layers": list(static.get("unavailable_optional_layers") or []),
            "truth_boundary": static.get("truth_boundary"),
        },
        stanza=stanza,
    )
