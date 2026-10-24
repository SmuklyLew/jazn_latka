# Jaźń Studio .66 — public P4/P5 evidence and remaining acceptance gates

**DRAFT / ALPHA — NOT PRODUCTION FINAL.** Date: 2026-10-24.
Stacked continuation of Draft PRs #409 → #410 → #411 → #412 → #413.
Source of .65 implementation: `ae7b8914516f687b74ae97b4e63d333e444aae74`;
metadata-only .65 HEAD: `ce999b699a7ffe4131a44697fb44dc4344ddd950`.

**Provenance boundary:** P4/P5 local observations below came from operator-supplied
terminal output and screenshots, not independent runs by GitHub/this patch.
Private prompt contents, request/session identifiers, host paths, user details
and runtime/MEMORY databases are deliberately excluded.

## Verified GitHub CI for .65 source

[release-hardening 40050989918](https://github.com/SmuklyLew/jazn_latka/actions/runs/40050989918)
passed after Windows targeted job `120778673427` was rerun.
[Run Studio 40050989942](https://github.com/SmuklyLew/jazn_latka/actions/runs/40050989942)
and [cleanroom 40050989919](https://github.com/SmuklyLew/jazn_latka/actions/runs/40050989919)
also succeeded; 15/15 source-associated workflows concluded success.
`release finalization` was **SKIPPED**. The initial Windows timing failure
was rerun, not corrected in code: do not declare a stable latency guarantee
from one green retry. CI on .65 is *not* .66 CI.

## Locally reported P4 (.65)

- Three Ollama-powered local conversation turns, session recall spanning a daemon
  restart; independent checkpoint integrity/read-only verification.
- Focused transport regression tests: **19 passed**.
- Async submit/retrieve: same request ID, eventually completed and OK.
- Client closed HTTP connection without receiving response; subsequent
  same-request-only result polling returned completed and OK.
- Source-origin ledger for all three turns: `model_provider=ollama`,
  `model_candidate_generated=true`, `model_candidate_validated=true`,
  `fallback_classification=not_fallback`.
- **Boundary:** observed provider attribution is not per-request raw model-HTTP
  capture, does not prove all transport failure modes or current ChatGPT
  `display_exact` host finalization.

## Locally reported P5 (.65)

- Historical Windows `onedir` build: Python 3.14.4, PyInstaller 6.22.3,
  PySide6-Essentials 6.12.0, EXE + `_internal` + `BUILD_INFO.json`.
- Historical build EXE SHA-256:
  `4321913B56EC0C74943DB8BFEFA6C09ACF8B746442CB0F54BAFECABC09F640E8`.
- Historical GUI smoke and `--run version` exit codes: **0**.
- Avast Behavior Shield reported `IDP.Generic` and quarantined the EXE.
  Later inspection: file absent, current SHA-256 unavailable, current
  integrity **UNVERIFIED**. Smart Scan reporting zero malware findings does
  **not** mean vendor adjudication of the quarantine finding.
- A historical local report accidentally carried stale successful values after
  `Get-FileHash` failed. It is **not valid as current artifact evidence**.
  The corrected private local `p5-security-hold.json` records absence,
  `CurrentIntegrityVerified=false`, and `SafetyGate=HOLD`.
- **Offline / independent verified SYSTEM / licensed final distribution:
  NOT RUN / NOT ACCEPTED.** Do not restore or allowlist to force green results.

## Closure matrix

| Gate | Current status | Closure criteria |
| --- | --- | --- |
| P0 source CI | PASS for .65 source only | Fresh .66 CI and canonical metadata synchronization |
| P1 Qt MEMORY/config/tests | PARTIAL | Full real user workflows, errors and independent memory evidence |
| P2 common native Qt forms and accessibility | PARTIAL | Keyboard/DPI/settings/process parity |
| P3 migration of 12 applications | PARTIAL; three not started | Per-app legacy/new action maps, positive/negative GUI/behavior and persistence tests |
| P4 Ollama local dialogue/transport | OPERATOR PASS (scoped, .65) | Separate exact model HTTP tracing and broader fault coverage |
| P5 EXE build/frozen GUI | HISTORICAL PASS (.65) | Reproducible final-source artifact with independent security review |
| P5 Avast IDP.Generic | **HOLD** | Vendor review / independent safe adjudication |
| P5 offline & independent SYSTEM | **NOT RUN** | Isolated no-network installation, external SYSTEM identity and license audit |
| final merge/release | BLOCKED | All required gates, reviewed stacked ancestry, explicit authorization |

`tools/jazn_run_studio/STUDIO_MIGRATION.md` remains the source of
12-app migration statuses; launching a legacy window is not native parity.
The new `tools/jazn_run_studio/p5_artifact_evidence.py` performs **read-only**
byte and metadata checks, with no private path output or automatic clearance.
Its `current_integrity_match` is false for a missing/quarantined file.
Even a matching artifact leaves security review HOLD and both offline and
external-SYSTEM gates NOT RUN.

Security sources: [Avast Quarantine / Threat Labs](https://support.avast.com/article/21/)
and [file false-positive submission](https://support.avast.com/en-en/article/submit-file-url/).
Do not disable antivirus or publish private executable bundles. The
new .66 patch cannot inherit .65 GitHub CI as its own release evidence.
