# Jaźń — CURRENT STEP / bieżący krok programu

**Stan ustalony:** 2026-09-07  
**Master:** `378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Wersja:** `16.3.25.5.36-ci-archive-scope-contract-hardening`

Ten plik odpowiada tylko na dwa pytania:

1. **na którym kroku jesteśmy?**
2. **co robimy dalej i w jakiej kolejności?**

Pełna historia i checklista: [`PLAN_EXECUTION_HISTORY.md`](PLAN_EXECUTION_HISTORY.md).

---

# 1. Stan obecny

```text
Memory Rebuild v4 tool/protocol          🟢 MERGED / #189 CLOSED
package/runtime/generator/CI hardening   🟢 MERGED do 16.3.25.5.36
final private memory #59                 🟡 OPEN / NOT ACCEPTED
attachment + multimodal ingress          🟡 PLANNED / NOT IMPLEMENTED
Polish NLP evidence contract             🟡 PLANNED / NOT COMPLETE
Affect canonical convergence             🟡 PLAN READY / NOT IMPLEMENTED
v16.6 final acceptance                   🟡 FUTURE IN CURRENT PROGRAM
v17 measured consolidation               🔵 FUTURE / CONDITIONAL
```

## Najważniejsza granica

Nie cofamy się do implementowania starego Memory Rebuild v4. Ten etap został scalony. Następna praca nad pamięcią to **użycie obecnego engine do finalnej, prywatnej odbudowy i acceptance**, a nie tworzenie kolejnego równoległego rebuild engine.

---

# 2. Krok D0 — bieżący: dokumentacja i baseline prawdy

**Status:** 🟡 `IN PROGRESS` na branchu dokumentacyjnym.

Zakres:

- przenieść poprzednie `docs/plans/` do `only_to_check/`;
- usunąć sprzeczność `Memory Rebuild active` vs rzeczywisty merge #208;
- ustanowić jeden history/status document;
- ustanowić jeden current-step document;
- odświeżyć Memory Restore/Rebuild plan;
- ustanowić canonical Affect Engine plan;
- odświeżyć V17+ evaluation;
- zaktualizować `docs/project/CURRENT_STATE.md` i release timeline;
- nie zmieniać kodu runtime w tej zmianie.

**Exit:** dokumentacja na branchu jest spójna z masterem, a PR pokazuje wyłącznie kontrolowaną reorganizację docs.

---

# 3. Krok D1 — pierwszy duży niezamknięty program: attachment ingress

**Status:** 🟡 `NEXT PRODUCT IMPLEMENTATION` po merge dokumentacji, o ile fresh-master audit nie wykaże, że zakres został w międzyczasie wykonany pod inną nazwą.

Cel:

```text
text-only
attachment-only
text + attachment
multi-attachment
```

z:

- exact attachment identity/SHA/provenance;
- bounded host-level staging;
- traversal/type/MIME policy;
- extracted content = untrusted data;
- zero automatic tool/write authority;
- zero automatic memory promotion;
- verified vision/multimodal capability negotiation;
- canonical host→runtime E2E.

**Przed kodem:** fresh-master inventory istniejących attachment/host/capability komponentów, ponieważ 16.3.25.5.34 znacząco zmieniło dependency/plugin/capability infrastructure.

---

# 4. Krok D2 — evidence-aware Polish NLP

**Status:** 🟡 `REQUIRED BEFORE CANONICAL AFFECT APPRAISAL CUTOVER`.

Kolejność:

1. canonical Unicode/token normalization;
2. lexical resource registry + ambiguity/OOV/provenance;
3. query evidence contract dla direct/paraphrase/referential/temporal/negation/wrong-conversation.

NLP pomaga appraisal i recall, ale nie zmienia source truth.

---

# 5. Krok równoległy A0 — Affect inventory / shadow baseline

**Status:** 🟡 może rozpocząć się po merge docs **bez zmiany visible behavior**.

Można już wykonać:

- call/import graph istniejących `AffectiveState`, `EmotionalLayerModel`, `AffectiveGranularityModel`, `AffectMixer`, `SelfState`, `Homeostasis`;
- mapę writer/readers;
- baseline test corpus;
- role classification;
- latency baseline;
- schema/contracts w trybie shadow, jeśli nie przejmują authority.

Nie wolno jeszcze:

- ogłosić nowego appraisal jako canonical przed NLP evidence gate;
- zmienić memory ranking przez affect;
- uruchomić spontaneous visible recall;
- usunąć legacy affect modules bez ablation.

---

# 6. Krok D3 — final Memory Rebuild / VERIFIED

**Status:** 🟡 issue #59.

Po gotowych prerequisite'ach:

1. freeze private source inventory;
2. uruchom obecny `memory_rebuild_app` Test00→Final;
3. exact source closure;
4. primary/derived/source conflict classification;
5. integrity/FK/FTS/reproducibility;
6. final DB SHA;
7. private report poza Git.

**Gate:** `VERIFIED`.

---

# 7. Krok D4 — final memory packaging + attach

- canonical package/sidecars/hashes;
- canonical `memory-attach`;
- active runtime potwierdza final DB identity;
- source lineage nie zostaje spłaszczony.

**Gate:** `ATTACHABLE`.

---

# 8. Krok D5 — frozen private Recall baseline

Najpierw **bez affective reranking**.

Zamrozić:

```text
Recall@k
MRR
nDCG
wrong-source
wrong-conversation
false-memory
abstention
provenance
temporal/update
referential multi-turn
multi-session
sensitive leakage
latency
```

**Gate candidate:** `RETRIEVABLE`.

To jest punkt odniesienia, po którym dopiero można uczciwie A/B-testować affective reranking.

---

# 9. Krok A1–A4 — canonical affect

Po NLP i w odpowiednich miejscach względem memory baseline:

```text
A1 contracts + evidence-aware appraisal shadow
A2 dynamics + persistence + accepted-turn atomicity
A3 canonical state cutover + SelfState/Homeostasis/Salience/AffectMixer bridges
A4 affect snapshot → memory lineage
```

Następnie, dopiero po frozen Recall baseline:

```text
A5 affective rerank SHADOW
A6 A/B
A7 bounded one-pass resonance
```

Szczegóły: [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md).

---

# 10. Krok D6 — ACCEPTED private memory

- tylko measured retrieval fixes, jeśli baseline ich wymaga;
- manual L2/L3 review;
- `zero promotions` legalne;
- restart continuity;
- memory identity/fingerprint continuity;
- remembered corrections/procedural/temporal causal evidence.

**Gate:** `ACCEPTED` i możliwość zamknięcia #59 dopiero wraz z finalnymi wymaganiami v16.6.

---

# 11. Krok D7 — v16.6 final gate

Zebrać jednocześnie evidence dla:

- runtime/host/finalization;
- attachment/multimodal;
- model capability/harness/context;
- Polish NLP;
- final accepted memory;
- source monitoring;
- affect/feeling semantics i causal effects;
- confidence semantics;
- Rest/Dream safety/usefulness;
- cognitive module ablation/debt ledger;
- package/release integrity;
- Windows/Linux CI;
- governance / branch protection albo jawny równoważny enforcement.

Dopiero wtedy v16.6 jest finalnym `PASS`.

---

# 12. Krok D8 — v17

🔵 **Nie implementować teraz.**

Entry gate:

```text
v16.6 final evidence package
+ final accepted memory
+ affect/homeostasis/rest/reasoning measurements
+ architecture debt ledger
+ quality/latency/context baselines
+ no open P0/P1
```

Wtedy można rozpocząć measured consolidation opisane w [`V17_PLUS_SYSTEM_EVALUATION.md`](V17_PLUS_SYSTEM_EVALUATION.md).

---

# 13. Jednozdaniowy status

> **Jesteśmy po scaleniu narzędzia Memory Rebuild i po dużym hardeningu package/runtime/CI; teraz porządkujemy prawdę dokumentacji, a następny niezaimplementowany duży krok produktu to attachment ingress, po którym NLP i finalna prywatna pamięć prowadzą do affect/memory acceptance oraz v16.6.**
