# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-06  
**Baza:** `master @ 712a25db94c634ea47fbf265c0d907608a668f00` / `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Branch:** `upgrade/v16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence`  
**Target:** `16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence`

## Bieżący krok v111

Seria jest przygotowana bez merge PR: v108 #318, v109 #319, v110 #320, v111 #321.
Każdy następny branch kontynuuje zweryfikowany baseline poprzedniego etapu.
Master pozostaje wskazanym wyżej v107; żaden PR nie został scalony.

v109 wydziela jawny lifecycle composition root i niezależną finalizację phase-2.
v110 wydziela TurnOrchestrator i etapy pipeline. v111 przenosi session ownership do
ConversationRunner (JaznRuntimeSession pozostaje aliasem tej samej klasy), używa
TurnStateMachine oraz strukturalnych kandydatów zwykłego dialogu. Default CLI text,
nazwane tryby chat i MCP dochodzą do runnera; debug/cognitive diagnostics mają jawne
compatibility wejścia. Replay po niejednoznacznym transporcie pozostaje zabroniony.

Końcowe CI v108–v110: Pyright, release-hardening, package cleanroom i PowerShell
SUCCESS; persistent-runtime E2E Linux/Windows SUCCESS na zweryfikowanych code SHA.
Metadane-only final SHA mają dodatkowo zakończone dispatch gates, bez udawania
osobnego dedicated E2E tam, gdzie workflow nie obsługuje workflow_dispatch.

v111 final checkpoint jest w pełnej weryfikacji. Trzy restarty izolowanego runtime
po poprawce kosztu ścieżek PASS, zachowując ten sam snapshot pamięci. Aktualne
compileall, audyty architektury/routingu PASS, Pyright 0 errors / 1 existing warning.
Pierwsze dwa pełne lokalne przebiegi FAIL przy lifecycle daemonu pozostają evidence;
nowy pełny przebieg i final-SHA CI IN_PROGRESS. Real-host E2E ChatGPT jest osobną
bramką NOT RUN i wymaga rzeczywiście callable aplikacji oraz accepted finalization.

Szczegóły i chronologia evidence:
[JAZN_V16_3_25_5_111_CONVERSATION_RUNNER_PROGRESS.md](../reports/JAZN_V16_3_25_5_111_CONVERSATION_RUNNER_PROGRESS.md).

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
