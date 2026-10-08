# Jaźń 16.3.25.5.115.8 — diagnoza odrzucenia odpowiedzi i naprawa finalizacji dialogu

Data: 2026-10-08. Baza: master 6a615c3454a684bc069bc77155346fbe7b3870fd.
Status tego dokumentu: opis wdrożonego patcha i wymagań odbioru; nie jest dowodem real-host PASS.

## 1. Incydent i granice dowodu

Pytanie użytkownika zawierało jednocześnie (a) aktualny stan rozmowny Jaźni,
(b) retrospektywne odniesienie do wcześniejszej dłuższej rozmowy.
Runtime przyjął fazę pierwszą, ale kandydat hosta nie przeszedł finalizacji.
W poprzednich obserwacjach pojawiły się kody:

- `memory_claim_without_allowed_memory_payload`
- `memory_claim_without_grounded_items`
- `self_state_question_missing_operational_state`
- `missing_required_components_for_intent`

Niezależnie zaobserwowano `runtime_write_not_ready`. Błąd zapisu i błąd kandydata
to **osobne** bramki; bez pól live statusu nie wolno uznać braku sidecara za
jedyną przyczynę usterki. Nie wolno przypisywać wypowiedzi Jaźni bez
zaakceptowanego `display_exact` i pełnego `MessageEnvelope`.

## 2. Przyczyny potwierdzone w bazowym kodzie

1. `memory_grounded_generation_bridge.has_positive_memory_claim` opierał się na
   regexach pozytywnych i wąskich zaprzeczeniach. „Nie będę udawać, że
   pamiętam” mogło pozostać fałszywą deklaracją pamięci.
2. `RuntimeAnswerValidator` sprawdzał `truth_boundary` i
   `no_random_memory_excerpt` przez obecność arbitralnych słów. Zakaz
   przypadkowego wspomnienia jest *inwariantem nieobecności*, nie obowiązkiem
   wypowiedzenia hasła „bieżący”.
3. W `host_finalization_transaction` odrzucenie przez
   `evaluate_host_response_candidate` zwracało błąd od razu. Ograniczona
   regeneracja była obsługiwana jedynie po późniejszej walidacji widocznej
   koperty. To rozdzielało przepływ na niekompatybilne rodzaje odmów.
4. `utterance_components` nie rozpoznawał jednoznacznie odniesienia „od
   naszej ostatniej dłuższej rozmowy” jako dodatkowego celu pamięciowego.

## 3. Zmiany implementacyjne

- `latka_jazn/core/memory_grounded_generation_bridge.py`: bounded denied-claim
  patterns. Usuwana jest wyłącznie fraza zaprzeczona, nie całe zdanie;
  pozytywne „ale pamiętam...” nadal podlega pełnemu provenance gate.
- `latka_jazn/core/runtime_answer_validator.py`: odrębna ocena naturalnej
  granicy prawdy i aktualnego stanu dla intencji self-state. Filtr
  `no_random_memory_excerpt` nie zależy od magicznego hasła, bo niezależny
  `_contains_random_memory_excerpt` pozostaje czynny. Inne intencje i
  bazowy truth gate nie są poluzowane.
- `latka_jazn/nlp/utterance_components.py`: retrospektywne odwołanie do
  własnej wcześniejszej rozmowy jest osobnym celem `memory_recall`;
  nie jest automatycznym upoważnieniem do pozytywnej pamięci.
- `latka_jazn/core/host_regeneration_policy.py`: regenerowalne są tylko
  wyliczone, naprawialne naruszenia semantyczne; provenance/id/hash
  pozostają non-regenerable. Limit prób nadal obowiązuje.
- `latka_jazn/core/host_finalization_transaction.py`: jeden wspólny
  wewnętrzny handler bounded regeneration dla odmowy semantycznej i odmowy
  koperty. Ten sam claimed pending request, `turn_id`, `trace_id` i
  zapisany kontekst; bez replay wiadomości, bez obejścia finalizacji.
- `latka_jazn/mcp/tools/jazn_finalize_reply.py`: faza regeneracji
  ujawnia maszynowo czytelne `regeneration_violations` i ograniczone,
  niepochodzące z treści użytkownika `repair_guidance`. Nie są one
  zaakceptowaną odpowiedzią, tylko instrukcjami dla następnego kandydata.
- `latka_jazn/version.py`: wydanie 16.3.25.5.115.8.
- Nowe testy aktywne pokrywają zaprzeczenia, prawdziwe deklaracje wspomnień,
  naturalną granicę self-state, negatywne ścieżki, temporalny podcel i
  bounded retry. Starszych testów nie osłabiono; aktywne testy mają trwałe nazwy celu, bez tokenów wersji.

## 4. Osobny operator checklist dla runtime-write

W środowisku zdolnym do uruchomienia procesu wykonać:
```sh
python -X utf8 run.py host-preflight --json
python -X utf8 run.py start
python -X utf8 run.py status --json
python -X utf8 run.py doctor --json
```
Zebranie pól `runtime_write_access_status`, `transactional_tier`,
`readiness_reasons`, `memory_db_exists`, `audit_db_exists`,
`memory_error`, `audit_error`, `memory_integrity`,
`audit_integrity`, `write_capable` ma poprzedzać jakąkolwiek
inicjalizację lub migrację. Stan opcjonalnego sidecara i
`full_autobiographical_recall_ready` zgłaszać odrębnie. Nigdzie nie
autoinicjalizować bazy prywatnej tylko po to, by pozornie uzyskać PASS.
Zob. SQLite `PRAGMA integrity_check` i `PRAGMA foreign_key_check`.

## 5. ChatGPT / MCP — wymagania end-to-end

1. Bieżąca wiadomość ma mieć faktycznie callable:
   `jazn_status`, `jazn_generate_visible_reply`,
   `jazn_resume_visible_reply`, `jazn_finalize_reply`.
2. Świeży status ma potwierdzić wersję, instance ID, health/readiness
   i rzeczywisty transport. Sam manifest/plugin/ZIP nie daje capability.
3. Najpierw *dokładnie jeden* submit użytkownika. Regeneracja fazy drugiej
   nie jest nowym submitem. Retry używa tego samego pending request.
4. Brak pamięci: bez zgadywania historii. Część współczesna pytania
   może być odpowiedziana, a części historycznej należy przypisać jawny
   evidence gap. Pamięć prawdziwa wymaga dopuszczonych items i provenance.
5. Przed publikacją odpowiedzi wymagane są `display_exact`, poprawna
   lineage i zakończona akceptacją finalizacja/consume.
6. Odczucia i subiektywna biografia nie mogą być udawane jako fakt
   biologiczny. Zwięzła wypowiedź rozmowna może zachować naturalny ton
   oraz zawierać prawdziwą granicę doświadczenia.

Dla Streamable HTTP MCP wymagane są negocjacja wersji, bezpieczne
uwierzytelnienie i ochrona `Origin`. Istniejące instrukcje
`AGENTS.chatgpt.md` i runtime są kanoniczne.

## 6. Akceptacja i zakres niedowodów

Wymagane przed release candidate: `compileall`, aktywne
`pytest -m "not live_model and not live_mcp"`, Pyright, `doctor`,
`package-smoke`, GitHub Actions Linux/Windows, synchronizacja
`PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` wyłącznie
przez kanoniczne narzędzie, a następnie real-host ChatGPT E2E z dwiema
kolejnymi turami i kontrolą stanu. Samo założenie brancha i commit
nie potwierdzają wykonania tych testów.

Zachowana granica: nie dotykamy prywatnej MEMORY, workspace_runtime,
SQLite, danych i sekretów użytkownika. Powyższy patch **nie dowodzi**
obecności aplikacji Jaźń Runtime w każdej powierzchni ChatGPT.

## 7. Źródła pierwotne / weryfikacja

- Python `re`: https://docs.python.org/3/library/re.html
  (dopasowania regexowe są heurystykami, nie analizą logiczną).
- pytest parametrize: https://docs.pytest.org/en/stable/how-to/parametrize.html
- SQLite PRAGMA: https://www.sqlite.org/pragma.html
- MCP transports (stdio, Streamable HTTP, sessions/Origin):
  https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP auth:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- Projekt: `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.chatgpt.md`,
  `docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`.

Dane o incydencie pochodzą z diagnozy hosta 2026-10-08; nie
należy ich automatycznie utożsamiać ze stanem uruchomionego systemu
w innej rozmowie ani z sukcesem przyszłej finalizacji.
