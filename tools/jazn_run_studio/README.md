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
