# Jaźń v16.3.25.4 — Memory Rebuild Application v4 consolidation

## Status

**Typ:** aktywny plan wykonawczy / release-prep  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Baza planu:** `master @ 420b1b6d3bd2b550fbbde1102b57ca2d3f7ba339`  
**Wersja bazowa:** `16.3.25.3-release-metadata-semantics`  
**Branch implementacyjny:** `upgrade/memory-rebuild-v4-consolidation`  
**Ostatni zweryfikowany zdalny HEAD przy aktualizacji planu:** `0b33c15e1257e77c30d6ba321c10d250a1d1920d`  
**Docelowy numer patch-release:** `16.3.25.4`  
**Proponowany release name:** `memory-rebuild-v4-consolidation`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Issue finalnej pamięci:** `#59`  
**Data aktualizacji:** 2026-08-30

> Ten etap **nie jest** finalnym Memory Rebuild z v16.5.0 i nie oznacza stanu `VERIFIED` prywatnej pamięci. Jego celem jest skonsolidowanie aplikacji/narzędzia Memory Rebuild i protokołu Test00–Final tak, aby v16.5.0 budowało finalny artefakt na jednej natywnej, testowalnej architekturze.

---

## 1. Pozycja w release train

Kolejność programu po `16.3.25.3`:

```text
16.3.25.3 release-metadata-semantics
-> 16.3.25.4 Memory Rebuild v4 consolidation
-> 16.3.26 host attachment + multimodal ingress
-> 16.4.x polski NLP
-> 16.5.0 final Memory Rebuild / VERIFIED
-> 16.5.1 ATTACHABLE
-> 16.5.2+ RETRIEVABLE / ACCEPTED
-> 16.6.0 final convergence
```

`16.3.26` pozostaje zarezerwowane dla attachment/multimodal ingress. Memory Rebuild v4 consolidation nie może zużyć tego numeru.

---

## 2. Co już jest na branchu

Branch `upgrade/memory-rebuild-v4-consolidation` jest obecnie `ahead` względem `master` i zawiera już merge aktualnego mastera. Na HEAD `0b33c15e...` znajdują się m.in.:

- natywny `SourceBundle` / `ChatGPTExportBundle`;
- `html_semantics.py` i jawne tryby `embedded_json_lossless`, `rendered_html_lossy`, `invalid_html`;
- wspólna normalizacja semantyczna JSON/HTML przy zachowaniu RAW;
- `chat_sources.py`;
- `l0_evidence.py` i rozszerzony L0;
- natywny `chat_archive_policy.py`;
- selektywny import bez aktywnej architektury monkey-patch;
- `ProtocolEngine`;
- `MemoryRebuildApplicationService`;
- `RunManifest`;
- wspólna integracja CLI/Studio;
- usunięcie aktywnych `v16311_hardening.py`, `v16312_ci_hotfix.py`, `v16325_hardening.py`;
- testy `test_memory_rebuild_v4_consolidation.py` i `test_memory_rebuild_v4_protocol_engine.py`;
- poprawiony kontrakt Test00 dla HTML LOSSY.

To jest ważny checkpoint, ale **nie jest jeszcze merge-ready**.

---

## 3. Twarda granica P0 / P1

### P0 — konsolidacja źródeł i granicy RAW -> SEMANTIC -> MEMORY

P0 uznajemy za funkcjonalnie skonsolidowane, o ile kolejne testy nie wykażą regresji:

- każdy członek eksportu ma rolę semantyczną;
- RAW payload/provenance pozostają zachowane;
- semantyka HTML jest normalizowana dopiero po parse;
- rendered HTML jest jawnie LOSSY i nie może udawać lossless PASS;
- technical/non-dialogue evidence nie jest tracone;
- visibility i `memory_eligible` są projekcjami, nie destrukcyjnym filtrem;
- warianty rozmów i branch union są zachowane deterministycznie;
- nierozstrzygnięta zmiana payload/parent pozostaje fail-closed;
- brak aktywnego `apply()/setattr()` hardening stacku.

### P1 — wspólny protokół Test00–Final

P1 musi zostać domknięte przed wersją, dokumentacją release i pełną walidacją.

Wymagany łańcuch:

```text
Test00 -> Test01 -> Test02 -> Test03 -> Test04 -> Final
```

Każdy etap ma mieć osobne `run_*` i `validate_*`, a silnik ma egzekwować zależności zamiast pozwalać uruchamiać etap bez wymaganych poprzedników.

---

## 4. P1 — Definition of Done

### 4.1 ProtocolEngine

- [ ] `run_test00()` + `validate_test00()`;
- [ ] `run_test01()` + `validate_test01()`;
- [ ] `run_test02()` + `validate_test02()`;
- [ ] `run_test03()` + `validate_test03()`;
- [ ] `run_test04()` + `validate_test04()`;
- [ ] `run_final()` + `validate_final()`;
- [ ] dependency graph wymusza pełny wcześniejszy łańcuch;
- [ ] jeden engine dla CLI i Studio;
- [ ] compatibility API deleguje, nie implementuje drugiego silnika.

### 4.2 Test00

- [ ] source inventory + exact source identity;
- [ ] source mirror / fidelity;
- [ ] source-set closure;
- [ ] jawne `PASSED / LOSSY / BLOCKED / FAILED`;
- [ ] `rendered_html_lossy` zachowane jako evidence, ale nigdy jako lossless PASS;
- [ ] source-union bierze wyłącznie lossless graph sources.

### 4.3 Test01

- [ ] fresh canonical L0 build;
- [ ] provenance closure;
- [ ] pełne rozmowy/branche/revisions/assets/sidecary;
- [ ] integrity/FK/FTS;
- [ ] zero automatycznej L2/L3/activation.

### 4.4 Test02

- [ ] projekcje visibility/role/sensitivity/eligibility/timestamp;
- [ ] raw <-> normalized reconciliation;
- [ ] projekcje nie modyfikują źródłowego L0.

### 4.5 Test03

- [ ] dwa świeże buildy A/B;
- [ ] odwrócona kolejność wejść;
- [ ] reproducibility / stable fingerprint;
- [ ] reconciliation z wcześniejszymi etapami;
- [ ] preserved branch union odróżniony od unresolved conflict.

### 4.6 Test04

Test04 jest realnym acceptance runnerem, nie parserem wcześniej przygotowanego raportu.

- [ ] final source set / operator attestation;
- [ ] real private Recall benchmark, gdy dane prywatne są lokalnie dostępne;
- [ ] provenance, wrong-conversation, false-memory, abstention, temporal/update, sensitive leakage;
- [ ] referential two-turn / natural multi-turn;
- [ ] brak prywatnej treści w repo/CI;
- [ ] gdy private dataset nie jest dostępny: jawne `NOT RUN`, nigdy syntetyczny „PASS”.

### 4.7 Final

- [ ] wymaga zaliczonego Test04 zgodnie z polityką finalnego artefaktu;
- [ ] SQLite Backup API do staging snapshot;
- [ ] `PRAGMA integrity_check`;
- [ ] `PRAGMA foreign_key_check`;
- [ ] FTS5 integrity-check;
- [ ] final source/provenance/database SHA;
- [ ] publikacja dopiero po walidacji stagingu;
- [ ] zero automatycznej aktywacji runtime memory.

### 4.8 RunManifest

- [ ] jeden manifest jednego przebiegu obejmuje kolejne Test00–Final;
- [ ] write-once/immutable final state, ale nie zamyka się po pierwszym etapie;
- [ ] source inventory/provenance/fingerprint/database SHA;
- [ ] private manifest + sanitized manifest;
- [ ] sanitized raport nie zawiera prywatnych ścieżek, treści ani PII.

---

## 5. Wersjonowanie

Aktualny branch nadal dziedziczy `16.3.25.3` z mastera. To stan WIP, a nie legalny finalny patch systemowy.

Przed merge wymagany jest systemowy bump:

```text
DISTRIBUTION_VERSION = "16.3.25.4"
PACKAGE_VERSION = "16.3.25.4"
PACKAGE_RELEASE_NAME = "memory-rebuild-v4-consolidation"
```

Jeżeli przed zamknięciem branchu master otrzyma kolejny patch z tej samej linii, numer trzeba ponownie rozstrzygnąć na świeżo. Nie wolno użyć `16.3.26` dla tego zakresu.

---

## 6. Dokumentacja i migracja hardeningów

Przed merge trzeba zaktualizować bieżące dokumenty operatorskie Memory Rebuild tak, aby nie opisywały starego engine jako aktywnej architektury.

Dawne moduły:

- `v16311_hardening.py`;
- `v16312_ci_hotfix.py`;
- `v16325_hardening.py`;

muszą być sklasyfikowane w raporcie jako:

- `SUPERSEDED` — zachowanie przeniesione natywnie;
- `RETIRED` — aktywna ścieżka nie istnieje i testy dowodzą braku zależności;
- albo `STILL_REQUIRED` — jeśli audyt znajdzie realny kontrakt, którego nie skonsolidowano.

Nie przywracać monkey-patch stacku tylko po to, aby zachować zgodność testu.

---

## 7. Walidacja merge gate

Kolejność pozostaje twarda:

```text
P1
-> VERSION
-> DOCUMENTATION
-> RELEASE METADATA
-> FULL VALIDATION
-> PR
```

Minimalne wymagania przed PR/merge:

```text
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
repozytoryjny Pyright zgodnie z AGENTS/workflow
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Dla dotkniętych baz SQLite dodatkowo:

- `PRAGMA integrity_check`;
- `PRAGMA foreign_key_check`;
- FTS5 integrity-check.

Release metadata synchronizować wyłącznie kanonicznym `release_metadata_sync`; nie edytować ręcznie `PACKAGE_INTEGRITY_MANIFEST.json` ani `SOURCE_PROVENANCE.json`.

GitHub CI na końcowym SHA musi przejść przed merge. Brak workflow/statusów na checkpointcie nie jest PASS.

---

## 8. Relacja do Issue #59

Ten release **nie zamyka #59**.

`16.3.25.4` ma dać wiarygodne narzędzie/protokół do późniejszego v16.5.0. Dopiero v16.5.0 buduje finalny prywatny artefakt i może osiągnąć `VERIFIED`; kolejne etapy prowadzą do `ATTACHABLE`, `RETRIEVABLE` i `ACCEPTED`.

---

## 9. Branch / PR policy

- pracujemy na istniejącym `upgrade/memory-rebuild-v4-consolidation`;
- bez rebase/force-push bez osobnej zgody;
- checkpointy mają być interrupt-safe;
- nie mergować dopóki P1/version/docs/metadata/full validation/CI nie są zielone;
- jeden finalny PR do `master` dla v16.3.25.4;
- branch attachment ingress 16.3.26 zaczyna się dopiero z mastera zawierającego zaakceptowaną konsolidację albo po jawnej decyzji o odłożeniu tej zależności.

---

## 10. Warunek zamknięcia etapu

`16.3.25.4-memory-rebuild-v4-consolidation` można uznać za gotowe dopiero, gdy:

1. P0 pozostaje zielone;
2. P1 Test00–Final jest jednym spójnym silnikiem;
3. RunManifest ma poprawny lifecycle;
4. CLI i Studio używają tego samego ApplicationService;
5. stary hardening stack nie jest aktywną zależnością;
6. wersja została podniesiona;
7. dokumentacja jest zgodna z kodem;
8. release metadata są kanonicznie zsynchronizowane;
9. pełna lokalna walidacja PASS;
10. wymagane CI na finalnym SHA PASS;
11. brak prywatnych danych/artefaktów runtime w diffie;
12. PR jest merge-ready bez otwartego P0/P1.
