# Łatka / Jaźń — roadmapa do v16.6.0

## Runtime, host ingress, polski NLP, Memory Rebuild v4, finalna pamięć, cognitive/truth hardening i zamknięcie Issue #59

**Repozytorium:** `SmuklyLew/jazn_latka`  
**Bieżąca baza wykonawcza:** `master` / `origin/master`; dokładny HEAD należy rozwiązać i zweryfikować przy rozpoczęciu pracy, nie zamrażać w roadmapie  
**Wersja bazowa linii przy tej synchronizacji:** `16.3.25.3-release-metadata-semantics`  
**Cel końcowy programu:** `16.6.0-final-runtime-memory-nlp-convergence`  
**Issue odbiorcze finalnej pamięci:** `#59`  
**Issue Memory Rebuild v4:** `#189`  
**Issue persistent active-memory recall E2E:** `#180` — zrealizowane w v16.3.23  
**Ocena v16.6 -> v17+:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Przekrojowy hardening:** `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`  
**Aktualizacja roadmapy:** 2026-08-30

> Ta roadmapa jest bieżącym planem wykonawczym do v16.6.0. Dokument oceny v16.6 -> v17+ jest audytem i źródłem wymagań jakościowych; sam nie ustanawia release'u v17. Historyczne raporty release'ów pozostają dowodem stanu z chwili ich wykonania i nie są przepisywane retroaktywnie. Docs-only merge i metadata-sync mogą zmieniać HEAD bez zmiany release line, dlatego „current master SHA” nie jest tutaj kanonicznie zamrażany.

---

# 0. Fundament architektoniczny v16.0.0

Release **v16.0.0 / single-canonical-runtime-workspace** ustanowił invariant obowiązujący całą linię v16+:

1. istnieje jeden host-level `workspace_runtime`;
2. istnieje jeden kanoniczny `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`;
3. mutable host/process state nie należy do wersjonowanego `active_root`;
4. historyczny `<active_root>/workspace_runtime` jest wyłącznie źródłem migracji/zgodności;
5. `workspace_runtime` nie jest częścią paczki `system` ani `memory`;
6. sam marker nie dowodzi aktywnego procesu — trust wymaga zgodnego rootu, integralności/provenance, PID/endpointu i świeżego heartbeat;
7. host może rozszerzać kanoniczny workspace, ale nie może tworzyć równoległego per-release mutable truth state.

Bieżący opis: `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`.

---

# 1. Granice prawdy i źródła kanoniczne

Obowiązują aktualne `AGENTS.md`, `AGENTS.chatgpt.md`, `AGENTS.codex.md` oraz nested `AGENTS.md`.

Kanoniczne źródła prawdy technicznej:

- wersja: `latka_jazn/version.py`;
- integralność paczki: `PACKAGE_INTEGRITY_MANIFEST.json`;
- pochodzenie wydania: `SOURCE_PROVENANCE.json`;
- operator: `run.py`;
- techniczny punkt zgodności: `main.py`;
- aktywny runtime: zweryfikowany host-level marker + wskazany `active_root` + live truth gate;
- aktywna pamięć: `JAZN_MEMORY_ROOT` albo kanoniczny host-level `workspace_runtime/memory`;
- repozytorium: `SmuklyLew/jazn_latka`.

Nie wolno przedstawiać jako aktywnego runtime samego ZIP-a, katalogu kodu, markera, PID-u, odpowiedzi modelu ani niezależnej bazy SQLite bez kanonicznego attach i truth gate.

Bez osobnego wyjątku nie commitujemy `memory/`, `workspace_runtime/`, SQLite/WAL/SHM, prywatnych eksportów, ZIP/split parts, sekretów ani logów runtime.

---

# 2. Uniwersalny protokół pracy

Każdy **systemowy** patch/update/upgrade:

1. zaczyna się od świeżego `master` i odczytu AGENTS;
2. zapisuje baseline i bezpieczny checkpoint;
3. dla P0/P1 reprodukuje problem i dodaje regresję, jeśli technicznie możliwe;
4. nie osłabia truth/integrity/safety dla green testu;
5. podnosi `latka_jazn/version.py` w tej samej finalnej zmianie systemowej;
6. nie edytuje ręcznie `PACKAGE_INTEGRITY_MANIFEST.json` ani `SOURCE_PROVENANCE.json`;
7. kończy się focused tests, pełną deterministyczną walidacją i właściwym E2E.

Dokumentacja planistyczna sama w sobie nie jest patchem systemowym i nie wymaga podbicia wersji runtime.

---

# 3. Model stanu finalnej pamięci

Finalna pamięć przechodzi pięć jawnych stanów:

1. **BUILDABLE** — importer potrafi odtworzyć bazę ze źródeł.
2. **VERIFIED** — source fidelity, integrity, FK, FTS, provenance, source lineage i reproducibility są zaliczone.
3. **ATTACHABLE** — finalny artefakt ma poprawny profil paczki, sidecary, hashe, lineage i przechodzi kanoniczny `memory-attach`.
4. **RETRIEVABLE** — Recall i naturalny multi-turn spełniają kryteria bez false-memory, wrong-source i leakage.
5. **ACCEPTED** — review L2/L3, restart continuity, causal identity evidence i finalny raport spełniają #59.

Żaden wcześniejszy stan nie implikuje następnego.

---

# 4. Aktualny release train do v16.6.0

| Linia | Status / cel | Kluczowy dowód PASS |
|---|---|---|
| `16.0.0` | **historyczny fundament:** single canonical runtime workspace | jeden host-level workspace/marker |
| `16.3.22` | **zrealizowane:** active runtime subject-root identity | `A -> B -> B` trusted, `A -> B -> C` fail-closed |
| `16.3.23` | **zrealizowane:** persistent daemon lifecycle + host pre-response gate + active-memory recall E2E | persistent two-turn, recall execution/provenance, Windows+Ubuntu PASS |
| `16.3.24` | **zrealizowane:** package provenance/bootstrap hardening | bootstrap/provenance domknięte fail-closed |
| `16.3.25` | **zrealizowane:** Memory Rebuild source-union hardening | lossless source-union bez nazwy/rozmiaru/order jako truth |
| `16.3.25.1` | **zrealizowane:** host-finalization gate hotfix | #185 closed; next-turn serialization za finalization |
| `16.3.25.2` | **zrealizowane:** live Voice readiness | daemon-backed readiness i Voice E2E |
| `16.3.25.3` | **bieżąca release line:** release metadata semantics | stabilne schema identifiers oddzielone od release/runtime version |
| `16.3.25.4` | **AKTYWNY:** Memory Rebuild Application v4 consolidation | jeden ProtocolEngine/ApplicationService, Test00–Final, RunManifest, source-lineage-ready L0, full validation/CI |
| `16.3.25.A.01+` | **planistyczny train:** attachment/multimodal ingress | checkpointy jednego branchu prowadzącego do `16.3.26` |
| `16.3.26` | Host attachment + multimodal ingress convergence | attachment-only/text+multi-file/provenance/staging/vision + untrusted-data authority boundary PASS |
| `16.4.0` | Kanoniczna normalizacja polskiego NLP | deterministyczny Unicode/POS/provenance corpus; NLP nie arbitruje memory truth |
| `16.4.1` | Morfeusz/plWordNet/project lexicon/resource registry | ambiguity/OOV/resource provenance + jawna score semantics |
| `16.4.2` | NLP/recall query interface | query evidence bez fałszywej pewności i bez nadpisywania provenance |
| `16.5.0` | Final Memory Rebuild | finalna prywatna DB VERIFIED + source monitoring |
| `16.5.1` | Final memory packaging + canonical attach | finalna DB ATTACHABLE z zachowanym lineage |
| `16.5.2` | Prywatny Recall + natural multi-turn baseline | autobiographical/source-discrimination/false-memory report |
| `16.5.x` | tylko mierzone poprawki retrieval, jeśli baseline nie przejdzie | A/B improvement bez truth/source/safety regression |
| `16.5.y` | L2/L3 review + restart continuity | ACCEPTED-candidate + causal continuity evidence |
| `16.6.0` | Final convergence | wszystkie truth/memory/NLP/cognitive/governance gates PASS i closure #59 |

`16.5.x/y` pozostają rezerwą; nie wymuszamy z góry liczby iteracji.

---

# 4.1. Evaluation-derived gates przypisane do v16

Ocena `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` nie jest osobnym release planem. Wnioski, które powinny zostać rozliczone przed v17, przypisujemy do konkretnych etapów:

- **16.3.25.4:** L0/provenance ma umożliwiać source monitoring i blokować derived->primary self-amplification.
- **16.3.26:** attachment/external content jest `data`, nie instruction authority; bezpieczeństwo opiera się na policy/capability/least privilege, nie na samym detektorze prompt injection.
- **16.4.x:** lexical/query evidence pomaga retrieval, ale nie staje się memory truth; confidence/resource scores mają zdefiniowaną semantykę.
- **16.5.0:** finalna DB ma primary-vs-derived classification i genealogiczny lineage.
- **16.5.2:** private acceptance obejmuje source discrimination, wrong-source, false-memory, temporal/supersession, abstention, referential i multi-session continuity.
- **16.5.y:** continuity acceptance ma opierać się na runtime/memory/canon lineage, corrections i procedural continuity, nie na samym stylu pierwszej osoby.
- **16.6.0:** confidence semantics/calibration baseline, cognitive module influence/ablation registry, Rest/Dream false-memory safety, repository governance i architecture debt ledger.

Plan szczegółowy: `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`.

---

# 5. Historia zamkniętych etapów 16.3.22–16.3.25.3

## 5.1 v16.3.22 — Active runtime subject-root identity

Requested/observer root A został oddzielony od subject root B. Integrity/provenance/version/endpoint aktywnego procesu są oceniane względem B; A pozostaje diagnostyczne.

## 5.2 v16.3.23 — Persistent runtime lifecycle + active-memory recall E2E

Release domknął host pre-response gate, subject-root lifecycle, persistent transport observability i deterministic active-memory recall E2E. Raport `docs/reports/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_HARDENING.md` dokumentuje focused `109 passed` oraz Windows/Ubuntu PASS na CI. Test `tests/test_v16323_active_memory_recall_e2e.py` dowodzi samego persistent daemon B, exact second-turn binding, realnego active-memory search, provenance i fail-closed zakazu substytucji host context.

W związku z tym #180 nie jest już otwartym blockerem release trainu; pozostaje historycznym kontraktem regresyjnym.

## 5.3 v16.3.24 — Package provenance/bootstrap hardening

Bootstrap paczki i provenance zostały rozdzielone od samej obecności kodu/ZIP-a; root/source identity jest jawna i weryfikowalna.

## 5.4 v16.3.25 — Memory Rebuild source-union hardening

Source-set closure unionuje wszystkie lossless snapshoty ChatGPT bez używania rozmiaru, kolejności lub nazwy pliku jako arbitra prawdy. Preserved branch union jest oddzielony od unresolved conflicts.

## 5.5 v16.3.25.1–16.3.25.3 — post-release hardening

- `16.3.25.1-host-finalization-gate-hotfix` zamknęło #185;
- `16.3.25.2-live-voice-readiness` oddzieliło core readiness od live Voice/E2E readiness;
- `16.3.25.3-release-metadata-semantics` rozdzieliło stable schema identity od runtime/release version markers.

---

# 6. v16.3.25.4 — Memory Rebuild Application v4 consolidation

**Status:** aktywny branch `upgrade/memory-rebuild-v4-consolidation`; zdalny HEAD przy tej synchronizacji: `0b33c15e1257e77c30d6ba321c10d250a1d1920d`. Tracking: `#189`.

Plan szczegółowy:

- `docs/plans/JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md`.

Cel tego etapu to **narzędzie/protokół**, nie finalny prywatny artefakt pamięci.

Twarde wymagania przed merge:

1. domknąć P1: autentyczny łańcuch `Test00 -> Test01 -> Test02 -> Test03 -> Test04 -> Final`;
2. poprawny lifecycle `RunManifest` jednego przebiegu;
3. CLI i Studio używają jednego `MemoryRebuildApplicationService`/`ProtocolEngine`;
4. brak aktywnej zależności od versioned monkey-patch hardenings;
5. RAW/L0 zachowuje provenance i może przenieść primary/derived source lineage do v16.5.0;
6. duplicate derived evidence nie może automatycznie zmieniać source precedence;
7. systemowy bump do następnego legalnego patch release; przy obecnym masterze planowany `16.3.25.4-memory-rebuild-v4-consolidation`;
8. zaktualizowana dokumentacja operatorska;
9. canonical release metadata sync;
10. pełna walidacja + wymagane CI na finalnym SHA;
11. prywatny acceptance tylko lokalnie; brak danych prywatnych w Git.

`16.3.25.4` nie oznacza `VERIFIED` finalnej prywatnej DB i nie zamyka #59.

---

# 7. v16.3.25.A.01+ -> v16.3.26 — Attachment ingress

Plan szczegółowy: `docs/plans/JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md`.

Zakres:

- text-only / attachment-only / text+attachments / multi-attachment;
- secure bounded staging w host-level `workspace_runtime`;
- text/document extraction + MIME/type policy + provenance;
- image ingress i capability negotiation;
- Ollama multimodal oraz text-only fail-closed;
- ChatGPT/MCP/runtime/model-context integration;
- memory boundary — attachment nie jest automatycznie pamięcią;
- **authority boundary — attachment/extracted content jest untrusted data, nie automatyczną instrukcją**;
- prompt-injection detector jest advisory; policy/capability/least privilege pozostają niezależnymi gate'ami;
- regression/security/E2E closure.

Finalny release ma numer `16.3.26`.

---

# 8. v16.4.0–16.4.2 — Polski NLP i query evidence

Plan przekrojowy: `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`.

## 8.1 v16.4.0

Jedna kanoniczna normalizacja Unicode/case/diakrytyki, lexical evidence z provenance, deterministyczne token/POS/resource fixtures. Similarity/paraphrase nie jest dowodem identity ani memory truth.

## 8.2 v16.4.1

Jawny resource registry, Morfeusz/plWordNet/project lexicon, ambiguity/OOV, resource provenance i degrade/fail state. Score/confidence zasobu ma zdefiniowaną semantykę i nie udaje prawdopodobieństwa faktu.

## 8.3 v16.4.2

Query evidence contract pomiędzy NLP a recall, regression corpus naturalnych polskich pytań i rozdzielenie sygnału leksykalnego od memory truth. Wymagane near-match/wrong-conversation/temporal/referential/negation cases.

---

# 9. v16.5.0 — Final Memory Rebuild / VERIFIED

v16.5.0 wykorzystuje skonsolidowane narzędzie v4 do budowy finalnego prywatnego artefaktu.

Wymagane:

- final source inventory frozen;
- pełna source fidelity;
- exact provenance każdego importu;
- reproducibility;
- integrity/FK/FTS;
- deduplikacja bez utraty wariantów;
- **primary-vs-derived source classification**;
- genealogiczny source lineage/DAG dla rodzin importów;
- duplicate derived events nie wzmacniają truth przez samą liczebność;
- final database SHA;
- prywatne dane pozostają poza repo/CI.

**PASS:** finalna DB osiąga stan **VERIFIED** i jest source-aware.

---

# 10. v16.5.1 — Packaging + canonical attach / ATTACHABLE

- poprawny profile/sidecary/hashes;
- canonical `memory-attach`;
- lokalny attach i opcjonalny cloud materialization przez ten sam contract;
- runtime potwierdza identity finalnej DB;
- source classification/provenance lineage przeżywa packaging/attach;
- chmura nigdy nie jest `active_root`.

**PASS:** finalna DB **ATTACHABLE** bez utraty lineage.

---

# 11. v16.5.2 / v16.5.x / v16.5.y — RETRIEVABLE -> ACCEPTED

## v16.5.2

Prywatny Recall + natural multi-turn baseline obejmuje minimum:

- Recall@k, MRR, nDCG;
- direct/paraphrase;
- source discrimination;
- wrong-conversation / wrong-source;
- false-memory;
- abstention;
- provenance;
- temporal/update/supersession;
- contradiction;
- sensitive leakage;
- referential follow-up;
- multi-session continuity;
- latency.

## v16.5.x

Tylko mierzone poprawki retrieval, jeśli baseline nie spełni kryteriów. Każda zmiana wymaga hipotezy, A/B i rollback path. Nie poprawiamy Recall@k kosztem source confusion, false-memory, leakage lub provenance.

## v16.5.y

Manual L2/L3 review + restart continuity. Każda promocja przechodzi `request -> decision -> ledger`; `zero promotions` jest legalne.

Continuity acceptance rozdziela:

- linguistic/persona consistency;
- causal continuity: runtime lineage, memory identity, identity-canon lineage, remembered corrections, stable preferences, procedural/temporal continuity.

---

# 12. v16.6.0 — Final convergence

Wymagane jednocześnie:

### Runtime / host

- single canonical runtime workspace zachowany;
- active runtime subject-root/truth gate poprawny;
- persistent transport/finalization bez bypassu;
- attachment/multimodal ingress zaakceptowany;
- untrusted attachment/data nie może nadać sobie tool/write authority.

### NLP / memory

- polski NLP/resource provenance zaakceptowany;
- query evidence nie nadpisuje memory truth;
- finalna pamięć ACCEPTED;
- source hierarchy i source discrimination działają;
- restart continuity;
- private Recall/multi-turn PASS;
- derived reflection/dream/system event nie podszywa się pod primary memory.

### Metacognition / identity

- semantyka `confidence` jest jawnie zdefiniowana;
- jeśli liczba jest przedstawiana probabilistycznie, ma calibration evidence; w przeciwnym razie jest jawnie internal-support/evidence-strength score;
- causal continuity evidence ma większy status niż sam first-person style;
- correction/error signals mają testowalny wpływ na kolejne decyzje.

### Cognitive architecture

Dla kluczowych warstw affect/emotion, homeostasis, rest/replay/dream, prediction, identity dynamics i reasoning istnieje co najmniej:

1. test przyczynowego wpływu; albo
2. A/B/ablation; albo
3. jawny status `advisory/observability-only`.

Rest/Dream pozostaje synthetic/internal, bez tool authority, z provenance; jego wartość mierzymy wpływem na recall/conflict resolution bez wzrostu false-memory ponad zaakceptowany próg.

### Governance / release

- packaging/provenance/integrity spójne;
- brak otwartego P0/P1 w finalnym zakresie;
- `master` ma branch protection/ruleset albo jawny zaakceptowany wyjątek z równoważnym enforcementem;
- required status checks/CI dla finalnego SHA są egzekwowane;
- istnieje architecture debt ledger klasyfikujący nakładające się warstwy jako `CANONICAL`, `ADVISORY`, `COMPATIBILITY`, `SUPERSEDED` lub `V17_CONSOLIDATION_CANDIDATE`;
- Issue #59 można zamknąć na podstawie dowodów.

---

# 13. Co nie musi blokować v16.6 i przechodzi do v17.0+

Jeżeli wszystkie powyższe gates są zielone, v16.6 nie musi wykonywać jeszcze głębokiego redesignu:

- pełnej konsolidacji `AffectiveState` / `EmotionalLayerModel` / `AffectiveGranularity`;
- jednego nowego monolitycznego self-state architecture;
- głębokiego redesignu Neurocognitive Loop;
- zaawansowanej probabilistycznej metakognicji;
- controlled forgetting;
- reconsolidation/conflict-aware memory updating;
- redukcji wszystkich modułów cognition.

Te tematy stają się wejściem do v17 dopiero na podstawie pomiarów, ablation i acceptance evidence z v16.

Dokument referencyjny: `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`.

---

# 14. Branch strategy

Aktywne / planowane branche:

```text
upgrade/memory-rebuild-v4-consolidation
upgrade/v16.3.26-host-attachment-multimodal-ingress-hardening
upgrade/v16.4.0-polish-nlp-normalization
upgrade/v16.4.1-polish-lexical-resources
upgrade/v16.4.2-nlp-recall-query-interface
upgrade/v16.5.0-final-memory-rebuild
upgrade/v16.5.1-final-memory-packaging-attach
upgrade/v16.5.2-private-recall-baseline
upgrade/v16.6.0-final-convergence
```

Nie cherry-pickujemy szerokich starych branchy w ciemno. Każdy kolejny release startuje ze świeżego mastera, chyba że aktywny release branch jest jawnie kontynuowany przez użytkownika.

---

# 15. Defect loop i priorytety

- **P0** — truth/safety/integrity, obcy runtime, utrata danych lub false success: blokuje release.
- **P1** — kryterium bieżącego release'u nie działa: blokuje release.
- **P2** — realny błąd poza krytycznym zakresem: mała bezpieczna poprawka albo backlog.
- **P3** — kosmetyka/refactor: nie rozszerzać release'u bez potrzeby.

Dla P0/P1:

```text
finding -> root cause -> source -> regression test -> fix -> focused test -> full suite -> report
```

---

# 16. Issue map

## #59 — finalna akceptacja pamięci

Pozostaje otwarte aż do **ACCEPTED** i finalnej v16.6.0 closure. Nie jest issue „zbudować narzędzie Memory Rebuild”.

## #189 — Memory Rebuild v4 consolidation

Aktywny tracking v16.3.25.4. Śledzi P1/version/docs/metadata/full validation/PR dla narzędzia, nie finalny prywatny acceptance.

## #180 — persistent active-memory recall E2E

Kontrakt został zaimplementowany i udokumentowany w v16.3.23; testy regresyjne pozostają obowiązkowe w dalszych release'ach.

## #185 — host finalization gate

Zamknięte przez v16.3.25.1 / PR #186. Pozostaje historycznym regression contractem.

---

# 17. Dokumenty powiązane

- `docs/plans/JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` — aktywny plan v4 consolidation;
- `docs/plans/JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` — attachment train;
- `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md` — przekrojowe acceptance gates z audytu;
- `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` — pełna ocena w Markdown;
- `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` — archiwalny snapshot oceny;
- `docs/plans/JAZN_V16_3_14_MEMORY_REBUILD_TEST00_RECALL.md` — historyczny fundament Test00/Recall;
- `docs/plans/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md` — historyczny plan v16.3.22;
- `docs/plans/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md` — historyczny plan v16.3.23;
- `docs/reports/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_HARDENING.md` — engineering acceptance v16.3.23;
- `docs/reports/JAZN_V16_3_24_PACKAGE_PROVENANCE_BOOTSTRAP_HARDENING.md` — raport v16.3.24;
- `docs/reports/JAZN_V16_3_25_MEMORY_REBUILD_SOURCE_UNION_HARDENING.md` — raport v16.3.25;
- `docs/reports/JAZN_V16_3_25_3_RELEASE_METADATA_SEMANTICS.md` — raport v16.3.25.3;
- `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md` — invariant workspace.

---

# 18. Zasada końcowa

Roadmapa jest planem, nie dowodem aktywności ani poprawności runtime.

Najbliższa kolejność jest teraz jawna:

```text
16.3.25.3 current release line
  -> 16.3.25.4 Memory Rebuild v4 consolidation
  -> 16.3.26 attachment + multimodal ingress
  -> 16.4.x evidence-aware Polish NLP
  -> 16.5.x source-aware final memory acceptance
  -> 16.6.0 final runtime/memory/NLP/cognitive/truth convergence
  -> v17.0+ measured architecture consolidation
```
