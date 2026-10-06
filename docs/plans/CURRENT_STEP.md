# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-06  
**Baza master:** `712a25db94c634ea47fbf265c0d907608a668f00` / `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Zweryfikowany v111:** `ee00529cdbd9a4d0a469007db787ed4895667ddf`  
**Branch:** `upgrade/v16.3.25.5.112-v111-closeout-real-host-evidence-convergence`  
**Target:** `16.3.25.5.112-v111-closeout-real-host-evidence-convergence`

## Bieżący krok v112 — closeout v111

Seria v108–v111 pozostaje ułożona nad niescalonym masterem: PR #318, #319, #320 i
#321. Żaden PR nie został scalony ani autoryzowany do merge.

Repozytoryjny zakres v111 jest zakończony na `ee00529`:

- `ConversationRunner` jest kanonicznym ownerem sesji/tury, a
  `JaznRuntimeSession` pozostaje aliasem tej samej klasy;
- `TurnStateMachine`, submit/poll/resume bez replayu, `FinalizationService`,
  recovery projekcji i strukturalny ordinary-dialogue cutover są aktywne;
- pełny świeży lokalny suite: **2107 PASS, 4 platform SKIPPED, 0 FAIL**,
  z jednym oczekiwanym ostrzeżeniem duplicate-ZIP;
- final-SHA GitHub gates: Pyright, stable contracts, dependency/Node/host-spawn,
  release-hardening, persistent-runtime E2E Linux/Windows, package cleanroom i
  PowerShell **SUCCESS**; końcowy rollup PR #321: **51 SUCCESS, 2 SKIPPED**.

### Real ChatGPT host E2E — PASS 2026-10-06

Bieżący host nie wystawił pełnego zdalnego toolsetu Jaźni, więc
`remote_runtime_available` nie został promowany. Niezależna lokalna powierzchnia
process execution była jednak dostępna i została użyta zgodnie z
`AGENTS.chatgpt.md`.

Finalny artefakt SYSTEM v111 z GitHub Actions został zweryfikowany i uruchomiony
na rzeczywistym hoście ChatGPT. Jedna dokładna wiadomość użytkownika została
związana z jednym `request_id`/ `turn_id`/ `trace_id`. Pierwsza próba
phase-2 z błędnym hashem kontraktu została odrzucona fail-closed; wiadomość nie
została wysłana ponownie. Ten sam trwały request został odczytany i sfinalizowany
z właściwym durable host-request bindingiem. Wynik końcowy:

```text
accepted=true
turn_authority_validation.ok=true
accepted_visible_turn_ready=true
action=display_exact
visible_output_source=runtime_finalized
replay_protected=true
```

To domyka wcześniej brakującą **lokalną trasę real-host E2E v111**. Nie jest to
dowód wdrożonego publicznego MCP ani Secure MCP Tunnel; remote connector route
pozostaje osobnym external deployment gate.

v112 nie wykonuje nowego refaktoru ConversationRunner. Jego zakres to:
synchronizacja źródeł prawdy, zapis real-host evidence, bump wersji oraz ponowna
walidacja canonical metadata/CI. Szczegóły:
[JAZN_V16_3_25_5_112_V111_CLOSEOUT_REAL_HOST_EVIDENCE.md](../reports/JAZN_V16_3_25_5_112_V111_CLOSEOUT_REAL_HOST_EVIDENCE.md).

## 1. Historyczny checkpoint v108

v108 wdraża **diagnostic spine przed dekompozycją JaznEngine**. Nie przenosi jeszcze
canonical turn ownership do nowego orchestratora. Celem jest zbudowanie pasa
bezpieczeństwa, który pokaże dokładnie, gdzie tura zboczyła, zanim zaczniemy
wydzielać kolejne odpowiedzialności z `engine.py`.

Implementowane na tym branchu:

- jeden `TurnDiagnosticTrace` związany z `TurnExecutionContext`;
- ordered diagnostic events i stabilny `JAZN-TURN-...` diagnostic id;
- typed `FailureKind` i `FallbackKind`;
- fallback lineage: origin stage/component, reason, from/to route, attempt;
- fallback history bez nadpisywania wcześniejszych odchyleń;
- `BlindRouteDetector`;
- statyczny `RouteGraphAudit`;
- jawne `EngineServices` extraction seams bez przejęcia ownership;
- characterization fixtures istniejących route families;
- privacy boundary dla telemetry;
- explicit CI gates na Linux i Windows.

## 2. Niezmienniki

```text
run.py -> main.py                          bez zmian
JaznRuntimeSession                         nadal canonical runtime session
JaznEngine.process_turn                    nadal canonical turn implementation w v108
accepted display_exact finalization        bez zmian
MEMORY truth/provenance                    bez zmian
Affect authority                           bez zmian
remote MCP/supervisor v107                 baseline, bez regresji
```

v108 nie może stworzyć drugiego runtime ani drugiego finalization ownera.

## 3. Exit gate v108

```text
one diagnostic root per logical turn       PASS required
event sequence monotonic                   PASS required
one immutable final diagnostic outcome     PASS required
fallback history preserved                 PASS required
anonymous active fallback                  0
unresolved classifier intents              0
routes without handlers                    0
unexplained unreachable handlers           0
required components without owner          0
characterization fixtures                  PASS required
diagnostic raw-private-text leakage        0
successful-turn behavior                   intended parity
compileall                                 PASS required
Pyright                                    PASS required
full deterministic pytest                  PASS required
persistent-runtime-e2e Linux/Windows       PASS required
release-hardening                          PASS required
canonical release metadata sync            PASS required
```

## 4. Następny krok po v108

Po merge-ready v108 i soak:

1. fresh master;
2. v109: side-effect-free construction + `FinalizationService`;
3. v110: `TurnOrchestrator` i dekompozycja pipeline;
4. v111: canonical `ConversationRunner` + `TurnStateMachine` + legacy dialogue cutover.

Pełny program:
`docs/plans/JAZN_V16_3_25_5_108_ENGINE_DECOMPOSITION_TURN_DIAGNOSTICS_PLAN.md`.

## 5. Granica prawdy

Branch i dokument nie certyfikują `PASS`, `MERGED`, `active_trusted` ani
realnego host E2E. Statusy wynikają z finalnego SHA, CI i — gdzie wymagane —
zewnętrznego live evidence.
