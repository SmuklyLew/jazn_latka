# Jaźń — operator installer for SYSTEM / JSS / MCP

The installation entrypoints are `setup.ps1` (PowerShell/Windows) and `setup.sh` (POSIX/Linux).
Both call the single, stdlib-only `tools/jazn_setup.py` orchestrator. It delegates all
dependency downloads, SHA-256 verification and package installation to the existing
`latka_jazn.tools.dependency_studio`, and does not create a competing package manager.

## Quick start — Windows

Run from any working directory with the project already unpacked.

```powershell
cd D:\.AI\jazn_latka_v100_acceptance
.\setup.ps1 doctor -Json
.\setup.ps1 install -Profile core -Online
.\setup.ps1 verify -Profile core -Json
```

PowerShell uses `python` by default; use `$env:PYTHON = 'C:\path\python.exe'`
to select a supported interpreter (Python 3.12, 3.13 or 3.14).
`install` explicitly prompts for operator approval. For automation use `-Yes`
after the operator has approved the exact action.

For optional JSS UI and MCP packages use:

```powershell
.\setup.ps1 install -Profile core,run-studio,mcp-http -Online
```

The `mcp-http` dependency profile only installs library dependencies. It does
**not** create a public endpoint, tunnel, OAuth client or API key.

## Quick start — Linux (glibc x86-64)

```bash
PYTHON=python3.14 sh ./setup.sh wizard\nPYTHON=python3.14 sh ./setup.sh doctor --json
PYTHON=python3.14 sh ./setup.sh install --profile core,run-studio --online
PYTHON=python3.14 sh ./setup.sh verify --profile core --json
```

Only Windows x64 and glibc Linux x64 with Python 3.12–3.14 are release-wheelhouse
targets currently supported by Dependency Studio. Python on macOS may be
discovered, but installation from unsupported release bundles is refused.
Other platforms require their own native lock, wheelhouse and acceptance matrix.

## Commands and side effects

| Command | Behavior |
| --- | --- |
| `doctor` | Read-only, checks project entrypoints, platform, local venv and managed environment |
| `verify` | Read-only, checks the active verified managed environment and selected profiles |
| `venv` | Explicitly creates local `.venv` for developer use, never overwrites an existing one |
| `install --bundle PATH` | Verifies an exact local wheelhouse bundle, then offline installs via Dependency Studio |
| `install --online` | After explicit approval, lets Dependency Studio download, verify, then offline install |
| `repair` | Creates a new verified managed environment rather than replacing an existing one |
| `preflight` | Compatibility alias for read-only `doctor` |
| `online` | Compatibility alias for opt-in online `install` |

`--yes` (`-Yes` in PowerShell) is intended for explicitly approved noninteractive use.
A non-interactive install without approval fails. No command implicitly upgrades pip,
runs `pip install -e .`, edits private MEMORY, copies SQLite, kills/restarts a daemon,
opens an MCP tunnel, or exposes a localhost development endpoint to the Internet.

The portable SYSTEM source tree is not treated as an environment. Production-style
dependency environments are created and versioned by Dependency Studio outside
the source tree, with an activation marker updated only after hash-locked wheel
installation, `pip check`, import smoke and inventory verification. A project's
`.venv` is optional and separate; copying a venv from an earlier installation
is prohibited. Keep old environments for rollback until explicitly cleaned up.

## Completing runtime / JSS / MCP configuration

After a successful install the result contains `python_executable`, the **exact
managed Python interpreter** to use with `run.py` or `run_studio.py`.
Use it to run a fresh `run.py host-preflight --json`, inspect the canonical
`run.py status --json` and start the daemon only through an explicitly selected
instance/port. Installer success is **not** proof of an active daemon, Ollama model
generation, trusted heartbeat, persistent MEMORY, MCP transport or ChatGPT finalization.

Configure JSS, Ollama, ports and local chat through the existing JSS first-run
wizard. Configure MCP only when requested in the JSS MCP/Cloudflare settings;
public authenticated OAuth MCP must be separate from `--loopback-dev`.
Never publish the local no-auth dev gateway through Cloudflare Tunnel.
The host must independently verify MCP authorization, `tools/list`, runtime
identity, the accepted turn and finalization.

## Offline, error handling and testing

Dependency Studio is the only package writer. Its wheelhouse bundles carry
manifest and hash-locked requirements, and installation uses
`--no-index --only-binary=:all: --require-hashes`. If no compatible verified
bundle exists and `--online` was not approved, setup fails closed with a
remedy; it never downloads arbitrary dependencies as a fallback.

A clean base Python without `packaging` must still pass stdlib-only discovery.
A release with no valid bootstrap wheelhouse may refuse installation; it must
not claim success or auto-install an unverified package. The online resolver
requires a correctly configured Dependency Studio and network access.
Supply a matching canonical release sidecar or repair the operator bootstrap
if the resolution cannot initialize safely.

Targeted regression tests:

```bash
python -m pytest -q tests/test_jazn_setup_installer.py tests/test_dependency_studio.py
```

Complete release acceptance additionally requires native Windows/Linux clean-room
install, offline replay, idempotent second run, port isolation with another
version's live daemon, and JSS/MCP authentication/readiness/turn tests.
The test status must be recorded explicitly; repository commits alone cannot
be described as a successful acceptance.

Sources: Python `venv` documentation (https://docs.python.org/3/library/venv.html),
PyPA secure pip installs (https://pip.pypa.io/en/stable/topics/secure-installs/),
MCP authorization (https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization),
and the repository's `docs/tools/JAZN_DEPENDENCY_STUDIO.md`.
