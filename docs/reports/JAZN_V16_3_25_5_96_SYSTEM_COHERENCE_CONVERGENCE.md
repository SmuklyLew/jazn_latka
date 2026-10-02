# Jaźń v16.3.25.5.96.6 — system coherence convergence

## Scope

This release starts from the post-PR #303 master and converts the remaining
actionable MCP findings into code-level invariants rather than documentation-only
claims. It intentionally does not fabricate external ChatGPT capability or a
successful real-account acceptance run.

## Confirmed findings fixed

1. **Unbounded usable task lifetime.** The task registry advertised a finite
   `ttlMs` but `tasks/get` never used it as a backstop. SEP-2663 permits a
   server to fail a task after `createdAt + ttlMs`. v96 does so before another
   runtime poll.
2. **Wrong `input_required` polling semantics.** A persisted
   `input_required` task was non-terminal, so a repeated `tasks/get` called
   `jazn_resume_visible_reply` again. The extension specifies that
   `tasks/get` should keep surfacing the outstanding `inputRequests` snapshot
   until client input is supplied. v96 returns the persisted snapshot without
   runtime re-entry.
3. **Cross-process write serialization.** The store had an `RLock`, WAL and a
   SQLite busy timeout, but read/modify/write state transitions began as the
   default DEFERRED transaction. v96 reserves the write transaction with
   `BEGIN IMMEDIATE` for create, update and cancel state changes.
4. **Public exception-detail leakage.** An unexpected polling exception was
   copied verbatim into the task JSON-RPC error message. v96 keeps the stable
   exception class while suppressing exception text that could contain operator
   paths, URLs or other sensitive detail.
5. **Cancellation race window.** Cancellation used a separate `get()` followed
   by `update()`. v96 performs terminal-state check and cancel-intent mutation
   in one immediate write transaction.

## Explicit non-change: custom Tasks HTTP bridge

The bridge is retained. As of this release, the official MCP Python SDK v2
supports the 2026-07-28 protocol core but its migration guide and roadmap still
state that SEP-2663 Tasks dispatch is not implemented. Jaźń therefore keeps the
bridge narrow: only task-capable generate plus `tasks/get|update|cancel` are
intercepted; all other requests remain owned by the official SDK.

## Security / OAuth review

The public ingress continues to use the MCP SDK bearer-auth middleware. The
Jaźń RFC 7662 verifier binds tokens to the configured resource audience; the SDK
middleware rejects expired `AccessToken.expires_at` values and mismatched
resource identifiers. RFC 7662 makes `iss` optional in an introspection
response, so this release does not incorrectly require a claim the standard
does not require. When `iss` is present, Jaźń already requires it to match the
configured issuer.

OpenAI's production requirements remain unchanged: stable HTTPS Streamable HTTP,
authorization on private/user-specific actions, protected-resource/OAuth
discovery, per-request token verification, scopes, and a real Developer Mode or
plugin connection for final acceptance.

## Regression coverage

`tests/test_mcp_task_lifecycle_bounds.py` adds deterministic coverage for:

- TTL expiry before runtime polling;
- stable repeated `input_required` snapshots;
- exception-detail redaction;
- idempotent creation from independent store instances;
- idempotent cancellation and terminal-state preservation;
- rejection of negative TTLs.

The persistent-runtime E2E workflow runs this file on both Ubuntu and Windows.

## External truth boundary

A green repository PR proves the code/test/release contracts exercised by CI. It
does **not** prove that a particular ChatGPT account currently has the Jaźń app
installed or that a public deployment is reachable. Real ingress acceptance
still requires a deployed HTTPS `/mcp` endpoint and a host-observed call in a
fresh ChatGPT conversation. That evidence must be collected outside this
repository and must never be synthesized by CI.


## CI follow-up 16.3.25.5.96.1

The first full deterministic release-hardening run exercised 1,934 tests and
found exactly two failures: both were stale release-identity assertions left on
the 16.3.25.5.95.1 line. The functional MCP/SQLite changes were not the failing
surface. Before updating the active tests, their exact source versions were
archived under
`tests/archive/v16.3.25.5.96.1-release-identity-fix/`.

The active release-identity checks now assert the v96.1 system-coherence line
with stable purpose names rather than continuing to describe the prior v95.1
ChatGPT-ingress release.


## Windows WAL contention follow-up 16.3.25.5.96.2

The v96.1 PR-context persistent-runtime matrix exposed a real Windows race:
constructing independent `McpTaskStore` instances concurrently could fail in
`_connect()` while every new connection re-issued
`PRAGMA journal_mode=WAL`. The failure happened before the intended
`BEGIN IMMEDIATE` task transaction.

v96.2 treats WAL as persistent database bootstrap state instead of connection
decoration. `_connect()` configures only per-connection properties. Schema
initialization checks the current journal mode and enables WAL only when needed,
using a six-attempt exponential backoff capped at 200 ms for SQLite
BUSY/LOCKED contention. The loop is deliberately bounded and fails closed as
`mcp_task_wal_bootstrap_lock_timeout` if contention cannot be resolved.

The release-identity tests were also converted from exact patch-version pins to
the stable `16.3.25.5.96[.*]` system-coherence release line. Their v96.1
sources are archived byte-for-byte under
`tests/archive/v16.3.25.5.96.2-sqlite-wal-contention-fix/`, so future CI-only
patch increments do not create another artificial release-identity failure.


## Generated-artifact ownership follow-up 16.3.25.5.96.3

CI exposed a second-order race between two branch mutators. The release-hardening
workflow could commit canonical metadata first, after which the Stable Test
Contracts workflow committed `test_contracts.json`. Because pushes made with
the repository `GITHUB_TOKEN` do not recursively trigger ordinary push
workflows, that later catalog commit could become the branch HEAD without a new
metadata synchronization pass.

The shared concurrency group prevented simultaneous mutation but did not impose
a semantic order between the two workflows. v96.3 therefore makes the Test
Studio mutator self-contained:

1. generate and locally commit `test_contracts.json` when it changed;
2. run the canonical `release_metadata_sync` against that new local HEAD;
3. commit `SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json`
   after the catalog commit;
4. push the whole generated sequence once, with metadata as the final commit;
5. verify metadata idempotence before the job can succeed.

Both branch-mutator jobs also use the current GitHub Actions `queue: max`
concurrency mode so multiple pending mutator runs are queued instead of silently
replacing an older pending run. Pull-request validation materializes the
deterministic Test Studio catalog locally, mirroring the existing local
materialization of release metadata, while push validation still proves the
committed branch is synchronized.

This removes the observed metadata-to-catalog inversion and makes the final
automation-generated branch HEAD a `[skip ci]` metadata commit rather than a
catalog commit that spawns approval-required recursive PR checks.


## Single generated-artifact owner follow-up 16.3.25.5.96.4

The v96.3 ordering fix proved that catalog-before-metadata produces a correct
final metadata HEAD, but it still left two workflows with branch-write
authority. v96.4 removes that architectural duplication.

`release-hardening` is now the only generated-artifact branch mutator. On
eligible push events it:

1. materializes the Test Studio contract catalog;
2. commits the catalog locally when it changed;
3. generates canonical provenance/integrity metadata against that local catalog
   commit;
4. commits metadata as the final `[skip ci]` commit;
5. pushes the complete generated sequence once.

`Stable test contracts` is read-only and materializes the catalog only inside
its validation checkout. Pull-request release-hardening verification likewise
materializes metadata and then the catalog locally, and its clean-checkout guard
restores all three generated files before asserting a clean tree.

This gives generated source/catalog/metadata one lifecycle owner and prevents a
workflow-created catalog commit from becoming an unverified final branch HEAD.
The previous active CI-order contract test was archived byte-for-byte before
being updated to assert this single-owner invariant.


## Final release-hardening follow-up 16.3.25.5.96.5

The v96.4 full-suite run exposed three stale assertions in
`tests/test_release_workflow_hardening.py`. They described the older
metadata-only writer and an exact PR-condition count that no longer matched the
intentional single-owner catalog+metadata workflow. Their exact v96.4 source is
archived under
`tests/archive/v16.3.25.5.96.5-release-hardening-finalization/` before the
active contract is updated.

The same run also exposed a real Windows shell defect in the clean-checkout
guard: a Bash-style backslash was being passed literally to native `git` from
PowerShell, producing `fatal: \\: '\\' is outside repository`. The Windows
guard now builds a PowerShell array of generated paths and passes that array to
`git checkout --`, with an explicit native exit-code check. This avoids
fragile line-continuation syntax and keeps the PR validation checkout clean.

The release-hardening tests now assert the architectural invariants rather than
the obsolete step label:

- `release-hardening` is the only branch writer for generated catalog and
  canonical metadata;
- catalog commit precedes metadata commit;
- the generated sequence is pushed exactly once;
- PR validation materializes both metadata and the Test Studio catalog locally;
- all three generated files are restored before the clean-tree assertion;
- upload-artifact pins and failure-only artifacts remain unchanged.


## Final contract cleanup 16.3.25.5.96.6

The v96.5 Windows release-hardening run confirmed the PowerShell clean guard
itself is fixed: `git checkout -- $generatedPaths` completed and the previous
`fatal: \\: \'\\\' is outside repository` failure did not recur.

The remaining targeted failure was a redundant legacy string assertion in
`test_release_workflow_hardening.py`: it required the literal summary text
`master/update/fix/hotfix/upgrade/release/tools-upgrade` even though the same
test already validates every allowed branch filter individually and validates
the `case` allowlist used by the writer. The literal had no runtime or policy
meaning after the single-owner workflow rewrite.

The v96.5 active test is archived byte-for-byte under
`tests/archive/v16.3.25.5.96.6-final-contract-cleanup/` before removing only
that duplicate textual requirement. No branch allowlist or fail-closed guard
is weakened.
