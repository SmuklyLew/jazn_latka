# Jaźń v16.2.0 — cognitive-state policy control

Version: `16.2.0-cognitive-state-policy-control`

## Scope and truth boundary

This stage turns the existing content-free Cognitive State Graph into a bounded,
operational policy input. It does not record private chain-of-thought, user text,
claim text or recalled excerpts. It cannot create facts, authorize memory promotion,
change classified intent, override an explicit route or overrule any truth gate.

The graph, salience controller and retrieval experiment operate only on explicit
runtime artifacts, opaque identifiers and bounded observable features. All control
effects are serialized with reason codes and fail-closed authority flags.

## Claim and evidence graph

Epistemic assessments are projected into the per-turn graph after visible-output
validation. Claim and evidence identifiers are hashes; raw claim text and raw source
identifiers are not persisted in the graph.

- `supports` is emitted only for a `supported` assessment carrying explicit source
  identifiers;
- `contradicts` is emitted only for a `contradicted` assessment carrying explicit
  source identifiers;
- unsupported, inferred or evidence-free assessments never receive a factual edge;
- the projection does not change the already-computed epistemic verdict.

## Deterministic global salience

`GlobalSalienceController` ranks at most 128 graph nodes and selects at most 24. Its
observable features are node kind, recency, graph connectivity, active status,
explicit conflict relation and explicit selected-evidence relation. Every selected
item contains feature values and reason codes.

Active goals and constraints are considered before other nodes and are pinned. If
they exceed either bounded input or selection capacity, the controller returns
`blocked_active_anchor_overflow` and emits no selected nodes. In blocked state, no
goal/evidence generation hint is applied.

The resulting response-policy extension contains only an allowlist of safe hints:
preserve an explicit active goal or constraint, ground claims in already selected
evidence, surface an explicit conflict without inventing a resolution, and never
emit private reasoning. Graph identifiers are not passed to the language model.

## Graph-aware working memory

Working-memory records carry at most 64 opaque cognitive anchors and retain a bounded
set of active-goal memberships. Eviction is deterministic and anchor-aware. At least
one representative of every active goal is pinned; duplicate canonical records merge
their goal memberships instead of silently replacing the old goal.

If record or character limits cannot be met without deleting the last representative
of an active goal or an explicitly pinned record, the write raises an error inside
the SQLite transaction. The whole write rolls back, so silent goal loss and partial
persistence are both forbidden.

## Graph-aware retrieval rollout

The read-only Living Memory gateway now has three explicit lanes:

- `shadow` (default): compute and measure the bounded candidate but return the exact
  FTS baseline;
- `ab`: choose baseline or candidate by a stable query-hash bucket;
- `active`: explicit test/opt-in lane only.

The candidate reranks at most 80 existing FTS hits using baseline relevance, focus
term coverage, focus-query provenance, explicit source metadata and grounded truth
status. A bounded per-conversation diversity pass reduces fan-out. Telemetry contains
only counts, reason counters and hashed result fingerprints. The controller exposes
no write or promotion API, and chronological searches bypass reranking. FTS remains
available as the fallback in every lane.

## Private A/B result

The same local private unified database and 15-case benchmark used in v16.1.2 were
rerun. The database again passed full integrity and foreign-key checks and contained
1,043 conversations, 144,105 nodes, 70,018 searchable archive documents and 533
journal entries. No private query, expected phrase, result content or path was
persisted in the report.

The graph candidate materially improved recall but failed the non-regression gate:

- recall@20: `0.266667` baseline to `0.533333` candidate (`+0.266666`);
- evidence-eligible recall at limit: `0.461538` to `0.538462`;
- wrong-conversation proxy: `0.719626` to `0.747475` (`+0.027849`, worse);
- changed result positions across evaluated cases: `350`;
- both baseline and candidate remained below full acceptance (`ok=false`).

Therefore `quality_gate_passed=false`, `approved_for_activation=false`, and no system
activation or L2/L3 promotion was performed or authorized. Issue #59 remains open:
the candidate is useful evidence for later tuning, not an activation-ready retriever.
The sanitized local report is kept outside the repository as
`v16.2.0-graph-retrieval-ab.sanitized.json`.

## Verification

- focused cognitive, retrieval, memory, epistemic, model-context and runtime-session
  suite: `97 passed, 1 skipped`;
- focused post-hardening memory suite: `17 passed`;
- Pyright 1.1.411: `0 errors, 0 warnings`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true and dialogue regressions
  `12/12` true;
- private graph-retrieval A/B: completed, candidate rejected, FTS fallback retained;
- diff whitespace check: clean.

Protected-path closure must find no repository changes under `memory/` or
`workspace_runtime/`, and no SQLite, WAL/SHM, ZIP, secret, raw private export or
generated package artifact may be included in the stage commit.
