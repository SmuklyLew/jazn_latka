# ChatGPT main-first bootstrap and MEMORY storage operations

Version: 16.3.25.5.116.0.34.20. Scope: code, paths, lifecycle and database contracts. Never import private MEMORY from a test archive during SYSTEM activation without an explicit, separate verified attach.

## Host-owned work vs Python-owned work

Before an active root exists, the host may inspect real tool capabilities, locate one exact SYSTEM ZIP, validate trusted SHA-256/size, inspect ZIP paths and CRC, and run the standalone stdlib `CHATGPT_BOOTSTRAP.py` only after Python process creation is confirmed. If there is a valid already-materialized root use warm/resume; do not re-extract or rehash on every message. An unexposed MCP toolset is **not** a blocker for local ZIP bootstrapping. A host `ClientError` before process creation is not a Python or Jaźń exception. Raw `extractall()` is not an approved substitute.

After `materialized_operator_ready`, read `AGENTS.md` and `AGENTS.chatgpt.md` exactly from that verified root, then invoke canonical `run.py` commands (which forward unchanged argv to `main.py`). Do not imitate daemon, memory, model, or phase-2 behavior using host prose. Do not read hundreds of source modules as an executable prompt. Complete `run.py host-preflight --json`, authorized `run.py start` or idempotent `host-op` submit/status, `run.py status --json`, and `run.py chat-gpt` / current verified MCP toolset. A visible Jaźń reply requires accepted `display_exact` finalization of the same request. Dependency installation is an external write capability: absent authorization, set `JAZN_DEPENDENCY_AUTOBOOTSTRAP=0` for host commands; diagnosis does not auto-install.

## Storage roots: resolve dynamically, never hardcode the checkout layout

- `active_root` is verified by package manifest, release provenance and runtime marker. The default canonical private MEMORY root is `<active_root>/memory` via `latka_jazn.memory.memory_root.resolve_memory_root()` / `JaznConfig.memory_root`.
- `JAZN_MEMORY_ROOT` may explicitly select a different root; a relative path is anchored to `active_root` and traversal outside it is rejected. With no override, an existing older `<workspace_runtime>/memory` payload can be selected for read compatibility. This is **not** an automatic migration.
- `workspace_runtime` itself is computed by `latka_jazn.core.runtime_root.workspace_runtime_path()` (some versioned roots share a sibling workspace). `JAZN_RUNTIME_WORKSPACE_DIR` is an explicit override. Do not assume it is `<active_root>/workspace_runtime`.
- Core process state, checkpoints and runtime write-through when private MEMORY is absent use `<workspace_runtime>/core_state` and `<workspace_runtime>/core_state/memory_runtime`, **not** autobiographical MEMORY. A lexical cache may reside at `<workspace_runtime>/dictionary_cache.sqlite3`; this does not establish recall.

## SQLite and other data identities

| Logical role | Root-relative identity / resolver | Use and safety boundary |
|---|---|---|
| Native autobiographical unified DB | `<selected_memory_root>/sqlite/memory_jazn.sqlite3`; `CANONICAL_DATABASE_NAME` | Read-only recall and, only after successful verification, transactional tier may reuse it. Supported schema identities `jazn_unified_memory/v2.4`, `v2.5`, `v3.0`; never equate file existence with readiness. |
| Transactional L1/L2/L3 fallback | `<selected_memory_root>/sqlite/runtime_write_v2/runtime_memory.sqlite3`; `resolve_memory_tier_database_path()` | Used if native unified candidate is not ready and private MEMORY is enabled. Only authorized runtime writes; transactional search readiness alone is not autobiographical readiness. |
| Historical runtime-write DB | `<selected_memory_root>/sqlite/runtime_write_v1/runtime_memory.sqlite3` | Compatibility/legacy runtime storage. Do not promote to unified MEMORY by renaming or copying. |
| Recovered/normalization DBs | `sqlite/recovery_current/runtime_memory_recovered.sqlite3`, `sqlite/runtime_write_v1/normalization_sidecar.sqlite3` | Recovery inputs/derived state; verify source identity before using. Not replacements for a native unified DB. |
| Conversation archive DB | `sqlite/conversation_archive_v1/conversation_archive_manifest.sqlite3` | Manifest of historical archive; FTS and staging directories are separate, not native unified readiness. |
| Audit and rest ledgers | `sqlite/runtime_write_v1/runtime_audit.sqlite3`, `sqlite/runtime_write_v1/rest_cycle.sqlite3` plus shard manifests | Read operational/audit identities via `JaznConfig` and shard manager; never infer autobiographical recall from them. |
| Older import sources | `archive_chats.sqlite3`, `journal.sqlite3`, `experience.sqlite3`, `import_catalog.sqlite3` | Legacy reconstruction inputs, **not** independently active unified recall; migration is explicit and verified. |

`JaznConfig` exposes per-role accessors; changing `JAZN_*_DB` env variables is an explicit operator override, not a reason to migrate files. No database bytes, SQLite WAL/SHM, secrets or runtime data should be committed in SYSTEM. `memory/` and `workspace_runtime/` must be excluded from static package integrity.

## Readiness and safe SQLite usage

1. `JAZN_MEMORY_MODE=optional` (default) lets core SYSTEM start with no private MEMORY. `off` disables use; `required` is explicit operator policy and can block startup if missing. Never silently change the default to required.
2. Use `resolve_memory_root_diagnostic()` and `build_memory_availability_status()` for no-private-record path selection evidence. A file or candidate marker proves only possible presence.
3. `probe_unified_memory_database()` opens with `connect_runtime_readonly()`, `query_only=ON`, verifies schema, tables/FTS, `PRAGMA quick_check` (or `integrity_check` when requested) and `foreign_key_check`. See SQLite official PRAGMA guide: https://www.sqlite.org/pragma.html . A successful quick check without FTS/provenance validation is insufficient.
4. To assert autobiographical recollection require `full_autobiographical_recall_ready=true`, `continuity_ready=true` when claiming continuity, and local MEMORY source provenance for memory items actually used. Do not infer these from `memory_search_ready=true` alone.
5. If an authorized, separate MEMORY package is presented, use existing `run.py memory-converge` while daemon is inactive; it performs verified extraction, schema/inventory validation, atomic installation, recovery and readiness. Never manually paste DBs into a versioned release, unzip with unchecked paths, run ad-hoc SQL writes, or copy a live WAL/SHM pair.
6. Any SQLite mutation/backup must use the canonical runtime writer and lock discipline, with proper SQLite backup/transaction handling; never clone a live DB as a bare file copy. `latka_jazn.db.runtime_sqlite` chooses WAL only on SQLite builds with the documented WAL-reset fix, otherwise DELETE.

## Acceptance matrix

Cold: validated ZIP => materialized operator => AGENTS/runbook => dependency-safe preflight => daemon live; warm: same verified root/recent daemon => reuse; resume: valid root but no daemon => canonical `start`. Remote: complete currently callable MCP tools plus live status. No route: explicit fail-closed diagnostics. SYSTEM-only mode must not create artificial private MEMORY. When MEMORY is available, native unified readiness and provenance must be checked separately. One user message must bind exactly one request, and phase-2 must accept `display_exact` before displaying a Jaźń-authored answer.

Sources: Python stdlib `sqlite3` and `zipfile`; https://www.sqlite.org/pragma.html ; https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt ; https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax .
