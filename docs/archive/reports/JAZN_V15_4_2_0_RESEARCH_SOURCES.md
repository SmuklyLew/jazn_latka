# v15.4.2.0 — research and engineering sources

This document records the sources used to design rest/replay/dream continuity. They support architectural choices; they do **not** establish that a software rest cycle is biological sleep or that an AI system has subjective experience.

## Agent memory and reflection

### Reflexion — Shinn et al. (2023)
- Primary source: https://arxiv.org/abs/2303.11366
- Relevant result: agents can use linguistic feedback and persist reflective text in episodic memory to improve later decisions without updating model weights.
- Used for: separation of generation, reflection/evaluation and persistent procedural/reflection candidates.

### CLIN — Majumder et al. (2023/2024)
- Primary source: https://openreview.net/forum?id=8wgNZ7Kado
- Relevant result: a language agent can continually refine persistent textual memory of experience without parameter updates.
- Used for: persistent, inspectable operational learning rather than automatic fine-tuning from synthetic rest output.

### MemGPT — Packer et al. (2023)
- Primary source: https://arxiv.org/abs/2310.08560
- Relevant result: hierarchical/virtual context management supports context beyond a model's bounded window and is evaluated for multi-session chat.
- Used for: keeping replay source memory, bounded wake context and durable rest report separate.

### Generative Agents — Park et al. (2023)
- Primary source: https://arxiv.org/abs/2304.03442
- Relevant result: record of experience, higher-order reflection and retrieval/planning are distinct components; ablations show the components matter to evaluated behaviour.
- Used for: replay -> reflection -> later planning separation.

## Internal simulation

### DreamerV3 — Hafner et al. (Nature, 2025)
- Primary source: https://www.nature.com/articles/s41586-025-08744-2
- Relevant result: a learned world model can improve behaviour using imagined future scenarios.
- Used for: the narrow architectural idea that internally simulated trajectories can be useful computation.
- Boundary: the Jaźń dream sandbox is not DreamerV3 reinforcement learning and is not claimed to be biological dreaming.

## Synthetic-data safety

### Model collapse — Shumailov et al. (Nature, 2024)
- Primary source: https://www.nature.com/articles/s41586-024-07566-y
- Relevant result: indiscriminate recursive training on model-generated data can cause model collapse and loss of distributional information.
- Used for: no automatic parameter training on dream text; synthetic output cannot certify itself as factual source memory; real-source anchors are required for durable candidates.

## Persistence and timing

### SQLite atomic commit
- Official source: https://sqlite.org/atomiccommit.html
- Relevant property: transactions provide atomic commit semantics; SQLite also supports atomic commit in WAL mode through a different mechanism.
- Used for: transactional rest ledger and crash-safe phase records.

### SQLite WAL
- Official source: https://sqlite.org/wal.html
- Relevant properties: readers and a writer can proceed concurrently; there is still one writer at a time; WAL requires processes using it to be on the same host; `synchronous=FULL` syncs the WAL at commit.
- Used for: a local single-host daemon ledger, explicit writer serialization and bounded persistence policy.

### Python monotonic clock
- Official source: https://docs.python.org/3/library/time.html#time.monotonic
- Relevant property: `monotonic()`/`monotonic_ns()` cannot go backwards and are not affected by system-clock updates.
- Used for: idle duration and rest-cycle intervals. UTC wall time remains audit metadata, not interval authority.

## Design conclusion

The sources support a design in which memory retrieval, synthetic simulation, evaluation, consolidation and wake reporting are separate and auditable. They do not support treating generated scenes as external facts or treating software execution as proof of phenomenal consciousness.
