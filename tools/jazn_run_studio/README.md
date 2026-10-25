# Studio Jaźni Starter

Desktop operator for the canonical `run.py -> main.py` system. This branch is
an implementation checkpoint, not a completed release candidate. The full
acceptance scope and remaining work are recorded in `ACCEPTANCE.md`.

## TPA — Testy przepuszczania aktualizacji (.86 checkpoint)

The former **Odbiór lokalny** page is named **TPA**. All 22 manual acceptance
cases, their version-scoped results and archival rules remain unchanged.
The new asynchronous **Uruchom podtest zaznaczonego** and **Uruchom bezpieczne
podtesty** actions execute only three curated isolated regression subsets:
`smoke-isolation`, `config-persistence`, `ui-accessibility`.
Their `PASS` means only that this regression subset ran successfully. It
**never** marks a local acceptance gate PASS or supplies proof of actual daemon,
Ollama, MEMORY, EXE, accessibility or full 12-Studio migration readiness.

Subchecks run under a temporary workspace with the inherited JAZN environment
removed, a fixed 120 s limit, bounded/redacted output and operator-only JSON
evidence. The operator may cancel the child process; neither TPA nor an error
handler may stop or adopt the existing Jaźń runtime. If selected Python or
pytest is missing, the action fails closed. Only verified external interpreter
paths are accepted; frozen Studio requires explicit Python configuration.

Existing legacy studios remain **archiwalne / do przeglądu** until their
functions, state/error handling and visual parity are independently verified.
The native profile editor and color picker remain usable, but do not confer
full Configuration Studio migration parity. Read
`docs/plans/JAZN_TPA_11603486_STUDIO_MODERNIZATION.md` for the remaining gates.

## Install and launch

Use Python 3.12 or later, with a Qt-supported interpreter/platform and a verified
SYSTEM checkout. Python 3.14 on Windows is the locally tested development host.
From the repository root, in an isolated virtual environment:

```text
python -m pip install -r tools/jazn_run_studio/requirements.txt
python -X utf8 jazn_run_studio.py
python -X utf8 jazn_run_studio.py --check
python -X utf8 jazn_run_studio.py --run version
python -X utf8 jazn_run_studio.py --gui-smoke
```

`requirements.txt` delegates to `pyproject.toml[run-studio]`; it is not a second
dependency version source. Qt Widgets only requires `PySide6-Essentials`, rather
than the larger optional Addons distribution. The core runtime does not require Qt.

For offline environments, use the existing Dependency Studio `run-studio`
profile to download/verify a native wheelhouse and install only its verified
hash-locked wheels. Native Windows x64 / Python 3.14 download, RECORD/hash
verification, offline installation and GUI smoke have passed. The exact generated
lock is preserved at `locks/windows-x64-py314.txt`; it was copied from Dependency
Studio output. Other target-specific Qt locks and native Linux offline acceptance
remain open. Never replay the Windows lock as a Linux installation contract.

The first screen detects executables and import availability. It never installs
programs, starts services, or tests a user turn automatically. Installation links
point to the official publishers. Missing dependencies are explicit errors.

## Operations

- Runtime commands use the public launcher; lifecycle, identity verification and
  finalization remain under the existing control plane.
- Diagnostics run asynchronously. Each command has a finite timeout and bounded
  output; diagnostic batches stop on the first failed step.
- Ollama, the local MCP gateway and a configured Cloudflare Tunnel can be launched
  as owned child processes. Stop/restart uses the retained process handle. Studio
  never adopts a PID or stops pre-existing system services.
- The local MCP service must explicitly start with `mcp-http --loopback-dev --host
  127.0.0.1`. The shared settings control `mcp_port` (1024–65535, default
  8080) and the loopback-only `daemon_url` (default
  `http://127.0.0.1:8787`). The same configured MCP port is used by the
  readiness probe; an occupied port is never adopted as Studio-owned.
  `mcp_python` optionally selects a verified Python interpreter with the
  separate MCP/uvicorn dependencies installed (the core Jaźń interpreter is
  unchanged). Public OAuth MCP is a distinct explicitly configured deployment,
  never an automatic fallback of this local action.
- Critical completion, state and validated chat-final events have a separate
  overflow channel. Saturated diagnostic log streams can lose redundant log
  updates but must not discard accepted final messages or terminal states.
- A running child is labeled as running, with functional readiness explicitly
  unverified. Runtime status preserves separate identity, heartbeat, endpoint and
  conversation-readiness fields.
- Existing studios open using their canonical entrypoints. Their existing Tk
  interfaces remain an explicit optional choice. The shared Qt forms now expose
  canonical Memory/Rebuild, Tests, Package Generator, Dependency and Python
  Runtime commands. Forms are derived from their original argparse definitions;
  original business logic validates and executes each operation. Configuration
  profiles are editable in the same Qt settings page. Specialized legacy visual
  inspectors and the Version Rebuild window remain separate.
- Reports contain the bounded logs of every job, job states and exit codes.
  Secret-like assignments and inherited secret values are filtered before display
  or export. Export creates a new file exclusively and never overwrites a source file.
- Closing Studio asks before cancelling its owned jobs. Daemon stop is a separate
  explicit runtime action. The application waits asynchronously for child shutdown.

Settings are secret-free JSON under the canonical
`workspace_runtime/jazn_run_studio/`, ignored by Git. Saves check the previous
content hash and replace atomically. An optional `operator` profile is validated
by Configuration Studio and applied to future runtime/chat starts only.

An optional secrets JSON file must live outside SYSTEM, in its canonical ignored
workspace, or in a path confirmed ignored by Git. Supported keys are
`JAZN_MCP_OAUTH_CLIENT_SECRET`, `JAZN_MEMORY_CLOUD_TOKEN`,
`JAZN_MEMORY_WRITER_LEASE_TOKEN`, and `TUNNEL_TOKEN`. Values enter only child
environments and the redaction registry; they are never copied into settings or
reports. The file is never sourced as executable shell code. Editing secret
values stays in the operator's local editor. Paid OpenAI API remains future work.

## Part 2 operator observability (.72 checkpoint)

The dashboard and **Usługi i procesy** now mirror the latest *observed*
service evidence. A retained subprocess PID is always labeled as process-only,
not as function or conversation readiness. Explicit HTTP readiness and canonical
runtime status have different messages; no background probe is inferred from
a running process. Data can be stale until an operator starts a new probe.

The lower diagnostic tabs can be shown/hidden with the status-bar toggle.
The technical per-job streams are separate from human-readable **Zdarzenia**
and **Błędy** tabs. This UI separation does not change runtime or daemon logs.

On a failed controller job, a bounded, structured and redacted diagnostic
entry is written to ignored
`workspace_runtime/jazn_run_studio/errors_jazn_studio.log`. It uses standard
Python rotating logs (1 MiB each, up to three backups), and contains only the
observation time, job key, failure reason and optional return code. It never
records raw stdout, arguments, chat text or secrets. If this diagnostic file
cannot be written, the event still reaches the GUI; a separate warning is
shown. Reports remain opt-in and redact inherited secret values.

Custom accent can now be selected with the native Qt color palette or typed
as validated `#RRGGBB`. Canceling the dialog changes nothing; accepting only
updates the unsaved draft until **Zapisz i zastosuj** is clicked.

This is **not** complete part-2 acceptance. The migration inventory in
`STUDIO_MIGRATION.md` still contains 12 partial/not-started rows.
Windows/Unix real runtime and model-generation checks, antivirus/vendor review,
portable offline EXE acceptance, accessibility and complete GUI parity remain
independent gates. Do not merge or distribute as production-ready solely on
successful synthetic Qt tests.

Qt references:
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QColorDialog.html
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QStatusBar.html
- https://docs.python.org/3/library/logging.handlers.html

## Read-only MEMORY evidence

The shared Qt page **Dowody MEMORY** exposes the existing P1 inspection,
snapshot comparison and active-runtime evidence services. It does not launch
the legacy Tk window. Three separate tabs retain separate observation times:
source/target/staging/host-selected roles; content and declared provenance; and
authenticated runtime/database evidence. Changing the selected project or pins
invalidates the view and rejects delayed results from the old selection.

The controller uses the public `run.py -> main.py` route:

```text
python -X utf8 run.py memory-inspection --operation layout --project <project.memory-rebuild.json> --json
python -X utf8 run.py memory-inspection --operation comparison --project <project.memory-rebuild.json> --json
python -X utf8 run.py memory-inspection --operation readiness --json
```

The project file is read with size, path and stability guards, without creating
a ProjectStore. Comparison explicitly asks before private-content reads; it
uses the original bounded Online Backup/diff implementation and temporary
cleanup. Optional independently reviewed frozen reference/parent artifacts and
their expected SHA-256 values are supplied only to readiness via `--reference`,
`--reference-sha256`, `--parent`, `--parent-sha256`. No pin is discovered or
trusted automatically. Reports include codes and aggregate observations, never
project contents or private paths. Completed observations are included in the
shared diagnostic export with their separate timestamps.

Successful observation execution does not mean successful readiness. Matching
content does not verify lineage. Configured database evidence does not prove
recall or continuity. Activation preflight and authorization remain false;
there is no activation control on this page. This is the P1 evidence slice,
not full Memory Studio migration parity (source editing/import, affect,
candidates, protocol and rebuild workflows remain listed in STUDIO_MIGRATION).

## Local chat

Start the runtime and Ollama explicitly, verify the model list, select a model in
settings, then connect the Local Chat page. Studio keeps one `run.py chat-ollama`
JSONL pipe and one stable session. Each request ID is saved **before** sending;
the checkpoint contains no user message. Only the canonical local final validator
may release text to the chat view, with request binding and turn/trace lineage.

On interrupted or uncertain transport, use **Wznów wynik**. It retrieves the same
daemon request through `run.py --daemon-result`; it never resubmits user text.
Until that request is resolved, a new message is blocked. Closing the transport
does not stop the daemon. Conversation text is displayed locally but is not added
to the shared diagnostic log export.

Service probe completion is separate from service readiness: an HTTP response with `ready=false` or non-ready gateway/Cloudflare status fails the operator check while preserving the response evidence. When a model is selected, its absence from Ollama `/api/tags` fails the model-selection check, but an installed model still does not prove generation or an accepted Jaźń turn.

Read-only service probes are also available from the terminal:
`python -X utf8 jazn_run_studio.py --probe ollama` (or `gateway`, `cloudflare`,
`tunnel_service`). HTTP, model availability, daemon identity and accepted speech
are reported as separate evidence.

Choose a verified installed SYSTEM root with `--root` / `JAZN_ROOT`. A development
checkout may differ byte-for-byte from the canonical package (notably Windows
line endings) and legitimately fail runtime preflight. Use the existing canonical
release staging/package workflow; never bypass integrity or edit manifest hashes
to make that checkout appear installed. Studio preserves the runtime's rejection.

## Build

Install PyInstaller into the isolated build environment. The build never installs
or downloads dependencies implicitly:

```text
python tools/jazn_run_studio/build.py --output <new-absolute-build-directory>
```

The result is an **onedir** application; keep the executable and `_internal`
directory together. This is a desktop operator for an external SYSTEM, not a
frozen copy of the runtime. Set `JAZN_ROOT` to that SYSTEM and
`JAZN_STUDIO_PYTHON` to a real Python interpreter, or use the corresponding
settings. Build diagnostics can use `--console`.
`BUILD_INFO.json` records the source commit and tool versions. PySide6 and
shiboken distribution metadata/license notices are copied into the artifact.
External child launches restore system DLL/library paths as prescribed by
PyInstaller, preventing the desktop's bundled Qt from contaminating runtime tools.

GitHub workflow `jazn-run-studio` tests Windows/Linux on Python 3.12/3.14 and
builds a Windows onedir artifact after tests. Actual CI outcomes are separate
from the existence of the workflow.

No LICENSE file was found at the audited baseline. This change does not invent
or grant a project license. Qt notices and a distribution-license review must be
completed before public binary distribution.
