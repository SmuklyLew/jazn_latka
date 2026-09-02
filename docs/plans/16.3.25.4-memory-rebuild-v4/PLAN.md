# Jaźń v16.3.25.4 — Memory Rebuild Application v4 consolidation

## Status

**Typ:** aktywny plan wykonawczy / release-prep  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Baza wykonawcza:** `origin/master@5f2c267cbff3bbacd15af06479d1f406bf85e686`, scalony zwykłym merge do brancha
**Wersja bazowa linii przy drugim merge:** `16.3.25.3.14-archive-tools-understanding-added`
**Branch implementacyjny:** `upgrade/memory-rebuild-v4-consolidation`  
**Ostatni wypchnięty bezpieczny checkpoint:** `39317cb23626cb930b05dda68c4a20c88dde6877`
**Bieżący zweryfikowany merge checkpoint:** `cdba4d2e209242454d7899fe0997b48ec3014953` — aktualny master scalony, P0/P1 ponownie zielone
**Tracking issue:** `#189`  
**Docelowy numer patch-release przy niezmienionej linii:** `16.3.25.4`  
**Proponowany release name:** `memory-rebuild-v4-consolidation`  
**Kanoniczne założenia:** `docs/plans/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Issue finalnej pamięci:** `#59`  
**Data aktualizacji:** 2026-09-01

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

## 2. Co jest na branchu — P0/P1 po merge DONE, release nadal otwarty

Na zweryfikowanym merge checkpointcie `cdba4d2e209242454d7899fe0997b48ec3014953` branch zawiera m.in.:

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

Branch scalił `origin/master@3983c577bc86ffdf6fa5bae138a4a20120bd9d5c` w merge commicie `2284ac735ddb9ef2b0c4ba9cdb6ee53955a4f7d9`. Gdy master przesunął się dalej, `origin/master@5f2c267cbff3bbacd15af06479d1f406bf85e686` został ponownie scalony zwykłym merge w `cdba4d2e209242454d7899fe0997b48ec3014953`, którego drugim rodzicem jest dokładnie ten master. Drugi merge zachował legalną wersję targetu, włączył nowe schematy kontraktowe i poprawkę aliasowania `TestOutcome`, zachował aktywne rozróżnienie `embedded_json_lossless` / `rendered_html_lossy` oraz skierował oba pliki generowane do ponownej kanonicznej synchronizacji. Wykryty na Windows problem kodowania blokującego JSON-u Dependency Studio został naprawiony w entrypoincie przez jawne UTF-8 stdio; bezpośrednia regresja jest zielona.

Po pierwszym merge aktywny nadzbiór Memory Rebuild dał `148 passed, 1` znane ostrzeżenie kolekcji, nadzbiór wersji/metadanych dał `43 passed`, a skupiony audyt stabilnego schematu dał `27 passed`. Po drugim merge skupiony zestaw konfliktów i nowych komponentów mastera dał `44 passed`, a pełny aktywny nadzbiór Memory Rebuild wzrósł do `172 passed`. Rzeczywisty audyt repo i brama wersji/metadanych są powtarzane po kanonicznej synchronizacji generowanych plików. Wykryte podczas integracji problemy zależnego od kolejności importu Pack Generatora v8.7, usuwania read-only `.git` na Windows, rozróżnienia stabilnego schematu metadanych od wersji runtime oraz kodowania bezpośredniego entrypointu mają osobne regresje i są zielone.

To potwierdza P0/P1 i legalny bump `16.3.25.4-memory-rebuild-v4-consolidation`, a nie finalny release. Post-merge release metadata są synchronizowane kanonicznym generatorem po tej finalnej treści dokumentacji. Pełna lokalna walidacja, prywatna akceptacja, GitHub CI i PR pozostają odrębnymi gate'ami.

Prywatny dataset nie został użyty w tych bramach. Stan Test04 na realnych danych pozostaje `PRIVATE ACCEPTANCE: NOT RUN`, nigdy syntetyczny PASS.

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

- [x] `run_test00()` + `validate_test00()`;
- [x] `run_test01()` + `validate_test01()`;
- [x] `run_test02()` + `validate_test02()`;
- [x] `run_test03()` + `validate_test03()`;
- [x] `run_test04()` + `validate_test04()`;
- [x] `run_final()` + `validate_final()`;
- [x] dependency graph wymusza pełny łańcuch;
- [x] CLI i Studio używają jednego engine;
- [x] compatibility API wyłącznie deleguje.

### 4.2 Test00 — source fidelity

- [x] source inventory + exact source identity;
- [x] source mirror/fidelity;
- [x] source-set closure;
- [x] jawne `PASSED / LOSSY / BLOCKED / FAILED`;
- [x] `rendered_html_lossy` zachowane jako evidence, nigdy lossless PASS;
- [x] source-union bierze wyłącznie lossless graph sources;
- [x] source role jest odrębna od memory/source-trust class.

### 4.3 Test01 — fresh canonical L0

- [x] fresh build;
- [x] provenance closure;
- [x] pełne conversations/branches/revisions/assets/sidecars;
- [x] integrity/FK/FTS;
- [x] zero automatic L2/L3/activation;
- [x] payload/schema pozwala zachować primary-vs-derived lineage bez destrukcyjnego spłaszczenia.

### 4.4 Test02 — projections

- [x] visibility/role/sensitivity/eligibility/timestamp;
- [x] raw <-> normalized reconciliation;
- [x] projections nie modyfikują source L0;
- [x] derived projection nie zmienia source precedence.

### 4.5 Test03 — reproducibility

- [x] fresh build A/B;
- [x] reversed input order;
- [x] stable fingerprint;
- [x] reconciliation z wcześniejszymi etapami;
- [x] preserved branch union != unresolved conflict;
- [x] input order/derived duplicate count nie zmienia source precedence.

### 4.6 Test04 — real private Recall acceptance

Test04 nie jest parserem gotowego raportu.

- [x] final source set/operator attestation;
- [x] real private benchmark runner, gdy dataset lokalnie dostępny;
- [x] provenance;
- [x] wrong-conversation / wrong-source;
- [x] false-memory;
- [x] abstention;
- [x] temporal/update/supersession;
- [x] sensitive leakage;
- [x] referential two-turn/natural multi-turn;
- [x] source discrimination: primary user/conversation vs reflection/runtime/system/dream;
- [x] derived-source trap: późniejsza refleksja systemu nie może zostać przypisana użytkownikowi;
- [x] brak prywatnej treści w repo/CI;
- [x] brak datasetu = `PRIVATE ACCEPTANCE: NOT RUN`, nigdy syntetyczny PASS.

Implementacja runnera jest DONE. Wykonanie na realnym prywatnym datasecie w tym release pozostaje `PRIVATE ACCEPTANCE: NOT RUN`.

### 4.7 Final

- [x] wymaga właściwie zaliczonego Test04 według policy;
- [x] SQLite Backup API do staging snapshot;
- [x] `PRAGMA integrity_check`;
- [x] `PRAGMA foreign_key_check`;
- [x] FTS5 integrity-check;
- [x] final source/provenance/database SHA;
- [x] publikacja dopiero po walidacji staging;
- [x] zero automatycznej aktywacji runtime memory.

### 4.8 RunManifest

- [x] jeden manifest obejmuje kolejne Test00–Final;
- [x] final seal jest write-once, ale run nie zamyka się po pierwszym etapie;
- [x] source inventory/provenance/fingerprint/database SHA;
- [x] source-class/lineage summary bez prywatnej treści;
- [x] private + sanitized manifest;
- [x] sanitized nie zawiera prywatnych paths/content/PII.

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

- [x] derived record nie staje się primary przez dedupe/merge;
- [x] liczba kopii derived eventu nie zwiększa epistemicznego priorytetu;
- [x] conflict primary-vs-derived pozostaje jawny;
- [x] RAW -> SEMANTIC -> MEMORY zachowuje source lineage;
- [x] classification wynika z evidence/provenance, nie samego similarity;
- [x] brak klasyfikacji nie oznacza `PRIMARY`;
- [x] Dream/reflection nie może self-certify factual memory.

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

Stan na 2026-09-02: kanoniczny bump został zapisany w `latka_jazn/version.py` w commicie `03859e7fd2ad357f9f645946c0572ba16306f7c3` i zachowany świadomie podczas obu merge; `DISTRIBUTION_VERSION` i `PACKAGE_VERSION` wynoszą `16.3.25.4`, a `PACKAGE_RELEASE_NAME` wynosi `memory-rebuild-v4-consolidation`.

Po pierwszym merge nadzbiór walidacji jednego źródła wersji i semantyki metadanych dał `43 passed`, skupiony nadzbiór audytu stabilnego schematu dał `27 passed`, a rzeczywisty `version_consistency_audit` zwrócił `ok: true`. Po drugim merge wersja targetu i nowe stabilne schematy mastera są zachowane; pełna brama jest powtarzana po bieżącym metadata sync. Drugi bump nie jest wymagany dla nadal niewydanego targetu `16.3.25.4`.

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
