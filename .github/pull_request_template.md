## Summary

<!-- What changed and why? Keep repository facts separate from external deployment evidence. -->

## Scope / ownership

- [ ] `run.py` remains a thin launcher and `main.py` remains the central control plane.
- [ ] This PR does not create a second runtime, memory owner, turn authority or finalization path.
- [ ] System patch version is bumped in `latka_jazn/version.py`.
- [ ] `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` were not edited by hand.

## Runtime / MCP changes

- [ ] MCP protocol revision and wire method names match the current contract.
- [ ] Remote readiness is fail-closed and separated from current-message host/app capability.
- [ ] Ambiguous transport resumes/polls the same request; the user message is never replayed.
- [ ] Jaźń-visible output still requires accepted finalization with `action=display_exact`.
- [ ] Liveness, readiness and supervisor/recovery ownership are tested separately.

## Packaging / MEMORY

- [ ] Package member sets are exact and SHA-256 verified where applicable.
- [ ] MEMORY remains a separate capability and never becomes `active_root`.
- [ ] Producer-side package validation and runtime attach validation both fail closed.
- [ ] No private MEMORY, credentials, tokens, SQLite/WAL/SHM runtime state or logs were committed.

## Security / deployment

- [ ] Public ingress uses HTTPS and production authentication.
- [ ] Private daemon ports remain loopback-only.
- [ ] Secrets are supplied by environment/secret store, not argv/source/package manifests.
- [ ] Mutable third-party deployment images/actions are pinned or explicitly rejected for production.
- [ ] Rollback procedure is documented.

## Verification

- [ ] `compileall`
- [ ] deterministic pytest selection / full non-live suite as required
- [ ] Pyright
- [ ] `persistent-runtime-e2e` on Windows and Linux
- [ ] `release-hardening`
- [ ] package smoke / manifest sync where applicable
- [ ] chaos/failure-injection evidence for lifecycle/transport changes
- [ ] external ChatGPT acceptance recorded separately when the PR changes remote ingress

## Evidence / residual risk

<!-- CI run IDs, external deployment evidence, known limitations, rollback target. -->

## Merge gate

Do not merge until the final PR HEAD has the required green checks and the user
has explicitly approved merge.
