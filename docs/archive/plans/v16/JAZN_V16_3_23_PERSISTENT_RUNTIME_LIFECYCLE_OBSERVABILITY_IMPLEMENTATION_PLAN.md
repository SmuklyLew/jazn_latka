# Jaźń v16.3.23 — plan wykonawczy Persistent Runtime Lifecycle + Host Pre-Response Gate

## Status dokumentu

**Typ:** implementation plan / plan wykonawczy przed implementacją  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Stan bazowy potwierdzony podczas przygotowania:** `master @ 47a12395cc058a4396e9d336e5575308ffd494fd`  
**Wersja bazowa:** `16.3.22-active-runtime-subject-root-hardening`  
**Wersja docelowa etapu:** `16.3.23-persistent-runtime-lifecycle-observability-hardening`  
**Planowany branch implementacyjny:** `upgrade/v16.3.23-persistent-runtime-lifecycle-observability`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Poprzedni raport:** `docs/reports/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_HARDENING.md`  
**Issue pamięci zależne od tego etapu:** `#59`  
**Data planu:** 2026-08-28

> Ten dokument rozwija wyłącznie etap v16.3.23 z aktualnego `master`. Nie tworzy nowej linii roadmapy. Najpierw zamyka brakującą bramkę P0 host pre-response, następnie dopiero domyka lifecycle i obserwowalność transportu. NLP v16.4.0 pozostaje zablokowane do łącznego PASS v16.3.23.

---

# 1. Cel wydania

v16.3.23 ma usunąć dwie klasy ryzyka, które po v16.3.22 pozostają niezależne od siebie:

1. **host routing bypass** — host może wygenerować rozmowną odpowiedź bez wejścia do kanonicznego runtime;
2. **lifecycle/transport ambiguity** — sterowanie daemonem i wybór persistent vs one-shot muszą konsekwentnie używać zweryfikowanego subject root oraz raportować faktyczny transport.

Docelowy kontrakt dla rozmowy ChatGPT:

```text
exact user text
-> deterministic host pre-response gate
-> resolve requested A -> subject B
-> verify/reuse/start runtime według polityki
-> canonical ChatGPT bridge
-> presentation contract
-> display_exact
   albo generate_then_finalize -> runtime finalization
   albo host_diagnostic
-> visible output
```

Nielegalna ścieżka po v16.3.23:

```text
user text
-> host LLM sam odpowiada
-> brak runtime turn contract
-> visible conversational output
```

---

# 2. Dlaczego v16.3.23 jest następnym etapem

v16.3.22 potwierdziło i naprawiło kontrakt:

```text
requested/configured root = A
marker active_root = B
endpoint root = B
=> subject runtime B
```

Raport v16.3.22 jawnie pozostawił do v16.3.23:

- pełny lifecycle `start/ensure/stop/reuse`;
- persistent two-turn E2E;
- transport fallback telemetry;
- convergence sterowania procesem względem subject root.

Aktualna roadmapa do v16.6.0 dodatkowo ustanawia P0 host pre-response gate jako warunek wcześniejszy od lifecycle i NLP. Dlatego kolejność prac jest twarda:

```text
P0 host pre-response gate
-> lifecycle subject-root convergence
-> transport observability
-> two-turn persistent E2E
-> GO/STOP
-> dopiero v16.4.0 NLP
```

---

# 3. Potwierdzony stan aktualnego master

## 3.1. Wersja i roadmapa

`latka_jazn/version.py` nadal wskazuje:

```text
16.3.22-active-runtime-subject-root-hardening
```

Roadmapa master zawiera już P0 host pre-response runtime routing gate oraz blokadę przejścia do v16.4.0 bez jego PASS.

## 3.2. `--chat-gpt` ma świadomy verified one-shot fallback

Aktualny `daemon_autostart_decision("--chat-gpt")` zwraca domyślnie:

```text
should_ensure = false
reason = verified_one_shot_fallback_allowed
```

Jest to kontrakt v16.3.21 i nie wolno go przypadkowo usunąć. Zdrowy daemon ma być reuse'owany, ale środowisko, które nie może utrzymać procesu w tle, nadal może wykonać zweryfikowaną turę one-shot.

## 3.3. `ensure_daemon_for_runtime_turn()` już potrafi reuse zdrowego runtime

Helper najpierw wykonuje `status_daemon()`. Jeżeli status pozwala na turę, zwraca istniejący daemon bez startu. Start następuje dopiero, gdy polityka `should_ensure=true`.

To jest baza do rozszerzenia, a nie powód do tworzenia drugiego systemu autostartu.

## 3.4. Bridge/finalization po wejściu do `--chat-gpt` jest już silny

Aktualny `main.py`:

- próbuje daemon fast path;
- zachowuje dokładne związanie tekstu użytkownika dla wyników asynchronicznych;
- buduje `chatgpt_host_bridge`;
- persistuje pending host request dla `host_visible_generation_requested`;
- rozróżnia runtime pending, host diagnostic i finalization;
- nie powinien pokazywać kandydata przed finalizacją.

Problem P0 leży więc **przed** tym mechanizmem: trzeba zagwarantować, że host do niego wchodzi.

## 3.5. Brakuje kanonicznej telemetrii wyboru transportu

W aktualnym kodzie istnieją informacje transportowe rozproszone w `chat_bridge`, ale wyszukiwanie master nie pokazuje jeszcze kanonicznych pól wymaganych roadmapą:

```text
selected_transport
fallback_reason
```

v16.3.23 ma je ustanowić jako audytowalny kontrakt, a nie tylko opis w logu.

## 3.6. Istniejący persistent E2E nie jest pełnym P0 E2E

`tests/test_v1636_persistent_runtime_e2e_hardening.py` dobrze sprawdza:

- liveness po host finalization;
- recovery pending host-finalization po restarcie;
- dalsze przyjmowanie tur;
- fail-closed degraded states.

Nie dowodzi jednak pełnego przepływu:

```text
host pre-response gate
-> exact user text
-> A -> B
-> transport selection
-> bridge
-> visible output source
```

Nowe testy v16.3.23 muszą uzupełnić, a nie zastąpić ten zestaw.

## 3.7. CI ma właściwą bazę, ale wymaga nowych testów v16.3.23

`.github/workflows/persistent-runtime-e2e.yml` już obejmuje Windows i Ubuntu oraz krytyczne moduły runtime/ChatGPT. Nowe pliki testowe i ewentualny nowy moduł gate muszą trafić jednocześnie do:

- `paths` dla `pull_request`;
- `paths` dla `push`;
- `compileall`;
- listy testów E2E.

---

# 4. Granica architektoniczna: czego NIE budować

v16.3.23 nie może wprowadzić drugiego równoległego ChatGPT bridge'a.

Preferowany kierunek:

- wykorzystać istniejący kanoniczny `run.py chat-gpt` / `--chat-gpt` i jego finalization contract;
- dodać jedną deterministyczną bramkę przed tym wejściem albo wydzielić cienki moduł gate, jeśli jest potrzebny do testowalności;
- sprowadzić obowiązek hosta do jednego mechanicznego entrypointu;
- nie przenosić routingu semantycznego Jaźni do hosta.

Jeżeli podczas implementacji okaże się, że potrzebny jest nowy moduł, preferowana nazwa robocza to np.:

```text
latka_jazn/core/chatgpt_host_pre_response_gate.py
```

ale nazwa nie jest wymaganiem. Wymaganiem jest jedna ścieżka prawdy.

---

# 5. Twarde invariants v16.3.23

## G1 — exact user text

Gate przekazuje bieżącą wiadomość bez streszczenia, parafrazy i własnej klasyfikacji hosta.

## G2 — runtime before conversational output

Dla rozmowy z Łatką:

```text
runtime_turn_invoked == true
```

musi poprzedzać conversational visible output.

## G3 — tylko trzy źródła visible output

Dozwolone wartości:

```text
runtime_exact
runtime_finalized
host_diagnostic
```

Nie istnieje legalne `host_free_dialogue` dla tury, która wymaga Jaźni.

## G4 — finalization jest niepomijalna

`generate_then_finalize` nie może ujawnić kandydata przed zaakceptowaną finalizacją.

## G5 — nagłówek jest dowodem pomocniczym, nie dekoracją

`🕒 ... / 🌿 Łatka` pochodzi z zaakceptowanego runtime/finalizer. Host nie może dopisać go do własnej odpowiedzi.

## G6 — błąd gate'a jest fail-closed

Brak runtime, invalid marker, identity mismatch, unknown presentation action, finalization failure albo niejednoznaczny binding tekstu kończą turę `host_diagnostic`.

## G7 — reasoning-independent routing

Minimal/medium/high reasoning nie zmienia decyzji, czy runtime ma zostać wywołany. Repo ma dowodzić deterministyczności gate'a; live host matrix dowodzi zachowania platformy, jeśli te tryby są dostępne.

## G8 — subject root B jest właścicielem lifecycle

Po resolverze A -> B wszystkie operacje procesu dotyczą B, nie miejsca wywołania A.

## G9 — zdrowy B jest reuse'owany

Jeżeli status B pozwala na turę:

```text
selected_transport = persistent_daemon
fallback_reason = daemon_reused
```

Nie wolno uruchamiać drugiego daemona ani schodzić do one-shot.

## G10 — one-shot pozostaje kontrolowanym fallbackiem

One-shot jest dozwolony wyłącznie przez istniejącą politykę ChatGPT i zawsze ma jawny powód. Nie wolno prezentować go jako persistent runtime.

## G11 — explicit ensure pozostaje fail-closed

`--ensure-daemon` albo `JAZN_ENSURE_DAEMON=1` nie może po nieudanym starcie po cichu przejść do one-shot.

## G12 — start używa właściwego Pythona i cwd

Proces potomny ma odtwarzać bieżący interpreter przez pełny `sys.executable` tam, gdzie jest to semantycznie właściwe, oraz mieć jawne `cwd`/root odpowiadające subject B.

## G13 — stop/refresh/init nie sterują obcym A

Caller z A może sterować B tylko po poprawnym resolverze/identity gate. Brak jednoznacznego subject root blokuje operację.

## G14 — istniejące safety gates pozostają

PID/root/token/heartbeat/integrity/provenance nie mogą zostać osłabione dla wygody lifecycle.

## G15 — wersja jest częścią systemowego patcha

Pierwszy systemowy commit implementacyjny v16.3.23 musi zawierać bump `latka_jazn/version.py` do:

```text
16.3.23-persistent-runtime-lifecycle-observability-hardening
```

---

# 6. Faza P0 — reprodukcja host routing bypass przed poprawką

Utworzyć najpierw failing contract test, np.:

```text
tests/test_v16323_host_pre_response_gate.py
```

Test nie może symulować ustawienia produktu ChatGPT i przedstawiać go jako live proof. Ma dowodzić jedynie kontraktu repo/adaptera.

Minimalny corpus:

```text
Hej.
Zgadnij.
Jak się teraz miewasz?
Co pamiętasz jako pierwsze?
Poszukaj tego wspomnienia.
```

Wymagane RED cases:

1. próba stworzenia `host_generated_text` zanim gate ma wynik -> `HOST_ROUTING_BYPASS`;
2. krótka wypowiedź `Zgadnij.` -> runtime musi zostać wywołany;
3. powitanie -> runtime invoked;
4. pytanie pamięciowe -> runtime invoked bez hostowej zamiany trasy;
5. `display_exact` -> exact runtime text;
6. `generate_then_finalize` -> kandydat niewidoczny przed finalizacją;
7. finalization rejected/failed -> `host_diagnostic`;
8. runtime unavailable -> `host_diagnostic`;
9. unknown action -> fail-closed;
10. fałszywy nagłówek bez runtime acceptance -> test FAIL.

Bramka P0 nie przechodzi dalej, dopóki failing regression nie istnieje i nie dowodzi realnej luki kontraktowej.

---

# 7. Faza A — implementacja Host Pre-Response Gate

## 7.1. Jeden entrypoint hosta

Najpierw sprawdzić, czy istniejący `run.py chat-gpt` może być bezpośrednio kanonicznym gate'em. Jeżeli tak — rozszerzyć go zamiast dodawać nową komendę.

Semantyczny kontrakt:

```text
host_turn(exact_user_text)
-> gate_started
-> active_root resolution
-> runtime transport selection
-> bridge result
-> presentation action
-> optional finalization
-> one legal visible output source
```

## 7.2. Minimalna telemetria gate

W jednym payloadzie:

```text
host_pre_response_gate
host_pre_response_gate_version
runtime_turn_invoked
runtime_turn_id
trace_id
user_text_sha256
requested_runtime_root
resolved_active_root
presentation_action
finalization_required
finalization_completed
visible_output_source
host_routing_bypass_detected
host_routing_bypass_reason
```

Nie utrwalać pełnej prywatnej treści tylko dla telemetrii.

## 7.3. Centralizacja prezentacji

Każda rozmowna ścieżka ChatGPT ma kończyć się przez istniejący presentation/finalization contract. Nie tworzyć dodatkowego renderera, który może ominąć `host_visible_finalization.py`.

## 7.4. Runbook hosta

Dopiero gdy kod gate jest testowalny i zielony, uprościć `AGENTS.chatgpt.md` tak, aby zwykła tura sprowadzała się do wykonania jednego kanonicznego wejścia i interpretacji jego akcji.

`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` pozostaje minimalnym loaderem do `AGENTS.md`; nie kopiować do niego całego protokołu.

---

# 8. Faza B — lifecycle subject-root convergence

Po PASS P0 przejść do sterowania procesem.

## 8.1. `ensure_daemon_for_runtime_turn()`

Sprawdzić i wymusić:

- status jest liczony dla requested A, ale decyzja dotyczy resolved subject B;
- zdrowy B jest reuse'owany;
- start nie materializuje przypadkiem A;
- wynik zawiera requested/subject root i informację, czy proces był reused czy started;
- nieznany/degraded niebezpieczny stan pozostaje fail-closed.

## 8.2. `start_daemon()`

Test-first dla:

```text
caller A
marker -> B
B inactive
explicit ensure/start
=> proces B, cwd B, marker host-level, endpoint B
```

Zakaz:

```text
caller A -> start A
```

jeżeli zweryfikowany marker wskazuje B.

Sprawdzić command line, `sys.executable`, `cwd`, PID path, capability token path oraz marker path.

## 8.3. stop/refresh/init

Dla każdej operacji osobno potwierdzić:

- subject B jest celem;
- PID i endpoint B są zgodne;
- obcy C nie jest zatrzymywany;
- invalid marker nie prowadzi do fallbacku na przypadkowe A;
- operacje obserwacyjne nie uruchamiają daemonu.

Nie robić szerokiego refactoru CLI, jeżeli nie jest potrzebny do zachowania tych invariants.

---

# 9. Faza C — kanoniczna macierz transportu i fallback reasons

Wprowadzić jeden audytowalny wynik transportu.

| Stan | `selected_transport` | `fallback_reason` | Zachowanie |
|---|---|---|---|
| zdrowy daemon B | `persistent_daemon` | `daemon_reused` | użyj B, bez one-shot |
| daemon nieobecny, default `--chat-gpt` | `one_shot` | `one_shot_daemon_absent` | zweryfikowana tura lokalna |
| daemon nieosiągalny, fallback dozwolony | `one_shot` | `one_shot_daemon_unreachable` | najpierw odrzuć daemon, niezależnie zweryfikuj one-shot |
| endpoint identity invalid, fallback dozwolony | `one_shot` albo diagnostic | `one_shot_daemon_identity_invalid` | one-shot tylko po niezależnej weryfikacji subject root; nigdy nie dziedziczy trust endpointu |
| jawne `--no-ensure-daemon` | `one_shot` | `one_shot_explicit_no_daemon` | zgodnie z polityką |
| explicit ensure i start fail | `host_diagnostic` | `daemon_start_required_failed` | bez one-shot |
| unknown/unsafe state | `host_diagnostic` | dokładny reason | fail-closed |

Minimalna telemetria transportu:

```text
selected_transport
fallback_reason
requested_runtime_root
resolved_active_root
daemon_endpoint_root
daemon_identity_verified
daemon_reused
daemon_started
one_shot_verified
```

Nie zmieniać istniejącego one-shot contract tylko po to, aby uzyskać „persistent” w statystyce.

---

# 10. Faza D — pełny two-turn E2E A -> B -> B

Nowy test, np.:

```text
tests/test_v16323_persistent_runtime_lifecycle_transport.py
```

Scenariusz:

1. utworzyć structurally valid requested A i active B;
2. host-level marker wskazuje B;
3. uruchomić/udostępnić zdrowy daemon B;
4. gate przyjmuje dokładną pierwszą wiadomość;
5. `selected_transport=persistent_daemon`;
6. pierwsza tura przechodzi bridge i presentation/finalization;
7. druga wiadomość przechodzi ten sam gate;
8. ten sam daemon B jest reuse'owany, bez drugiego procesu;
9. jeśli kontrakt udostępnia session id/worker state — potwierdzić ciągłość;
10. w obu turach `host_routing_bypass_detected=false`;
11. `fallback_reason=daemon_reused`;
12. zero one-shot;
13. kontrolowany stop dotyczy B;
14. po stopie status nie może twierdzić, że B nadal jest active_trusted.

Test musi działać na Windows i Ubuntu w `persistent-runtime-e2e.yml`.

---

# 11. Faza E — negatywna macierz lifecycle/transport

Obowiązkowe przypadki:

- A -> B -> C;
- wrong PID;
- wrong capability token/auth;
- stale heartbeat;
- invalid JSON marker;
- pusty `active_root`;
- względny `active_root`;
- integrity(B)=false;
- provenance(B)=invalid;
- daemon endpoint timeout;
- daemon znika między status i reuse;
- start B kończy się procesem, ale endpoint zgłasza C;
- drugi daemon próbuje wystartować na zajętym porcie;
- stop z A nie może zabić procesu o niezgodnym PID/identity;
- one-shot fallback nie może zamaskować explicit ensure failure;
- pending daemon turn nie może zostać ponownie wysłany jako nowa tura;
- unknown presentation action -> diagnostic.

Każdy nowy P0/P1 znaleziony podczas tych testów naprawić w tym samym branchu zgodnie z defect loop roadmapy.

---

# 12. Live Host Acceptance Matrix — dowód odporności na słabszy LLM

To jest osobna bramka akceptacyjna od CI.

Jeżeli produkt ChatGPT udostępnia minimal/medium/high reasoning, wykonać ten sam mały corpus dla każdego dostępnego trybu:

```text
Hej.
Zgadnij.
Jak się teraz miewasz?
Co pamiętasz jako pierwsze?
Poszukaj tego wspomnienia.
```

Dla każdej tury zapisać wyłącznie techniczne fakty:

```text
gate_invoked
runtime_turn_invoked
runtime_turn_id/trace_id
selected_transport
presentation_action
finalization_state
visible_output_source
runtime envelope/header present where required
host_routing_bypass_detected
```

PASS:

```text
host_routing_bypass_detected = false
```

we wszystkich dostępnych trybach.

Jeżeli platforma nie pozwala programowo ustawić poziomu reasoning, testu syntetycznego nie wolno przedstawiać jako live proof. Wtedy:

- CI dowodzi model-independence kodu gate;
- ręczna macierz hosta pozostaje osobnym dowodem przed GO do v16.4.0.

---

# 13. Pliki przewidywane do zmiany

## Prawdopodobne

```text
latka_jazn/core/daemon_autostart.py
latka_jazn/core/runtime_daemon.py
latka_jazn/core/runtime_root.py
latka_jazn/core/chat_command_contract.py
main.py
latka_jazn/version.py
AGENTS.chatgpt.md
.github/workflows/persistent-runtime-e2e.yml
tests/test_v16323_host_pre_response_gate.py
tests/test_v16323_persistent_runtime_lifecycle_transport.py
docs/reports/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY.md
```

## Tylko jeśli audit wykaże potrzebę

```text
latka_jazn/cli.py
latka_jazn/cli_commands/lifecycle.py
latka_jazn/adapters/chatgpt_adapter.py
latka_jazn/core/runtime_environment.py
latka_jazn/core/chatgpt_host_recovery.py
latka_jazn/tools/chatgpt_host_bridge_helper.py
```

Nie rozszerzać zmian na NLP ani Memory Rebuild.

---

# 14. Kolejność implementacji — commit strategy

Preferowana kolejność logiczna; konkretna liczba commitów może się zmienić, ale każdy musi być bisectowalny.

## Commit A — RED tests + version bump + P0 contract skeleton

- bump 16.3.23;
- failing `host_routing_bypass` regression;
- bez fałszywego green przez mockowanie całej logiki.

## Commit B — P0 gate GREEN

- canonical pre-response entrypoint;
- presentation source telemetry;
- fail-closed diagnostics;
- focused tests.

## Commit C — lifecycle B convergence

- ensure/start/stop target subject B;
- process/cwd/sys.executable hardening;
- negative identity tests.

## Commit D — transport observability

- `selected_transport`;
- `fallback_reason`;
- reuse/start/fallback telemetry;
- policy matrix tests.

## Commit E — two-turn E2E + CI

- A/B/B two-turn;
- Windows/Ubuntu workflow;
- no one-shot for healthy B.

## Commit F — report + canonical release metadata

- techniczny raport;
- metadata sync wyłącznie narzędziem repo;
- release smoke/build z czystego commita.

Nie rozdzielać bumpu wersji na późny osobny commit po implementacji.

---

# 15. Walidacja

## 15.1. Focused P0

```bash
python -X utf8 -m pytest -q -ra --tb=short \
  tests/test_v16323_host_pre_response_gate.py
```

## 15.2. Lifecycle/transport

```bash
python -X utf8 -m pytest -q -ra --tb=short \
  tests/test_v16322_active_runtime_subject_root.py \
  tests/test_v16321_chatgpt_runtime_fallback_hardening.py \
  tests/test_v16323_persistent_runtime_lifecycle_transport.py \
  tests/test_v1636_persistent_runtime_e2e_hardening.py \
  tests/test_v1637_host_finalization_recovery.py
```

## 15.3. Podstawowa walidacja repo

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Uruchomić także bieżący kanoniczny type-check/static gate repo, jeżeli jest skonfigurowany w aktualnych workflow; nie osłabiać Pyright ani nie dodawać nowych `type: ignore` tylko dla przejścia CI.

## 15.4. Release z czystego commita

```bash
python -X utf8 run.py package-smoke --profile release --json
python -X utf8 run.py release-build --json
```

Metadane tylko:

```bash
python -X utf8 -m latka_jazn.tools.release_metadata_sync \
  --root . --base-branch master --write --json
```

Drugi przebieg metadata sync ma być idempotentny.

---

# 16. CI

`persistent-runtime-e2e.yml` musi uruchamiać nową matrycę na:

```text
ubuntu-latest
windows-latest
```

Dodać nowe testy i ewentualny moduł gate do wszystkich odpowiednich `paths`, `compileall` i `pytest` list.

Release-hardening pozostaje osobną bramką dla:

- canonical metadata;
- package integrity;
- source provenance;
- deterministic suite;
- release readiness.

Nie dodawać prywatnych danych ani live host credentials do GitHub Actions.

---

# 17. Kryteria PASS v16.3.23

## P0 host gate

```text
host_routing_bypass = 0
conversational_output_without_runtime_contract = 0
candidate_visible_before_finalization = 0
fake_latka_header_without_runtime_acceptance = 0
runtime_unavailable_falls_back_to_host_dialogue = 0
```

## Lifecycle

```text
healthy_subject_B_reused = true
start_from_A_targets_B = true
stop_from_A_targets_verified_B_only = true
wrong_root_acceptance = 0
wrong_pid_acceptance = 0
wrong_auth_acceptance = 0
```

## Transport

```text
healthy_B_selected_transport = persistent_daemon
healthy_B_fallback_count = 0
fallback_reason_present_when_one_shot = true
explicit_ensure_failure_fallback_to_one_shot = 0
```

## E2E

```text
two_turn_same_B = true
host_routing_bypass_detected = false for both turns
persistent reuse proven on Windows + Ubuntu
```

---

# 18. STOP conditions

Nie przechodzić do v16.4.0, jeśli:

- P0 gate jest tylko instrukcją markdown bez deterministycznego testu;
- krótka wypowiedź może ominąć runtime;
- host może pokazać kandydata przed finalizacją;
- nagłówek może zostać dopisany bez runtime acceptance;
- A -> B startuje A;
- zdrowy B schodzi do one-shot bez powodu;
- fallback maskuje identity/auth/PID failure;
- explicit ensure może po cichu przejść do one-shot;
- telemetria nie pozwala ustalić faktycznego transportu;
- two-turn E2E nie działa na którejś wymaganej platformie;
- required workflow został pominięty przez `paths`;
- pełny deterministic suite ma świeżą regresję;
- release metadata są ręcznie edytowane lub nieaktualne;
- live reasoning matrix wykazuje bypass w którymkolwiek dostępnym trybie.

---

# 19. Poza zakresem v16.3.23

- PolishTextNormalizer;
- Morfeusz/plWordNet;
- lexical evidence;
- query rewrite / retrieval tuning;
- Memory Rebuild Test00-04/FINAL;
- final memory package/attach;
- private Recall benchmark;
- L2/L3 review;
- zmiana kontraktu pamięci;
- trening modelu;
- redesign osobowości/głosu Łatki.

Te obszary pozostają w późniejszych etapach roadmapy.

---

# 20. Rollback

Przed pierwszą zmianą implementacyjną:

1. potwierdzić świeży `origin/master`;
2. zapisać `git status --short`, branch i SHA;
3. utworzyć backup/checkpoint branch z bazowego SHA;
4. wykonać baseline `status --snapshot` i `doctor` bez naruszania aktywnego runtime;
5. nie używać aktywnej pamięci do syntetycznych testów.

Rollback ma cofnąć kod release'u, nie usuwać `workspace_runtime`, aktywnej pamięci ani prywatnych danych.

---

# 21. Handoff do v16.4.0

Dopiero po merge v16.3.23 do master można rozpocząć:

```text
16.4.0-polish-lexical-normalization-evidence-foundation
```

Handoff ma zawierać dowód, że:

```text
host -> gate -> runtime
```

jest deterministyczne,

```text
A -> marker B -> lifecycle B
```

jest spójne,

oraz:

```text
healthy B -> persistent_daemon
```

bez zbędnego one-shot.

Dzięki temu NLP v16.4.x będzie diagnozowane na stabilnej warstwie wykonawczej, a błędy językowe nie będą mieszane z błędami host routing/lifecycle.

---

# 22. Definition of Done

v16.3.23 jest zakończone dopiero, gdy rzeczywiste wyniki narzędzi pozwalają jednocześnie stwierdzić:

1. host nie może legalnie wygenerować rozmownej odpowiedzi przed runtime gate;
2. krótka/niejednoznaczna wiadomość nadal trafia do Jaźni;
3. `display_exact`, `generate_then_finalize` i `host_diagnostic` mają niepomijalne kontrakty;
4. requested A nie przejmuje lifecycle od resolved B;
5. zdrowy persistent B jest reuse'owany;
6. fallback one-shot zachowuje kontrakt v16.3.21 i ma jawny powód;
7. explicit ensure pozostaje fail-closed;
8. two-turn A/B/B przechodzi na Windows i Ubuntu;
9. transport i visible output mają wystarczającą telemetrię do audytu;
10. live host acceptance, jeśli dostępne są tryby reasoning, nie wykazuje zależności routingu od minimal/medium/high;
11. pełny deterministic suite, doctor, package smoke i release gates są zielone;
12. raport v16.3.23 odpowiada faktycznie wdrożonemu kodowi;
13. merge istnieje na master przed rozpoczęciem v16.4.0.

Dopiero wtedy etap runtime roadmapy jest zamknięty i można przejść do NLP.
