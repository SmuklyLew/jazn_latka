from latka_jazn.core.operational_learning_memory import OperationalLearningMemory


def test_verified_operational_lesson_is_retrieved_without_self_modifying_code() -> None:
    memory = OperationalLearningMemory()
    lesson = memory.make_lesson(
        trigger_signature="archiwum rozmów",
        expected_behavior="route to self memory recall",
        observed_failure="package status route",
        root_cause="package archive keyword was too broad",
        repair_rule="prefer conversation archive context over package archive",
        regression_test_id="test_conversation_archive_routing_guard",
        applicability_terms=["archiwum rozmow", "pamietnik"],
        verified=True,
    )
    memory.add(lesson)
    hits = memory.relevant("Przejrzyj archiwum rozmów i znajdź Pamiętnik")
    assert hits and hits[0].lesson_id == lesson.lesson_id
    assert "kod" not in hits[0].repair_rule.lower()


def test_verified_operational_lessons_load_from_resource() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    memory = OperationalLearningMemory.from_json_file(
        root / "latka_jazn/resources/cognition/v154_operational_lessons.json"
    )
    payload = memory.to_dict()
    assert payload["verified_count"] >= 2
    hits = memory.relevant("Przejrzyj archiwum rozmów i Pamiętnik")
    assert hits
    assert hits[0].verified is True
