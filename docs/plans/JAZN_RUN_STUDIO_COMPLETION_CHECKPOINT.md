# Studio Jaźni completion checkpoint — 2026-10-24

Branch: `codex/jazn-run-studio-completion-20261024`.
Verified source SHA: `f6eb491965d8b90d3e4109022f96e16a3f586bf5` (PR #411).
PR #409 HEAD `fd3491a34188e188d58be29d74c80ce99e7a6670` and PR #410 HEAD
`b8642e75f649e23dad8db212bc2b131616e2356b` are both ancestors.
The new remote branch was created and read back at that source SHA before edits.
Base: `master`; existing release workflows explicitly use that base. Do not
merge this stacked continuation independently of review of #409–#411.

## Implementation checkpoint

SYSTEM: `16.3.25.5.116.0.34.59-run-studio-native-brotli-locks`.
Draft PR: https://github.com/SmuklyLew/jazn_latka/pull/412.
First pushed metadata checkpoint: `e84be3ad0fdf71a40bd5198cb01fbd038bca9e07`;
implementation source: `0599a198475258723f1ce3704e448d84616ee790`.
Current implementation SHA: resolve this document's commit with `git log -1`;
the final report records the actual pushed SHA without a self-referential hash.

P0.1: Job.error now represents absence as None, serialized as JSON null. Existing
consumers use truth testing and failure paths preserve explicit string codes.
Existing readiness assertions were retained unchanged. New tests cover null and
failure-code serialization. Focused Studio regression run: 71 passed; focused
Studio Pyright: 0 errors, 0 warnings. Canonical test catalog regenerated.

P0.2: IN_PROGRESS. Six native Dependency Studio regeneration workflows dispatched
on the verified source SHA: Linux 3.12/3.13/3.14 runs 40038160333, 40038163339,
40038166152; Windows 3.12/3.13/3.14 runs 40038168790, 40038171762, 40038174494.
All six runs completed SUCCESS (native download/verification, offline install,
strict audits and package publication). Exact generated lock bytes copied into
the six committed release locks; each changes only Brotli 1.2.0 to 1.2.1 plus
the native wheel hash. Independent local checks matched GitHub artifact digests
to their separate digest reports, all published file sizes/SHA-256, sidecar hashes,
embedded lock bytes and manifest lock hashes, native-resolve target/Python identity,
every embedded wheel size/hash and Brotli RECORD evidence. All six audit reports
contain zero vulnerabilities. Independent read-only candidate review found no
concrete bypass/regression in release-lock scope. Final-source replay remains pending.
pyproject already requires Brotli>=1.2.1,<2 in optional archive; no optionality change.
Official advisory: https://github.com/advisories/GHSA-9v8h-qqgm-4m35.

P0.3: .58 full Pyright PASS (zero errors/warnings), active-tree compile PASS,
doctor exit 0, independent metadata check PASS (3321 files, synchronized=true).
Sandbox full pytest stalled in async MCP descriptor tests; identical focused
test outside sandbox passed 2/2. Owned stalled processes were stopped; that full
run is INTERRUPTED, not PASS. Package-smoke likewise needs execution outside
the restricted async environment. .58 PR CI caught an outdated MCP deployment
runtime_version; .59 updates the declaration without changing assertions.
Full deterministic suite, release-hardening, PowerShell, cleanroom and final
PR CI remain required. Historical CI 40032360672 had 2976 passed, 16 skipped, three Job.error
failures; those are baseline evidence only.

P1: Existing inspection, provenance and active-memory-readiness backends present;
specialized shared Qt integration remains partial. Activation remains read-only,
unauthorized; recall and continuity require independent evidence.
P2: Partial inherited implementation; current acceptance not yet verified.
P3: Partial inventory in tools/jazn_run_studio/STUDIO_MIGRATION.md; no parity claim.
P4: NOT RUN on this source; previous accepted turns do not establish recovery.
P5: NOT RUN on this source; previous builds do not establish EXE acceptance.

Next: obtain six native generated locks and audit reports, verify artifact digest
and native target provenance, copy exact canonical lock bytes, run focused lock
regressions, then complete full P0 gates before larger P1 work. Keep PR Draft.
No private MEMORY, active runtime data, historical tests or source branches changed.
