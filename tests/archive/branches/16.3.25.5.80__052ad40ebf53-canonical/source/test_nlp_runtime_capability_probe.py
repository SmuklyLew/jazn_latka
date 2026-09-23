from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from latka_jazn.nlp.runtime_capability_probe import probe_nlp_runtime_capability


@dataclass
class _FakeStatus:
    available: bool = True
    provider: str = "stanza-pl"
    reason: str | None = None

    def to_dict(self):
        return {"provider": self.provider, "available": self.available, "reason": self.reason}


@dataclass
class _FakeToken:
    text: str
    lemma: str
    upos: str
    deprel: str


@dataclass
class _FakeAnalysis:
    available: bool
    sentences: list[list[_FakeToken]]
    processors: list[str]
    error: str | None = None


class _FakeProvider:
    def analyse_text(self, _text: str, *, include_ner: bool = False):
        assert include_ner is False
        return _FakeAnalysis(
            available=True,
            sentences=[[_FakeToken("System", "system", "NOUN", "nsubj"), _FakeToken("działa", "działać", "VERB", "root")]],
            processors=["tokenize", "mwt", "pos", "lemma", "depparse"],
        )


class _FakeAdapter:
    status = _FakeStatus()
    provider = _FakeProvider()


def test_fast_probe_executes_synthetic_polish_core_corpus() -> None:
    root = Path(__file__).resolve().parents[1]
    report = probe_nlp_runtime_capability(root, mode="fast")

    assert report.core_probe_executed is True
    assert report.core_ready is True
    assert report.corpus_case_count >= 7
    assert report.corpus_passed_count == report.corpus_case_count
    assert report.corpus_failures == []
    assert report.enhanced_probe_requested is False
    assert report.enhanced_probe_executed is False
    assert report.enhanced_ready is False
    assert report.status == "core_ready_enhanced_probe_not_requested"


def test_fast_probe_never_claims_enhanced_ready_from_static_module_presence() -> None:
    root = Path(__file__).resolve().parents[1]
    report = probe_nlp_runtime_capability(root, mode="fast")

    assert report.stanza["pipeline_call_performed"] is False
    assert report.enhanced_ready is False


def test_deep_probe_missing_local_stanza_resources_is_explicit_and_non_green(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    corpus_source = source_root / "latka_jazn/resources/nlp/polish_capability_probe_corpus.json"
    corpus_target = tmp_path / "latka_jazn/resources/nlp/polish_capability_probe_corpus.json"
    corpus_target.parent.mkdir(parents=True)
    corpus_target.write_bytes(corpus_source.read_bytes())
    # The implementation files used by NLPCapabilityAudit are intentionally absent.
    # The runtime core probe still executes from imported code, while enhanced Stanza
    # must remain non-green because this root has no canonical local resources.
    report = probe_nlp_runtime_capability(tmp_path, mode="deep")

    assert report.core_probe_executed is True
    assert report.enhanced_probe_requested is True
    assert report.enhanced_probe_executed is True
    assert report.enhanced_ready is False
    assert report.stanza["pipeline_call_performed"] is True
    assert report.stanza["status"] in {
        "stanza_not_provisioned_in_install_manifest",
        "stanza_module_unavailable",
        "stanza_polish_models_unavailable",
        "stanza_execution_failed",
    }


def test_deep_probe_can_be_green_only_after_executed_annotated_provider() -> None:
    root = Path(__file__).resolve().parents[1]
    report = probe_nlp_runtime_capability(
        root,
        mode="deep",
        stanza_adapter_factory=lambda _root: _FakeAdapter(),
    )

    assert report.core_ready is True
    assert report.enhanced_probe_requested is True
    assert report.enhanced_probe_executed is True
    assert report.stanza["pipeline_call_performed"] is True
    assert report.stanza["available"] is True
    assert report.stanza["valid_annotation_count"] == report.stanza["annotation_count"]
    assert report.enhanced_ready is True
    assert report.status == "enhanced_ready"
