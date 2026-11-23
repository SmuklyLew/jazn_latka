# v127.23.6 stabilization and acceptance

Base: `fix/v12723-5-dev-monitor-identity-20261123`, commit
`71969f743e382cc714f9620e5057063aa8745f61`.
Branch: `fix/v12723-6-stabilization-20261123`.

This patch does not deploy or restart existing daemons. MEMORY remains off for
validation; all writes in tests use synthetic isolated roots. No EXE or local
dependency installation is needed. Account usage counter: `usage_unknown`.

## Scope and evidence boundaries

| Area | Change / acceptance criterion |
| --- | --- |
| CLI | `start --daemon-port` and historical `start -- --daemon-port` reach the same canonical handler; explicit ROOT is preserved. |
| UTF-8 | Monitor JSON configures UTF-8 stdout/stderr; PowerShell process JSON explicitly emits UTF-8. Existing run.py UTF-8 handling is retained. |
| Workspace | Monitor uses the canonical workspace resolver and root configuration without modifying environment or migrating state. |
| Finalization | UI calls recovery metadata a job result; `completed_job` does not set `accepted_finalization=true`. Missing finalization evidence stays unknown. |
| Ollama evidence | Bounded SourceOriginLedger tail reports an actual historical generated candidate, model, turn and validation. No prompts or answers are returned. Private MEMORY is not opened. |
| Diagnostics | API reachability, model loading, runtime readiness and generation history remain separate; MEMORY disabled is distinct from unknown. |
| VS Code | Remove workspace settings forcing `.venv`; choose the existing external interpreter with Python: Select Interpreter. On this operator host: `D:\.AI\.venv\Scripts\python.exe`. Do not create/install an environment. |
| Qt title | Standalone title is `Tylko odczyt`; Qt supplies the application display name. Integrated JSS retains an explicit Monitor title. |
| Processes | Logical Daemon/Worker roles use verified root, instance, PID and parent birth order. Linux reads `/proc`; Windows reads CIM. Executable image names are unchanged. |
| Multi-instance | Synthetic roots, ports, jobs and ledger data cannot be mistaken for another selected installation. |
| Operator acceptance | `jazn_monitor.py --root ROOT --daemon-port PORT --probe-json` is observational. Never use start/stop/restart to collect acceptance. |
| Release | Windows/Ubuntu source tests, canonical catalog and manifest/provenance synchronization; no binary build workflow is requested. |

## Ollama architecture review

Keep the existing stdlib HTTP adapter and runtime-owned routing/finalization.
The adapter already sends `/api/chat`, `messages`, `stream=false`, explicit
model/token limits and timeouts. It requires `done=true`, retains provider
model/metrics and distinguishes HTTP response errors from transport failures.
The patch fixes duplicate `/api/api` paths, rejects nonpositive/nonfinite
timeouts, provider error objects and explicitly incorrect message roles.
The language retry remains bounded and transport failures are not replayed.
Socket timeout is not a total turn deadline; the daemon owns the overall job
budget. Tags/ps health checks do not generate text or prove a successful turn.

The ledger is historical evidence, not an accepted finalization transaction.
When MEMORY is on, private ledgers are intentionally outside this observer's
scope. No available operational ledger means unknown, never fabricated history.

## Validation checkpoint

- Local host: Windows 11, external `D:\.AI\.venv` (no installation performed).
- Initial focused regression: 53 passed; standalone Qt offscreen smoke exited 0.
- Combined Windows CLI/Ollama/Monitor regression: 105 passed, 1 skipped (native
  Linux `/proc` only), JUnit saved outside the source tree. The initial snapshot
  progress failure reproduces in host temporary paths containing `#`; the same
  existing test passes in the explicit isolated workspace test directory.
  No SQLite policy or private database was changed to work around this.
- Actions/Node24 audit passed; `git diff --check` passed.
- Live operator acceptance of PIDs 2680/30800 and ports 8787/18785 is unverified:
  these PIDs were not visible in the restricted process observation. No lifecycle
  commands were sent to them.
- Full release gate and final-SHA CI remain pending at this checkpoint.

## Primary references

- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Ollama errors](https://docs.ollama.com/api/errors)
- [Python standard streams](https://docs.python.org/3/library/sys.html)
- [Qt window titles](https://doc.qt.io/qt-6/qwidget.html#windowTitle-prop)
- [VS Code environments](https://code.visualstudio.com/docs/python/environments)
- [Windows process names](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.processname)
- [Linux proc filesystem](https://kernel.org/doc/html/v6.11/filesystems/proc.html)
