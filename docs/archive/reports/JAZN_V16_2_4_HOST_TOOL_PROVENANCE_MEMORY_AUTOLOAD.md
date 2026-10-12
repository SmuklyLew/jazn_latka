# Jaźń v16.2.4 — host tool provenance and automatic memory attachment

## Scope

This patch fixes two failures found while running the v16.2.3 ChatGPT host lifecycle.

1. A host response for an NLG plan with `source_policy=requires_external_web` was always represented as `source=model_adapter`. The generic candidate evaluator therefore rejected it as `model_candidate_cannot_fake_external_web_sources` even when the ChatGPT host had actually executed `web.run`.
2. `runtime-bootstrap` installed and could start a system runtime before discovering and attaching a standalone `profile=memory` package located beside the system package. This left the daemon alive while memory search/continuity remained unavailable.

## Fix A — authenticated host tool provenance

The two-phase finalizer now accepts a bounded `external_tool_evidence` list. The currently accepted host tool attestations are `web.run` and `GitHub`. Each item carries an operation plus returned source refs and/or HTTP(S) source URLs. The runtime validates size, shape and allowed tool names before the generic candidate guard evaluates the evidence.

The generic evaluator remains fail-closed: `source_policy=requires_external_web` is satisfied only by accepted host-attested `web.run` evidence. GitHub evidence is preserved as bounded host provenance but cannot satisfy an external-web requirement by itself. A normal model candidate with `requires_external_web` and no accepted `web.run` evidence is still rejected. The evidence is explicitly recorded as host-attested provenance; the local runtime does not claim that it independently executed or verified either host tool.

## Fix B — memory autoload before daemon start

`runtime-bootstrap` now defaults to automatic standalone-memory discovery in its `parts-dir`. The sequence is:

1. verify/install or reuse the system runtime;
2. discover exactly one `profile=memory` sidecar (or require `--memory-zip-name` when ambiguous);
3. if a legacy binary transport exceeds existing ZIP safety limits, migrate it with the existing verified v3 repacker rather than increasing limits;
4. run the existing canonical `memory-attach`;
5. run quick memory validation and, only when needed, recovery/normalization/wake-state reconstruction;
6. keep L2/L3 automatic promotion disabled;
7. start the daemon only after this memory stage has succeeded or no standalone memory package is present.

`--no-auto-memory` provides an explicit opt-out for diagnostics.

## Security basis

The patch follows the existing fail-closed ZIP model. Python's `zipfile` documentation warns callers to inspect untrusted archives and validate extraction paths. OWASP file-upload/input-validation guidance recommends archive-path validation and limits on decompressed size/compression behavior to prevent traversal and ZIP-bomb style resource exhaustion. Therefore v16.2.4 reuses the v3 logical segmentation/repack pipeline instead of enlarging the 8 GiB total / 2 GiB member defaults.

For tool provenance, the design follows the general provenance distinction between an entity/result, the activity that produced it, and the agent that performed the activity: the host may attest that `web.run` or GitHub occurred and supplies bounded source locators, while runtime truth boundaries continue to distinguish those attestations from local execution. Only `web.run` evidence is eligible to satisfy `requires_external_web`.

## Regression coverage

Added coverage verifies that:

- model candidates still cannot fake required external-web sourcing;
- valid host-attested `web.run` evidence removes only that specific provenance violation;
- bounded GitHub evidence is accepted as host provenance but does not satisfy `requires_external_web`;
- malformed/unknown tool evidence fails closed;
- MCP finalization exposes only bounded evidence and still does not accept mutable identity fields;
- one standalone memory package is auto-discovered, multiple packages are ambiguous without explicit selection;
- legacy oversize packages select v3 repack while v3 packages do not;
- auto-memory runs before daemon start on a reused verified runtime;
- CLI exposes `--memory-zip-name` and `--no-auto-memory`.
