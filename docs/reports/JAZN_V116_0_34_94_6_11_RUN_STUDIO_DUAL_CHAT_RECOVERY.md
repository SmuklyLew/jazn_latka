# Jaźń 16.3.25.5.116.0.34.94.6.11 — Run Studio dual-chat recovery

Status: **branch implementation checkpoint / draft for review**, NOT a release, not a live ChatGPT ingress proof.
Base master: `759014304bfa5b38c0502ec33345e27fe96f5f5d`.
Branch: `fix/run-studio-dual-chat-recovery-20261028`.
No edits to `memory/`, `workspace_runtime/`, private SQLite or the active daemon.

## Incident and diagnosed evidence

The 2026-10-28 operator evidence showed:
- the local Jaźń daemon had verified process identity and live readiness at one observed time;
- the MCP gateway exited with status 1 after `ModuleNotFoundError: pydantic`, with missing `mcp`, `uvicorn`, `starlette` and `pydantic` in the detected Studio interpreter;
- the Ollama API sometimes returned `gemma3:latest` and then an empty model list, so available API was not usable generation;
- local chat exited 3, resume exited 1, and the report's `accepted_visible_turn` was hard-coded false;
- the runtime services table diverged from the header/sidebar readiness labels.

The mismatch in Ollama's model directory/user environment is **a hypothesis**, not a confirmed root cause; do not download or move models automatically.

## Implemented scope

1. **Selected-interpreter MCP preflight.** Before `service:gateway` is reserved or spawned, Studio runs an isolated, bounded import check using the same explicitly selected Python executable as the gateway. It checks `mcp`, `uvicorn`, `starlette`, `pydantic` and shows missing module names without installing dependencies or claiming host readiness.
2. **Ollama observation.** Missing model list is a distinct failure reason. A new explicit button calls the local `/api/chat` with short, bounded non-streaming output, and only marks **model API generation** verified after a non-empty assistant payload and `done=true`. This does not constitute Jaźń finalization or a ChatGPT turn.
3. **Local chat and recovery.** CLI and resume keep the same request identity; stderr failure codes are reported without copying unvalidated candidate responses or user input. A successful pending poll is not misreported as a fatal resume failure.
4. **Accepted-visible-turn report.** Previously unconditional `false` becomes `null` when no accepted GUI turn was observed. `true` requires actual GUI presentation followed by successful checkpoint acknowledgment. Report evidence contains only bounded IDs and UTC timestamp, not message text.
5. **Qt workspaces.** `Czat lokalny` shows an Ollama model selector, generation test, transcript and replay-safe resume. `Połączenie z ChatGPT` is a separate connection control page with runtime, MCP gateway, tunnel and independent external authorization/toolset/host-turn boundaries. Tunnel start still requires user approval; local chat disconnection does not terminate unrelated services.
6. **Synchronized status evidence.** The verified runtime observation updates the same header and sidebar labels. It does not claim the host accepted an answer.

## Validation and release gates

New tests (run on a working Python environment before merging):
```powershell
python -X utf8 -m pytest -q tests/test_heart_system_connection_recovery.py tests/test_heart_system_ollama_generation.py tests/test_heart_system_connection_panels_qt.py
python -X utf8 -m pytest -q tests/test_jazn_run_studio_integrations.py tests/test_heart_system_dashboard_qt.py
python -X utf8 tools/jazn_run_studio/check_types.py
git diff --check
```

**Not executed in the authoring host:** local process spawning was unavailable. CI must be reviewed and remaining Windows/Qt/runtime integration acceptance run. There is no observed live MCP/OAuth/tunnel acceptance, no proof of a working ChatGPT conversation, and no automatic migration of MEMORY.

**Release metadata pending** — run the canonical synchronizer in a clean build worktree, then verify idempotency and CI; do not hand-edit the manifests:
```powershell
python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json
```
Do not install any optional MCP dependency or replace live daemons without operator consent. For missing gateway imports, use the project's official optional `.[mcp-http]` profile in the selected interpreter, through the trusted Dependency Studio/verified wheelhouse workflow.

## Official references

- MCP Python SDK installation and HTTP dependencies: https://py.sdk.modelcontextprotocol.io/ and https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/installation.md
- MCP Streamable HTTP (not legacy SSE): https://py.sdk.modelcontextprotocol.io/run/
- Ollama API (`/api/tags`, `/api/chat`, terminal `done`): https://github.com/ollama/ollama/blob/main/docs/api.md
- Qt thread and GUI ownership: https://doc.qt.io/qtforpython-6.11/PySide6/QtCore/QThread.html
- OpenAI plugin authentication: https://developers.openai.com/plugins/build/auth
- OpenAI MCP remote / Secure MCP Tunnel boundary: https://developers.openai.com/plugins/build/mcp-server

None of these documents alone proves a deployed and callable Jaźń MCP app in the current ChatGPT turn.
