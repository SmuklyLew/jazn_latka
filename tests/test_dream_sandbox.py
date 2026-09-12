from __future__ import annotations

from latka_jazn.config import JaznConfig
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text


def _item() -> RestReplayItem:
    text = "Krzysztof poprosił o audytowalny mechanizm czasu pomiędzy rozmowami."
    return RestReplayItem(
        source_memory_id="m1", source_tier="short_term", kind="reflection", truth_status="user_confirmed",
        content=text, content_sha256=sha256_text(text), domain="project", confidence=0.9,
        importance=0.9, score=0.9, provenance={"memory_record_content_sha256": sha256_text(text)},
    )


def test_dream_sandbox_labels_injected_generation_as_simulation(tmp_path) -> None:
    config = JaznConfig(root=tmp_path)
    sandbox = DreamSandbox(config, generator=lambda prompt, items: "Symuluję wariant bez uznawania go za fakt.")
    scene, diag = sandbox.generate(cycle_id="c1", ordinal=2, replay_items=[_item()])
    assert scene is not None
    assert scene.simulation_kind.value == "rehearsal"
    assert scene.factual_claim_allowed is False
    assert diag["status"] == "scene_generated"


def test_dream_sandbox_without_sources_does_not_generate(tmp_path) -> None:
    scene, diag = DreamSandbox(JaznConfig(root=tmp_path), generator=lambda *_: "x").generate(
        cycle_id="c1", ordinal=1, replay_items=[]
    )
    assert scene is None
    assert diag["status"] == "no_replay_sources"
