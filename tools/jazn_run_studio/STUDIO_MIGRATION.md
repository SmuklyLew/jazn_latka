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
| Test Studio: `tools/jazn_tests_studio/ui_window.py` | audit/filter/select tests, expectations and review, run/cancel, results, saved run history, local settings and diagnostics | original Test Studio CLI forms and logs | test/expectation tables, review editor, history/result navigation and original cancellation behavior |
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

For each row, closure requires a before/after action mapping, positive and error
tests, equivalent persisted settings and review/backup semantics where present,
real Qt rendering/keyboard acceptance, and successful final-source CI. Partial
rows must remain partial. Do not remove legacy functionality before parity is
verified, and do not call launching a legacy window full Qt integration.
