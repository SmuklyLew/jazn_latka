# v16.3.25.5 — rest scheduler + executable NLP readiness convergence

## Cel

Usunąć dwa błędy obserwowalności bez rozszerzania uprawnień runtime:

1. scheduler odpoczynku działa w daemonie, ale `run.py status` raportuje `unknown`/`ready=false`;
2. `nlp_enhanced` jest raportowane jako `not_yet_capability_probed`, mimo istniejącego audytu statycznego NLP.

## Potwierdzone przyczyny

### Rest scheduler

- `/ready` zwraca `rest_cycle_status` z jawnymi polami `state`, `rest_scheduler_ready` i `rest_scheduler_running`.
- `status_payload()` zapisuje odpowiedź `/ready` w `daemon["readiness"]`, lecz później odczytuje `daemon.get("rest_cycle_status")` z niewłaściwego poziomu.
- diagnostyka szuka pola `status`, podczas gdy kontroler wystawia pole `state`.
- `RestCycleController.status_payload()` może oznaczyć scheduler jako ready przed uruchomieniem wątku; live readiness powinna wymagać żywego wątku scheduler-a.

### NLP

- `diagnostics.status_payload()` ustawia status `nlp_enhanced` na stałe jako `not_yet_capability_probed`.
- istniejący `NLPCapabilityAudit` potwierdza głównie obecność kodu/providerów; `find_spec()` nie jest dowodem wykonania pipeline ani obecności modeli.
- ciężki provider Stanza ma poprawny kontrakt offline (`download_method=None`) i nie powinien być automatycznie pobierany w ścieżce status/doctor.

## Zasady implementacji

- `/live` pozostaje lekkim dowodem liveness; readiness podsystemów jest czytane z osobnego `/ready`.
- scheduler jest live-ready tylko przy jawnym `rest_scheduler_ready=true` **i** żywym wątku (`rest_scheduler_running=true`).
- brak dowodu nie jest zamieniany na sukces ani nieprecyzyjne `unknown`; raport zawiera źródło evidence i jawny stan niedostępności.
- NLP dostaje wykonywany probe na syntetycznym, nieprywatnym polskim korpusie regresyjnym.
- szybki probe wykonuje deterministyczny rdzeń NLP bez ciężkich modeli.
- deep probe może wykonać lokalne Stanza wyłącznie wtedy, gdy modele są już provisioned; brak modeli, brak pakietu albo niewykonany deep probe nie może dać `nlp_enhanced_ready=true`.
- Stanza pozostaje opcjonalne i nie blokuje `runtime_core_ready` ani live voice.

## Etapy / checkpointy

1. dokumentacja przyczyny i kontraktu;
2. naprawa bindingu scheduler-a + testy + bump wersji;
3. wykonywany probe NLP + korpus + testy + bump wersji;
4. spięcie probe z `status`/`doctor` + bump wersji;
5. pełna walidacja, raport końcowy i push historii wielu commitów.

## Walidacja

- targeted pytest dla nowych testów;
- `compileall`;
- pełny `pytest -m "not live_model and not live_mcp"`;
- `run.py doctor --json` oraz deep capability probe;
- `run.py package-smoke --profile system --json` (po synchronizacji release metadata, jeśli wymagana);
- `git diff --check`;
- po pushu: rzeczywiste GitHub Actions / manifest sync.
