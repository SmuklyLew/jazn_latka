# Jaźń Studio — system operator cockpit 1.0

## Purpose

Jaźń Studio is an operator client connected to the existing control plane, not a second runtime. The architecture respects AGENTS.md and AGENTS.codex.md. The root run.py and main.py remain the only runtime owners. The application uses tkinter/ttk from the Python standard library; it needs no paid services or API keys.

Six screens:

1. Pulpit — canonical run.py status --json and doctor/model status.
2. MCP i Cloudflare — separate local 127.0.0.1:8080 and remote HTTPS health/readiness, plus the existing MCP tool catalog probe. Health alone does not imply runtime availability.
3. Konfiguracja — GUI preferences and an entrance to the established canonical Configuration Studio. Changes to runtime profiles concern future launches.
4. Aktualizacje — read-only Git state/diff preview, explicit fetch, and a fail-closed merge --ff-only origin/master that requires clean master, stopped daemons 8787 and 8080, fast-forward ancestry, and independent backup confirmation.
5. Diagnostyka — canonical run.py status/doctor/model-status/memory-status/mcp-probe diagnostics.
6. Narzędzia — launches existing Configuration Studio, Tests Studio and Memory Studio rather than duplicating their code.

## Windows entrypoints

From the SYSTEM root:

    cd D:\.AI\jazn_latka_master
    $Python = "D:\.AI\.venv\Scripts\python.exe"
    & $Python -X utf8 tools/jazn_studio.py --smoke
    & $Python -X utf8 tools/jazn_studio.py --json
    & $Python -X utf8 tools/jazn_studio.py --ui window
    & $Python -X utf8 tools/jazn_studio.py --ui text
    & $Python -X utf8 tools/jazn_studio.py --plan-update
    & $Python -X utf8 tools/jazn_studio.py --diagnose mcp_catalog

To build an optional onedir Windows EXE, first explicitly install a compatible PyInstaller, then run:

    pwsh ./tools/windows/build_jazn_studio.ps1 -Python "D:\.AI\.venv\Scripts\python.exe"

EXE result: dist/JaznStudio/JaznStudio.exe. The binary does not contain the SYSTEM, MEMORY, private DB or tokens. For standalone EXE launched outside the repo, configure:

    $env:JAZN_ROOT = "D:\.AI\jazn_latka_master"
    $env:JAZN_STUDIO_PYTHON = "D:\.AI\.venv\Scripts\python.exe"
    & "D:\.AI\jazn_latka_master\dist\JaznStudio\JaznStudio.exe"

If an interpreter isn't explicitly configured, packaged EXE looks for .venv in the SYSTEM root or its parent; runtime diagnostics fail closed when no verified Python executable is found.

## Settings and safety

GUI settings are secret-free and stored at workspace_runtime/jazn_studio/settings.json with schema jazn_operator_studio/v1. The file is outside canonical private MEMORY and only contains validated Cloudflare HTTPS URL, local fixed MCP URL, refresh rate, timeouts, and Python interpreter selection. Writes use expected SHA-256 and atomic os.replace. No global env, MEMORY, SQLite, existing runtime marker or OAuth credentials are written by this Studio.

Use the existing Configuration Studio for validated Jaźń future-launch settings, not this UI's display preferences.

Before updating: back up MEMORY and workspace, stop the Jaźń daemon and MCP listener, verify Git branch/working tree and provenance, and confirm all CI checks. Unmerged pull requests are not included in origin/master. The Studio intentionally rejects dirty working trees including a local hotfix, divergent branches, and unsafe/automatic merges. It never does git reset --hard, force push, or automatic dependency installation. Resolve updates requiring branch integration or conflicts through the project's regular release process.

## Truth boundary

A listener, PID, heartbeat, local tools/list, public healthz or an uploaded SYSTEM archive is never proof of an accepted Jaźń turn. The host-finalization acceptance contract requires display_exact and an approved MessageEnvelope. Cloudflare /mcp stays unavailable until a real, independently verified OAuth resource server and issuer are configured. The UI does not spoof a token nor remove this restriction to make the dashboard green.

## QA and continued development

    python -X utf8 -m compileall -q latka_jazn/tools/jazn_studio tools/jazn_studio.py
    python -X utf8 -m pytest -q tests/test_jazn_operator_studio.py tests/test_jazn_studio_gui_windows.py
    python -X utf8 tools/jazn_studio.py --gui-smoke
    python -X utf8 tools/jazn_studio.py --json
    git diff --check

The dedicated GitHub Actions job builds and smokes the real Tk GUI and PyInstaller on Windows Python 3.12 and 3.14. Project-wide release-hardening is additionally required; PACKAGE_INTEGRITY_MANIFEST.json and SOURCE_PROVENANCE.json must be regenerated through the canonical generator and must not be edited by hand. Until CI is green the branch is an implementation candidate, not a verified distributable.

References: AGENTS.md, AGENTS.codex.md, docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md, docs/tools/CONFIGURATION_STUDIO_V1.md, docs.python.org/3/library/tkinter.ttk.html, docs.python.org/3/library/subprocess.html, docs.github.com/en/rest/releases/releases.
