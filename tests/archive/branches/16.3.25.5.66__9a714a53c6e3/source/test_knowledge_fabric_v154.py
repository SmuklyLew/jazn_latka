from pathlib import Path

from latka_jazn.core.knowledge_fabric import KnowledgeFabric
from latka_jazn.memory.hybrid_retriever import HybridRetriever


def test_selective_retrieval_reuses_hybrid_fts5(tmp_path: Path) -> None:
    retriever = HybridRetriever(tmp_path / "knowledge.sqlite3")
    retriever.rebuild([
        {"document_id": "a", "text": "Pamiętnik i pierwsze rozmowy Łatki.", "source_locator": "chat:a"},
        {"document_id": "b", "text": "Instrukcja techniczna pakowania ZIP.", "source_locator": "doc:b"},
    ], rebuild_vectors=False)
    fabric = KnowledgeFabric(retriever)
    plan, evidence = fabric.retrieve("znajdź Pamiętnik", explicit_retrieval=True)
    assert plan.retrieval_required is True
    assert evidence
    assert evidence[0].source_locator == "chat:a"
    assert evidence[0].provenance["database"].endswith("knowledge.sqlite3")


def test_global_scope_can_enable_relation_graph_without_forcing_new_memory_stack(tmp_path: Path) -> None:
    fabric = KnowledgeFabric(tmp_path / "knowledge.sqlite3")
    fabric.add_relations([("Pamiętnik", "Łatka"), ("Łatka", "rozmowy")])
    plan = fabric.plan_query("Prześledź chronologicznie historię na przestrzeni wszystkich rozmów", explicit_retrieval=True)
    assert plan.scope == "global"
    assert "relation_graph" in plan.modes
    assert "fts5_bm25" in plan.modes
