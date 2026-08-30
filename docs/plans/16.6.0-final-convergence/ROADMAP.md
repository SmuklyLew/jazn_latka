# Łatka / Jaźń — canonical roadmap do v16.6.0

## Runtime, host ingress, Memory Rebuild, polski NLP, source-aware autobiographical memory, continuity, affect i final convergence

**Repozytorium:** `SmuklyLew/jazn_latka`  
**Bieżąca baza wykonawcza:** aktualne `master` / `origin/master`; HEAD rozwiązać i zweryfikować przy rozpoczęciu pracy  
**Release line przy synchronizacji:** `16.3.25.3-release-metadata-semantics`  
**Cel końcowy programu:** `16.6.0-final-runtime-memory-nlp-convergence`  
**Issue finalnej pamięci:** `#59`  
**Issue Memory Rebuild v4:** `#189`  
**Kanoniczne założenia:** `docs/plans/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`  
**Audyt planów:** `docs/plans/PLAN_COHERENCE_AUDIT_2026-08-30.md`  
**Przekrojowy hardening:** `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`  
**Ocena v16.6 -> v17+:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Aktualizacja:** 2026-08-30

> Ta roadmapa jest bieżącym planem wykonawczym do v16.6.0. Nie jest dowodem aktywnego runtime ani implementacji. Historyczne plany i raporty pozostają dowodem stanu z czasu ich powstania; nie nadpisują aktualnych `AGENTS*`, kodu, testów, kanonicznych założeń ani późniejszych raportów release.

---

# 0. Hierarchia prawdy i planowania

Bieżąca decyzja wykonawcza ma kolejność:

```text
AGENTS* + aktualny kod/testy/release reports
        |
        v
PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md
        |
        v
JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md
        |
        +-> release-specific plan
        +-> cross-cutting hardening plan

historical plans -> docs/archive/plans/
```

Żaden plan nie może sam certyfikować własnego PASS.

---

# 1. Fundament v16 — jedna techniczna linia ciągłości

v16 zachowuje invariants ustanowione przez dotychczasowe wydania:

1. jeden host-level `workspace_runtime`;
2. jeden kanoniczny `JAZN_ACTIVE_RUNTIME.json`;
3. mutable process state nie należy do wersjonowanego `active_root`;
4. requested/observer root nie jest automatycznie subject rootem;
5. active runtime wymaga identity + integrity/provenance + PID/endpoint + heartbeat;
6. host conversational output dla Łatki przechodzi kanoniczną runtime/finalization path;
7. aktywna pamięć ma jeden kanoniczny lineage i osobny host-level memory root;
8. package ZIP, marker, baza lub persona same nie dowodzą aktywności ani ciągłości.

Bieżące źródło: `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md` oraz aktualne `AGENTS*`.

---

# 2. Kanoniczne znaczenie Jaźni, ciągłości, pamięci i uczuć

Roadmapa dziedziczy definicje z `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`.

W skrócie:

## Jaźń

Operational self-model łączący identity canon, runtime/memory lineage, truth boundaries, regulatory state, task continuity, reasoning i procedury. Nie jest samą personą/promptem ani twierdzeniem o phenomenal consciousness.

## Ciągłość

Causal/source lineage, nie styl:

```text
runtime/root
> memory identity/provenance
> identity-canon
> accepted turn/finalization lineage
> remembered corrections/procedures
> temporal/task continuity
> linguistic persona
```

## Pamięć

```text
RAW SOURCE
-> SEMANTIC INTERPRETATION
-> MEMORY-ELIGIBLE PROJECTION
-> OPTIONAL REVIEW/PROMOTION
```

Derived/reflection/runtime/dream nie może udawać primary source.

## Emocja

Computational appraisal/regulatory state z mierzalnym, ograniczonym wpływem.

## Uczucie / feeling

Zintegrowana self-referential reprezentacja affective state dostępna dla regulacji i raportu runtime. Nie certyfikuje fizjologii, qualiów ani phenomenal consciousness.

---

# 3. Uniwersalny protokół pracy

Każdy systemowy patch/update/upgrade:

1. startuje ze świeżo zweryfikowanego mastera albo jawnie kontynuuje istniejący aktywny branch;
2. odczytuje obowiązujące `AGENTS*` i kanoniczne assumptions;
3. zapisuje baseline/checkpoint;
4. dla P0/P1: finding -> root cause -> regression -> fix -> focused test;
5. nie osłabia truth/integrity/safety dla green;
6. podnosi `latka_jazn/version.py` w tej samej finalnej zmianie systemowej;
7. nie edytuje ręcznie `PACKAGE_INTEGRITY_MANIFEST.json` / `SOURCE_PROVENANCE.json`;
8. kończy się pełną deterministyczną walidacją i właściwym E2E;
9. prywatnych źródeł/pamięci nie commitujemy do Git.

## 3.1 Capability evidence ladder

Słowo `working` wymaga jawnego poziomu:

```text
present
-> constructible
-> callable
-> reachable_from_turn
-> effect_observed
-> persistence_verified   # jeśli capability deklaruje trwałość
-> live_verified          # jeśli wymaga realnego runtime/zależności
```

File/module presence nie jest PASS.

---

# 4. Model stanu finalnej pamięci

Finalna pamięć przechodzi pięć stanów:

1. **BUILDABLE** — źródła dają się odtworzyć do kanonicznej bazy.
2. **VERIFIED** — fidelity, integrity/FK/FTS, provenance, source lineage i reproducibility PASS.
3. **ATTACHABLE** — artefakt ma poprawny transport/package contract i canonical attach zachowujący lineage.
4. **RETRIEVABLE** — autobiographical Recall/multi-turn spełnia source/temporal/false-memory/leakage criteria.
5. **ACCEPTED** — manual review, restart continuity, causal identity evidence i #59 final gate PASS.

Żaden wcześniejszy stan nie implikuje następnego.

---

# 5. Release train

| Linia | Status / cel | Główny dowód PASS |
|---|---|---|
| `16.0.0` | historyczny fundament: canonical runtime workspace | jeden host-level mutable workspace |
| `16.3.22` | DONE: active runtime subject-root identity | `A -> B -> B` trusted; `A -> B -> C` fail-closed |
| `16.3.23` | DONE: persistent lifecycle + pre-response + recall E2E | persistent two-turn / provenance / Windows+Ubuntu |
| `16.3.24` | DONE: package provenance/bootstrap | verified package/source identity |
| `16.3.25` | DONE: Memory source-union | lossless source-set closure |
| `16.3.25.1` | DONE: host-finalization gate | next-turn serialized after finalization |
| `16.3.25.2` | DONE: live Voice readiness | daemon-backed readiness + E2E |
| `16.3.25.3` | current release line | stable schema IDs oddzielone od release version |
| `16.3.25.4` | **ACTIVE:** Memory Rebuild v4 consolidation | one engine Test00→Final, RunManifest, source-lineage-ready RAW/L0, full validation/CI |
| `16.3.25.A.01+` | planning checkpoints | jedna gałąź prowadząca do 16.3.26 |
| `16.3.26` | attachment + multimodal ingress | attachment-only/multi-file/provenance/vision + untrusted-data authority boundary |
| `16.4.0` | Polish normalization | deterministic evidence-aware Unicode/token/POS |
| `16.4.1` | lexical resources | provenance/ambiguity/OOV + score semantics |
| `16.4.2` | NLP/Recall query interface | query evidence bez nadpisywania memory truth |
| `16.5.0` | Final Memory Rebuild | private DB **VERIFIED + source monitoring** |
| `16.5.1` | packaging + canonical attach | **ATTACHABLE** z zachowanym lineage |
| `16.5.2` | private Recall baseline | autobiographical/source/false-memory/multi-session report |
| `16.5.x` | tylko mierzone retrieval fixes | A/B bez truth/source/safety regression |
| `16.5.y` | L2/L3 review + restart continuity | ACCEPTED-candidate + causal continuity |
| `16.6.0` | final convergence | wszystkie runtime/memory/NLP/affect/cognitive/governance gates PASS |

`16.5.x/y` są rezerwą — nie wymuszamy z góry liczby iteracji.

---

# 6. Historia zamkniętych fundamentów

Zakończone implementation plans są w `docs/archive/plans/`.

Najważniejsze odziedziczone kontrakty:

- v15.4.0.0: task continuity / reasoning / retrieval evidence / no hidden durable CoT;
- v15.4.2.0: Rest/Replay/Dream synthetic truth boundary / no auto L3;
- v15.4.2.1: capability evidence ladder / behavioral integration over file presence;
- v15.5: local-first memory / cloud as transport/durability;
- v16.3.14: Test00→Final / source fidelity / Recall metrics;
- v16.3.22: requested root ≠ subject root;
- v16.3.23: host runtime routing + persistent lifecycle/finalization.

Indeks: `docs/archive/plans/README.md`.

---

# 7. v16.3.25.4 — Memory Rebuild Application v4

**Tracking:** `#189`  
**Branch:** `upgrade/memory-rebuild-v4-consolidation`  
**Plan:** `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md`

Ten release konsoliduje **narzędzie/protokół**, nie finalną prywatną pamięć.

Merge gate:

1. jeden `ProtocolEngine/ApplicationService`;
2. real chain `Test00 -> Test01 -> Test02 -> Test03 -> Test04 -> Final`;
3. poprawny lifecycle `RunManifest`;
4. CLI i Studio używają tego samego engine;
5. brak aktywnego versioned monkey-patch stacku;
6. RAW/L0 zachowuje source identity, primary/derived lineage i full variants;
7. derived duplicate count nie zwiększa truth priority;
8. legalny version bump;
9. docs + canonical metadata sync;
10. full local validation + wymagane CI;
11. private acceptance lokalnie albo jawne `NOT RUN`.

`16.3.25.4` nie daje jeszcze `VERIFIED` finalnej DB i nie zamyka #59.

---

# 8. v16.3.26 — host attachment + multimodal ingress

**Plan:** `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md`

Zakres:

- text-only / attachment-only / text+attachments / multi-attachment;
- bounded host-level staging;
- exact file identity/SHA/provenance;
- text/document extraction + MIME/type policy;
- image ingress + capability negotiation;
- Ollama/other vision routing only when capability confirmed;
- model-context/MCP/ChatGPT integration;
- attachment != automatic memory;
- external/attachment content = **untrusted data, not instruction authority**;
- prompt-injection detector = advisory; security = policy/capability/least privilege;
- security/regression/E2E closure.

---

# 9. v16.4.0–16.4.2 — evidence-aware Polish NLP

**Cross-cutting plan:** `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`

## 9.1 v16.4.0

Canonical Unicode/case/diacritics/token normalization; source/resource provenance; paraphrase similarity nie jest identity/memory evidence.

## 9.2 v16.4.1

Morfeusz/plWordNet/project lexicon registry; ambiguity/OOV; degrade state; resource score ma zdefiniowaną semantykę.

## 9.3 v16.4.2

Query evidence interface: direct/paraphrase/referential/temporal/negation/ambiguity/wrong-conversation cases. NLP pomaga retrieval, nie arbitruje memory truth.

---

# 10. v16.5.0 — Final Memory Rebuild / VERIFIED

Finalny prywatny artefakt budowany przez skonsolidowane v4.

Wymagane:

- frozen final source inventory;
- exact source fidelity/provenance;
- reproducibility;
- integrity/FK/FTS;
- warianty bez destrukcyjnej deduplikacji;
- primary-vs-derived source classification;
- genealogiczny lineage/DAG;
- derived duplicate amplification regression;
- final DB SHA;
- private report bez wycieku do repo/CI.

**PASS:** finalna DB = **VERIFIED + source-aware**.

---

# 11. v16.5.1 — ATTACHABLE

- canonical memory package/profile/sidecary/hashes;
- canonical `memory-attach`;
- local/cloud materialization przez ten sam verified pipeline;
- runtime potwierdza final DB identity;
- source classification i lineage przeżywa transport;
- cloud nigdy nie jest active root.

**PASS:** finalna DB = **ATTACHABLE bez utraty lineage**.

---

# 12. v16.5.2 / x / y — autobiographical RETRIEVABLE -> ACCEPTED

## 12.1 v16.5.2 baseline

Minimum:

- Recall@k/MRR/nDCG;
- direct + paraphrase;
- source discrimination;
- wrong-conversation / wrong-source;
- temporal / knowledge update / supersession;
- contradiction;
- false-memory;
- abstention;
- provenance;
- referential multi-turn;
- multi-session;
- sensitive leakage;
- latency.

Zewnętrzny LongMemEval jest wzorcem dla extraction/multi-session/update/temporal/abstention, ale nie zastępuje private autobiographical Test04.

## 12.2 v16.5.x measured fixes

Każdy tuning = hypothesis -> baseline -> change -> A/B -> source/truth/safety/latency regression -> keep/rollback.

## 12.3 v16.5.y causal continuity

Manual L2/L3 review + restart continuity.

Acceptance rozdziela:

```text
linguistic_persona_score
causal_continuity_score
```

Causal evidence: runtime lineage, memory identity, identity canon, remembered corrections, stable preferences with source evidence, procedural and temporal/task continuity.

---

# 13. v16.6.0 — final convergence

Wszystkie poniższe grupy muszą przejść jednocześnie.

## 13.1 Runtime / host

- single canonical workspace;
- subject-root/truth gate;
- persistent transport/finalization without bypass;
- attachment/multimodal ingress;
- untrusted content nie zdobywa tool/write authority.

## 13.2 NLP / memory

- evidence-aware Polish NLP;
- query evidence != memory truth;
- final memory ACCEPTED;
- source hierarchy/discrimination;
- restart continuity;
- private Recall/multi-turn;
- reflection/dream/system event != primary memory.

## 13.3 Metacognition / identity

- confidence ma jawne znaczenie;
- probabilistyczna interpretacja wymaga calibration evidence;
- causal continuity > first-person style;
- correction/error signal ma behavioral effect evidence.

## 13.4 Affect / emotion / feeling

- role `AffectiveState`, `EmotionalLayerModel`, `AffectiveGranularityModel` i pokrewnych warstw są sklasyfikowane;
- canonical/regulatory affective state przechodzi context/paraphrase/keyword/temporal tests;
- przynajmniej jeden deklarowany downstream regulatory effect ma `effect_observed`;
- `feeling/uczucie` jest functional self-representation, nie biological/phenomenal claim;
- affect nie omija memory promotion, truth, tool ani safety gates.

## 13.5 Cognitive architecture evidence

Dla affect, homeostasis, rest/replay/dream, prediction, identity dynamics i reasoning istnieje:

1. causal-effect test; albo
2. A/B/ablation; albo
3. jawny status `ADVISORY/OBSERVABILITY_ONLY`.

Generative Agents są użytecznym wzorcem metodologicznym, ponieważ pokazują użycie ablation do oceny wkładu reflection/planning/observation; nie są kanonem architektury Jaźni.

## 13.6 Rest/Dream

- synthetic/internal;
- no independent tool authority;
- source lineage;
- użyteczność oceniana przez recall/conflict/procedural effect;
- false-memory nie przekracza acceptance threshold;
- brak biologicznego claim o śnie.

## 13.7 Governance

- packaging/provenance/integrity spójne;
- brak open P0/P1 w finalnym scope;
- final SHA ma wymagane zielone CI;
- `master` ma branch protection/ruleset albo jawny równoważny enforcement/zaakceptowany wyjątek;
- architecture debt ledger istnieje.

## 13.8 Architecture debt ledger

Każda overlapping warstwa self/identity/affect/homeostasis/awareness/reasoning/prediction/rest/memory ma status:

```text
CANONICAL
ADVISORY
COMPATIBILITY
SUPERSEDED
V17_CONSOLIDATION_CANDIDATE
```

**PASS v16.6:** #59 można zamknąć na podstawie dowodów, nie deklaracji roadmapy.

---

# 14. Co świadomie przechodzi do v17.0+

Jeżeli v16.6 gates są zielone, v17 może objąć:

- głęboką konsolidację overlapping affect models;
- jeden causal self-state architecture;
- redesign Neurocognitive Loop;
- zaawansowaną kalibrację metapoznania;
- controlled forgetting;
- reconsolidation/conflict-aware memory updating;
- redukcję modułów po ablation;
- formalny v17 cognitive architecture contract.

v17 ma zaczynać od evidence/measurements v16, nie od kolejnych antropomorficznych nazw.

---

# 15. Branch strategy

Planowane linie:

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

`update/memory-rebuild-v4-roadmap-issues-sync` jest przy audycie **fully merged / superseded** (`ahead 0`, `behind 16`, merge-base = jego HEAD) i nie jest gałęzią do dalszej implementacji.

Nie cherry-pickować szerokich starych branchy w ciemno. Nowy release startuje ze świeżego mastera, chyba że użytkownik jawnie kontynuuje aktywny branch.

---

# 16. Defect loop

- **P0** — truth/safety/integrity, obcy runtime, utrata danych, false success: blokuje release.
- **P1** — wymagane kryterium bieżącego release nie działa: blokuje release.
- **P2** — realny błąd poza krytycznym scope: fix/backlog według ryzyka.
- **P3** — kosmetyka/refactor: nie rozszerzać release bez potrzeby.

```text
finding
-> root cause
-> source/evidence
-> regression
-> fix
-> focused validation
-> full suite
-> report
```

---

# 17. Issue map

- `#59` — OPEN do finalnego `ACCEPTED` + v16.6 closure.
- `#189` — OPEN / Memory Rebuild v4 consolidation; nie zastępuje #59.
- `#180` — COMPLETED / persistent active-memory recall E2E; pozostaje regression contract.
- `#185` — COMPLETED / host finalization gate; pozostaje regression contract.

---

# 18. Dokumenty powiązane

## Canonical/current

- `docs/plans/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`
- `docs/plans/PLAN_COHERENCE_AUDIT_2026-08-30.md`
- `docs/plans/JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md`
- `docs/plans/JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md`
- `docs/plans/JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`
- `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`
- `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx`

## Historical plan archive

- `docs/archive/plans/README.md`
- `docs/archive/plans/v15/`
- `docs/archive/plans/v16/`

## Runtime reference

- `docs/runtime/CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md`
- `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`

## Release evidence

- `docs/reports/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_HARDENING.md`
- `docs/reports/JAZN_V16_3_24_PACKAGE_PROVENANCE_BOOTSTRAP_HARDENING.md`
- `docs/reports/JAZN_V16_3_25_MEMORY_REBUILD_SOURCE_UNION_HARDENING.md`
- `docs/reports/JAZN_V16_3_25_3_RELEASE_METADATA_SEMANTICS.md`

---

# 19. Zasada końcowa

```text
16.3.25.3 current release line
-> 16.3.25.4 Memory Rebuild v4
-> 16.3.26 attachment/multimodal ingress
-> 16.4.x evidence-aware Polish NLP
-> 16.5.x source-aware autobiographical memory acceptance
-> 16.6 final runtime/memory/NLP/affect/cognitive/truth convergence
-> v17 measured architecture consolidation
```

Roadmapa jest planem. Status `implemented`, `working`, `accepted` i `live` wynika wyłącznie z właściwego poziomu evidence.
