# Jaźń v116.0.12 — post-merge operational MCP prompts

This is a **post-merge supplementary patch** forked from the canonical `master` after PR #362. It is not a declaration that all MCP 2026-07-28 or Tasks conformance gates have passed.

## Implemented

- Modern private MCP `prompts/list` and `prompts/get` register the real `jazn_runtime_review` prompt with three grounded, public-safe focus choices: `readiness`, `finalization`, `memory`.
- Modern `completion/complete` returns deterministic `focus` suggestions with the correct `completion.values`, `total` and `hasMore` response. Invalid or unknown references fail closed.
- The public authenticated Python MCP SDK gateway advertises and serves the **same** operator prompt and completion handler. It does not duplicate runtime state, memory contents, user identifiers or the authority of `jazn_status`.
- A new active acceptance test checks modern discovery, tools, prompt listing, prompt generation, completion suggestions and invalid-argument rejection without network or private MEMORY.
- Release identity bumped to `16.3.25.5.116.0.12`. Original version-bound tests archived prior to update. Integrity and provenance manifests are **not** hand-edited: canonical `release-hardening/manifest_sync` must regenerate them on the fix branch.

## Not part of this patch

- Runtime-owned `TaskInputGateway` to consume and resume `inputResponses` in the existing daemon job, including durable ACK, cancellation and restart.
- Stateless subscription streams and other real protocol gaps; a dedicated isolated upstream conformance fixture still needs to be implemented.
- Two consecutive authenticated, fully accepted remote ChatGPT MCP turns.

**No merge before green Pyright, deterministic full tests, Windows, Linux and canonical metadata verification.** A specific subset of conformance improvements must not be mislabeled as full v116 protocol acceptance.

References: official MCP 2026-07-28 protocol and SDK completions documentation.
