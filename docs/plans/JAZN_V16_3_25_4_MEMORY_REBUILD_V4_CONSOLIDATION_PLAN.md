# Jaźń v16.3.25.4 — Memory Rebuild Application v4 consolidation

## Status

**Typ:** aktywny plan wykonawczy / release-prep  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Baza wykonawcza:** bieżące `master` / `origin/master`; dokładny SHA zweryfikować przed synchronizacją brancha  
**Wersja bazowa linii przy audycie:** `16.3.25.3-release-metadata-semantics`  
**Branch implementacyjny:** `upgrade/memory-rebuild-v4-consolidation`  
**Ostatni zweryfikowany zdalny HEAD przy audycie:** `0b33c15e1257e77c30d6ba321c10d250a1d1920d` — zawsze sprawdzić ponownie przed pracą  
**Tracking issue:** `#189`  
**Docelowy numer patch-release przy niezmienionej linii:** `16.3.25.4`  
**Proponowany release name:** `memory-rebuild-v4-consolidation`  
**Kanoniczne założenia:** `docs/plans/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Issue finalnej pamięci:** `#59`  
**Data aktualizacji:** 2026-08-30

> Ten etap **nie jest** finalnym Memory Rebuild z v16.5.0 i nie oznacza stanu `VERIFIED` prywatnej pamięci. Konsoliduje narzędzie/protokół Test00–Final i przygotowuje source-lineage-ready RAW/L0 dla późniejszej finalnej odbudowy.

---

## 1. Pozycja w release train

```text
16.3.25.3 release line
-> 16.3.25.4 Memory Rebuild v4 consolidation
-> 16.3.26 attachment + multimodal ingress
-> 16.4.x evidence-aware Polish NLP
-> 16.5.0 final Memory Rebuild / VERIFIED + source monitoring
-> 16.5.1 ATTACHABLE
-> 16.5.2+ autobiographical RETRIEVABLE / ACCEPTED
-> 16.6 final convergence
```

`16.3.26` pozostaje zarezerwowane dla attachment/multimodal ingress. Jeżeli master zużyje `16.3.25.4` przed finalizacją tego brancha, numer trzeba rozstrzygnąć na świeżo — nie wolno mechanicznie przejąć 16.3.26.

---

## 2. Co już jest na branchu — checkpoint, nie finalny PASS

Branch zawiera m.in.:

- natywny `SourceBundle` / `ChatGPTExportBundle`;
- `html_semantics.py` i jawne `embedded_json_lossless`, `rendered_html_lossy`, `invalid_html`;
- wspólną normalizację semantyczną JSON/HTML przy zachowaniu RAW;
- `chat_sources.py`;
- `l0_evidence.py` i rozszerzony L0;
- natywny `chat_archive_policy.py`;
- selective import bez aktywnego monkey-patch stacku;
- `ProtocolEngine`;
- `MemoryRebuildApplicationService`;
- `RunManifest`;
- wspólną integrację CLI/Studio;
- wycofanie aktywnych `v16311_hardening.py`, `v16312_ci_hotfix.py`, `v16325_hardening.py`;
- testy v4 consolidation/protocol;
- jawny HTML LOSSY boundary.

Samo istnienie tych artefaktów jest najwyżej `present/constructible/callable`. Merge gate wymaga właściwego poziomu z kanonicznej drabiny evidence, zwłaszcza `reachable_from_turn/effect_observed` dla engine paths i rzeczywistych wyników walidacji.

---

## 3. Twarda granica P0 / P1

### P0 — RAW -> SEMANTIC -> MEMORY boundary

P0 pozostaje zielone tylko jeśli regresje potwierdzają:

- każdy członek eksportu ma rolę semantyczną;
- RAW payload/provenance pozostaje zachowany;
- semantyka HTML jest normalizowana po parse;
- rendered HTML jest jawnie LOSSY i nie udaje lossless PASS;
- technical/non-dialogue evidence nie jest tracone;
- visibility i `memory_eligible` są projekcjami, nie destrukcyjnym filtrem;
- warianty rozmów/branch union są deterministyczne;
- nierozstrzygnięty payload/parent conflict jest fail-closed;
- brak aktywnego `apply()/setattr()` hardening stacku;
- source role nie jest utożsamiona z późniejszym source-trust/memory class.

### P1 — jeden protokół Test00–Final

```text
Test00 -> Test01 -> Test02 -> Test03 -> Test04 -> Final
```

Każdy etap ma osobne `run_*` i `validate_*`. Engine egzekwuje zależności zamiast pozwalać na legalny etap bez poprzedników.

---

## 4. P1 — Definition of Done

### 4.1 ProtocolEngine

- [ ] `run_test00()` + `validate_test00()`;
- [ ] `run_test01()` + `validate_test01()`;
- [ ] `run_test02()` + `validate_test02()`;
- [ ] `run_test03()` + `validate_test03()`;
- [ ] `run_test04()` + `validate_test04()`;
- [ ] `run_final()` + `validate_final()`;
- [ ] dependency graph wymusza pełny łańcuch;
- [ ] CLI i Studio używają jednego engine;
- [ ] compatibility API wyłącznie deleguje.

### 4.2 Test00 — source fidelity

- [ ] source inventory + exact source identity;
- [ ] source mirror/fidelity;
- [ ] source-set closure;
- [ ] jawne `PASSED / LOSSY / BLOCKED / FAILED`;
- [ ] `rendered_html_lossy` zachowane jako evidence, nigdy lossless PASS;
- [ ] source-union bierze wyłącznie lossless graph sources;
- [ ] source role jest odrębna od memory/source-trust class.

### 4.3 Test01 — fresh canonical L0

- [ ] fresh build;
- [ ] provenance closure;
- [ ] pełne conversations/branches/revisions/assets/sidecars;
- [ ] integrity/FK/FTS;
- [ ] zero automatic L2/L3/activation;
- [ ] payload/schema pozwala zachować primary-vs-derived lineage bez destrukcyjnego spłaszczenia.

### 4.4 Test02 — projections

- [ ] visibility/role/sensitivity/eligibility/timestamp;
- [ ] raw <-> normalized reconciliation;
- [ ] projections nie modyfikują source L0;
- [ ] derived projection nie zmienia source precedence.

### 4.5 Test03 — reproducibility

- [ ] fresh build A/B;
- [ ] reversed input order;
- [ ] stable fingerprint;
- [ ] reconciliation z wcześniejszymi etapami;
- [ ] preserved branch union != unresolved conflict;
- [ ] input order/derived duplicate count nie zmienia source precedence.

### 4.6 Test04 — real private Recall acceptance

Test04 nie jest parserem gotowego raportu.

- [ ] final source set/operator attestation;
- [ ] real private benchmark, gdy dataset lokalnie dostępny;
- [ ] provenance;
- [ ] wrong-conversation / wrong-source;
- [ ] false-memory;
- [ ] abstention;
- [ ] temporal/update/supersession;
- [ ] sensitive leakage;
- [ ] referential two-turn/natural multi-turn;
- [ ] source discrimination: primary user/conversation vs reflection/runtime/system/dream;
- [ ] derived-source trap: późniejsza refleksja systemu nie może zostać przypisana użytkownikowi;
- [ ] brak prywatnej treści w repo/CI;
- [ ] brak datasetu = `PRIVATE ACCEPTANCE: NOT RUN`, nigdy syntetyczny PASS.

### 4.7 Final

- [ ] wymaga właściwie zaliczonego Test04 według policy;
- [ ] SQLite Backup API do staging snapshot;
- [ ] `PRAGMA integrity_check`;
- [ ] `PRAGMA foreign_key_check`;
- [ ] FTS5 integrity-check;
- [ ] final source/provenance/database SHA;
- [ ] publikacja dopiero po walidacji staging;
- [ ] zero automatycznej aktywacji runtime memory.

### 4.8 RunManifest

- [ ] jeden manifest obejmuje kolejne Test00–Final;
- [ ] final seal jest write-once, ale run nie zamyka się po pierwszym etapie;
- [ ] source inventory/provenance/fingerprint/database SHA;
- [ ] source-class/lineage summary bez prywatnej treści;
- [ ] private + sanitized manifest;
- [ ] sanitized nie zawiera prywatnych paths/content/PII.

---

## 5. Source monitoring / anti-self-amplification

v16.3.25.4 nie musi przypisać wszystkich finalnych prywatnych rekordów, ale musi przygotować natywny kontrakt, który v16.5.0 zastosuje bez przebudowy L0.

Minimalna semantyka:

```text
PRIMARY_USER_SOURCE
PRIMARY_CONVERSATION_SOURCE
USER_CONFIRMED
DERIVED_RUNTIME_EVENT
DERIVED_REFLECTION
DERIVED_SEMANTIC
SYNTHETIC_DREAM
FICTION_OR_BOOK
SYSTEM_METADATA
```

Twarde zasady:

- [ ] derived record nie staje się primary przez dedupe/merge;
- [ ] liczba kopii derived eventu nie zwiększa epistemicznego priorytetu;
- [ ] conflict primary-vs-derived pozostaje jawny;
- [ ] RAW -> SEMANTIC -> MEMORY zachowuje source lineage;
- [ ] classification wynika z evidence/provenance, nie samego similarity;
- [ ] brak klasyfikacji nie oznacza `PRIMARY`;
- [ ] Dream/reflection nie może self-certify factual memory.

---

## 6. Wersjonowanie

Branch WIP może tymczasowo dziedziczyć wersję mastera, ale finalny system patch musi mieć własny legalny bump w tej samej zmianie systemowej.

Jeżeli numer pozostaje wolny:

```text
DISTRIBUTION_VERSION = "16.3.25.4"
PACKAGE_VERSION = "16.3.25.4"
PACKAGE_RELEASE_NAME = "memory-rebuild-v4-consolidation"
```

Jeżeli master przesunie release line, rozstrzygnąć ponownie na aktualnej roadmapie/AGENTS. Nie używać `16.3.26` dla Memory Rebuild.

---

## 7. Dokumentacja i migracja hardeningów

Dawne moduły:

- `v16311_hardening.py`;
- `v16312_ci_hotfix.py`;
- `v16325_hardening.py`

muszą być sklasyfikowane jako:

- `SUPERSEDED` — zachowanie przeniesione natywnie;
- `RETIRED` — aktywna ścieżka nie istnieje i regresje to dowodzą;
- `STILL_REQUIRED` — audyt znalazł realny nieprzeniesiony kontrakt.

Nie przywracać monkey-patch stacku tylko dla starego testu.

---

## 8. Walidacja merge gate

Twarda kolejność:

```text
P1
-> VERSION
-> DOCUMENTATION
-> RELEASE METADATA
-> FULL VALIDATION
-> PR
```

Minimum:

```text
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
repozytoryjny Pyright zgodnie z AGENTS/workflow
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Dla SQLite:

- `PRAGMA integrity_check`;
- `PRAGMA foreign_key_check`;
- FTS5 integrity-check.

Release metadata wyłącznie przez kanoniczny `release_metadata_sync`; zero ręcznej edycji hashy. Wymagane GitHub CI na finalnym SHA musi być rzeczywiście green.

---

## 9. Relacja do #59 i #189

- `#189` śledzi consolidation/tool release i zamyka się przy właściwym finalnym merge/DoD.
- `#59` pozostaje otwarte do finalnego `ACCEPTED` / v16.6 closure.

`16.3.25.4` daje wiarygodne narzędzie/protokół. v16.5.0 dopiero buduje finalny prywatny artefakt `VERIFIED`.

---

## 10. Branch / PR policy

- kontynuować istniejący `upgrade/memory-rebuild-v4-consolidation`;
- bez rebase/force-push bez osobnej decyzji;
- checkpointy interrupt-safe;
- nie mergować przed P1/version/docs/metadata/full validation/CI;
- jeden finalny PR do master;
- attachment 16.3.26 startuje z mastera zawierającego zaakceptowaną konsolidację, chyba że jawna decyzja engineeringowa udowodni bezpieczne rozdzielenie.

---

## 11. Warunek zamknięcia

Release jest gotowy tylko gdy:

1. P0 remains green;
2. P1 Test00–Final = jeden engine;
3. RunManifest lifecycle jest poprawny;
4. CLI/Studio = ten sam ApplicationService;
5. stary hardening stack nie jest aktywną zależnością;
6. source-lineage contract działa i blokuje derived->primary amplification;
7. finalny poziom capability evidence odpowiada deklaracji `working`;
8. wersja jest legalna i podniesiona;
9. docs odpowiadają kodowi;
10. release metadata są zsynchronizowane;
11. pełna lokalna walidacja PASS;
12. wymagane CI na finalnym SHA PASS;
13. brak prywatnych/runtime artefaktów w diff;
14. PR jest merge-ready bez open P0/P1.
