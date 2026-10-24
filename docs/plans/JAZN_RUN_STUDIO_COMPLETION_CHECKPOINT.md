# Studio Jaźni completion checkpoint — 2026-10-24

Branch: `codex/jazn-run-studio-completion-20261024`.
Verified source SHA: `f6eb491965d8b90d3e4109022f96e16a3f586bf5` (PR #411).
PR #409 HEAD `fd3491a34188e188d58be29d74c80ce99e7a6670` and PR #410 HEAD
`b8642e75f649e23dad8db212bc2b131616e2356b` are both ancestors.
The new remote branch was created and read back at that source SHA before edits.
Base: `master`; existing release workflows explicitly use that base. Do not
merge this stacked continuation independently of review of #409–#411.

## Implementation checkpoint

SYSTEM: `16.3.25.5.116.0.34.63-studio-memory-offscreen-layout`.
Native-lock checkpoint pushed and read back:
`2438327f81085f2fcd6a379b6adfe39c3279975c` (source `380d825363e7abc25af06ba1d0f3978ac3f632ad`).
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

## .59 full validation and .60 correction

The preceding next-step paragraph is superseded: native lock recovery and its
artifact verification are complete. .59 targeted dependency/MCP checks: 32 PASS,
1 SKIPPED. Existing synthetic memory P1 checks: 31 PASS, 2 SKIPPED. Active compile,
source Qt GUI smoke, catalog check and diff check PASS. SYSTEM package-smoke
outside sandbox: exit 0, ok=true. Status snapshot: exit 1, daemon inactive,
marker invalid and endpoint unavailable; no accepted conversation established.
Independent .59 metadata check PASS, 3322 files, synchronized=true.

.59 full local Windows pytest: 2966 PASS, 21 SKIPPED, 16 FAIL, 328.42s. Twelve
failures expose stale startup_contract.json version .57. .60 synchronizes it
with version.py and deployment.contract.json; no assertion was changed. Two
subprocess-output failures are reproduced and resolved by inheriting explicit
PYTHONUTF8=1 and PYTHONIOENCODING=utf-8 (parent -X utf8 does not propagate).
Focused release/coverage/bootstrap set after correction: 69 PASS, 1 SKIPPED,
1 FAIL in Tk initialization. Tk failed to read installed init.tcl/ttk.tcl even
though OS inspection confirms the files exist; another focused attempt passed
that GUI case. This intermittent local-host issue remains unresolved. The MCP
real-process smoke consistently fails with mcp_catalog_invalid_http_framing;
do not accept malformed content or claim a local MCP pass.

.59 CI passed Studio, full active-tree Pyright, persistent-runtime E2E,
MCP conformance, host-spawn, memory-cloud, stable contracts and container smoke.
Release-hardening Windows failed; remaining jobs/PowerShell/cleanroom were still
in progress when .60 was prepared. These results apply to .59 only.

Next exact step: commit/push .60 with generated metadata, verify final-source
full CI, rerun deterministic suite with inherited UTF-8, investigate residual
local Tk/MCP issues without weakening tests. Do not call P0 complete yet.
P1 Qt integration, P2/P3 parity, P4 live recovery, P5 EXE acceptance remain open.

## .60 P0 source and .61 P1 resource-boundary unit

P0 pushed checkpoint: `0904e9376b782a70867ea15c3f96d088a1582f23`, source
`28184b66d7b94a41d7d2b81d1246cf2b75e3e000`. PR synthetic merge at inspection:
`4644d4c8046f1a573468a489bd27169f30f5bcda`. Release-hardening explicitly
checks the head source; default PR checkout workflows use the synthetic merge.
Independent .60 metadata check PASS (3322 files, synchronized=true).
Release-hardening 40039984983 SUCCESS: Ubuntu full suite 2987 PASS, 16 SKIPPED;
full Pyright zero errors/warnings. Cleanroom 40039985026 SUCCESS, all six native
builders/strict audits, all six opposite-OS replays and all six consumers.
PR rollup: 57 SUCCESS, 2 SKIPPED, 1 IN_PROGRESS when .61 was prepared.
Last job is PowerShell 40039984946: full deterministic suite completed without
failure; SYSTEM package-smoke still in progress. Do not cancel it with a push.

.60 full local Windows suite: 2981 PASS, 21 SKIPPED, 1 FAIL, 485.06s. The sole
failure is the MCP real-process probe reporting invalid HTTP framing. The same
test on a separately checked-out, unchanged source f6eb4919 also failed with
that diagnostic (7.27s). Local MCP acceptance remains FAIL; no framing bypass
was introduced. Tk passed this full run. Explicit inherited UTF-8 corrected
subprocess decoding. Ollama read-only /api/tags probe succeeded with
gemma3:latest; no new accepted runtime turn or recovery is claimed.

.61 repairs a reproduced P1 limit gap: setting both declared row/index budgets
to 64 bytes previously still yielded equal for a synthetic 1 KiB row. The
existing comparator now limits native SQLite record decoding, canonical row
bytes, index pages and comparison time (including diff/fingerprint iteration).
Source connections remain read-only; no activation behavior changed.

| Synthetic regression | Expected | Observed |
| --- | --- | --- |
| Oversized record | blocked, original database bytes unchanged | PASS |
| Index over budget | blocked, no equality result | PASS |
| Expired comparison | blocked, no equality result | PASS |
| Bounded equal pair | equal | PASS |
| Composite PK / changed payload | one changed key | PASS |
| No PK / duplicate multiplicity | difference retained | PASS |
| NULL, integer, real, text, BLOB, Unicode | distinct types, no raw output | PASS |
| Volatile timestamp, including key exception | ignore only non-key timestamp | PASS |
| Signed wrong PID/root/instance/nonce/proof | runtime not ready | PASS |
| Stale heartbeat, wrong process, missing auth | runtime not ready | PASS |
| Runtime generation changes during observation | conflict | PASS |
| Correct configured observation | no recall/continuity/activation inference | PASS |

Combined synthetic P1 run: 53 PASS, 2 SKIPPED; focused Pyright zero errors and
warnings; active-tree compile and diff check PASS. Existing tests unchanged;
three new regression files need no predecessor snapshots. Catalog regenerated.
Full .61 suite/CI and canonical metadata check remain required after commit.
Official limit contracts: https://www.sqlite.org/limits.html and
https://docs.python.org/3.14/library/sqlite3.html#sqlite3.Connection.setlimit.

Next: finish the .60 PowerShell observation, push the .61 metadata checkpoint,
then integrate the existing read-only P1 services into a dedicated Qt view via
the canonical run.py/main.py command route. Preserve all ten evidence boundaries.

## .62 dedicated Qt MEMORY evidence

P0 .60 final rollup: 58 SUCCESS, 2 SKIPPED, no pending/failed checks. PowerShell
40039984946 SUCCESS: isolated Tk 2 PASS, Memory GUI 2 PASS, exact failure surface
59 PASS, isolated health-check 1 PASS, full suite 2943 PASS/24 SKIPPED/1 DESELECTED
in 848.31s, followed by successful SYSTEM package-smoke and clean checkout guard.
The deselected health-check was run separately with its unchanged assertion.
The local MCP framing failure remains an explicitly reproduced baseline-host
acceptance limitation, not a green local MCP claim.

.61 pushed checkpoint: `aa2b32300bf4fb7914f1f00cd8e59d03dfe7763f`, source
`daa0282296d4292931121f1ca84a265454474727`. Independent metadata check PASS,
3325 files, manifest/provenance synchronized. Its PR rollup was 60 SUCCESS,
2 SKIPPED, 1 IN_PROGRESS; do not transfer that state to .62.

.62 adds the actual shared Qt P1 evidence slice, via:
`Window/MemoryPanel -> Controller -> run.py memory-inspection -> main.py ->
latka_jazn.cli -> existing P1 services`. No domain parser or lifecycle is added
to run.py. The adapter reads bounded/stable project JSON without constructing
ProjectStore, creating directories, saving projects or activating MEMORY.
Optional independently supplied frozen reference/parent pins use the existing
verifier. Incomplete/invalid pins fail closed; no automatic pin discovery.

Three Qt tabs separately expose source/target/staging/host-selected roles,
content/declared UUID/lineage differences, and authenticated runtime/schema/
identity/provenance/recall/continuity evidence. Readiness now includes only
validated stable reason codes; paths/arbitrary diagnostics are discarded.
Content equality never promotes lineage. Recall/continuity need independent
positive evidence; preflight and activation remain false. Comparison requires
an explicit private-read confirmation. Source/SQLite data stay read-only.

Changing selections invalidates the display and rejects delayed responses.
Failed operations cannot remain visually running. The diagnostic export stores
separate dated code/aggregate observations, never project contents or private
paths; it explicitly disclaims cross-database atomicity and activation authority.
Optional pin fields collapse; empty logs do not consume the initial viewport.

Validation: 187 PASS/2 SKIPPED across Studio/P1/CLI before the last extra Qt
roundtrip; final additional Qt set 9 PASS, including real asynchronous public
launcher roundtrip and redacted export. Type checks: zero errors/warnings.
Native Qt Windows captures at 1240x840 and 860x580 inspected; initial excessive
vertical controls corrected, final minimum-width page has no horizontal overflow.
GUI tests cover separate tabs, evidence boundaries, errors and stale replies.
Node24 install/check/probe and GitHub Actions SHA audit PASS (22 workflows,
zero findings); no action pins changed. Existing active tests remain unchanged.

P1 evidence integration is implemented, pending final-source full suite/CI.
Memory Studio as a whole remains partial. All twelve migration inventory rows
now have explicit partial/not-started states; none claims full parity. P2/P3,
real P4 multi-turn/recovery, and P5 final-source EXE/offline acceptance remain open.

Next exact steps: sync catalog, commit .62, canonical metadata write/check,
push/read back SHA, run full deterministic suite/Pyright/doctor/package-smoke
and final-source PR CI. Preserve the local MCP baseline limitation separately.
Then continue remaining shared Studio workflows and real Ollama recovery.

## .63 Windows offscreen follow-up

.62 pushed checkpoint: `0dcba60c83bce352da8aba99e70cda4ae871d6b5`, source
`2b5ec75f8c295c0c2cfb662f5d1e6303ce8a5c10`.
Studio CI 40043367907 passed Linux 3.12–3.14 but failed Windows 3.12–3.14:
the unchanged minimum-width assertion observed 170 px horizontal overflow.
Exact local QT_QPA_PLATFORM=offscreen reproduction confirmed it. Widget geometry
identified the optional pin button minimum width as 688 px. .63 shortens that
button and tab labels, stacks pin form rows, and wraps observation timestamps.
Both collapsed and expanded pins plus completed results now fit 860 px.
Native-mode rendering alone had missed this platform/style difference.

Exact offscreen regression set: 12 PASS, including the original unchanged
assertion and two new expanded/completed-layout cases. No existing active test
was edited. A separate new regression verifies that a supplied independent pin
with no ready runtime is diagnosed as runtime_not_ready_for_pinned_provenance,
rather than incorrectly claiming no pin was supplied. No readiness or activation
gate was weakened. Versions/startup/deployment are synchronized at .63.

Broader .63 targeted run: 37 PASS; Studio type gate zero errors/warnings;
catalog regenerated and diff check PASS. Independent .62 metadata check PASS
for source 2b5ec75f (3329 files); doctor and SYSTEM package-smoke exited 0.

Final-source .63 full suite, metadata check, doctor/package-smoke and CI are
required. .62 interim local runs started before this correction and must not
be treated as .63 acceptance. Continue to classify the baseline-local MCP
framing limitation separately. All P2–P5 remaining gates above are unchanged.
