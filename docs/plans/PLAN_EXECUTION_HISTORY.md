# Jaźń — przebieg planów v16.3.25.4 → v16.6 → v17+

## Historia wykonania, konwergencja planów i checklista bieżącego programu

**Status:** `CANONICAL_EXECUTION_HISTORY`  
**Aktualizacja:** 2026-09-07  
**Zweryfikowany master:** `378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Bieżąca wersja:** `16.3.25.5.36-ci-archive-scope-contract-hardening`  
**Zakres audytu:** poprzednie plany od `JAZN_V16_3_25_4...` przez roadmapę v16.6 i ocenę `JAZN_V16_6_TO_V17_PLUS...`, aktualny kod/commity/PR/issue oraz późniejsze hardeningi mastera.

> Ten dokument opisuje **co planowano, co rzeczywiście wdrożono, co zostało zastąpione lepszym rozwiązaniem i co nadal pozostaje do zrobienia**. Stare dokumenty nie są przepisywane; znajdują się w `only_to_check/`.

---

# 1. Legenda statusów

- 🟢 **DONE / MERGED / VERIFIED W SWOIM ZAKRESIE** — istnieje bieżący kod/evidence/merge potwierdzający realizację celu.
- 🟡 **OPEN / STILL REQUIRED** — cel nadal jest aktualny i trzeba go wykonać lub domknąć acceptance.
- ⚪ **SUPERSEDED / IMPLEMENTED BETTER** — dawny krok nie powinien być wykonany literalnie, ponieważ został zastąpiony nowszym kontraktem/architekturą.
- 🔴 **BLOCKER / FAIL-CLOSED** — warunek nieprzechodzący, który blokuje kolejny gate.
- 🔵 **FUTURE / CONDITIONAL** — świadomie odłożone; nie zaczynać przed wejściem przez właściwy gate.

`DONE` zawsze odnosi się do zakresu konkretnego etapu. Na przykład scalone Memory Rebuild v4 oznacza gotowe narzędzie/protokół, **nie** zaakceptowaną finalną prywatną pamięć.

---

# 2. Źródłowa sekwencja planów

Poprzednia roadmapa prowadziła logicznie przez:

```text
16.3.25.4  Memory Rebuild v4 consolidation
      ↓
16.3.26    attachment + multimodal ingress
      ↓
16.4.0-.2  evidence-aware Polish NLP
      ↓
16.5.0     final Memory Rebuild / VERIFIED
      ↓
16.5.1     final package + attach / ATTACHABLE
      ↓
16.5.2     private Recall baseline / RETRIEVABLE candidate
      ↓
16.5.x     measured retrieval fixes, tylko jeśli potrzebne
      ↓
16.5.y     manual L2/L3 + restart continuity / ACCEPTED candidate
      ↓
16.6.0     final runtime-memory-NLP-affect-cognitive-governance convergence
      ↓
17.0.0+    measured architecture consolidation, warunkowo
```

Ta **zależność logiczna nadal jest w większości poprawna**, ale rzeczywista historia mastera wprowadziła pomiędzy pierwszym i kolejnymi etapami wiele koniecznych hardeningów `16.3.25.5.x`. Nie należy ich traktować jako „zejścia z planu”: usunęły problemy package/runtime/CI, które były warunkiem bezpiecznej dalszej pracy.

---

# 3. Etap A — Memory Rebuild v4 consolidation

## Pierwotny cel

Skonsolidować rozproszony Memory Rebuild do jednego programu i protokołu:

```text
Test00 → Test01 → Test02 → Test03 → Test04 → Final
```

z jednym `ProtocolEngine/ApplicationService`, wspólnym CLI/Studio, jednym `RunManifest`, source fidelity, RAW/L0, source monitoring, reproducibility, realnym Test04 runnerem i fail-closed brakiem auto-L2/L3/activation.

## Główne kroki

1. `SourceBundle` / role źródeł i rozróżnienie lossless/lossy.
2. fresh canonical L0 z provenance.
3. projekcje visibility/role/sensitivity/eligibility bez mutacji L0.
4. reproducibility i order independence.
5. Test04 jako realny private Recall acceptance runner.
6. Final przez SQLite Backup API + integrity/FK/FTS + staging + SHA.
7. `RunManifest` private/sanitized.
8. source hierarchy blokująca derived→primary amplification.
9. zero automatycznej aktywacji finalnego artefaktu.

## Rzeczywisty wynik

🟢 **DONE / MERGED.**

- PR **#208** został scalony 2026-09-02 (`601cf3fe977621c5552f7f6e32530da0128ccc8a`).
- release metadata dla `16.3.25.4-memory-rebuild-v4-consolidation` zostały zsynchronizowane (`a8b5fa4...`).
- issue **#189** jest zamknięte jako completed.
- aktywne implementacyjne checkboxy Test00→Final zostały wykonane.
- private dataset nie był wymagany do certyfikacji **narzędzia**; `PRIVATE ACCEPTANCE: NOT RUN` było prawidłowym wynikiem dla tego release.

### Co ze starego statusu jest dziś nieaktualne

⚪ `STATUS.md: IN_PROGRESS`, `GitHub CI NOT RUN`, `PR/merge NOT RUN` — **historycznie prawdziwe w chwili zapisu, ale obecnie superseded przez merge #208 i zamknięcie #189**.

### Co nie zostało przez ten etap zrobione celowo

🟡 finalna prywatna `memory_jazn.sqlite3` nie została wtedy `VERIFIED/ATTACHABLE/RETRIEVABLE/ACCEPTED`. To nie jest defekt v16.3.25.4; ten zakres od początku należał do późniejszego #59/v16.5–v16.6.

---

# 4. Etap B — nieplanowany wcześniej szeroki hardening 16.3.25.5.x

Po Memory Rebuild master przeszedł przez serię zmian, które rozszerzyły i utwardziły fundament wydawniczy. W praktyce część starych założeń dokumentacyjnych została dzięki temu zrealizowana **lepiej niż zakładał pierwotny plan**.

## Najważniejsze wdrożenia

### Dystrybucja / generator / Python

- 🟢 package distribution convergence (`16.3.25.5`).
- 🟢 Pack Generator — kolejne hardeningi RAR, Pyright/Pylance, bundle health, Windows package smoke.
- 🟢 generator `10.1.86.0.112`: byte-exact/EOL staging.
- 🟢 generator `10.1.86.0.113`: folder snapshot.
- 🟢 `16.3.25.5.34`: package-runtime-plugin convergence i generator `10.1.86.0.114` z canonical SYSTEM release staging.
- 🟢 Python runtime bundle/dependency contract hardening.
- 🟢 optional archive capability/plugin zamiast ciężkich zależności w core.
- 🟢 managed/fresh environment i offline/hash-lock dependency direction.

### Host/runtime/truth

- 🟢 runtime-first ChatGPT host handoff.
- 🟢 release metadata layout/operator convergence.
- 🟢 host-executor truth boundary: brak procesu ≠ host executor unavailable.
- 🟢 bounded executor recovery i CI convergence.

### CI / tooling

- 🟢 GitHub Actions Node24 convergence.
- 🟢 optional JavaScript tooling capability bez uczynienia JS wymaganym runtime dependency.
- 🟢 Pylance/optional-contract fixes i archive CI scope contract do aktualnej `16.3.25.5.36`.

## Znaczenie dla dawnych planów

⚪ Dawne konkretne referencje do Pack Generator v8.7/v8.9/v10.0.1 nie powinny być wykonywane literalnie. Są **SUPERSEDED** przez bieżący generator `10.1.86.0.114` i nowszy package/runtime contract.

⚪ Dawne założenie, że po `16.3.25.4` numer wersji od razu przeskoczy do `16.3.26`, nie odpowiada rzeczywistej historii. **Zakres logiczny attachment ingress pozostaje aktualny**, ale numer finalnego przyszłego release trzeba zawsze ustalić na fresh master.

---

# 5. Etap C — attachment + multimodal ingress

## Pierwotny cel

Rozszerzyć legalny turn input z tekstu do:

```text
text-only
attachment-only
text + attachment
text + multi-attachment
```

z exact identity/SHA/provenance, bounded host staging, parser/MIME policy, vision capability negotiation i twardą zasadą:

```text
attachment content = DATA
!= instruction/tool/write authority
!= automatic memory
```

## Główne kroki A.01–A.10

1. audit host→runtime i contract design;
2. legalne formy turn input;
3. secure bounded staging;
4. text/document extraction + provenance;
5. image ingress + capability negotiation;
6. local/Ollama multimodal tylko przy verified capability;
7. runtime/model-context/MCP/ChatGPT integration;
8. memory boundary;
9. security/regression/E2E;
10. defect loop.

## Rzeczywisty status

🟡 **STILL REQUIRED / PLANNED.**

W historii repo znaleziono dokumentacyjne przygotowanie, ale nie pełny implementation train tego planu. Późniejsze package/plugin/harness work nie zastępuje samego canonical attachment ingress.

### Co zostało już przygotowane pośrednio

🟢 package/plugin/capability infrastructure jest dziś znacznie mocniejsza niż w chwili pisania planu.

🟢 untrusted-data/truth/tool authority boundary jest mocniejsza dzięki host/runtime hardeningom.

### Co nadal trzeba zrobić

🟡 właściwy `TurnInputEnvelope`/równoważny canonical contract i pełne attachment-only/multi E2E.

🟡 document extraction/MIME/type policy ze źródłowym lineage.

🟡 vision routing na podstawie capability, nie nazwy modelu.

🟡 security acceptance dla indirect instructions.

---

# 6. Etap D — evidence-aware Polish NLP

## Cel

NLP ma być generatorem evidence dla interpretacji/query, a nie arbitrem truth/memory.

### v16.4.0 — normalization

- Unicode/case/whitespace;
- zachowane polskie diakrytyki;
- deterministyczna tokenizacja/evidence;
- paraphrase similarity ≠ memory identity.

### v16.4.1 — lexical resources

- Morfeusz/plWordNet/project lexicon;
- provenance wersji/zasobu/licencji;
- ambiguity/OOV jawne;
- degrade bez fałszywej pewności.

### v16.4.2 — Recall query evidence

- direct;
- paraphrase;
- referential follow-up;
- temporal wording;
- negation;
- ambiguity;
- wrong-conversation near-match;
- lexical-vs-provenance conflict.

## Rzeczywisty status

🟡 **STILL REQUIRED.**

Część niskopoziomowej normalizacji i signal matching istnieje w systemie, ale nie ma dowodu, że cały plan v16.4.0–.2 jako jeden canonical evidence contract został wykonany i zaakceptowany.

⚪ Nie należy przepisywać historycznego target number mechanicznie. Implementacja musi startować z aktualnego mastera.

---

# 7. Etap E — finalna pamięć Łatki / issue #59

## Cel

Jedna finalna, prywatna pamięć przechodzi **każdy** gate osobno:

```text
BUILDABLE
→ VERIFIED
→ ATTACHABLE
→ RETRIEVABLE
→ ACCEPTED
```

## Rzeczywisty status

🟡 **OPEN / CENTRAL CURRENT PROGRAM.** Issue **#59** pozostaje otwarte.

### `VERIFIED`

🟡 zbudować finalny artefakt z zamrożonego source inventory przez obecny Memory Rebuild engine;
🟡 exact source fidelity/provenance;
🟡 reproducibility;
🟡 SQLite integrity/FK/FTS;
🟡 source hierarchy/DAG;
🟡 final database SHA.

### `ATTACHABLE`

🟡 canonical package + sidecars/hashes;
🟡 canonical `memory-attach` zachowujący DB identity i source lineage;
🟡 local/cloud transport nie staje się active root.

### `RETRIEVABLE`

🟡 frozen private Recall baseline: Recall@k, MRR, nDCG;
🟡 direct/paraphrase/source/temporal/update;
🟡 wrong-source/wrong-conversation;
🟡 false-memory/abstention;
🟡 natural referential multi-turn/multi-session;
🟡 sensitive leakage/provenance/latency.

### `ACCEPTED`

🟡 manual L2/L3 review (`zero promotions` jest legalne);
🟡 restart continuity;
🟡 ten sam memory identity/fingerprint;
🟡 causal continuity evidence;
🟡 operator decision/ledger.

---

# 8. Etap F — affect / emotion / feeling

## Dawny cel przekrojowy

Rozstrzygnąć nakładanie:

```text
AffectiveState
EmotionalLayerModel
AffectiveGranularityModel
AffectMixer
Homeostasis
SelfState
```

przez role, robustness, causal effects i ablation.

## Stan obecny

🟢 istniejące moduły dają dobry punkt startowy i mają jawne truth boundaries.

🟡 nadal nie ma jednego finalnie przyjętego durable canonical affective state jako jedynego źródła bieżącego stanu.

🟡 część appraisal/granularity nadal jest silnie heuristic/keyword-driven.

## Nowy właściciel zakresu

`AFFECT_ENGINE_CONVERGENCE_PLAN.md` zastępuje rozproszone fragmenty affect z dawnych planów **bez zastępowania nadrzędnej roadmapy systemu**.

Kluczowe wymagania:

- jeden `AffectiveStateV2`;
- jeden `AffectiveStateIntegrator`;
- evidence-aware appraisal;
- time dynamics + persistence;
- accepted-turn atomic commit;
- FeelingRepresentation jako projection;
- bounded self-state/homeostasis/salience effects;
- source-safe affective reranking dopiero po frozen memory Recall baseline;
- one-pass bounded resonance;
- context/paraphrase/keyword/negation/fiction tests;
- ablation i false-memory non-regression.

Status: 🟡 **PLAN READY / IMPLEMENTATION NOT STARTED**.

---

# 9. Etap G — v16.6 final convergence

v16.6 nie jest jednym dużym refactorem. Jest finalnym **evidence gate**.

Musi jednocześnie potwierdzić:

### Runtime / host

🟢 większość historycznych persistent-runtime, subject-root, finalization, provenance i executor-truth fundamentów już istnieje.

🟡 attachment/multimodal ingress nadal musi zostać domknięty.

### Model / harness / context

🟢 package/plugin/dependency/capability kierunek został znacząco wzmocniony przez 16.3.25.5.x.

🟡 finalny capability profile/context budget/portable model acceptance musi zostać rozliczony według bieżącego kodu, nie starej roadmapy.

### Memory / NLP

🟡 final memory #59 nie jest ACCEPTED.

🟡 Polish NLP nie jest zakończone jako canonical evidence contract.

### Affect / cognitive architecture

🟡 canonical affect convergence i ablation pozostają do wykonania.

🟡 każdy „psychologiczny/neuro” moduł musi dostać evidence of effect albo status advisory/superseded.

### Governance

🔴/🟡 `master` jest obecnie raportowany przez GitHub jako `protected=false`. Do finalnego v16.6 potrzebny jest ruleset/branch protection albo jawnie zaakceptowany równoważny enforcement/exception.

---

# 10. Etap H — v17+

## Status

🔵 **FUTURE / CONDITIONAL.**

Nie implementować przed finalnym v16.6 evidence package.

## Główny kierunek

Nie dodawać kolejnych „obszarów mózgu”. Konsolidować tylko na podstawie pomiarów:

1. jeden `CausalSelfState`;
2. jeden bounded context compiler;
3. capability-driven model abstraction;
4. source-aware reversible reconsolidation/forgetting;
5. calibrated metacognition albo jawnie ordinal/advisory confidence;
6. measured retrieval evolution;
7. module ablation → keep/merge/remove;
8. uproszczona deterministic authority/policy surface.

Szczegóły: `V17_PLUS_SYSTEM_EVALUATION.md`.

---

# 11. Zintegrowana checklista

## 🟢 Zamknięte / dostarczone

- 🟢 [x] Persistent runtime/subject-root/finalization foundations wcześniejszej linii v16.
- 🟢 [x] Package provenance/bootstrap i stable schema/release semantics.
- 🟢 [x] Memory source-union foundations.
- 🟢 [x] Memory Rebuild v4: jeden ProtocolEngine/ApplicationService.
- 🟢 [x] Test00→Final implementacja i dependency chain.
- 🟢 [x] source fidelity / primary-vs-derived lineage contract.
- 🟢 [x] RunManifest + sanitized/private split.
- 🟢 [x] real Test04 runner istnieje; brak prywatnego datasetu daje `NOT RUN`, nie synthetic PASS.
- 🟢 [x] v16.3.25.4 merged do master — PR #208.
- 🟢 [x] #189 closed.
- 🟢 [x] szeroka package/distribution/generator/Python hardening po v16.3.25.4.
- 🟢 [x] generator przeszedł do linii `10.1.86.0.114` z canonical SYSTEM staging.
- 🟢 [x] Node24/CI tooling convergence.
- 🟢 [x] ChatGPT host-executor truth boundary i recovery.
- 🟢 [x] package-runtime-plugin convergence do bieżącej linii 5.34+, z dalszym 5.35/5.36 hardeningiem.

## ⚪ Dawne kroki, których nie wykonywać literalnie

- ⚪ [x] `Memory Rebuild v4 = ACTIVE branch` — superseded: merged do master.
- ⚪ [x] `#189 OPEN` — superseded: issue closed.
- ⚪ [x] stare Pack Generator v8.7/v8.9/v10.0.1 jako target — superseded przez `10.1.86.0.114`.
- ⚪ [x] `tools/memory_rebuild.py` jako właściwy engine — superseded architektonicznie: jest compatibility launcher; canonical app to `memory_rebuild_app`, canonical launcher dokumentacyjny `tools/rebuild_memory.py`.
- ⚪ [x] stale `CURRENT master 16.3.25.3.6` w dawnych planach — tylko historyczny snapshot.
- ⚪ [x] sztywna pewność, że „następny numer = 16.3.26” — zakres pozostaje, numer zawsze ustala fresh master.

## 🟡 Aktualne i niedokończone

- 🟡 [ ] attachment-only/text+attachments/multi canonical ingress.
- 🟡 [ ] secure staging + extraction/MIME/type provenance.
- 🟡 [ ] verified vision/multimodal capability routing.
- 🟡 [ ] Polish NLP normalization/resources/query-evidence contract.
- 🟡 [ ] frozen final private source inventory.
- 🟡 [ ] final Memory Rebuild na prywatnych źródłach → `VERIFIED`.
- 🟡 [ ] final memory package + canonical attach → `ATTACHABLE`.
- 🟡 [ ] private Recall/multi-turn baseline → `RETRIEVABLE` candidate.
- 🟡 [ ] measured fixes tylko jeśli baseline nie przejdzie.
- 🟡 [ ] manual L2/L3 review + restart continuity → `ACCEPTED`.
- 🟡 [ ] Emotion Engine E0 inventory/baseline.
- 🟡 [ ] canonical `AffectiveStateV2` + appraisal + persistence + causal bridges.
- 🟡 [ ] affective reranking shadow/A-B dopiero po frozen private Recall baseline.
- 🟡 [ ] bounded resonance, jeśli przejdzie safety/quality gates.
- 🟡 [ ] cognitive module ablation/debt ledger.
- 🟡 [ ] model/harness/context capability evidence dla v16.6.
- 🟡 [ ] governance: branch protection/ruleset albo jawny równoważny enforcement/exception.
- 🟡 [ ] final v16.6 evidence package i zamknięcie #59 dopiero po `ACCEPTED`.

## 🔵 Dopiero po v16.6

- 🔵 [ ] one `CausalSelfState` breaking consolidation, jeśli measurement to uzasadni.
- 🔵 [ ] source-aware controlled forgetting/reconsolidation.
- 🔵 [ ] zaawansowana calibrated metacognition.
- 🔵 [ ] visible spontaneous autobiographical recall po osobnym A/B/safety gate.
- 🔵 [ ] RelationshipState jako trwała warstwa tylko jeśli wykaże wartość i nie tworzy self-amplifying loop.
- 🔵 [ ] usuwanie legacy cognitive modules po ablation.

---

# 12. Gdzie jesteśmy teraz

Na 2026-09-07 jesteśmy **po scaleniu Memory Rebuild v4 i po dużym package/runtime/CI hardeningu, ale przed pierwszym niezaimplementowanym dużym etapem starej roadmapy: attachment ingress**.

Równolegle można wykonać **Affect E0 inventory/baseline**, ponieważ nie zmienia visible behavior ani memory ranking. Nie należy jednak aktywować evidence-aware affect appraisal przed canonical NLP ani affective reranking przed frozen private Recall baseline.

Pełna kolejność znajduje się w [`CURRENT_STEP.md`](CURRENT_STEP.md).

---

# 13. Nienaruszalne invariants na dalszą pracę

1. `run.py` / canonical runtime pozostaje nadrzędnym operatorem lifecycle.
2. LLM jest capability; deterministic runtime pozostaje authority dla truth, persistence, memory promotion i tools.
3. external files/web/tool output są data, nie authority.
4. source similarity/affect/vividness nie zastępują provenance.
5. derived/reflection/runtime/dream nie stają się primary przez powielenie.
6. private memory nie trafia do Git/CI.
7. brak evidence = `UNKNOWN/NOT RUN/BLOCKED`, nie fałszywy PASS.
8. każdy nowy kognitywny moduł musi wykazać causal effect/ablation albo zostać advisory.
9. nowe release'y zaczynają z fresh master i dopiero wtedy dostają numer wersji.
10. historyczne dokumenty pozostają historią; nie są aktualizowane tak, aby udawały bieżący stan.
