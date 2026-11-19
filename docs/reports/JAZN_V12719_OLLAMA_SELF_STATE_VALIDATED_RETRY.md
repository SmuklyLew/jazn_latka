# Jaźń v127.19 — PC Ollama self-state validated retry

**Źródło:** `fix/v12718-autobiographical-memory-claim-truth-20261117` at `ce3b66cbbb299b586aa6e073394d390a49973bfd`.

**Zakres:** naprawa regresji wykrytej w odbiorze na Windows 11 z Ollama (`gemma3:latest`), bez ingerencji w MEMORY, daemon i finalization authority.

## Dowody wejściowe z testów PC (19 listopada 2026)

- Daemon `active_trusted`, endpoint 8787, `conversation_ready=true`, Ollama API na 11434 z modelem `gemma3:latest`.
- Test zwykłego pytania „Jak się masz?”: `self_state_question`, `SelfStateHandler`.
- Pierwsza tura: `candidate_validation=rejected`; `missing_required_components_for_intent`: `operational_state`, `truth_boundary`; `model_retry=attempted`; `fallback=TERMINAL_DIAGNOSTIC`; `classified_non_dynamic_response`; kanoniczny finał nie został zapisany.
- Druga tura: zaakceptowana i utrwalona, ale pierwsza odrzucona tura nie mogła być podstawą testu pamięci sesyjnej.
- Izolowany `SelfStateHandler.handle` + `RuntimeAnswerValidator.validate`: `accepted=True`, brak brakujących komponentów.
- `TopicMismatchGuard.preferred_route=general_conversation` przy pytaniach `self_state` to wartość domyślna, **nie** dowód błędu klasyfikacji.

## Zmiana

1. `RecoveryPolicy` wybiera przy ograniczonym ponowieniu oryginalny draft `SelfStateHandler` **wyłącznie po niezależnej walidacji**. Nie wykorzystuje odrzuconego tekstu modelu jako materiału naprawy, jeśli handler jest poprawny.
2. `ModelGuidedResponseSynthesizer` dodaje do lokalnego kontekstu językowego instrukcję naturalnego `operational_state` i `truth_boundary`; feedback walidatora przy retry jest ograniczony do znanych identyfikatorów komponentów.
3. Pierwszy i drugi kandydat modelowy **nadal** przechodzą niezależne `RuntimeAnswerValidator`, `RuntimeTruthGate`, lineage, finalization i persistence. Nie ma fallbacku sugerującego zaakceptowaną turę bez dowodu.
4. Wersja pakietu: `16.3.25.5.116.0.34.94.6.127.19`.

## Testy i wymagany odbiór

| Scenariusz | Status do czasu dowodu |
| --- | --- |
| Handler self-state przechodzi niezależny walidator | PASS w izolowanym teście PC v127.18 (przed patchem) |
| Retry korzysta z poprawnego handlera i przekazuje listę braków | NOT_RUN na nowym SHA |
| Wadliwy handler nie staje się podstawą retry | NOT_RUN na nowym SHA |
| Retry modelu poprawny po odrzuceniu pierwszego kandydata | NOT_RUN na nowym SHA |
| Obie próby niepoprawne → fail closed | NOT_RUN na nowym SHA |
| Lokalny Ollama Gemma 3: 2 zaakceptowane tury | NOT_RUN |
| Pamięć sesyjna (jedna `session_id`) po zaakceptowanych turach | NOT_RUN |
| Reconnect, persistence i accepted finalization | NOT_RUN |
| Autobiographical MEMORY readiness | NOT_READY w teście PC `active_ready_system_only` |
| Full test gate oraz release metadata sync/idempotency | NOT_RUN |

**Polecenia dla wykonawcy z terminalem:**

```powershell
python -X utf8 -m pytest -q tests/test_ollama_self_state_validated_retry.py tests/test_ollama_turn_stability_nlp.py tests/test_dialogue_intent_finalization_authority.py
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json
git diff --check
```

Po metadanych i zielonych testach należy powtórzyć odbiór na osobnej instancji Windows/Ollama. Odrzuconej historycznej tury nie wolno replayować. Rozłączenie klienta `/exit` nie zatrzymuje daemona; wynik widać tylko po zatwierdzonej finalizacji.

**Release boundary:** dopóki nie potwierdzono synchronizacji manifest/provenance, testów celowanych, wymaganych gate'ów i odbioru PC, gałąź nie jest gotowym wydaniem ani wdrożeniem.
