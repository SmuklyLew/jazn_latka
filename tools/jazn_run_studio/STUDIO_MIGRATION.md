# Studio functionality inventory and migration gates

Audited 2026-10-23 against the current source entrypoints and their concrete UI
implementations. The main catalog contains ten studios; import and restore
cursor applications are additional active interfaces. A command form or legacy
window launcher does not establish complete GUI parity. This inventory retains
the full migration requirement and identifies what still needs implementation.

| Application and canonical implementation | Existing functions to preserve | Current shared Qt exposure | Remaining parity evidence/work |
| --- | --- | --- | --- |
| System Studio: `tools/jazn_studio.py`, `latka_jazn/tools/jazn_studio/ui.py` | dashboard, connection probes, settings, update plan/fetch/apply, diagnostics, cognitive audits, other studio launchers | runtime commands, connection probes and diagnostics; legacy window explicitly available | update workflow and cognitive audit views; original settings semantics; functional comparisons |
| Start Studio: `tools/jazn_start_studio.py`, `tools/jazn_start_studio_dashboard.py` | service/task catalog, owned process controls, live logs, settings, diagnostics, readiness dashboard | common controller service controls and runtime diagnostic batch | compare the complete original task catalog and settings; richer readiness/process presentation |
| Configuration: `latka_jazn/tools/configuration_studio_ui.py` | overview, path map/copy, validated editing/file pickers, validate, preview diff, reload, CAS save, previous-profile restore, copy launch command, diagnostics, unsaved-edit protection | validated profile read/save and future-launch environment in common settings | dedicated path map, draft/preview/restore, copy command and dirty-state protection in Qt |
| Memory Studio: `latka_jazn/tools/memory_rebuild_app/ui_desktop.py` | project creation/selection, paths, DB roles/provenance/readiness, project/file/selected import, affect, candidates, source validation, tests/resume, preflight/protocol, rebuild, export, runtime/tool settings, diagnostics | commands from the original memory CLI; original validators/execution | specialized source-picker, database/provenance, affect/candidate and protocol inspectors; interactive parity cases |
| Memory Rebuild: `latka_jazn/tools/memory_rebuild_app/ui_window.py` and CLI | project/source operations, plan, protocol, validation, rebuild, export and command diagnostics | original parser-derived forms and original command execution | compare all command options/defaults and specialized dialogs; preserve read-only/destructive distinctions |
| Test Studio: `tools/jazn_tests_studio/ui_window.py` | audit/filter/select tests, expectations and review, run/cancel, results, saved run history, local settings and diagnostics | original Test Studio CLI forms and logs; native read-only searchable test/expectation table (Qt .68) | review editor, history/result navigation and original cancellation behavior remain open |
| Package Generator: `tools/jazn_pack_generator_app/ui_studio.py` | home, pack/plan/split, unpack/join, verify, settings, progress/cancel, diagnostics | original parser-derived pack/unpack/join/verify/config forms | structured plan/progress/result views and original persisted user settings |
| Dependency Studio: `latka_jazn/tools/dependency_studio.py` | canonical profile inspection, native download/verify/install, lock/replay/offline policy and tool settings | original argparse commands and original execution; verified native Windows Qt offline evidence | structured inventory/lock and installation progress views; native Linux Qt offline acceptance |
| Python Runtime Studio: `latka_jazn/tools/python_runtime_studio.py` | host detection, interpreter/bundle operations and verification | original argparse forms and original execution | interpreter inventory/diagnostic views and complete operational comparison |
| Version Rebuild: `tools/jazn_version_rebuild.py` | inspect version, preview/save with backup, canonical metadata sync, audit, diffs/patches, settings | explicit legacy window | shared Qt version/backup/diff workflow using existing business functions, with destructive-step review |
| Chat export/import: `tools/memory_import_ui.py`, `latka_jazn/tools/chat_export_ui.py` | sources, inspect, plan, import, verify, topics/domain queue, review, search, database selection | not yet a dedicated Qt page | preserve cursor workflow operations and source identity; use existing import/search services |
| Memory restore: `latka_jazn/tools/memory_restore_ui.py` | source scan/selection, target/settings, baselines, preview plan, restore, compare, configuration load/save, progress | not yet a dedicated Qt page | full plan/compare/restore workflow through the existing orchestrator and its write guards |

`ui_window.py` and the dependency/Python studios reuse the original shared
`latka_jazn/tools/application_shell/command_studio.py`; they are not independent
business implementations. Inventorying class methods alone misses their nested
GUI callbacks and command specifications, so those facades and specs are part
of the audit. Legacy/archive versions are historical evidence, not migration
targets or active test gates.

## Explicit shared-Qt migration state (.62)

These states apply to the complete application, not just CLI availability.

| Application | State | Current evidence / remaining gate |
| --- | --- | --- |
| System Studio | integracja częściowa | shared runtime controls; update/cognitive/settings parity open |
| Start Studio | integracja częściowa | common service controller; full original catalog/settings comparison open |
| Configuration Studio | integracja częściowa | profile read/save; path map, preview/restore and dirty-state parity open |
| Memory Studio | integracja częściowa | dedicated Qt P1 role/comparison/readiness evidence view in .62; imports, affect/candidates, protocol and full operational parity open |
| Memory Rebuild | integracja częściowa | canonical forms; specialized plan/progress/dialog parity open |
| Test Studio | integracja częściowa | canonical commands/logs; expectation review, selection and history UI parity open |
| Package Generator | integracja częściowa | canonical commands; structured plan/progress/settings parity open |
| Dependency Studio | integracja częściowa | canonical forms and native locks; structured inventory/install UI parity open |
| Python Runtime Studio | integracja częściowa | canonical forms; interpreter inventory and operational UI parity open |
| Version Rebuild | nierozpoczęta | legacy window only; no dedicated shared-Qt workflow yet |
| Chat export/import | nierozpoczęta | dedicated Qt workflow not yet implemented |
| Memory restore | nierozpoczęta | dedicated Qt plan/compare/restore workflow not yet implemented |

No row is fully integrated. Native Qt rendering and regressions for the P1
evidence slice do not establish parity for the rest of Memory Studio.

For each row, closure requires a before/after action mapping, positive and error
tests, equivalent persisted settings and review/backup semantics where present,
real Qt rendering/keyboard acceptance, and successful final-source CI. Partial
rows must remain partial. Do not remove legacy functionality before parity is
verified, and do not call launching a legacy window full Qt integration.

## Native Qt migration checkpoint (.88, PR review)

This is an **incremental source implementation, not proof of full parity or
local operator acceptance**. The historical .62 state table above is retained
as its original audit checkpoint; the following describes the newer .88 delta.

| Application | .88 source-level change | Remaining acceptance |
| --- | --- | --- |
| Configuration Studio | Dedicated Qt page (`configuration_view.py`) with canonical path map, field kinds, validation, CAS-bound dry-run preview, guarded save, previous-profile restore, reload, unsaved-draft close check and copy-only launch command | Compare all original Tk screens, file selectors, launcher paths, migrations, error recovery and real Windows keyboard/DPI workflows; observe tests/CI |
| Version Rebuild | Dedicated read-only Qt inspection (`version_view.py`) via original `read_version`, no metadata writes | Editable version, canonical metadata sync, backups, diffs/patches, audit, settings, rollback and operator confirmation; legacy remains active |
| System / Start / Memory / Memory Rebuild / Tests / Package / Dependency / Python | No unsupported claim of new parity; existing Qt integrations and canonical operation forms remain | Original parity gates remain open as listed above |
| Chat export/import | No native Qt workflow delivered in .88 | Source review, plan, import, validation, review queue and search require explicit private-data guards |
| Memory restore | No native Qt workflow delivered in .88 | Select/scan, dry-run plan, protected restore, compare, checkpoints and recovery remain open |

**State:** 10 partial, 2 not yet started for full Qt parity. No row
is called complete. Do not remove or deprecate functioning legacy interfaces
until accepted functional equivalents exist. A canonical read-only view does
not prove whole-Studio migration.

Safety: the Qt panel delegates profile operations to the original
`latka_jazn.tools.configuration_studio` services in the selected external
Python process; do not duplicate private MEMORY write logic in the GUI.
Profile drafts and automatic results never represent the active daemon state.

Engineering references: [Qt QComboBox signals](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QComboBox.html),
[Qt QFileDialog](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFileDialog.html),
[Qt confirmation dialogs](https://doc.qt.io/qt-6/qmessagebox.html).

## .89 — native Configuration ROOT migration acceptance

The Qt page additionally exposes the original `migrate_operator_profile`
through a separate worker. The write operation is explicit, confirmation-gated
and restricted to an on-disk operator profile matching the visible SHA-256.
Original ROOT validation, conflict checks, rollback semantics and durable
write remain owned by the canonical `latka_jazn.core.system_config` service.
Unsaved GUI draft changes are rejected rather than implicitly migrated.
Migration does **not** reconfigure an already running daemon. Positive,
conflict and unsaved-input regressions are collected in the Qt suite.

The .88 migration inventory and full application parity gates remain open:
no claim of full parity for all twelve Studios and no deprecation of the
original Tk Configuration Studio without accepted Windows operator tests.

## .94.6.15 — executable TPA workbench

TPA now provides per-interpreter preflight, a background queue, durable run
history, JUnit interpretation, logs and redacted report export for all 22
catalogue rows. Five runtime/chat rows additionally have real isolated
acceptance clients over the canonical Controller/ChatClient. Each Studio row
can open a fresh synthetic Studio sandbox with a concrete procedure and collect
human evidence. See [TPA_WORKBENCH.md](TPA_WORKBENCH.md) for the complete map.

These executors do not complete the open migration rows above. Regression
status and full acceptance are distinct report fields; missing native
workflows, unavailable models and untested offline EXEs remain explicit gates.
