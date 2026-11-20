# Jaźń v127.23 — Memory Rebuild Studio: source-fidelity hardening

Status: **implementation branch, not release-ready**. Base: `fix/v12722-jazn-monitor-observability-autostart-20261120` at `5d16526c9d7f12067a9d26c167e80e8ca20c081e`.

## Scope and canonical ownership

Only the existing `latka_jazn/tools/memory_rebuild_app` pipeline is changed. No competing importer, live daemon control, MEMORY attach, promotion to L2/L3, or private source publication is introduced.

1. **Embedded ChatGPT HTML**: use incremental JSON-array decoding from `var/let/const jsonData = [ ... ]` for ordinary `.html`/`.htm` inputs, with per-conversation semantic HTML entity normalization. The same iterator feeds the native archive, the versioned L0 adapter and standalone HTML Test00 census. Rendered HTML and HTML inside ZIP retain the previous parser until a separately reviewed bounded parser is implemented.
2. **Archive content truth boundary**: technical `content_type` values (including `thoughts`, `reasoning_recap`, `code`, `execution_output`) remain archived but are classified as non-dialogue and ineligible for direct autobiographical-memory promotion. This does not claim that every retrieval path filters technical L0 documents; typed recall and candidate-generation gates still require end-to-end validation.
3. **Music analysis identity**: prefer explicit stable IDs; otherwise use `numer` plus title; for missing IDs/numbers, use canonical record SHA-256. This prevents distinct analyses with the same title becoming unintended revisions. Review older databases for existing title-key revisions before any migration; no automatic re-keying.
4. **Synthetic regressions**: technical content classification; same-title numbered and unnumbered music analyses; streaming HTML parsed without whole-source `read_text()`, with graph counting, entity decoding and repeat-import idempotence.

## Private evidence boundary

An isolated streaming-parser smoke check on a private HTML source matched the independently established conversation and graph-node counts; this is not the full repository integration suite. Private source counts, dates, paths, message content, media, user history and credentials are not included in this public report. The complete private source collection on Windows has not yet been inventoried or imported.

## Remaining acceptance gates (NOT VERIFIED)

- Run targeted pytest including `tests/test_memory_rebuild_alpha_source_regressions.py` and existing HTML/JSON archive regressions on the actual branch SHA; compileall and Pyright.
- Run independent Test00–Final, large-file peak-RAM checks, idempotent interrupted-import recovery, mixed-version export conflict resolution and source/graph counts on private **isolated** staging.
- Resolve residual whole-file HTML parsing for ZIP and rendered fallback and validate malformed/truncated source behavior.
- Validate atomic recovery between native archive and common L0 writes; they currently use separate connections/transactions.
- Sync package provenance and integrity metadata through the canonical `latka_jazn.tools.release_metadata_sync` command; manifests must **not** be hand-edited. Do not merge or label production-ready while unsynchronized.
- Validate Windows GUI/executable packaging through existing `memory-rebuild-v24-windows` CI, and obtain separate operator approval before attach to live MEMORY.

## Source references

- Python JSON incremental decoding: https://docs.python.org/3/library/json.html
- Python HTML parser: https://docs.python.org/3/library/html.parser.html
- SQLite atomic transactions: https://www.sqlite.org/lang_transaction.html
- SQLite Online Backup API: https://www.sqlite.org/backup.html
- OWASP RAG source boundary: https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html
