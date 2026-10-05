# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-06  
**Baza:** `master @ 712a25db94c634ea47fbf265c0d907608a668f00` / `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Planning branch:** `plan/v16.3.25.5.108-engine-decomposition-turn-diagnostics`  
**Initial target:** `16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`

## 1. Stan wejściowy

v107 jest **MERGED**. Produkcyjny remote-MCP deployment ma strict canonical
readiness, supervisor ownership, rozdzielone liveness/readiness oraz wersjonowany
deployment contract. MEMORY v3 producer self-verifies exact-set manifest przed
utworzeniem transportu.

Te punkty są baseline i nie są ponownie implementowane w v108.

## 2. Bieżący krok — diagnostic spine przed dekompozycją JaznEngine

Najbliższy bezpieczny krok to stworzenie jednego maszynowo czytelnego śladu
tury oraz jawnych fallbacków przed przenoszeniem dużych fragmentów
`JaznEngine`.

Kolejność:

1. characterization/parity fixtures obecnego `JaznEngine.process_turn`;
2. `TurnDiagnosticTrace` jako jeden turn-root diagnostic contract;
3. typed fallback taxonomy z origin/reason/from/to lineage;
4. `BlindRouteDetector` dla pojedynczej tury;
5. statyczny `RouteGraphAudit` jako CI gate;
6. `EngineServices` jako jawne dependency/composition seams;
7. dopiero po tych gate'ach rozpocząć ekstrakcję lifecycle/finalization i
   kolejnych pipeline components.

Kanoniczny plan:
`docs/plans/JAZN_V16_3_25_5_108_ENGINE_DECOMPOSITION_TURN_DIAGNOSTICS_PLAN.md`.

## 3. Dlaczego nie big-bang rewrite

Obecny runtime ma działające invariants: single turn owner, request/turn/trace
lineage, replay protection, truth/finalization gates i accepted
`display_exact`. Przepisanie `engine.py` od zera utrudniłoby odróżnienie
zamierzonej zmiany od regresji.

Obowiązuje:

```text
add
-> shadow/parity
-> canonical switch
-> soak
-> remove legacy
```

## 4. Exit gate pierwszego implementation release v108

```text
TurnDiagnosticTrace one root per turn             PASS required
ordered event_seq + stage/component/reason        PASS required
anonymous fallback count                          0
critical fallback without from/to lineage         0
unresolved classifier intents                     0
routes without handlers                           0
unexplained unreachable handlers                  0
required components without owner                 0
characterization/parity suite                     PASS required
no new runtime/session/finalization owner          PASS required
successful-turn intended behavior                 parity required
Windows/Linux runtime CI                          PASS required
Pyright + release-hardening                       PASS required
```

## 5. Następne releasy po v108

Po udanym diagnostic spine:

- v109: side-effect-free construction + `FinalizationService` extraction;
- v110: Context/Cognitive/Dialogue/Response/Validation/Recovery/Persistence
  decomposition; `JaznEngine` staje się cienką fasadą;
- v111: redukcja legacy `conversation.py` i canonical structured response
  planning.

Numery są provisional i każdorazowo muszą zostać rozwiązane z fresh `master`.

## 6. Granica prawdy

Plan/branch nie dowodzi działającego refactoru. `MERGED`, `PASS`,
`accepted`, `active_trusted` i `live` nadal wymagają właściwego kodu,
testów, CI albo live runtime evidence.
