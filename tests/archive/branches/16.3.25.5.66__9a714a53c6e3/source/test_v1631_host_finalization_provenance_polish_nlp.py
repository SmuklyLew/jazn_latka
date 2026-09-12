from __future__ import annotations

import inspect
import json
from pathlib import Path

import main as main_module

from latka_jazn.nlp.intent_feature_engine import IntentFeatureEngine
from latka_jazn.nlp.polish_lemmatizer import PolishLemmatizationEngine
from latka_jazn.nlp.polish_morphology_frame import PolishMorphologyAnalyzer
from latka_jazn.nlp.providers.builtin_provider import BuiltinPolishLemmaProvider



def test_cli_fast_path_submits_as_host_capable_daemon_bridge_client() -> None:
    source = inspect.getsource(main_module._try_chat_gpt_one_shot_via_daemon)
    assert 'client="chatgpt_daemon_bridge"' in source
    assert 'client="chatgpt_bridge_one_shot_daemon_fast_path"' not in source


def test_builtin_override_keys_are_unicode_normalized_and_ascii_folded(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    resource = root / "latka_jazn" / "resources"
    resource.mkdir(parents=True)
    (resource / "polish_lemma_overrides.json").write_text(
        json.dumps({"overrides": {"źródłami": "źródło"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    provider = BuiltinPolishLemmaProvider(root)
    candidates = provider.analyse_token("źródłami", folded="zrodlami")
    assert candidates[0].lemma == "źródło"
    assert candidates[0].confidence == 0.94


def test_private_override_merges_after_project_resource(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    project = root / "latka_jazn" / "resources"
    private = root / "memory" / "raw"
    project.mkdir(parents=True)
    private.mkdir(parents=True)
    (project / "polish_lemma_overrides.json").write_text(
        json.dumps({"overrides": {"łatko": "łatka"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (private / "polish_lemma_overrides.json").write_text(
        json.dumps({"overrides": {"łatko": "łatka-prywatna"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    provider = BuiltinPolishLemmaProvider(root)
    candidates = provider.analyse_token("Łatko", folded="latko")
    assert candidates[0].lemma == "łatka-prywatna"


def test_packaged_dictionary_is_available_without_explicit_runtime_root() -> None:
    report = PolishLemmatizationEngine(enable_optional=False).analyse("źródłami")
    word = next(item for item in report.tokens if item.is_word)
    assert word.selected_lemma == "źródło"
    assert word.confidence >= 0.9


def test_morphology_frame_reuses_layered_lemma_candidates() -> None:
    frame = PolishMorphologyAnalyzer(enable_optional=False).analyse_token("źródłami")
    assert frame.schema_version == "polish_morphology_frame/v2"
    assert frame.lemma_candidates[0] == "źródło"
    assert frame.confidence >= 0.9


def test_update_intent_recognizes_patch_nlp_and_dictionary_expansion() -> None:
    text = "Przygotuj patch na nowym branchu, napraw błędy i rozbuduj słownik oraz NLP systemu Jaźni."
    frame = IntentFeatureEngine().analyse(text)
    update = next(item for item in frame.candidates if item.intent == "system_update_execution_request")
    assert "explicit_execution_action" in update.positive_evidence
    assert "system_update" in frame.domains
    assert update.score >= 0.7
