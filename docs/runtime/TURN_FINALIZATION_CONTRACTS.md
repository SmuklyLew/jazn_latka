# Jaźń — indeks kontraktów tury, narzędzi i finalizacji

**Linia implementacji:** `16.3.25.5.115.13`
**Status:** indeks nawigacyjny dla kodu źródłowego; nie jest statusem żywego daemona ani źródłem tożsamości.
**Główny router:** [AGENTS.md](../../AGENTS.md) · [runbook ChatGPT](../../AGENTS.chatgpt.md) · [runbook zmian kodu](../../AGENTS.codex.md)

> Kontrakty rzeczywiste są implementowane i walidowane w kodzie. Ten indeks nie kopiuje ich schematów i nie zastępuje runtime. Zawsze sprawdź wersję aktywnego `active_root` oraz `latka_jazn/version.py`.

## 1. Indeks źródeł prawdy

| Odpowiedzialność | Kanoniczne miejsce | Testy regresyjne |
| --- | --- | --- |
| Plan syntezy, zbudowanie kontekstu phase-1 | [`core/model_guided_response_synthesizer.py`](../../latka_jazn/core/model_guided_response_synthesizer.py) | [`test_host_turn_finalization_contract_regression.py`](../../tests/test_host_turn_finalization_contract_regression.py) |
| Kanoniczny kontekst generowania i jego hash | [`core/host_response_candidate_guard.py`](../../latka_jazn/core/host_response_candidate_guard.py) | [`test_host_tool_turn_ownership.py`](../../tests/test_host_tool_turn_ownership.py) |
| Polityka narzędzi hosta, w tym voice/identity boundary | [`core/host_tool_turn_policy.py`](../../latka_jazn/core/host_tool_turn_policy.py) | [`test_host_tool_turn_ownership.py`](../../tests/test_host_tool_turn_ownership.py) |
| Uruchomienie overlay i powiązanie kontraktu turn-authority | [`core/turn_authority_runtime_overlay.py`](../../latka_jazn/core/turn_authority_runtime_overlay.py) | [`test_turn_pipeline_authority_integration.py`](../../tests/test_turn_pipeline_authority_integration.py) |
| Etapy i walidacja pipeline (phase-1, phase-2) | [`core/turn_pipeline_contract.py`](../../latka_jazn/core/turn_pipeline_contract.py) | [`test_host_turn_finalization_contract_regression.py`](../../tests/test_host_turn_finalization_contract_regression.py) |
| Trwały binding i hashe żądania | [`core/chatgpt_host_pending_store.py`](../../latka_jazn/core/chatgpt_host_pending_store.py) | [`test_finalization_crash_atomicity.py`](../../tests/test_finalization_crash_atomicity.py) |
| Budowanie kontraktu bridge, host reply i prezentacji | [`core/chat_command_contract.py`](../../latka_jazn/core/chat_command_contract.py) | [`test_accepted_visible_turn_e2e.py`](../../tests/test_accepted_visible_turn_e2e.py) |
| Semantyczna walidacja kandydata przed persistence | [`core/host_finalization_transaction.py`](../../latka_jazn/core/host_finalization_transaction.py) | [`test_host_semantic_regeneration_transaction.py`](../../tests/test_host_semantic_regeneration_transaction.py) |
| Finalizacja, receipt i integralność | [`core/turn_authority.py`](../../latka_jazn/core/turn_authority.py), [`core/host_visible_finalization.py`](../../latka_jazn/core/host_visible_finalization.py) | [`test_host_finalization_lifecycle.py`](../../tests/test_host_finalization_lifecycle.py) |
| Wersje i kompatybilność schematów | [`version.py`](../../latka_jazn/version.py) | [`test_host_turn_finalization_contract_regression.py`](../../tests/test_host_turn_finalization_contract_regression.py) |

## 2. Jeden przebieg i twarde warunki

1. **Wejście:** runtime przyjmuje dokładny tekst z `session_id/request_id/turn_id/trace_id`; `main.py` instaluje overlay przed importem modułów bridge.
2. **Phase-1:** syntezator odwołuje się do `host_response_candidate_guard.build_host_generation_context` w momencie wywołania, nie zapamiętuje przed nałożeniem overlay starej funkcji. `context_sha256` obejmuje również `host_tool_turn_policy`.
3. **Pipeline gate:** przy `host_generation_required=True` wymagane są jawne `runtime_owns_turn`, zakaz przejęcia głosu przez narzędzie, obowiązek finalizacji, same-turn resume i MessageEnvelope. Brak polityki jest naruszeniem już w phase-1; dla **runtime-exact** (bez host generation) polityka narzędzi nie jest wymagana.
4. **Phase-2:** `host_finalization_transaction` rozwiązuje aktualny evaluator (łącznie z overlay) **przed zapisem**; niedozwolony kandydat zostaje odrzucony lub przechodzi ograniczoną regenerację, bez pozorowania zaakceptowanej odpowiedzi.
5. **Accepted visible:** wyłącznie poprawny `turn_authority_receipt` i wynik `display_exact` dają prawo do przypisania tekstu Jaźni. Odrzucenia raportuje host jako diagnozę, nie jako słowa Łatki.

## 3. Interpretacja kodów naruszeń

| Kod | Znaczenie i sprawdzany element |
| --- | --- |
| `host_tool_turn_policy_missing` | Brak `host_generation_context.host_tool_turn_policy` dla tury host-generated. Sprawdź syntezator, kolejność instalacji overlay i hash. |
| `host_tool_policy_requirement_missing:<field>` | Konkretny obowiązek turn-ownership, voice, finalizacji lub resume nie jest `true`. |
| `host_tool_policy_may_bypass_finalization` | Polityka dopuszcza widoczny wynik narzędzia przed finalizacją runtime. |
| `host_tool_authorization_incomplete` | Etap `tool_authorization` nie jest zakończony. |
| `runtime_turn_ownership_missing` | Brak powiązania autorstwa runtime (`runtime_owns_turn`). |
| `tool_voice_boundary_missing` | Wynik narzędzia mógłby zastąpić głos runtime; końcowy evaluator także kontroluje ten warunek. |
| `host_generation_context_sha256_mismatch` | Hash kontekstu się nie zgadza; nie poprawiaj go przez przepisywanie hasha bez poprawnego źródła. |

## 4. Test kontrolny po zmianie

```bash
python -X utf8 -m pytest -q tests/test_host_turn_finalization_contract_regression.py tests/test_turn_pipeline_authority_integration.py tests/test_host_tool_turn_ownership.py tests/test_host_semantic_regeneration_transaction.py
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
git diff --check
```

Bieżący daemon uruchomiony z poprzedniego `active_root` nie przyjmuje automatycznie nowego kodu ani kontraktów. Pakiet i staging są artefaktami odrębnymi od wdrożenia; po aktualizacji potrzebne są standardowe metadata sync, pełne wymagane testy i jawnie zweryfikowany start/reload oraz nowy accepted-visible-turn test. Nie wykonuj replayu zawieszonego requestu.
