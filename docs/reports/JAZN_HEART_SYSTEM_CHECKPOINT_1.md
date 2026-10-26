# Jaźń — Serce Systemu: checkpoint 1 (.94.1)

2026-10-26. Development checkpoint; NOT release-ready.

## Verified starting state

- Windows NT 10.0.26300; native Python 3.14.4 in the existing Studio venv.
- Worktree: `D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics`.
- Branch: `fix/jazn-v11603494-system-studio-diagnostics-20261026`.
- Baseline local and remote SHA: `d6b7b66ecd383b031ebb70f6f4824c48f75c4eb5`.
- Master: `9e388555dbba2dc973987270c130e80a3ef806f2`; .93: `aeadd20345f20f0ecf12bca551ed67e043390dd3`.
- PR #422 OPEN, unmerged; #423 OPEN Draft, based on .93. Exact baseline HEAD only has GitGuardian SUCCESS. Older Actions runs are not final-HEAD evidence.
- The requested parent directory was absent and was created explicitly. Write probe succeeded and was removed. Active master files/runtime/MEMORY were not modified.
- Backup ref: `backup/jazn-heart-system-before-20261026` at baseline SHA.
- Read root AGENTS, Codex and Ollama runbooks, repository/dependency policy, scientific boundaries and turn/finalization index. No nested AGENTS found.
- Attachment folder contains only the task text. Historical JSON report and visual references were not supplied there; their contents are not asserted.

## Changes and evidence

- New thin `run_studio.py` delegates to the existing Qt Workbench. Existing launchers and main.py are preserved.
- Default named `violet-night` palette; compatibility purple/light/dark/custom modes retained. Text contrast >=4.5:1 and control outlines >=3:1 are tested against all four dark surfaces.
- In-flight diagnostic actions/probes are shared atomically. Batch can wait for an existing status read and preserves its failure. Canceling the batch does not cancel a shared read. Lifecycle mutations still exclude one another.
- MCP catalog diagnostic follows the selected local MCP port.
- Updated launcher architecture contracts and version .94.1, avoiding .95 allocation.
- Baseline: 190 PASS, 1 SKIPPED, 17.83s. After change: 198 PASS, 1 SKIPPED, 17.72s. Native Windows interpreter, offscreen Qt. Local Studio type gate: 0 errors/warnings.
- Tests are additions; no existing tests or immutable archives modified.

## Remaining gates and continuation

Wizard, durable dock/layout controls, richer settings/Developer/terminal and service tables remain to implement. Full active suite, native visible GUI/DPI capture, live model/MCP/lifecycle tests, packaging/cleanroom and final SHA CI remain required. No acceptance is inferred from window opening.

Commit and remote SHA are recorded by Git and in the external checkpoint record after push, avoiding a self-referential tracked SHA. Before continuing, verify HEAD/remote and inspect this report. Next step: integrate first-run checks and persistent Qt operator workspace.
