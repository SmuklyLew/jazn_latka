"""v127.14: source-exact current-session quote and projection regression."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.memory_intent_contract import parse_session_turn_reference
from latka_jazn.core.model_context_compiler import _sanitize_conversation_history
from latka_jazn.core.session_exact_quote import (
    exact_quote_from_accepted_turn, parse_exact_session_quote_request,
)


@pytest.mark.parametrize("question,selector,role,fragment,count", [
    ("Zacytuj dokładnie pierwszych sześć słów swojej poprzedniej odpowiedzi.",
     "last", "assistant", "first_words", 6),
    ("Podaj pierwsze 6 słów poprzedniej odpowiedzi!", "last", "assistant", "first_words", 6),
    ("Zacytuj pierwszych trzech słów mojej poprzedniej wiadomości.",
     "last", "user", "first_words", 3),
    ("Przypomnij ostatnie zdanie swojej pierwszej wypowiedzi.",
     "first", "assistant", "last_sentence", None),
])
def test_parse_literal_polish_session_quote(question, selector, role, fragment, count):
    expected = {"selector": selector, "role": role, "fragment": fragment, "count": count}
    assert parse_exact_session_quote_request(question) == expected
    assert parse_session_turn_reference(question) == expected


@pytest.mark.parametrize("question", [
    "Zacytuj pierwsze sześć słów swojej odpowiedzi z wczoraj.",
    "Podaj ostatnie zdanie z innej sesji.",
    "Opowiedz o swoich poprzednich odpowiedziach.",
    "Zacytuj pierwszych 99 słów poprzedniej odpowiedzi.",
    "Co pamiętasz z dzieciństwa?",
])
def test_no_cross_session_or_ambiguous_literal_selection(question):
    assert parse_exact_session_quote_request(question) is None


def _seed(root: Path, session: str = "test-a") -> ConversationStateStore:
    store = ConversationStateStore(root)
    saved = store.append_finalized_turn(
        session_id=session, turn_id="turn-a", trace_id="trace-a",
        user_text="Hasło do testu jest bursztynowe i krótkie.",
        assistant_text=(
            "🕒 2026-11-16 22:30:07\n🌿 Łatka\n\n"
            "Słońce delikatnie budzi las, a promienie padają na mech. "
            "Ptaki budzą się o świcie."
        ),
        source="ollama_terminal_one_shot",
    )
    assert saved["ok"] is True
    return store


def test_quote_is_deterministic_without_editing_original_record(tmp_path):
    store = _seed(tmp_path)
    before = store.lookup_accepted_turn("test-a", selector="first")
    question = "Zacytuj dokładnie pierwszych sześć słów swojej poprzedniej odpowiedzi."
    result = exact_quote_from_accepted_turn(tmp_path, "test-a", question)
    assert result is not None and result["ok"] is True
    assert result["text"] == "Słońce delikatnie budzi las, a promienie"
    assert result["source"] == "accepted_session_turn_record"
    assert store.lookup_accepted_turn("test-a", selector="first") == before


def test_last_sentence_and_user_message_roles(tmp_path):
    _seed(tmp_path)
    assistant = exact_quote_from_accepted_turn(
        tmp_path, "test-a", "Przypomnij ostatnie zdanie swojej poprzedniej odpowiedzi."
    )
    assert assistant["text"] == "Ptaki budzą się o świcie."
    user = exact_quote_from_accepted_turn(
        tmp_path, "test-a", "Zacytuj pierwszych trzech słów mojej poprzedniej wiadomości."
    )
    assert user["text"] == "Hasło do testu"


def test_unavailable_session_never_guesses(tmp_path):
    _seed(tmp_path, "test-a")
    question = "Zacytuj pierwsze sześć słów swojej poprzedniej odpowiedzi."
    missing = exact_quote_from_accepted_turn(tmp_path, "test-b", question)
    assert missing is not None and missing["ok"] is False
    assert missing["status"] == "not_found"
    assert "text" not in missing


def test_corrupt_accepted_record_is_rejected(tmp_path):
    store = _seed(tmp_path)
    record_file = next(store._session_dir("test-a").glob("*.json"))
    record_file.write_text('{"tampered":true}', encoding="utf-8")
    result = exact_quote_from_accepted_turn(
        tmp_path, "test-a", "Zacytuj pierwsze sześć słów poprzedniej odpowiedzi."
    )
    assert result["ok"] is False
    assert result["status"] == "integrity_error"
    assert "text" not in result


def test_model_projection_strips_envelope_but_canonical_turn_keeps_it(tmp_path):
    store = _seed(tmp_path)
    projection = store.load_context_projection("test-a")
    original = projection["turns"][0]["assistant_text"]
    assert original.startswith("🕒 2026-11-16")
    sanitized = _sanitize_conversation_history(projection)
    assert sanitized["turns"][0]["assistant_text"].startswith("Słońce delikatnie")
    assert "🌿 Łatka" not in sanitized["turns"][0]["assistant_text"]
    assert store.load_context_projection("test-a")["turns"][0]["assistant_text"] == original
