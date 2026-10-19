from pathlib import Path
import shutil

from latka_jazn.tools.cognitive_architecture_audit import _source_integration_checks


def test_composed_cognition_requires_constructor_binding_and_execution(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    paths = ["latka_jazn/core/engine.py", "latka_jazn/core/engine_construction.py",
             "latka_jazn/memory/rest_replay.py", "latka_jazn/config.py",
             "latka_jazn/core/runtime_turn_contract.py"]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    checks = _source_integration_checks(tmp_path)
    assert checks["knowledge_fabric_reachable_from_turn"]
    assert checks["lexical_intelligence_reachable_from_turn"]
    engine = tmp_path / paths[0]
    before = engine.read_text(encoding="utf-8")
    engine.write_text(before.replace("self.knowledge_fabric = services.knowledge_fabric", "self.knowledge_fabric = None"), encoding="utf-8")
    assert not _source_integration_checks(tmp_path)["knowledge_fabric_reachable_from_turn"]
    engine.write_text(before, encoding="utf-8")
    construction = tmp_path / paths[1]
    construction.write_text(construction.read_text(encoding="utf-8").replace("self.lexical_intelligence = LexicalIntelligenceEngine(", "self.lexical_intelligence = MissingEngine("), encoding="utf-8")
    assert not _source_integration_checks(tmp_path)["lexical_intelligence_reachable_from_turn"]
