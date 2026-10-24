# Verified implementation sources

Retrieved 2026-10-22. Primary vendor documentation is authoritative for external
APIs; repository source is authoritative for Jaźń contracts. Links are recorded
by feature so subsequent stages can verify signatures without repeating discovery.

| Feature | Primary source | Consequence |
| --- | --- | --- |
| Qt installation and Widgets | https://doc.qt.io/qtforpython-6/gettingstarted.html | Optional PySide6 Widgets shell; no Qt requirement in core |
| Linux GUI system dependencies | https://doc.qt.io/qt-6/linux-requirements.html | Headless CI still needs Qt shared graphics libraries; use offscreen without skipping GUI assertions |
| External processes / async state | https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html | Running is distinct from completion; never block GUI waiting for work |
| GUI thread boundaries | https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html | Workers publish data, only GUI thread touches widgets |
| Child process execution and timeout | https://docs.python.org/3/library/subprocess.html | argv arrays, shell=False, retained ownership handles, terminate/wait/kill |
| Native deployment | https://doc.qt.io/qtforpython-6/deployment/index.html | Existing repo PyInstaller approach retained; Qt provides other deployment tooling |
| PyInstaller onedir and options | https://pyinstaller.org/en/stable/usage.html | External SYSTEM remains separate; explicit build/work/dist locations |
| Frozen external child process environment | https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html | Restore external DLL paths and original Unix library variables when spawning system tools |
| Qt license notices | https://doc.qt.io/qtforpython-6/licenses.html | Distribution review is a release gate; no invented project license |
| Ollama model discovery | https://docs.ollama.com/api/tags | GET /api/tags is model listing, not proof of accepted Jaźń generation |
| cloudflared installation | https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/ | Official installation links only |
| Configured Windows tunnel service | https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/as-a-service/windows/ | Existing service is separately owned; Studio only stops its own child |
| User visual reference | https://github.com/ntrospect0/glint | Inspiration only; no copied source or license assumptions |

Relevant local sources: `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.ollama.md`,
`docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`,
`docs/runtime/TURN_FINALIZATION_CONTRACTS.md`, `main.py`, `latka_jazn/cli.py`,
`latka_jazn/core/runtime_lifecycle.py`, `latka_jazn/core/chat_command_contract.py`,
`latka_jazn/tools/jazn_studio/core.py`, `latka_jazn/tools/configuration_studio.py`,
`latka_jazn/tools/application_shell/`, `tools/jazn_start_studio.py` and its dashboard.

GitHub Actions reused full SHA pins from the repository audit contract. The
official `action.yml` at each SHA was read via GitHub API; all declare node24:

- checkout `3d3c42e5aac5ba805825da76410c181273ba90b1`
- setup-python `5fda3b95a4ea91299a34e894583c3862153e4b97`
- upload-artifact `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`

The user-mentioned PNG was not present alongside the supplied objective file.
The Medium examples are visual suggestions, not relied-on API documentation.

Continuation sources checked 2026-10-23: Python's
https://docs.python.org/3/library/pathlib.html#pathlib.Path.is_file documents
file-query semantics, without promising a fixed internal stat-call count;
https://docs.python.org/3/library/tkinter.html#threading-model describes shared
event queues and cautions about multiple Tk interpreters in one thread;
https://docs.ollama.com/api/chat documents messages, done and completion metrics.
The request/session/turn binding fix is derived from the canonical
DaemonConversationSession and runtime_daemon._unwrap_daemon_chat_job source,
and a captured isolated synthetic live turn, rather than a guessed API shape.

The malformed-HTTP diagnosis follows Python's documented transport exception
boundary: https://docs.python.org/3/library/http.client.html#http.client.HTTPException.
Server serialization versus receiving-socket capture was compared in an isolated
synthetic gateway. Do not infer the responsible filtering product from its mere
presence, and never accept raw bodies after an HTTP framing failure.

Frozen/redirected output encoding follows Python TextIOWrapper.reconfigure
https://docs.python.org/3.14/library/io.html#io.TextIOWrapper.reconfigure and
https://docs.python.org/3.14/using/cmdline.html#envvar-PYTHONIOENCODING.
An inherited PYTHONIOENCODING overrides UTF-8 mode for child standard streams;
Studio explicitly configures both its own streams and external process pipes.

P1 completion sources checked 2026-10-24:
https://www.sqlite.org/limits.html documents SQLITE_LIMIT_LENGTH as both a
string/BLOB and encoded-record limit. Python exposes the per-connection guard
through https://docs.python.org/3.14/library/sqlite3.html#sqlite3.Connection.setlimit.
The comparator also enforces its existing index/time budgets. The new Qt view
calls the existing P1 services through run.py/main.py; it does not reconstruct
the daemon verifier or infer recall/activation from configured database evidence.
