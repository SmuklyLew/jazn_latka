# Jaźń v15.4.2.0 — Rest / Replay / Dream Continuity

**Target:** `v15.4.2.0-rest-replay-dream-continuity`
**Safety default:** `JAZN_REST_SHADOW_MODE=1`
**Network topology:** no new public service and no new port; the scheduler is owned by the existing loopback daemon.
**Truth boundary:** an internal simulation is not an observed event, a user-confirmed fact, a biological dream, or evidence of consciousness.

## Goal

The update gives the runtime an auditable notion of **time between conversations**. During a verified period in which the daemon remains alive and the user is idle, the daemon may execute bounded rest cycles. A cycle can replay source-grounded memory, generate an explicitly synthetic internal scene using a local model, evaluate it, and optionally create an inferred L2 candidate. The system then creates a hash-verified wake report.

The purpose is not to teach the runtime to *say* it dreamed. The purpose is to let it later prove what internal computation actually occurred. If the daemon was not alive, no rest ledger exists, a report is invalid, or a cycle failed, the visible system must not invent continuity.

## Non-goals

- no automatic fine-tuning or other parameter updates;
- no claim of biological sleep, dreaming, sentience, or phenomenal experience;
- no network browsing, messaging, repository writes, shell commands or other external tool execution from the dream sandbox;
- no automatic L3 promotion;
- no replacement of source memory with model-generated text;
- no requirement that rest be healthy for ordinary dialogue readiness.

---

## Phase 0 — contracts, truth boundary, persistence invariants

### Deliverables

1. `latka_jazn/memory/rest_contracts.py`
   - `RestEpisodeStatus` and `RestCycleStatus`;
   - `SimulationTruthStatus`: `simulated_internal`, `counterfactual`, `rehearsal`, `associative`;
   - `RestConsolidationDisposition`: `discard`, `rest_transient`, `reflection_candidate`, `procedure_candidate`, `user_review_required`;
   - `RestContinuityStatus`: `rest_verified`, `rest_partial`, `rest_none`, `rest_integrity_failed`;
   - immutable payloads for replay items, scenes, evaluations and consolidation decisions;
   - SHA-256 verification of replay excerpts and scene content;
   - constructor-level rejection of automatic L3 and `target_tier=long_term`.

2. `latka_jazn/memory/rest_cycle_store.py`
   - dedicated SQLite database, separate from factual memory;
   - `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, configurable `synchronous=FULL|NORMAL`, `busy_timeout`;
   - `BEGIN IMMEDIATE` transaction boundary guarded by an in-process `RLock`;
   - tables for episodes, cycles, replay provenance, dream scenes, source links, evaluations, consolidation decisions, wake reports;
   - database `CHECK` constraints forcing `factual_claim_allowed=0` and `automatic_l3_allowed=0`;
   - `integrity_check` + `foreign_key_check` validation.

### Security invariants

- a `DreamScene` can never be accepted as factual evidence merely because a model generated it;
- the synthetic scene itself is never a real-source anchor;
- a rest decision cannot target L3;
- private replay text is not duplicated into the replay ledger; that table stores source IDs, content hashes and provenance metadata. Synthetic dream text is stored only in the dedicated rest database;
- rest database failure is isolated from the primary dialogue daemon.

### Exit criteria

- SQLite refuses a direct write setting `factual_claim_allowed=1`;
- Python contracts refuse automatic L3;
- integrity and FK checks are green;
- no rest module changes active `memory/` truth by default.

---

## Phase 1 — `RestCycleController`: a real bounded idle-time scheduler

### Deliverables

`latka_jazn/core/rest_cycle_controller.py` owns the state machine:

`active_dialogue -> waiting_for_idle -> cycle_running -> resting_between_cycles`

with explicit degraded/budget states. It is instantiated by `JaznDaemonServer`; it does not start a second server.

### Timing

Default values:

- idle threshold: 900 s;
- cycle interval: 1800 s;
- poll: 5 s;
- maximum cycles per idle episode: 16;
- replay budget: 6 records;
- local dream model enabled, but generation remains optional;
- shadow mode enabled.

The scheduler uses `time.monotonic_ns()` for elapsed/idle intervals and UTC wall timestamps only for audit. User activity resets the idle anchor and closes the current rest episode with a wake report. The scheduler pauses while chat work or a runtime session is active.

### Daemon integration

- `JaznDaemonServer` constructs the controller inside a fail-soft boundary;
- newly accepted chat jobs call `note_user_activity()`;
- the rest thread starts after the regular heartbeat;
- shutdown stops the rest controller before sessions are closed;
- `/ready`, marker and status payloads expose `rest_cycle_status`;
- rest failure **must not** become a readiness reason for ordinary dialogue.

### Idempotence/restart

On startup an unfinished `rest_episode` is marked `interrupted` and gets a report. A deterministic cycle ID derives from episode ID + ordinal, and SQLite uniqueness forbids duplicate ordinals inside an episode.

### Exit criteria

- no new port;
- a simulated scheduling failure leaves dialogue available;
- user activity closes the idle episode;
- no more than configured cycle budget can execute.

---

## Phase 2 — source-grounded `Memory Replay`

### Deliverable

`latka_jazn/memory/rest_replay.py` reads canonical memory tiers using the existing memory store. It never writes memory.

### Eligibility

Allowed truth statuses:

- `source_recorded`;
- `user_confirmed`;
- `inferred`;
- `symbolic`;
- `canonical`.

`draft`, `book_scene`, `rejected`, empty records and non-checkpointable working-memory records are excluded.

### Ranking

A bounded score combines:

- importance;
- confidence;
- recency with a bounded decay;
- memory kind priority (`open_task`, `reflection`, `procedural`, episodic etc.);
- truth-source bonus;
- tier bonus;
- anti-loop penalty for records replayed in recent rest cycles.

The first pass enforces domain/kind diversity. A second pass fills unused capacity when the available memory set is homogeneous; this prevents diversity protection from accidentally collapsing a valid two-record replay set to one record.

### Provenance

Each replay item carries:

- canonical memory ID;
- tier/kind/truth status;
- bounded excerpt + excerpt SHA;
- canonical record content SHA;
- evidence keys;
- update timestamp;
- explicit `read_only=true`.

Only `source_recorded`, `user_confirmed`, and `canonical` records count as **real source anchors** for consolidation.

### Exit criteria

- selection is bounded;
- recent items receive a measurable anti-loop penalty;
- source IDs and hashes survive to the dream-source link;
- no replay write occurs to L0/L1/L2/L3.

---

## Phase 3 — `DreamSandbox`: simulations that cannot impersonate memories

### Deliverable

`latka_jazn/memory/dream_sandbox.py` turns a replay set into at most one bounded internal scene per cycle.

### Model authority

Background generation may use only an adapter that proves it is local:

- Ollama;
- llama.cpp;
- OpenAI-compatible endpoint whose hostname is `127.0.0.1`, `::1`, or `localhost`.

Host ChatGPT, paid OpenAI, remote OpenAI-compatible endpoints and other remote providers are rejected for autonomous rest. The request has `tools=[]` and `parallel_tool_calls=False`; a response containing tool calls is rejected.

If no eligible local model is available, the cycle still produces an auditable `model_unavailable`/skipped outcome. Absence of a model never causes fabricated dream text.

### Simulation classes

Cycles rotate between:

- associative replay;
- rehearsal;
- counterfactual;
- generic internal simulation.

The prompt explicitly forbids adding external events, presenting simulation as memory, executing an action, or claiming a biological dream.

### Exit criteria

- no source => no dream;
- remote model => rejected;
- requested tool call => rejected;
- every accepted scene is persisted with `factual_claim_allowed=0` and source links.

---

## Phase 4 — reflection and evaluation

### Deliverable

`latka_jazn/memory/rest_reflection.py` performs an independent deterministic first-pass evaluation rather than asking the generator to certify itself.

Metrics:

- source overlap / groundedness;
- source consistency;
- novelty;
- bounded utility;
- uncertainty;
- self-reference/confabulation risk;
- count of real source anchors.

A scene with no real source anchor may at most remain `rest_transient`. Low source consistency or strong self-certifying language causes `discard`. Only a sufficiently grounded and useful scene can become a `reflection_candidate`.

The evaluation does **not** assert that the reflection is true. It says only whether the synthetic output is worth entering the existing review/consolidation path.

### Exit criteria

- self-generated text cannot be its own real-source anchor;
- deliberately unsupported scenes do not become memory candidates;
- all metrics are bounded 0..1 and persisted with reasons.

---

## Phase 5 — consolidation gate without self-poisoning

### Deliverable

`latka_jazn/memory/rest_consolidation.py` is the only bridge from a rest scene toward ordinary tiered memory.

### Default: shadow mode

In `JAZN_REST_SHADOW_MODE=1` the gate records the decision but materializes **nothing** in L2. This is the production default for the first release.

### Optional non-shadow mode

When explicitly disabled and only when a candidate has at least one real source anchor:

- target is `short_term` only;
- truth status is forced to `INFERRED`;
- evidence points to the original source memory IDs and hashes;
- tags include `rest`, `simulated_internal`, simulation kind, `requires_review`;
- confidence/importance are capped below authoritative-source levels;
- resulting record remains subject to existing L2 review/promotion mechanisms.

L3 remains impossible from this module, both in Python constructors and SQLite constraints.

### Exit criteria

- shadow mode produces zero L2 writes;
- non-shadow mode can create only inferred L2;
- no branch can produce an automatic L3 decision;
- synthetic scene SHA is preserved in evidence metadata but not treated as independent factual evidence.

---

## Phase 6 — wake report, restart bridge and 8-hour integration scenario

### Deliverable

`latka_jazn/memory/rest_wake_report.py` creates a canonical JSON report and SHA-256 digest for a closed rest episode.

Report fields include:

- episode status and IDs;
- recorded UTC begin/end;
- monotonic process elapsed duration;
- verified idle window (initial idle threshold + recorded rest episode);
- cycles completed/skipped/failed;
- replay item count and source IDs;
- number and kinds of synthetic scenes;
- evaluation and consolidation counts;
- count of L2 candidates materialized;
- scene hashes;
- SQLite integrity report;
- explicit truth boundary.

A read-only loader validates `quick_check`, canonical report hash and validation status without creating or altering the rest DB.

### Wake integration

`WakeStateRuntimeBridge` exposes independent fields:

- `rest_continuity_status`;
- bounded `rest_report`.

A valid rest report can survive even if the ordinary normalized wake-state is missing. This **does not** set `continuity_claim_allowed=true`; cross-session memory continuity still depends on the existing verified wake contract. When a normal wake packet is verified, only the bounded rest summary is appended to context—not raw dream text.

### 8-hour deterministic scenario

The integration test uses a fake monotonic clock:

1. 15-minute idle threshold;
2. first rest cycle;
3. fifteen more 30-minute cycles;
4. final 15 minutes to an 8-hour idle window;
5. 16-cycle budget reached;
6. episode closes;
7. report is re-opened and hash-validated.

Required assertions:

- 16 recorded scenes when an injected local test generator is available;
- zero factual dream-scene violations;
- zero automatic L3 violations;
- zero L2 candidates in shadow mode;
- verified idle window exactly 28,800 seconds;
- restart/report read works from disk.

Additional failure scenarios cover tampered wake report, missing model, missing source, rest subsystem initialization failure, missing normal wake sidecar, and non-shadow L2 materialization.

---

## Release gates

The update is not release-ready until all of the following are green:

- new phase 0–6 tests;
- existing wake/continuity tests;
- existing daemon stability tests on Linux and targeted Windows CI;
- `compileall`;
- Pyright in canonical CI;
- semantic route audit;
- cognitive architecture audit containing rest invariants;
- full deterministic pytest suite (`not live_model and not live_mcp`);
- clean checkout guard;
- canonical metadata sync;
- release `package-smoke` after merge.

`SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json` must be generated by the existing canonical metadata synchronization workflow; they are not edited manually in the feature commit.

## Rollout strategy

1. Merge only with shadow mode default.
2. Run real multi-hour idle sessions with a local model and inspect rest ledgers/wake reports.
3. Keep L2 materialization disabled until false-positive and self-reference evaluations are acceptable.
4. Enable L2 candidates only by explicit operator configuration.
5. Keep automatic L3 permanently forbidden unless a later separately reviewed architecture changes the global memory contract.
