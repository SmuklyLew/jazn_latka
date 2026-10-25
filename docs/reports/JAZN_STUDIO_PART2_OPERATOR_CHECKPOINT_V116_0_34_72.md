# Jaźń Starter — część 2: checkpoint .72 (2026-10-24)

## Lineage and scope

- Parent: [Draft PR #415](https://github.com/SmuklyLew/jazn_latka/pull/415),
  exact starting SHA `b9991b1f6f9a427d19512b2e0ecca3e9a387f084`.
- Follow-up: `fix/jazn-studio-part2-verified-ui-20261024`, stacked on
  `fix/jazn-studio-local-acceptance-20261024`. Do not merge either without review.
- SYSTEM version: `16.3.25.5.116.0.34.72-studio-part2-operator-observability`.
- `run.py -> main.py` remains unchanged. No MEMORY, state-marker, identity,
  daemon lifecycle or accepted-turn contract was modified.

## Implemented checkpoint, not full acceptance

1. Dashboard and Services share the same explicitly observed status messages
   from existing canonical status and bounded HTTP/Cloudflare/Ollama probes.
   A PID is only a process observation, not a functioning model or accepted turn.
2. The operator may explicitly refresh these observations. Missing Cloudflare
   configuration is shown as such, not automatically provisioned.
3. The lower Qt diagnostics area has a show/hide control. User-readable
   **Zdarzenia** and **Błędy** are separated from per-job technical log tabs.
4. Failed job state emits a redacted structured record to
   `workspace_runtime/jazn_run_studio/errors_jazn_studio.log`
   using bounded 1 MiB x four rotating files (current + 3 backups).
   No arguments, raw stdout, chat, secrets, or private memory are in records.
   If disk logging fails, the terminal event remains deliverable and an
   operator warning is queued.
5. The Custom theme has a native Qt palette (`QColorDialog`); cancel is
   non-mutating and acceptance remains an unsaved draft until Save.
6. New regression tests cover the Qt palette, panel, status truth, explicit
   read-only refresh and redacted journal failure modes. The
   `jazn-run-studio` workflow includes them across Windows/Linux 3.12/3.13/3.14
   and a Windows frozen Qt smoke/package job.

## Validation evidence / limitations

- Baseline PR #415 source .71: all 15 queried workflow results were SUCCESS.
  This evidence is **not** evidence for this .72 branch.
- Direct local `container` and `python` executor probes returned `ClientError`
  before command execution. Therefore no local compileall, pytest, Pyright,
  package-smoke or Windows service/model integration success is claimed.
- Full .72 final-source CI, release metadata synchronization and independent
  physical-device acceptance must be confirmed after the final push.
- No five-hour quota percentage can be read from these available tools;
  this is an explicit durable Git checkpoint, not a claimed 20% limit trigger.
- Changes from current source should be validated by CI (not prior green SHAs).
  Final release remains **HOLD**, even if focused checks become green.

## Part 1 inheritance and Part 2 open gates

Existing part-1 responsibilities remain in the parent Draft: dependencies,
verified owned-process lifecycle, settings/secrets and run.py control plane,
MCP/Cloudflare probing, diagnostics, real local chat transport and frozen EXE.
This checkpoint adds operator presentation and error persistence, not a second
runtime implementation.

Still open before complete **Część 2**:

- Full native Qt functional equivalence of the 12 entries in
  `tools/jazn_run_studio/STUDIO_MIGRATION.md`, including version rebuild,
  memory export/import/restore, configuration preview/restore and test history.
- Real Windows/Linux Ollama generation, Jaźń multi-turn delivery ACK/recovery,
  local HTTP/MCP framing and ChatGPT final acceptance with live identity.
- Non-Qt sources' licensing and independent antivirus vendor assessment;
  Avast IDP.Generic is a separate HOLD.
- DPI, keyboard, screen-reader/high-contrast and offline Linux distribution
  acceptance, plus verified full deterministic suite and release metadata.
- More detailed nonsecret developer log retention and robust batch cancellation
  acceptance; avoid conflating UI event history with canonical runtime logs.

## Official implementation sources

- Qt QColorDialog: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QColorDialog.html
- Qt QSplitter: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html
- Qt QStatusBar: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QStatusBar.html
- Python RotatingFileHandler: https://docs.python.org/3/library/logging.handlers.html
- Ollama model listing: https://docs.ollama.com/api/tags

## Continuation

Read the latest `AGENTS.md` and `AGENTS.codex.md`, ensure metadata check
and CI are green on the exact last source SHA, fix any regression without
weakening tests, then continue one legacy studio at a time with functional
before/after parity (Configuration, Test History, Version Rebuild, Import and
Restore). Keep all unfinished rows explicitly open and preserve their legacy
entrypoints until parity and user-machine acceptance are proven.
