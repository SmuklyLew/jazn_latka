# Jaźń v16.3.25.5.116.0.34.41 — first-run and evidence hardening

## Scope and safety

This patch changes source code and tests only. It does not read, migrate, copy or
normalize private operator MEMORY and never deploys Cloudflare. A GitHub commit,
healthy HTTP listener, Ollama `/api/ps` and configured model adapter each prove
different things. None alone proves a finalized visible Jaźń turn.

### First-run CLI (offline by default)

From a verified SYSTEM root:

```powershell
& "D:\.AI\.venv\Scripts\python.exe" -X utf8 tools/jazn_minimal_setup.py --root . --json
& "D:\.AI\.venv\Scripts\python.exe" -X utf8 tools/jazn_minimal_setup.py --root . --probe-ollama --probe-ram --json
```

The default run reports Python, import spec availability, location of the
operator profile and **unverified** runtime/MEMORY/MCP/OAuth state. It performs
no network calls and writes nothing. The optional probe checks local
`/api/tags` (installed model names) and `/api/ps` (currently loaded model
names); an empty `/api/ps` response is **not an Ollama failure**. The optional
RAM probe samples only the current host via Windows `GlobalMemoryStatusEx` or
Linux `/proc/meminfo`, with a UTC timestamp and system source. No unmeasured
RAM utilization may be cited.

To create a **new, missing** future-run profile without overriding existing
settings, operator may explicitly run:

```powershell
& "D:\.AI\.venv\Scripts\python.exe" -X utf8 tools/jazn_minimal_setup.py --root . --create-profile --json
```

This delegates atomic storage and path validation to the existing canonical
Configuration Studio backend and applies only `JAZN_LLM_ROUTE=local` and
`JAZN_MEMORY_MODE=optional`. It refuses to overwrite a current profile and
never restarts a process. It does not replace the independent Dependency
Studio/Configuration Studio/Start Studio, or configure OAuth credentials.

PR #406 proposes separate tracked operator TOML and ignored secrets. That PR
remains independently reviewable; this new CLI does not silently cherry-pick
or consume its files, alter environment precedence or enable paid APIs.
Reconcile PR #406 against this branch before merging the two approaches.

## Normalization status

Snapshot runtime_version is provenance, not a compatibility contract.
`schema_version`, `fingerprint_contract_version`, coverage, logical schema,
row revisions and (on deep verify) source contents determine freshness.

After a runtime version bump, bounded `status()` reports
`normalization_unverified` and requests a deep check; it **never** assumes
that memory is either stable or stale. Explicit `deep_verify=True` can report
`ready` only when the stored fingerprints and the current logical contents
match and SQLite structural/foreign-key checks pass. Missing old fingerprints
remain `normalization_stale`; changed content becomes `source_changed`.
A historic `status=ok` on an old run never proves current readiness.

```powershell
& "D:\.AI\.venv\Scripts\python.exe" -X utf8 run.py --normalize-memory-sidecar --dry-run
& "D:\.AI\.venv\Scripts\python.exe" -X utf8 run.py memory-validate --root . --json --progress
```

Neither command is a license to rewrite MEMORY. Before any later writes, use a
consistent SQLite online backup and explicit operator acceptance. Never infer
autobiographical recall from a snapshot containing only procedural rules.

## Model and telemetry truth boundaries

`response_candidate_generator.py` now attaches
`adapter_response.turn_evidence` to adapter candidates where the response is
a concrete `ModelAdapterResponse`. It binds `turn_id/trace_id`, reports actual
adapter response status, and distinguishes observed generated text from model
names inferred from config. A provider model identity is confirmed only when
a transport response includes `actual_model` matching the adapter response.
This is **candidate evidence**, not evidence that the candidate was chosen
for the final visible answer; finalization and source-origin ledger remain
independent gates.

The `--model-adapter-status` handler explicitly says its configured
provider/model are diagnostics, not evidence of generating a visible turn.
Host RAM evidence must come from direct OS sampling with origin and timestamp;
a prior unsourced percentage (e.g. 78%) must not be repeated as fact.

## Acceptance gates

- New tests: `tests/test_memory_normalization_release_freshness.py`,
  `tests/test_minimal_setup_preflight.py`,
  `tests/test_model_turn_and_host_telemetry_evidence.py`.
- Existing normalization, recall, model candidate and Configuration Studio tests
  must remain green.
- CI: Pyright, compileall, Python Windows/Linux deterministic tests, release
  manifest synchronization, PowerShell regressions, system package-smoke.
- No Cloudflare deployment and no memory rebuild in CI.

## Primary external references

- https://github.com/ollama/ollama/blob/main/docs/api.md
- https://learn.microsoft.com/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
- https://www.sqlite.org/backup.html
