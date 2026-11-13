# V127.4 — one canonical Python environment per Jaźń ROOT

## Contract

A prepared Jaźń ROOT owns exactly one selected Python interpreter:
- Windows: \`ROOT\.venv\Scripts\python.exe\`
- Linux: \`ROOT/.venv/bin/python\`

The system Python (3.12–3.14 in this release) is used to create the project
venv on first installation. The project venv is not portable between hosts and
must be recreated when the system Python or project location changes.

Core, JSS, MCP libraries and the TPA/pytest evidence adapter share the same
interpreter. Optional profiles such as Polish NLP are explicitly selected;
a profile choice is not a claim that every optional capability is installed.
No package installation starts a daemon, publishes a tunnel, or touches MEMORY.

## First installation

Use the operator-owned \`setup.ps1 -Mode wizard\` (or \`setup.sh wizard\`).
Choices 2–4 now include \`test-evidence\`; choice 3 also installs local MCP
libraries. The installer creates \`ROOT/.venv\` and installs a verified
hash-locked wheelhouse. JSS only selects the validated private Python.

## Existing ROOT/.venv (e.g. a V127.4 installation predating this patch)

Close running JSS, inspect the ROOT and confirm its daemon is not active before
modifying dependencies. Never delete or overwrite an active runtime marker.

    # Windows PowerShell, in the test checkout
    $env:PYTHON = (& py -3.14 -c 'import sys; print(sys.executable)').Trim()
    .\setup.ps1 -Mode doctor -Json
    .\setup.ps1 -Mode extend -Profile @("run-studio", "mcp-http", "test-evidence") -Online
    .\setup.ps1 -Mode verify -Profile @("run-studio", "mcp-http", "test-evidence") -Json

The explicit \`extend\` command:
1. Verifies that \`ROOT/.venv\` belongs to this checkout.
2. Refuses an active runtime marker at either the selected or canonical workspace.
3. Downloads a wheelhouse only after the operator authorizes network activity.
4. Verifies wheel structure, hashes, target/ABI and the dependency contract.
5. Compares the existing \`pip inspect\` inventory against every pinned version.
6. **Refuses any upgrade/downgrade of an already installed package.**
7. Installs only missing wheels into \`ROOT/.venv\` offline, with \`--no-deps\`,
   \`--no-index\` and \`--require-hashes\`.
8. Runs \`pip check\`, import smoke and inventory checks before publishing the
   canonical \`ROOT/.venv\` activation marker.

The existing second Python at
\`ROOT/.settings_local/acceptance/dependency_environments\` remains untouched
until a separate, verified cleanup. It is never reselected as the runtime.
Do not delete it, or manipulate JSON markers manually, as part of this patch.

### Important failure boundary

An interrupted pip operation can leave optional wheels partly installed,
but must **not** publish a new ready activation marker. The installation is
intentionally additive, not a general-purpose rollback-safe upgrade. A change
to an already installed version requires offline maintenance and separately
tested backup/restore procedure; \`extend\` will refuse rather than modify it.

JSS now rechecks the actual interpreter selected in the first-run wizard.
Manual changes to a foreign executable are refused when finalizing a prepared
ROOT. Dependency Studio's legacy managed layout remains for old checkouts,
but a fresh prepared ROOT must not activate such an environment.

## Release metadata and acceptance

A source patch changes tracked files and invalidates previously generated
PACKAGE_INTEGRITY_MANIFEST and SOURCE_PROVENANCE evidence. Do not declare
release readiness until canonical metadata has been regenerated against a
committed source SHA and \`--check\` reports synchronization:

    & .\.venv\Scripts\python.exe -X utf8 -m latka_jazn.tools.release_metadata_sync --write --json
    & .\.venv\Scripts\python.exe -X utf8 -m latka_jazn.tools.release_metadata_sync --check --json

Use a clean branch/checkpoint for the source SHA before these commands,
because release metadata must reflect committed code. Also run unit/Windows
GUI tests on the exact final SHA and complete TPA and live runtime continuity
checks separately. A successful package verification does not establish a
running daemon, MEMORY continuity, MCP authentication or an accepted ChatGPT turn.
