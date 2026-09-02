# v16.3.25.3.15 — package distribution convergence

This release converges system/memory packaging on one `PackagePlanBuilder`,
one fail-closed path boundary, one `jazn_package_set/v3` writer contract and
one compatibility reader contract.  `.gitignore` is not a security boundary.

The portable Pack Generator remains a two-file distribution, but its embedded
implementation is now generated from checked-in build sources plus the current
canonical package/path modules.  CI `--check` fails when any source SHA changes
without regenerating the bundle.

Runtime Python dependencies are transported as a separate target-specific,
verified wheelhouse artifact.  A virtual environment is always recreated on the
target and installed offline with `--no-index --find-links`; an existing `.venv`
is never packaged.

Memory attach stages the fully copied tree on the destination filesystem and
uses local atomic renames for promotion/rollback.  External memory roots no
longer depend on cross-device `os.replace` into the runtime workspace.

Legacy oversized memory remains a migration-only input for
`memory-repack-legacy`; normal system/memory ZIP safety limits are not raised.

`package-distribution-cleanroom.yml` consumes the actual release ZIP and actual
dependency artifact in a job with no source checkout and no editable install.
Package acceptance requires plan/sidecar/manifest/ZIP agreement and a real
bootstrap → doctor → daemon endpoint → ChatGPT turn → stop cycle.
