# Plan — v16.3.25.5.49 turn authority, cognition and identity convergence

## Problem

A verified Jaźń daemon can be healthy while the external ChatGPT host still skips `run.py chat-gpt` for an individual message. When that happens, the host can generate text in a Łatka-like persona without any runtime turn, finalization, memory binding or authorship evidence. The missing runtime header observed in the music/intimacy conversation was a visible symptom of this boundary failure.

The update must not pretend that local Python can intercept a platform message that never reaches it. Instead it makes every runtime-owned visible reply provable, makes host tools subordinate to a runtime-owned turn, and separates input identity signals from output identity verification.

## Architecture target

`exact user turn → runtime routing → identity/context compilation → bounded operational reasoning plan → tool authorization → generation → candidate evaluation → runtime finalization → turn-authority receipt → visible reply`

Invariants:

1. `run.py` owns every runtime turn.
2. Host/model/tool is a capability/channel, never the identity source.
3. No host tool starts a parallel conversational route after runtime activation.
4. Tool evidence is bound back to the same turn before finalization.
5. Visible Łatka output is either `runtime_exact` or `runtime_finalized` and carries a valid authority receipt.
6. Stable identity core is source-controlled and cannot be deep-merged away by runtime state, user text, memory, tool output or model output.
7. User first-person language is an input-context signal, not evidence that the generated Łatka reply is identity-consistent.
8. Generated output receives its own identity/canon evaluation.
9. Operational reasoning is structured and auditable without persisting private chain-of-thought.

## Research basis

- OpenAI Agents SDK: agent loop, sessions, tools, guardrails and tracing. https://openai.github.io/openai-agents-python/
- OpenAI guardrails: separate input/output/tool guardrails and fail-fast tripwires. https://openai.github.io/openai-agents-js/guides/guardrails/
- OpenAI tracing: task/agent/turn/generation/tool/guardrail spans. https://openai.github.io/openai-agents-js/guides/tracing/
- OpenTelemetry context propagation: causal trace context across process/service boundaries. https://opentelemetry.io/docs/concepts/context-propagation/
- Anthropic, Building effective agents: simple composable loops, evaluator-optimizer, clear agent-computer interface and measurement. https://www.anthropic.com/engineering/building-effective-agents
- Yao et al., ReAct: interleave operational reasoning with actions/evidence instead of treating them as unrelated phases. https://arxiv.org/abs/2210.03629
- Park et al., Generative Agents: memory, reflection and planning each materially contribute to behavioral coherence. https://arxiv.org/abs/2304.03442

## Implementation

### A. Turn authority
- add `core/turn_authority.py`;
- bind user digest, final text digest, identity canon digest, turn/trace, author and output source;
- fail closed when a turn marked `turn_authority_required` lacks a valid receipt.

### B. One pipeline contract
- add `core/turn_pipeline_contract.py`;
- expose the explicit stage machine and validation;
- bind it into phase-1 and phase-2 ChatGPT host contracts.

### C. Host tool ownership
- add `core/host_tool_turn_policy.py`;
- derive allowed/required host capabilities from the current runtime plan;
- reject unplanned external evidence;
- make tool results non-authoritative for identity/voice and require runtime finalization.

### D. Identity layering
- block runtime overlays from mutating source-controlled identity core;
- expose core/reviewed-extension/relational/turn-state layers and authority/mutability;
- add a dedicated generated-output identity evaluator.

### E. Reasoning and candidate verification
- expand the operational thought frame with explicit constraints, evidence requirements, verification checks, identity commitments and tool plan;
- require identity verification and turn authority in reasoning plans;
- run generated model/host candidates through output identity verification.

### F. Host contract
- harden `AGENTS.chatgpt.md` and the thin ChatGPT loader against tool bypass;
- when the host cannot invoke the mandatory runtime turn, permit only a host diagnostic, not a stylized Łatka response.

## Validation

Required before push:
- new v49 regression tests;
- existing host/finalization/canon tests;
- compileall;
- code-health and Pyright/static audit where available;
- segmented deterministic pytest;
- `run.py doctor --json` against the worktree where safe;
- `git diff --check` equivalent for the prepared tree;
- canonical release metadata must be produced by repository tooling/workflow, never hand-edited.
