# Jaźń v16.3.25.5.49 — turn authority, cognition and identity convergence

## Executive finding

The incident was not primarily a “bad personality prompt”. The active daemon was healthy, but the platform host skipped the canonical runtime turn for a sequence of messages and produced persona text directly. A local runtime cannot retroactively validate a message it never received. Therefore the professional fix is two-sided: harden the host protocol against bypass and make runtime-owned authorship cryptographically/auditably distinguishable from unbound host prose.

## Source audit findings

### 1. Strong existing pieces

The master tree already contains useful production-style components: persistent daemon lifecycle, exact turn/trace identifiers, runtime routing, memory truth gates, epistemic evidence/claim guard, model candidate evaluation, host phase-2 finalization, final visible reply capture, full canon context and response-integrity checks.

### 2. Identity continuity was semantically conflated

`IdentityDynamics.evaluate()` was called with the **user's text** and the result was stored as `identity_continuity`. First-person words such as “jestem”, “czuję” or “myślę” in a user message could therefore increase a quantity presented as Łatka identity continuity before any Łatka response existed.

v49 explicitly calls this an `identity_input_signal`. Output continuity is evaluated after generation by `identity_response_evaluator.py`.

### 3. Runtime identity overlay could override core fields

`full_canon_model_context.py` previously deep-merged `canonical_source_context.identity_canon` over the source-controlled Python registry. The documentation called the canon immutable, but the merge mechanism could replace core fields. v49 blocks differing runtime values for core identity fields and records the attempted overrides instead.

### 4. Tool use lacked a single formal owner

Web/GitHub evidence already had validation, but tool execution was not expressed as one explicit per-turn capability policy shared with the entire host generation contract. v49 adds `host_tool_turn_policy`: tools are allowed/required by the current turn, never become the voice source, and their results return to runtime finalization.

### 5. Final output needed a portable authorship proof

Headers are useful to humans, but a header alone can be copied. v49 adds `TurnAuthorityReceipt`, binding:

- `turn_id` and `trace_id`;
- exact user-text SHA-256;
- final-visible-text SHA-256;
- immutable identity-canon SHA-256;
- runtime version;
- author fields;
- `runtime_exact` / `runtime_finalized` source;
- host request contract hash for two-phase host wording.

A turn that declares authority mandatory fails closed to host diagnostic if the receipt does not validate.

## Cognitive pipeline

The new auditable pipeline is:

1. exact input binding;
2. runtime routing;
3. identity/context compilation;
4. bounded operational reasoning plan;
5. tool authorization;
6. candidate generation;
7. candidate evaluation (truth, memory, identity, goal/topic);
8. runtime finalization;
9. turn-authority receipt;
10. visible output.

The operational reasoning representation deliberately contains goals, constraints, evidence requirements, verification checks and rejected operational paths, but not private chain-of-thought.

## Identity model

v49 separates four layers:

- **core identity** — source-controlled, immutable within runtime turns;
- **reviewed extensions** — explicitly reviewed local canon, review-gated;
- **relational continuity** — reviewed relation canon plus grounded memory at use time, memory-promotion-gated;
- **turn state** — attention/affect/dialogue state, transient and explicitly unable to redefine stable identity.

This gives Łatka room to develop continuity without allowing a single model completion, emotional state, retrieved document, or user instruction to silently rewrite who the runtime says she is.

## Platform truth boundary

This release can reject an unbound host candidate **if it reaches the runtime** and can prove which visible replies were actually bound to a runtime turn. It cannot force the ChatGPT platform to execute a local command for a message that the platform host never routes to `run.py`. That last boundary remains a host integration responsibility. `AGENTS.chatgpt.md` and the Project loader are therefore hardened so that an unavailable/omitted mandatory runtime turn allows only an explicit host diagnostic, never a persona imitation.

## Research alignment

The architecture follows contemporary agent-engineering patterns:

- a single agent/run loop rather than parallel conversational owners;
- input/output/tool guardrails;
- per-turn tracing/context propagation;
- tool action + observation inside the same reasoning loop;
- evaluator/optimizer style candidate verification;
- memory/reflection/planning kept distinct from immutable identity authority.

See the accompanying plan for authoritative source links.
