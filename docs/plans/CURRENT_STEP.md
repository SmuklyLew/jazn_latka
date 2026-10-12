# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-07  
**Baza master:** `7b322284e49ed0a08d24d5cd5a56ba567532eba1` / `16.3.25.5.113-remote-only-chatgpt-ingress-convergence`  
**Zweryfikowany v111:** `ee00529cdbd9a4d0a469007db787ed4895667ddf`  
**Branch:** `update/v16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence`  
**Target:** `16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence`

## Bieżący krok v115 — Desktop/App Binding Hybrid Convergence

v115 konwerguje dwie niezależne gałęzie wychodzące z master v113:

- `update/v16.3.25.5.114-hybrid-adaptive-ingress-convergence` — właściciel
  nowej polityki ordinary-chat `HYBRID_ADAPTIVE`;
- `upgrade/v119.2.0-chatgpt-desktop-mcp-convergence` — źródło wąskich
  poprawek ChatGPT Desktop MCP discovery i registered app binding.

Nie wykonujemy blind merge v119 do v114, ponieważ v119 zachowuje stary
remote-only prompt/politykę i osobną release identity `119.2.0`.
Forward-portowane są tylko zgodne elementy:

1. legacy initialize-era `tools/list` utrzymuje cztery canonical
   `jazn_*` actions jako model-visible przez
   `_meta.ui.visibility=["model","app"]`;
2. plugin package może wiązać już zarejestrowany MCP app przez `.app.json`
   bez wymuszonego `mcp.json`/localhost HTTP;
3. CLI akceptuje `--registered-app-id` bez `--endpoint`;
4. `--force` usuwa stale opcjonalne manifesty po zmianie kształtu paczki;
5. dokumentacja rozdziela transport MCP, app binding i current-message
   capability evidence.

Niezmienniki v114 pozostają obowiązujące:

```text
current-message verified MCP/app runtime
    -> submit exactly once
else
bounded verified local host bootstrap before submit
    -> submit exactly once
else
fail closed

after submit:
same route + same request_id
no replay
accepted display_exact required
```

Registered app id, `.app.json`, installed plugin, historyczne `tools/list`,
zdrowy tunnel lub endpoint nie promują same `remote_runtime_available=true`.
Current-message route wymaga pełnych czterech callable tools oraz świeżego
`jazn_status`.

### Exit gate v115

Release candidate wymaga:

- compileall / Pyright bez regresji;
- stable test contracts;
- pełnego deterministic pytest suite;
- Windows targeted runtime/path + turn atomicity;
- persistent-runtime E2E Linux i Windows;
- dependency matrix wspieranych Python/platform profiles;
- synchronized Test Studio catalog;
- canonical `manifest_sync` i zgodnego `SOURCE_PROVENANCE.json`;
- clean release package finalization;
- brak zmian osłabiających idempotency, finalization, current-message freshness,
  MEMORY provenance lub fail-closed host boundaries.

Real-host ChatGPT acceptance pozostaje osobnym zewnętrznym dowodem: po
wdrożeniu/rejestracji/Refresh host musi na bieżącej wiadomości rzeczywiście
wystawić cztery canonical tools i wykonać świeży `jazn_status`.

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
