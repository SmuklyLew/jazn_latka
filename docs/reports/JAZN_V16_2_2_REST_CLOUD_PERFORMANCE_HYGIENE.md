# Jaźń v16.2.2 — rest, cloud, performance and project hygiene

Version: `16.2.2-rest-cloud-performance-hygiene`

## Scope and truth boundary

This stage closes the remaining operational convergence work without turning an
optional provider, optional history directory or cloud replica into a runtime truth
claim. Local memory remains authoritative for the running process. Dream scenes are
synthetic and always retain `factual_claim_allowed=false`. Cloud synchronization is
optional durability, not automatic promotion or proof of continuity.

No Ollama CLI/server or llama.cpp server was available on the verification host.
Therefore no live local-model generation is claimed. No external cloud provider was
called because no explicit endpoint, operator identity and credentials were present.

## Bounded local-model context

`local_model_context_compiler.py` now provides an allowlisted, bounded transport
packet for local generation:

- default context budget: 16,000 JSON characters;
- hard operator ceiling: 32,768 JSON characters;
- per-section budgets with relevance ordering and duplicate removal;
- exact preservation of required goal, constraint and evidence identifiers;
- fail-closed rejection when required references or the total packet cannot fit;
- direct-user, request-byte and prompt-token gates before any HTTP request;
- no raw payload, SQLite dump or private reasoning in the request or telemetry;
- the current user message appears only once on the Ollama wire.

The local adapter exposes rolling p50/p95 request bytes, observed/estimated prompt
tokens and end-to-end latency over a bounded 256-sample content-free window. A
five-run deterministic transport benchmark used a 6,100,333-character historical
shape and produced:

| Metric | p50 | p95 |
| --- | ---: | ---: |
| Request bytes | 2,909 | 2,909 |
| Prompt tokens reported by provider fixture | 8,195 | 8,195 |
| End-to-end latency | 18.276 ms | 18.541 ms |

The compiled context was 1,875 characters. Individual compiler durations were
17.934–18.292 ms. The benchmark provider response was deterministic and mocked; it
proves the wire contract and metrics, not live Ollama availability or model quality.

## Offline rest

Existing deterministic eight-hour idle, restart/wake, interruption and rest-store
tests remain green. Autonomous dream generation accepts only an injected test
generator or a configured local provider on a loopback endpoint. New regressions
reject both a paid remote provider and a remotely hosted OpenAI-compatible endpoint
before generation. Dream scenes remain simulations with no tools, no external action
authority and no factual or automatic L3 promotion path.

## Optional encrypted cloud durability

The existing local-first memory sync and snapshot design was exercised with the
separate `memory-cloud` dependency profile. PyNaCl 1.6.2 was installed only in the
isolated test dependency directory, not in the repository or base dependency set.
Production XChaCha20-Poly1305 event and snapshot round trips ran successfully.

The verified contracts retain these boundaries:

- plaintext memory is encrypted before it crosses the backend boundary;
- local commits and local readiness do not depend on cloud availability;
- cloud sync is opt-in and refuses incomplete endpoint, identity, key or secret
  configuration before network access;
- cloud input does not automatically promote L2/L3 memory;
- restore materializes into a verified staging root and cannot overwrite an existing
  active-memory target automatically.

No live cloud call was attempted because operator configuration and credentials were
absent.

## Project-index hygiene

`docs/update_history` and `docs/archive/manifest_history` are now represented as
optional audit sources rather than required self-knowledge sources. Their absence is
reported as `optional_not_configured` with `required=false`, `warning=false` and
`missing_is_error=false`. The stale archived-manifest path was removed from the
self-architecture source description. Missing optional directories can no longer
produce a perpetual false warning.

## Verification

- new Stage G regressions: `9 passed`;
- rest/cloud Stage G selection before optional crypto install: `50 passed, 2 skipped`;
- encrypted cloud profile with PyNaCl installed: `30 passed`, no skips;
- focused release, context, adapter and code-health tests: `27 passed`;
- full repository suite: `870 passed, 4 skipped`;
- full Pyright 1.1.411 analysis: 679 files, `0 errors, 0 warnings`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true and dialogue regressions
  `12/12` true;
- diff whitespace check: clean.

Generated release metadata is intentionally synchronized once after the Stage G
commit so it can point at a clean, immutable source commit. Protected-path closure
must find no repository changes under `memory/` or `workspace_runtime/`, and no
SQLite, WAL/SHM, ZIP, secret, raw private export or generated package artifact may be
included in the stage commit.
