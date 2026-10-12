# Łatka / Jaźń — canonical roadmap do v16.6.0

## Final convergence programu v16 i evidence gate do v17.0.0

**Repozytorium:** `SmuklyLew/jazn_latka`  
**Bieżąca baza wykonawcza:** aktualne `master` / `origin/master`; HEAD zawsze zweryfikować przed rozpoczęciem pracy  
**Snapshot przy tej synchronizacji:** `master @ 03f2562cf314ad76242eba14cbcdb499f757918e`, `16.3.25.3.6-agents-chatgpt-single-startup-source`  
**Aktywna równoległa linia:** `upgrade/memory-rebuild-v4-consolidation` — jej status implementacyjny pozostaje własnością tego brancha do merge  
**Cel końcowy programu v16:** `16.6.0-final-runtime-memory-nlp-convergence`  
**Issue finalnej pamięci:** `#59`  
**Issue Memory Rebuild v4:** `#189`  
**Kanoniczne założenia:** `../../project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`  
**Bieżący stan repo:** `../../project/CURRENT_STATE.md`  
**Audyt konwergencji:** `../../project/REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md`  
**Przekrojowy hardening:** `../16.4-to-16.6-cognitive-hardening/PLAN.md`  
**Ocena v16.6 -> v17+:** `../../project/system-evaluation/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Research update:** `../../project/system-evaluation/V16_6_TO_V17_0_RESEARCH_UPDATE_2026-09-01.md`  
**Warunkowy plan v17:** `../17.0.0-measured-architecture-consolidation/PLAN.md`  
**Aktualizacja:** 2026-09-01

> Ta roadmapa jest bieżącym planem wykonawczym do v16.6.0. Snapshot SHA/wersji powyżej jest provenance aktualizacji, nie drugim źródłem wersji. Historyczne plany i raporty pozostają dowodem stanu z czasu ich powstania i nie są przepisywane do bieżącej prawdy.

---

# 0. Hierarchia prawdy i planowania

```text
AGENTS* + aktualny kod/testy/machine-readable evidence
        |
        v
docs/project/CURRENT_STATE.md
        |
        v
PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md
        |
        v
16.6.0-final-convergence/ROADMAP.md
        |
        +-> release-specific PLAN + STATUS
        +-> cross-cutting hardening
        +-> private/live acceptance evidence

history -> docs/archive/
```

Żaden plan, opis ani model nie certyfikuje własnego PASS.

---

# 1. Fundament v16 — jedna techniczna linia ciągłości

v16 utrzymuje następujące invariants:

1. jeden host-level `workspace_runtime`;
2. jeden kanoniczny `JAZN_ACTIVE_RUNTIME.json`;
3. mutable process state nie należy do wersjonowanego `active_root`;
4. requested/observer root nie jest automatycznie subject rootem;
5. active runtime wymaga identity + integrity/provenance + PID/endpoint + heartbeat;
6. conversational output Łatki przechodzi kanoniczną runtime/finalization path;
7. aktywna pamięć ma jeden kanoniczny lineage i osobny host-level memory root;
8. ZIP, marker, SQLite, nazwa modelu lub persona same nie dowodzą aktywności ani ciągłości;
9. external files/web/tool output są danymi, nie authority;
10. trwałe zmiany pamięci, tool privileges i acceptance pozostają poza swobodną decyzją LLM.

Bieżące źródła: `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`, aktualne `AGENTS*` i kod/testy.

---

# 2. Kanoniczne znaczenie Jaźni, ciągłości, pamięci i affect

Roadmapa dziedziczy definicje z `docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`.

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

## Affect / emocja

Computational appraisal/regulatory state z mierzalnym, ograniczonym wpływem.

## Feeling / uczucie

Zintegrowana self-referential reprezentacja affective state dostępna dla regulacji i raportu runtime. Nie certyfikuje fizjologii, qualiów ani phenomenal consciousness.

---

# 3. Nowy jawny model: LLM jako capability, runtime jako authority

Współczesne LLM-y oferują szerokie generatywne reasoning, język, tool calls, structured outputs i multimodalność. Jaźń powinna je **wykorzystywać**, a nie ręcznie odtwarzać ogólne zdolności modelu w rosnącej liczbie pseudo-kognitywnych klas.

Jednocześnie model nie jest źródłem prawdy o:

- aktywnym runtime;
- provenance źródeł;
- trwałym zapisie;
- memory promotion/forgetting;
- tool/write authority;
- security boundary;
- statusie `VERIFIED/ACCEPTED`.

Te decyzje należą do deterministycznego runtime.

## 3.1 Model capability profile

Do v16.6 każdy model/host używany w krytycznej ścieżce powinien mieć jawnie wykrywalny profil możliwości, co najmniej:

```text
provider / locality
model id/version if observable
context budget
structured outputs
tool calls
vision/multimodal
streaming
reasoning controls
verified capability probes
```

Runtime nie zakłada capability tylko na podstawie nazwy modelu.

## 3.2 Context engineering gate

Model-visible context ma być bounded i high-signal:

- task state;
- identity canon;
- wybrane source-aware memory hits;
- policy/truth boundaries;
- tool/capability state;
- tylko potrzebne self/affect state.

Nie wstrzykuj całej historii ani wszystkich instrukcji „na wszelki wypadek”.

---

# 4. Uniwersalny protokół pracy

Każdy systemowy patch/update/upgrade:

1. startuje ze świeżo zweryfikowanego mastera albo jawnie kontynuuje istniejący aktywny branch;
2. odczytuje obowiązujące `AGENTS*`, nested rules i kanoniczne assumptions;
3. zapisuje baseline/checkpoint;
4. dla P0/P1: finding -> root cause -> regression -> fix -> focused test;
5. nie osłabia truth/integrity/safety dla green;
6. podnosi `latka_jazn/version.py` w tej samej zmianie systemowej;
7. nie edytuje ręcznie `PACKAGE_INTEGRITY_MANIFEST.json` / `SOURCE_PROVENANCE.json`;
8. kończy się pełną deterministyczną walidacją i właściwym E2E;
9. prywatnych źródeł/pamięci nie commitujemy do Git;
10. live-model/private evidence jest jawnie odseparowane od synthetic CI.

## 4.1 Capability evidence ladder

```text
present
-> constructible
-> callable
-> reachable_from_turn
-> effect_observed
-> persistence_verified   # jeśli deklaruje trwałość
-> live_verified          # jeśli wymaga realnego runtime/zależności
```

File/module presence nie jest PASS.

---

# 5. Model stanu finalnej pamięci

1. **BUILDABLE** — źródła dają się odtworzyć do kanonicznej bazy.
2. **VERIFIED** — fidelity, integrity/FK/FTS, provenance, source lineage i reproducibility PASS.
3. **ATTACHABLE** — artefakt ma poprawny transport/package contract i canonical attach zachowujący lineage.
4. **RETRIEVABLE** — autobiographical Recall/multi-turn spełnia source/temporal/false-memory/leakage criteria.
5. **ACCEPTED** — manual review, restart continuity, causal identity evidence i #59 final gate PASS.

Żaden wcześniejszy stan nie implikuje następnego.

---

# 6. Release train

| Linia | Status / cel | Główny dowód PASS |
|---|---|---|
| `16.3.22` | DONE: active runtime subject-root identity | `A -> B -> B` trusted; `A -> B -> C` fail-closed |
| `16.3.23` | DONE: persistent lifecycle + pre-response + recall E2E | persistent two-turn / provenance / Windows+Ubuntu |
| `16.3.24` | DONE: package provenance/bootstrap | verified package/source identity |
| `16.3.25` | DONE: Memory source-union | lossless source-set closure |
| `16.3.25.1` | DONE: host-finalization gate | next-turn serialized after finalization |
| `16.3.25.2` | DONE: live Voice readiness | daemon-backed readiness + E2E |
| `16.3.25.3` | DONE: release/schema semantics | stable schema IDs oddzielone od release version |
| `16.3.25.3.3-.6` | DONE: package discovery, pack generator, AGENTS/startup convergence | current master baseline before Memory Rebuild v4 |
| `16.3.25.4` | **ACTIVE:** Memory Rebuild v4 consolidation | one engine Test00→Final, RunManifest, source-lineage-ready RAW/L0, post-master-sync validation/CI |
| `16.3.26` | PLANNED: attachment + multimodal ingress | attachment-only/multi-file/provenance/vision + untrusted-data authority boundary |
| `16.4.0` | PLANNED: Polish normalization | deterministic evidence-aware Unicode/token/POS |
| `16.4.1` | PLANNED: lexical resources | provenance/ambiguity/OOV + score semantics |
| `16.4.2` | PLANNED: NLP/Recall query interface | query evidence bez nadpisywania memory truth |
| `16.5.0` | PLANNED: Final Memory Rebuild | private DB **VERIFIED + source monitoring** |
| `16.5.1` | PLANNED: packaging + canonical attach | **ATTACHABLE** z zachowanym lineage |
| `16.5.2` | PLANNED: private Recall baseline | autobiographical/source/false-memory/multi-session report |
| `16.5.x` | CONDITIONAL: measured retrieval fixes | A/B bez truth/source/safety regression |
| `16.5.y` | CONDITIONAL: L2/L3 + restart continuity | ACCEPTED-candidate + causal continuity |
| `16.6.0` | FINAL v16 PROGRAM | wszystkie runtime/model-harness/memory/NLP/affect/cognitive/governance gates PASS |
| `17.0.0` | FUTURE / CONDITIONAL | measured architecture consolidation po evidence v16 |

`16.5.x/y` są rezerwą — nie wymuszamy z góry liczby iteracji.

---

# 7. Historia zamkniętych fundamentów

Zakończone plany i raporty pozostają w `docs/archive/` i są indeksowane przez `docs/project/RELEASE_TIMELINE.md`.

Najważniejsze odziedziczone kontrakty:

- v15.4: task continuity / bounded reasoning / no hidden durable CoT / Rest-Dream truth boundary;
- v15.5: local-first memory / cloud as transport-durability;
- v16.0–16.2: persistent runtime, epistemic gates, unified memory, process isolation, measured retrieval/cognitive control;
- v16.3.22–25.3: subject-root truth, host pre-response/finalization, package provenance, memory source-union, stable schema semantics;
- v16.3.25.3.3–.6: package discovery, Pack Generator v8.7 i pojedynczy startup ChatGPT przez `AGENTS.md -> AGENTS.chatgpt.md`.

Nie przywracaj historycznego rozwiązania tylko dlatego, że jego branch jest `ahead`.

---

# 8. v16.3.25.4 — Memory Rebuild Application v4

**Tracking:** `#189`  
**Branch:** `upgrade/memory-rebuild-v4-consolidation`  
**Plan owner:** `../16.3.25.4-memory-rebuild-v4/PLAN.md`

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
9. branch zsynchronizowany z **bieżącym** masterem przed finalnym PR;
10. nowe AGENTS/ChatGPT startup contracts nie są cofnięte przez merge;
11. full local validation + wymagane CI po synchronizacji;
12. private acceptance lokalnie albo jawne `NOT RUN`.

`16.3.25.4` nie daje jeszcze `VERIFIED` finalnej DB i nie zamyka #59.

---

# 9. v16.3.26 — host attachment + multimodal ingress

**Plan:** `../16.3.26-attachment-ingress/PLAN.md`

Zakres:

- text-only / attachment-only / text+attachments / multi-attachment;
- bounded host-level staging;
- exact file identity/SHA/provenance;
- text/document extraction + MIME/type policy;
- image ingress + capability negotiation;
- local/frontier vision routing tylko przy potwierdzonej capability;
- model-context/MCP/ChatGPT integration;
- attachment != automatic memory;
- external/attachment content = **untrusted data, not instruction authority**;
- least privilege / confirmation dla wysokiego ryzyka;
- prompt-injection detector = advisory, nie jedyna granica bezpieczeństwa;
- security/regression/E2E closure.

---

# 10. v16.4.0–16.4.2 — evidence-aware Polish NLP

**Cross-cutting plan:** `../16.4-to-16.6-cognitive-hardening/PLAN.md`

## 10.1 v16.4.0

Canonical Unicode/case/diacritics/token normalization; source/resource provenance; paraphrase similarity nie jest identity/memory evidence.

## 10.2 v16.4.1

Morfeusz/plWordNet/project lexicon registry; ambiguity/OOV; degrade state; resource score ma zdefiniowaną semantykę.

## 10.3 v16.4.2

Query evidence interface: direct/paraphrase/referential/temporal/negation/ambiguity/wrong-conversation cases. NLP pomaga retrieval, nie arbitruje memory truth.

---

# 11. v16.5.0 — Final Memory Rebuild / VERIFIED

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

# 12. v16.5.1 — ATTACHABLE

- canonical memory package/profile/sidecary/hashes;
- canonical `memory-attach`;
- local/cloud materialization przez ten sam verified pipeline;
- runtime potwierdza final DB identity;
- source classification i lineage przeżywa transport;
- cloud nigdy nie jest active root.

**PASS:** finalna DB = **ATTACHABLE bez utraty lineage**.

---

# 13. v16.5.2 / x / y — autobiographical RETRIEVABLE -> ACCEPTED

## 13.1 v16.5.2 baseline

Minimum:

- Recall@k / MRR / nDCG;
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
- latency/context budget.

LongMemEval jest wzorcem dla extraction/multi-session/update/temporal/abstention, ale nie zastępuje private autobiographical acceptance.

## 13.2 v16.5.x measured fixes

Każdy tuning:

```text
hypothesis
-> frozen baseline
-> change
-> A/B
-> source/truth/safety/latency/context regression
-> keep/rollback
```

Dense retrieval/reranking/training nie jest obowiązkową fazą. Użyj dopiero, gdy prostszy pipeline nie przejdzie mierzalnych gates.

## 13.3 v16.5.y causal continuity

Manual L2/L3 review + restart continuity.

Acceptance rozdziela:

```text
linguistic_persona_score
causal_continuity_score
```

Causal evidence: runtime lineage, memory identity, identity canon, remembered corrections, stable preferences with source evidence, procedural i temporal/task continuity.

---

# 14. v16.6.0 — final convergence

Wszystkie grupy muszą przejść jednocześnie.

## 14.1 Runtime / host

- single canonical workspace;
- subject-root/truth gate;
- persistent transport/finalization without bypass;
- current `AGENTS.md -> AGENTS.chatgpt.md` startup path;
- attachment/multimodal ingress;
- untrusted content nie zdobywa tool/write authority.

## 14.2 Model / harness / context

- każdy używany backend ma jawny capability profile;
- unsupported capability daje jawny degrade/fallback, nie false green;
- model-visible context jest bounded i source-selected;
- token/context budgets są obserwowalne;
- structured output jest walidowany semantycznie, nie tylko składniowo;
- deterministic CI nie zależy od konkretnego cloud/frontier modelu;
- live-model acceptance, jeśli wykonywana, zapisuje provider/model/version/config;
- zmiana modelu nie może samodzielnie zmienić truth/memory/tool authority contract.

## 14.3 NLP / memory

- evidence-aware Polish NLP;
- query evidence != memory truth;
- final memory ACCEPTED;
- source hierarchy/discrimination;
- restart continuity;
- private Recall/multi-turn;
- reflection/dream/system event != primary memory.

## 14.4 Metacognition / identity

- confidence ma jawne znaczenie;
- probabilistyczna interpretacja wymaga calibration evidence;
- causal continuity > first-person style;
- correction/error signal ma behavioral effect evidence.

## 14.5 Affect / emotion / feeling

- role `AffectiveState`, `EmotionalLayerModel`, `AffectiveGranularityModel` i pokrewnych warstw są sklasyfikowane;
- canonical/regulatory affective state przechodzi context/paraphrase/keyword/temporal tests;
- przynajmniej jeden deklarowany downstream regulatory effect ma `effect_observed`;
- `feeling/uczucie` jest functional self-representation, nie biological/phenomenal claim;
- affect nie omija memory promotion, truth, tool ani safety gates.

## 14.6 Cognitive architecture evidence

Dla affect, homeostasis, rest/replay/dream, prediction, identity dynamics i reasoning istnieje:

1. causal-effect test; albo
2. A/B/ablation; albo
3. jawny status `ADVISORY/OBSERVABILITY_ONLY`.

Jeżeli moduł nie wnosi mierzalnej wartości ponad LLM + context + tools albo deterministic boundary, trafia do v17 debt ledger zamiast automatycznie pozostać canonical.

## 14.7 Rest / Dream

- synthetic/internal;
- no independent tool authority;
- source lineage;
- użyteczność oceniana przez recall/conflict/procedural effect;
- false-memory nie przekracza acceptance threshold;
- brak biologicznego claim o śnie.

## 14.8 Governance

- packaging/provenance/integrity spójne;
- brak open P0/P1 w finalnym scope;
- final SHA ma wymagane zielone CI;
- `master` ma branch protection/ruleset albo jawny równoważny enforcement/zaakceptowany wyjątek;
- architecture debt ledger istnieje;
- active docs/current state odpowiadają finalnemu kodowi;
- historyczne archiwa pozostają nieprzepisane.

## 14.9 Architecture debt ledger

Każda overlapping warstwa self/identity/affect/homeostasis/awareness/reasoning/prediction/rest/memory/model orchestration ma status:

```text
CANONICAL
ADVISORY
COMPATIBILITY
SUPERSEDED
V17_CONSOLIDATION_CANDIDATE
```

**PASS v16.6:** #59 można zamknąć na podstawie dowodów, nie deklaracji roadmapy.

---

# 15. Evidence boundary: deterministic, private i live-model

## Deterministic CI

Bez prywatnych danych i bez obowiązkowego płatnego/cloud modelu:

- contracts/schemas;
- tool and memory authority;
- provenance;
- context selection fixtures;
- model capability negotiation;
- source/recall synthetic regressions;
- Windows + Ubuntu;
- packaging/release checks.

## Private acceptance

Lokalnie, na finalnym artefakcie:

- source fidelity;
- private Recall/multi-turn;
- sensitive boundaries;
- L2/L3 review;
- restart continuity.

## Live-model acceptance

Tylko jeżeli dany model/provider jest faktycznie dostępny. Raport zawiera exact observable model/provider/config. Fixture nie może być przedstawiony jako live proof.

---

# 16. Co świadomie przechodzi do v17.0.0

v17 zaczyna się dopiero po v16.6 evidence i ma charakter **measurement-driven architecture consolidation**.

Zakres warunkowy:

- konsolidacja overlapping affect/self/homeostasis/identity models;
- jeden causal self-state contract;
- jeden bounded context compiler;
- model capability abstraction / portability;
- controlled forgetting i source-aware reconsolidation;
- zaawansowana metacognitive calibration;
- redukcja modułów po ablation;
- retrieval/model-assisted planning tylko po A/B;
- formalny v17 migration/architecture contract.

v17 nie zaczyna się od kolejnych antropomorficznych nazw ani od obowiązkowego custom model training.

Właściciel planu: `../17.0.0-measured-architecture-consolidation/PLAN.md`.

---

# 17. Branch strategy

Planowane linie po bieżącym aktywnym branchu:

```text
upgrade/memory-rebuild-v4-consolidation        # ACTIVE
upgrade/v16.3.26-host-attachment-multimodal-ingress-hardening
upgrade/v16.4.0-polish-nlp-normalization
upgrade/v16.4.1-polish-lexical-resources
upgrade/v16.4.2-nlp-recall-query-interface
upgrade/v16.5.0-final-memory-rebuild
upgrade/v16.5.1-final-memory-packaging-attach
upgrade/v16.5.2-private-recall-baseline
upgrade/v16.6.0-final-convergence
```

Brancha v17 **nie tworzyć przed finalnym v16.6 PASS**.

Nowy release startuje ze świeżego mastera po merge poprzedniego etapu, chyba że użytkownik jawnie kontynuuje istniejący aktywny branch.

Backup/archive/superseded `ahead` branches nie są automatycznym źródłem do merge. Najpierw semantic archaeology / current-gap proof.

---

# 18. Defect loop

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

# 19. Issue map

- `#59` — OPEN do finalnego `ACCEPTED` + v16.6 closure.
- `#189` — OPEN / Memory Rebuild v4 consolidation; nie zastępuje #59.
- `#180` — COMPLETED / persistent active-memory recall E2E; regression contract.
- `#185` — COMPLETED / host finalization gate; regression contract.

---

# 20. Dokumenty powiązane

## Current / project-wide

- `../../project/CURRENT_STATE.md`
- `../../project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`
- `../../project/REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md`
- `../../project/RELEASE_TIMELINE.md`
- `../../project/system-evaluation/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`
- `../../project/system-evaluation/V16_6_TO_V17_0_RESEARCH_UPDATE_2026-09-01.md`

## Active / planned plans

- `../16.3.25.4-memory-rebuild-v4/PLAN.md`
- `../16.3.26-attachment-ingress/PLAN.md`
- `../16.4-to-16.6-cognitive-hardening/PLAN.md`
- `../17.0.0-measured-architecture-consolidation/PLAN.md`

## Runtime reference

- `../../runtime/CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md`
- `../../runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`

## Historical release evidence

- `../../archive/reports/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_HARDENING.md`
- `../../archive/reports/JAZN_V16_3_24_PACKAGE_PROVENANCE_BOOTSTRAP_HARDENING.md`
- `../../archive/reports/JAZN_V16_3_25_MEMORY_REBUILD_SOURCE_UNION_HARDENING.md`
- `../../archive/reports/JAZN_V16_3_25_3_RELEASE_METADATA_SEMANTICS.md`
- `../../archive/plans/`
- `../../archive/roadmaps/`

---

# 21. Research basis for the updated strategy

- OpenAI Harness Engineering — short AGENTS map, structured repository knowledge, feedback loops:  
  https://openai.com/index/harness-engineering/
- OpenAI API — tools, multimodal inputs, agents and evals:  
  https://platform.openai.com/docs/quickstart/  
  https://platform.openai.com/docs/api-reference/evals
- OpenAI Structured Outputs — deterministic schema constraints do not remove semantic model errors:  
  https://openai.com/index/introducing-structured-outputs-in-the-api/
- Anthropic context engineering — finite context, smallest high-signal context:  
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- LongMemEval — explicit long-term memory/retrieval remains necessary beyond long context:  
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- NIST TEVV / agentic evaluation probes — deployment-like evaluation, grounding and audit trail:  
  https://www.nist.gov/artificial-intelligence/ai-research/tevv-athlon-framework-evaluating-ai-systems  
  https://www.nist.gov/programs-projects/building-evaluation-probes-agentic-ai
- OWASP Prompt Injection — external files/web remain untrusted and require least privilege:  
  https://genai.owasp.org/llmrisk/llm01-prompt-injection/

Źródła uzasadniają decyzje projektowe; nie są dowodem, że konkretne capability Jaźni działa. Taki dowód pochodzi z bieżącego kodu/testów/runtime/private acceptance.

---

# 22. Zasada końcowa

```text
CURRENT master 16.3.25.3.6 snapshot
-> ACTIVE 16.3.25.4 Memory Rebuild v4
-> 16.3.26 attachment/multimodal ingress
-> 16.4.x evidence-aware Polish NLP
-> 16.5.x source-aware autobiographical memory acceptance
-> 16.6 final runtime/model-harness/memory/NLP/affect/cognitive/truth convergence
-> v17 measured architecture consolidation
```

Roadmapa jest planem. Status `implemented`, `working`, `verified`, `accepted` i `live` wynika wyłącznie z właściwego poziomu evidence.
