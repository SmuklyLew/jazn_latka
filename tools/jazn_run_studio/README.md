# Studio Jaźni Starter

Desktop operator for the canonical `run.py -> main.py` system. This branch is
an implementation checkpoint, not a completed release candidate. The full
acceptance scope and remaining work are recorded in `ACCEPTANCE.md`.

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
hash-locked wheels. This checkpoint registers the profile; native Windows/Linux
wheelhouse generation and verified offline-install acceptance remain open.

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
- A running child is labeled as running, with functional readiness explicitly
  unverified. Runtime status preserves separate identity, heartbeat, endpoint and
  conversation-readiness fields.
- Existing studios open using their canonical entrypoints. Their existing Tk
  interfaces are still present in this checkpoint; a common Qt migration is pending.
- Reports contain the bounded logs of every job, job states and exit codes.
  Secret-like assignments and inherited secret values are filtered before display
  or export. Export creates a new file exclusively and never overwrites a source file.
- Closing Studio asks before cancelling its owned jobs. Daemon stop is a separate
  explicit runtime action. The application waits asynchronously for child shutdown.

Settings are secret-free JSON under `workspace_runtime/jazn_run_studio/`, ignored
by Git. Saves check the previous content hash and replace atomically. Runtime ENV
profiles continue to use Configuration Studio validation. This checkpoint does
not add a secret editor, import arbitrary ENV files, or support paid OpenAI API.

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

GitHub workflow `jazn-run-studio` tests Windows/Linux on Python 3.12/3.14 and
builds a Windows onedir artifact after tests. Actual CI outcomes are separate
from the existence of the workflow.

No LICENSE file was found at the audited baseline. This change does not invent
or grant a project license. Qt notices and a distribution-license review must be
completed before public binary distribution.
