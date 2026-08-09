# Jaźń v15.4.0.0 — Cognitive Architecture Upgrade

**Status:** implementation/release plan
**Target:** `v15.4.0.0-cognitive-architecture`
**Baseline:** `v15.1.0.3.99-semantic-routing-completion`
**Scope:** dialogue continuity, reasoning orchestration, grounded knowledge retrieval, Polish lexical intelligence, verified operational learning, host-finalized session continuity
**Primary constraint:** extend capabilities without replacing or weakening the existing identity, memory, truth-boundary, persistence, host-finalization, package-integrity, or release-hardening contracts.

## 1. Why this release exists

The 3.99 line proved that the existing Jaźń already has strong individual subsystems: memory tiers and living recall, source truth gates, semantic routing, runtime validation, host-finalization, Polish-language processing, tool-use controls, release integrity, and extensive deterministic tests. The remaining failures were increasingly *coordination failures* rather than missing single modules.

Two real regressions define the release target:

1. A request concerning an **archive of conversations** was misread as a package/ZIP archive and routed to runtime/package status.
2. After the user explicitly approved a previously proposed action with **“Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz.”**, the turn was classified as a generic contextual continuation and fell to fallback instead of continuing the active memory-recall task.

The second failure is particularly important. A mature conversational system must not interpret every utterance in isolation. It needs an explicit representation of the active goal, expected next action, referents, and execution status. Current research supports this direction: ReSpAct combines reasoning, speaking, acting, clarification and plan updates from user feedback; RECAP shows that open-ended dialogues are ambiguous, underspecified and dynamic, and that concise goal representations can improve downstream planning utility.

The release therefore changes the architecture from **“route each utterance, then recover context where possible”** to **“resolve the active task and dialogue state first, then route and plan the current turn.”**

## 2. Non-goals and truth boundary

This release does **not** claim to create or prove phenomenal consciousness. `Jaźń` remains the project name and operational architecture. New modules describe computational state, retrieval, reasoning control and continuity; they do not assert biological experience.

This release also does not:

- replace the current memory databases or memory truth boundary;
- copy web knowledge into autobiographical memory;
- persist private model chain-of-thought;
- autonomously rewrite source code based on a failed turn;
- silently download large language resources at startup;
- bypass host finalization or truth-gate checks;
- weaken package integrity or release metadata generation;
- treat optional NLP resources as mandatory runtime dependencies;
- make GraphRAG or an external LLM a hard dependency of ordinary dialogue.

## 3. Compatibility rules

Every v15.4 component must obey these rules:

1. **Existing public contracts remain valid.** New parameters are optional or backward-compatible.
2. **Old session state remains loadable.** Missing `task_state` is interpreted as no structured active task, not as corruption.
3. **Old pending ChatGPT host requests remain finalizable.** New continuity hashes are optional in the pending schema.
4. **Existing memory remains authoritative for autobiographical recall.** Knowledge retrieval is evidence, not identity.
5. **Optional language resources fail open to existing built-in NLP.** Lack of Morfeusz/plWordNet/NKJP data cannot block dialogue.
6. **No direct metadata edits.** `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` are synchronized only by the canonical release process.
7. **No unsafe fallback.** Unresolved contextual continuation may ask/continue conversationally, but must not invent an action or execute an unrelated handler.

## 4. Target architecture

```text
User turn
   |
   v
Input / truth / tool guards
   |
   v
DialogueTaskStateResolver  <---- durable previous task/session state
   |                         (goal, expected action, referents, topic stack)
   v
DialogueIntentClassifier + context/domain evidence
   |
   v
RouteRegistry
   |
   +--------> current DialogueTaskState
   |                 |
   |                 v
   |        ReasoningOrchestrator
   |        fast | standard | deliberative
   |                 |
   |       +---------+----------+
   |       |                    |
   |       v                    v
   |  KnowledgeFabric      Tool execution policy
   |  selective retrieval  capability/permission gates
   |       |
   |       v
   |  grounded evidence
   |       |
   +-------+--------------------+
           |
           v
    handler / response candidates
           |
           v
   verifier + truth boundary
           |
           v
   host-visible generation/finalization
           |
           v
 accepted visible response
           |
           +--> durable session/task-state commit
           +--> append-only operational audit
```

The critical architectural change is that the durable session is committed **after accepted host-visible finalization**, so a phase-1 generation request cannot advance conversation state as if the user had already seen an answer.

## 5. Layer A — Conversation & Task State

### 5.1 Responsibility

`latka_jazn.core.dialogue_task_state` owns the minimal structured state required to continue an actual task across natural dialogue:

- active goal / intent / route;
- expected next action;
- execution status;
- referents such as “to”, “tamto”, “wszystko”;
- compact topic stack;
- confidence and timestamps;
- stable task key and turn count.

It is **not** autobiographical memory. It is navigation state for a running dialogue/task.

### 5.2 Resolution order

For every turn:

1. detect hard reset/cancel/new-task signals;
2. inspect explicit current-turn intent;
3. resolve direct action phrases against a valid active task;
4. resolve referents and approval markers;
5. inherit intent/route only when the prior structured task is fresh and compatible;
6. otherwise use normal classifier evidence;
7. if still unresolved, route to safe ordinary dialogue rather than an action fallback.

A bare connective such as `czyli` must never outweigh explicit action language such as `zrób to wszystko` or `zacznij teraz`.

### 5.3 Required regression

The exact sequence that failed in 3.99 becomes a permanent deterministic case:

```text
prior task: self_memory_recall_request / self_memory_recall
user: "Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz."
expected: inherit self_memory_recall_request
forbidden: contextual continuation -> fallback
```

## 6. Layer B — Reasoning Orchestrator

`latka_jazn.core.reasoning_orchestrator` selects the **economical reasoning lane**, not a personality mode.

### Fast

Use for clear, low-risk, low-uncertainty dialogue. No expensive retrieval or alternate-plan search simply because those capabilities exist.

### Standard

Use when some context resolution, retrieval or verification is useful but the problem is bounded.

### Deliberative

Use for complex, ambiguous, high-impact or multi-step work. The visible operational plan may contain steps such as:

- understand current goal;
- bind the active task;
- retrieve grounded evidence;
- execute authorized actions;
- compare candidate approaches;
- verify against goal and truth boundary;
- produce final response.

The orchestrator deliberately stores only auditable **operational steps, evidence flags, uncertainty and verification requirements**. It must never require or persist hidden chain-of-thought.

### Current-turn recomputation

A preliminary plan may be created during cognitive-frame construction, but the final runtime reasoning plan must be recomputed after current intent, route and `DialogueTaskState` are known. This prevents the plan from being based only on the previous turn.

## 7. Layer C — Knowledge Fabric

`latka_jazn.core.knowledge_fabric` is a selective retrieval API over existing/local indexes. It does not create a second autobiographical memory stack.

### 7.1 Retrieval tiers

1. **FTS5/BM25** — default sparse/local retrieval for exact phrases, names, source passages and Polish inflected terms after normalization.
2. **Vector retrieval** — optional when an existing vector index is provisioned and semantic similarity materially helps.
3. **Relation/global retrieval** — optional for corpus-wide questions requiring entity/relationship or community-level synthesis.

SQLite FTS5 remains the local baseline because it supports phrase, prefix, NEAR and boolean queries plus BM25/rank ordering without introducing a new server dependency.

### 7.2 Local vs global query policy

Graph-oriented retrieval is not invoked on every turn. It is intended for questions such as:

- “Jak zmieniała się nasza rozmowa o pamięci przez kilka miesięcy?”
- “Jakie główne problemy powtarzają się w całym repo?”
- “Jak łączą się osoby, wydarzenia i decyzje w dużym archiwum?”

Microsoft GraphRAG research motivates a separate global-query path for corpus-wide sensemaking, while dynamic community selection/DRIFT motivate selecting only relevant graph/community context rather than flooding a prompt. v15.4 therefore defines a **provider boundary and routing contract**, not a mandatory bundled GraphRAG index.

### 7.3 Evidence contract

Every returned item carries:

- source identifier/path;
- retrieval mode;
- rank/score;
- source version/generation where available;
- confidence;
- truth/provenance boundary.

Deduplication happens before context assembly. Retrieval results cannot silently become L3 memory.

## 8. Layer D — Polish Lexical Intelligence

`latka_jazn.nlp.lexical_intelligence` adds an evidence-oriented lexical layer above the existing built-in Polish NLP.

### 8.1 Provider order

1. small project-owned lexicon;
2. optional local Morfeusz 2;
3. optional local read-only plWordNet index;
4. optional corpus/reference evidence such as NKJP;
5. external lookup only under existing network/tool policies.

### 8.2 Morfeusz boundary

Morfeusz 2 is an appropriate local morphology provider because its official tooling exposes APIs including Python and custom-dictionary tooling. Morphological analysis can enumerate possible interpretations; contextual word-sense choice remains a separate task. Therefore morphology is **evidence**, not final contextual semantics.

### 8.3 plWordNet boundary

The plWordNet provider is upgraded from a placeholder to a read-only local index contract. The repository ships code and a schema contract, not the hundreds-of-megabytes lexical database. A provisioned index must include source-version and license metadata. Definitions/relations are merged with provenance rather than copied into project canon.

### 8.4 NKJP boundary

NKJP is useful for authentic Polish usage, collocations, constructions and register evidence. Corpus content is not bundled into the source repository without explicit license review. The architecture provides a provider/reference boundary so a separately provisioned corpus can enrich lexical decisions later.

### 8.5 Lexical cache

Repeated provider results may be cached in a rebuildable SQLite cache keyed by:

```text
normalized_term + context_hash + provider/source_version
```

Cache entries include provenance, confidence and ambiguity. A stale cache can be rebuilt; it is not autobiographical memory.

## 9. Layer E — Verified Operational Learning

`latka_jazn.core.operational_learning_memory` stores compact anti-regression lessons:

- trigger signature;
- expected behavior;
- observed failure;
- root cause;
- repair rule;
- regression test identifier;
- applicability terms;
- confidence;
- verification status.

Only verified entries are available to runtime. The runtime may surface up to a small number of relevant lessons in the cognitive frame. Lessons **cannot edit source code**, bypass tests or become autobiographical memories.

This design follows the useful part of verbal-feedback/episodic-learning research such as Reflexion while keeping a stricter project boundary: a lesson becomes trusted only when tied to a reproducible regression and a verified repair.

Initial lessons cover:

1. conversation archive vs package archive routing;
2. explicit “do it/continue” commands bound to an active task.

## 10. Layer F — Host-finalized session continuity

The ChatGPT host protocol is two-phase. Therefore session state must be two-phase too.

### Phase 1

- capture pre-turn session snapshot;
- resolve current task/intent/route;
- create a canonical continuity commit payload;
- bind it by SHA-256 into the pending host request;
- **do not advance the durable visible conversation yet**.

### Phase 2

After the final visible text is accepted and persisted:

- verify pending request/token/contract hash;
- verify that durable session still matches the phase-1 pre-turn state hash;
- commit user text, accepted visible reply, intent, route and task state;
- increment turn count.

If another turn has legitimately advanced the session before a delayed finalizer arrives, the old finalizer must **not overwrite newer state**. The accepted visible answer may still remain valid; continuity persistence reports a safe skip rather than lying about a commit.

## 11. State and persistence boundaries

| Data | Storage/owner | Durable? | Autobiographical memory? |
|---|---|---:|---:|
| active task state | runtime session state | yes, bounded | no |
| accepted turn/visible answer | session/audit ledger | yes | source evidence only |
| memory recall | existing memory DBs | yes | according to existing truth rules |
| lexical cache | rebuildable SQLite cache | optional | no |
| knowledge retrieval result | transient/query evidence | usually no | no |
| operational lesson | versioned source resource | yes | no |
| hidden model reasoning | nowhere | no | no |

## 12. Performance design

Adding capabilities must not turn every message into a heavy agent run.

Target policy:

- fast-path orchestration overhead target: <= 10 ms excluding model/tool work;
- standard-path extra orchestration target: <= 40 ms excluding retrieval provider latency;
- graph/global retrieval only when query scope demands it;
- optional lexical providers lazy-loaded and cached;
- FTS queries use bounded result counts and ranking;
- no runtime startup download;
- no full archive injection into model context;
- no fan-out to multiple reasoning branches for trivial dialogue.

These are engineering budgets, not guaranteed wall-clock SLAs across all hosts.

## 13. Failure handling

### Missing optional lexical resource

Return provider-unavailable telemetry and continue with built-in NLP.

### No active task for “zrób to”

Use safe contextual/ordinary dialogue and request/resolve context. Never guess an executable action.

### Conflicting memory/knowledge evidence

Preserve both sources, mark uncertainty/conflict and let existing truth boundaries control usage.

### Retrieval timeout

Return bounded partial/insufficient-evidence state. Do not convert timeout into an empty fabricated answer.

### Host finalization races

Do not overwrite newer session state. Report continuity commit skipped/stale.

## 14. Test architecture

v15.4 adds four classes of gates.

### 14.1 Unit contracts

- task-state derivation and inheritance;
- reasoning lane and verification selection;
- Knowledge Fabric bounded retrieval and deduplication;
- lexical cache/provider provenance;
- operational-learning filtering;
- phase-2 session continuity commit.

### 14.2 Dialogue continuity benchmark

`latka_jazn/resources/cognition/v154_dialogue_benchmark.json` is a versioned regression corpus. It includes exact production failures plus package/archive and update-intent counterexamples.

### 14.3 Independent architecture audit

`python -X utf8 -m latka_jazn.tools.cognitive_architecture_audit --root . --json`

The audit checks required files, safe contextual route, reasoning/tool verification gates, benchmark results, verified lessons and the no-private-CoT boundary.

### 14.4 Existing release gates

No old gate is removed:

- compileall;
- Pyright;
- semantic route audit;
- full deterministic non-live pytest;
- Windows runtime/path suite;
- canonical metadata sync + idempotence;
- clean checkout guard;
- release package smoke;
- post-merge CI.

The new audit and v15.4 targeted tests are added **on top** of these gates.

## 15. Migration plan

1. Add new modules/resources with no version change.
2. Integrate structured dialogue state backward-compatibly.
3. Make unresolved contextual continuation safe.
4. Bind host-finalized session continuity to phase-2 acceptance.
5. Add reasoning orchestration without removing existing reasoning modules.
6. Add optional Knowledge Fabric wrapper over existing retrievers.
7. Add lexical intelligence and local plWordNet contract; preserve built-in providers.
8. Add operational-learning resource and independent audit.
9. Run targeted and full regression suites on 3.99 baseline behavior.
10. Bump canonical source version to `v15.4.0.0-cognitive-architecture` only after integration is green.
11. Let `release_metadata_sync` regenerate canonical metadata.
12. Merge only after synchronized PR CI is fully green.
13. Run post-merge release-hardening on `master`.

## 16. Rollback

The release is designed for source-level rollback without destructive memory migration:

- no existing memory DB schema is replaced;
- no optional lexical resource is required to start;
- old session records without task state remain readable;
- pending host records without new continuity hash remain supported;
- graph retrieval is optional;
- all new operational resources are source-controlled and versioned.

If a severe regression appears, rolling back the code release does not require rewriting user memory databases.

## 17. Definition of done for v15.4.0.0

The update is not done merely because new files exist. Release requires all of the following:

- exact known continuation failure routes correctly;
- conversation archive recall remains distinct from package archive diagnostics;
- unresolved continuation cannot trigger an unrelated action;
- final accepted host reply advances durable task/session state exactly once;
- delayed finalization cannot overwrite newer session state;
- reasoning plan uses **current** resolved task state;
- Knowledge Fabric preserves source/provenance and bounded retrieval;
- lexical providers are optional, licensed/provenanced and non-blocking;
- operational lessons are verified/test-linked and non-self-modifying;
- existing functionality and full deterministic suite remain green;
- Pyright is green;
- release metadata sync is idempotent;
- release package smoke is green on clean synchronized source;
- post-merge master CI is green.

Only then should `master` be considered upgraded to 15.4.0.0.

## 18. Research basis

The design is informed by primary/official sources, but project behavior remains governed by Jaźń's own tests and truth boundaries:

- ReSpAct (ACL Anthology, 2025): https://aclanthology.org/2025.iwsds-1.7/
- RECAP (Findings of EACL, 2026): https://aclanthology.org/2026.findings-eacl.105/
- SQLite FTS5 documentation: https://www.sqlite.org/fts5.html
- Morfeusz 2 official site: https://morfeusz.sgjp.pl/en
- plWordNet 4.2 / CLARIN-PL: https://clarin-pl.eu/dspace/handle/11321/891
- NKJP: https://nkjp.pl/
- GraphRAG global search: https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- GraphRAG dynamic community selection: https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/
- DRIFT Search: https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/
- Reflexion (NeurIPS 2023): https://papers.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html
