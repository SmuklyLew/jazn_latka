# v15.4.2.1 — research and engineering sources

This report records sources used to justify **engineering boundaries and tests** in the cognitive-truth/memory-integration hardening release. None of the cited work establishes that Jaźń is biologically conscious, has a biological nervous system, or experiences sleep.

## Cognitive architecture: integration must include decision/action

### CoALA — Sumers et al. (2023)
- Primary source: https://arxiv.org/abs/2309.02427
- Relevant result: language-agent architecture is described using modular memory, structured actions and a generalized decision-making process selecting actions.
- Engineering use: a module existing in source is not enough; runtime reachability and an observable decision/action effect are stronger evidence of integration.

### Generative Agents — Park et al. (2023)
- Primary source: https://arxiv.org/abs/2304.03442
- Relevant result: memory, reflection and planning form distinct architectural components; ablation experiments show each contributes to evaluated behavior.
- Engineering use: v15.4.2.1 adds effect/reachability checks and recommends ablation-style regressions instead of presence-only capability claims.

## Continual learning without changing model weights

### Reflexion — Shinn et al. (2023)
- Primary source: https://arxiv.org/abs/2303.11366
- Relevant result: linguistic feedback stored in episodic memory can improve subsequent decisions without model-weight updates.
- Engineering use: durable reflections/candidates remain explicit memory artifacts rather than hidden autonomous fine-tuning.

### CLIN — Majumder et al. (2023/2024)
- Primary source: https://openreview.net/forum?id=8wgNZ7Kado
- Correct title: *CLIN: A Continually Learning Language Agent for Rapid Task Adaptation and Generalization*.
- Relevant result: persistent dynamic textual memory, including causal abstractions, supports improvement/adaptation without parameter updates.
- Engineering use: source metadata corrected; persistent learning remains inspectable and source-bound.

## Memory-system separation and consolidation analogy

### Preston & Eichenbaum — hippocampus/prefrontal memory interactions
- Primary full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC3789138/
- Engineering use: fixes a previously unresolved scientific source key used by the neuropsychology map. The source supports a biological-memory interaction discussion; it does not imply software equivalence.

### Hippocampus, prefrontal cortex and amygdala interactions
- Primary full text record used by project: https://pmc.ncbi.nlm.nih.gov/articles/PMC6676505/
- Engineering use: fixes the second unresolved source key in the neuropsychology map.

## Persistence and crash safety

### SQLite atomic commit
- Official source: https://sqlite.org/atomiccommit.html
- Relevant property: transaction commit is intended to be atomic; interrupted transactions do not become half-committed logical changes.
- Engineering use: rest/wake and persistence ledgers retain explicit transaction boundaries.

### SQLite WAL
- Official source: https://sqlite.org/wal.html
- Relevant properties: WAL separates readers and writer more effectively but remains a single-host/local-filesystem design and still requires explicit writer coordination.
- Engineering use: dedicated local rest ledger remains serialized and bounded; WAL is not treated as a substitute for application-level truth or freshness checks.

## Design conclusions for v15.4.2.1

1. **Presence is not capability.** Evidence should progress from source presence through reachability/effect/live verification.
2. **Memory sources and mutable state require distinct ownership.** A recovered snapshot should not be casually mutated by ordinary turns when its fingerprint anchors continuity.
3. **Replay must read real source-grounded records.** An aggregate wake summary is insufficient evidence of diverse memory replay.
4. **Scheduler readiness is not model readiness.** A working timer/ledger does not prove autonomous DreamSandbox generation.
5. **Software homeostasis must be described by its enforced control effect.** A number in telemetry is not a regulatory loop until something consumes it.
6. **Neuroscience references are analogical design grounding, not identity claims.**
