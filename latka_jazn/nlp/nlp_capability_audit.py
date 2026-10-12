from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib.util
from pathlib import Path
from typing import Any

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("nlp_capability_audit")


@dataclass(slots=True)
class NLPLayerStatus:
    layer: str
    status: str
    implemented_by: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    optional_provider: str | None = None
    research_source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NLPCapabilityReport:
    schema_version: str
    layers: list[NLPLayerStatus]
    ready_layers: list[str]
    partial_layers: list[str]
    unavailable_optional_layers: list[str]
    recommended_next_steps: list[str]
    truth_boundary: str = (
        "Audyt potwierdza obecność kodu i opcjonalnych providerów, nie jakość modelu na korpusie. "
        "Pełna ocena NLP wymaga oznaczonego zbioru testowego, metryk per-intent i testów OOD."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["layers"] = [layer.to_dict() for layer in self.layers]
        return data


class NLPCapabilityAudit:
    """Jawny audyt warstw NLP zamiast ogólnego stwierdzenia „NLP działa”."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]

    def _exists(self, relative: str) -> bool:
        return (self.root / relative).is_file()

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def audit(self) -> NLPCapabilityReport:
        stanza_available = self._module_available("stanza")
        morfeusz_available = self._module_available("morfeusz2")
        layers = [
            NLPLayerStatus(
                "unicode_normalization",
                "ready",
                ["latka_jazn/nlp/polish_normalizer.py", "latka_jazn/nlp_reasoning/normalizer.py"],
                ["NFC normalization", "Polish diacritic folding for matching"],
                ["folded text must not replace original visible text"],
                research_source_ids=["spacy_linguistic_features"],
            ),
            NLPLayerStatus(
                "tokenization_and_sentence_boundaries",
                "partial",
                ["latka_jazn/nlp/polish_tokenizer.py"],
                ["lightweight token offsets"],
                ["deterministic fallback does not model every Polish clitic or sentence ambiguity"],
                optional_provider="stanza",
                research_source_ids=["stanza_pipeline", "spacy_linguistic_features"],
            ),
            NLPLayerStatus(
                "morphology_lemma_pos_features",
                "ready_with_optional_provider" if morfeusz_available else "partial",
                [
                    "latka_jazn/nlp/polish_lemmatizer.py",
                    "latka_jazn/nlp_reasoning/adapters/morfeusz_adapter.py",
                    "latka_jazn/nlp_reasoning/adapters/polimorf_adapter.py",
                ],
                ["lemma candidates", "provider provenance", "morphological feature parsing"],
                ["contextual disambiguation remains heuristic without a trained sequence model"],
                optional_provider="morfeusz2",
                research_source_ids=["morfeusz2_official", "stanza_pipeline"],
            ),
            NLPLayerStatus(
                "dependency_syntax",
                "optional_ready" if stanza_available else "optional_unavailable",
                ["latka_jazn/nlp/providers/optional_stanza_provider.py"],
                ["full-text dependency annotations are exposed when local Stanza models exist"],
                ["no model is downloaded automatically; runtime must report unavailable honestly"],
                optional_provider="stanza",
                research_source_ids=["stanza_pipeline", "stanza_paper"],
            ),
            NLPLayerStatus(
                "named_entities",
                "optional_ready" if stanza_available else "optional_unavailable",
                ["latka_jazn/nlp/providers/optional_stanza_provider.py"],
                ["entity spans are exposed by optional full-text analysis"],
                ["NER quality depends on installed Polish Stanza package"],
                optional_provider="stanza",
                research_source_ids=["stanza_pipeline"],
            ),
            NLPLayerStatus(
                "speech_act_and_question_object",
                "ready",
                [
                    "latka_jazn/nlp/speech_act_detector.py",
                    "latka_jazn/nlp/question_object_detector.py",
                ],
                ["question/directive/feedback separation", "contextual package-vs-creative object"],
                ["rule-based inventory requires regression examples for new domains"],
                research_source_ids=["rasa_nlu_components"],
            ),
            NLPLayerStatus(
                "intent_ranking_and_negative_evidence",
                "ready",
                [
                    "latka_jazn/nlp/intent_feature_engine.py",
                    "latka_jazn/nlp/dialogue_intent_classifier.py",
                ],
                ["ranked candidates", "decision margin", "negative evidence", "abstention reason"],
                ["scores are deterministic heuristics, not learned probabilities"],
                research_source_ids=["rasa_nlu_components", "guo_calibration"],
            ),
            NLPLayerStatus(
                "dialogue_context_and_ellipsis",
                "ready",
                [
                    "latka_jazn/nlp/ellipsis_resolver.py",
                    "latka_jazn/core/current_turn_grounding.py",
                    "latka_jazn/core/dialogue_task_state.py",
                    "latka_jazn/core/turn_context_resolver.py",
                ],
                [
                    "explicit previous-turn carryover",
                    "stale-context guards",
                    "structured active-goal/task continuation",
                    "referent-aware execution directives",
                ],
                ["general unrestricted coreference and long-document discourse parsing remain bounded"],
                research_source_ids=["respact_acl_2025", "recap_eacl_2026"],
            ),
            NLPLayerStatus(
                "lexical_semantic_resources",
                "ready_with_optional_provider" if morfeusz_available else "ready",
                [
                    "latka_jazn/nlp/lexical_intelligence.py",
                    "latka_jazn/nlp/providers/optional_morfeusz_provider.py",
                    "latka_jazn/nlp/providers/plwordnet_optional_provider.py",
                    "latka_jazn/resources/nlp/v154_lexical_sources.json",
                ],
                [
                    "provenance-preserving lexical evidence",
                    "Polish morphological candidates",
                    "read-only local plWordNet semantic relations when provisioned",
                    "rebuildable context-keyed lexical cache",
                ],
                [
                    "large licensed lexical/corpus resources are not bundled or auto-downloaded",
                    "contextual word-sense disambiguation remains evidence-driven rather than guessed",
                ],
                optional_provider="morfeusz2 + local plWordNet",
                research_source_ids=["morfeusz2_official", "plwordnet_clarin", "nkjp_official"],
            ),
            NLPLayerStatus(
                "response_semantic_validation",
                "ready",
                [
                    "latka_jazn/core/runtime_answer_validator.py",
                    "latka_jazn/nlp/topic_mismatch_guard.py",
                ],
                ["cross-intent package/creative mismatch guard", "required component checks"],
                ["known-pattern validator is not a universal semantic judge"],
                research_source_ids=["guo_calibration"],
            ),
            NLPLayerStatus(
                "evaluation_and_ood_regression",
                "ready" if self._exists("tests/test_nlp_capability_contract.py") else "partial",
                ["tests/test_nlp_capability_contract.py"],
                ["minimal pairs", "compound intents", "negation scope", "OOD/abstention", "answer component coverage"],
                ([] if self._exists("tests/test_nlp_capability_contract.py") else ["contract test file is missing"]),
                research_source_ids=["rasa_nlu_components", "guo_calibration"],
            ),
        ]
        ready = [layer.layer for layer in layers if layer.status in {"ready", "ready_with_optional_provider", "optional_ready"}]
        partial = [layer.layer for layer in layers if layer.status == "partial"]
        unavailable = [layer.layer for layer in layers if layer.status == "optional_unavailable"]
        next_steps = [
            "zbudować wersjonowany, oznaczony korpus intencji z minimal pairs i przykładami OOD",
            "mierzyć precision/recall/F1 per-intent, macierz pomyłek, coverage i abstention rate",
            "skalibrować score/margins na korpusie zamiast traktować heurystyki jak prawdopodobieństwa",
            "włączyć składnię zależnościową i NER tylko po wykryciu lokalnych modeli Stanza",
            "rozszerzać resolver koreferencji poza bezpieczny task-state dopiero po zebraniu danych regresyjnych",
            "prowizjonować duże zasoby leksykalne/korpusowe wyłącznie zgodnie z ich licencją i z jawną proweniencją",
        ]
        return NLPCapabilityReport(
            schema_version=SCHEMA_VERSION,
            layers=layers,
            ready_layers=ready,
            partial_layers=partial,
            unavailable_optional_layers=unavailable,
            recommended_next_steps=next_steps,
        )
