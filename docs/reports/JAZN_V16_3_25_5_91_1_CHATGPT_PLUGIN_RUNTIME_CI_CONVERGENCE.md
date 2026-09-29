# Jaźń v16.3.25.5.91.1 — ChatGPT plugin runtime CI convergence

## Zakres

Patch naprawia regresje wykryte przez GitHub Actions już po scaleniu v91.0 do master.

## Naprawy

- standalone Pyright: test RFC 7662 nie wykonuje już operatora `in` na wartości typowanej jako `object`; wartość body jest jawnie zawężana do `bytes`;
- OAuth RFC 6749: `client_secret_basic` stosuje pełne `application/x-www-form-urlencoded` dla danych klienta, wraz z regresją dla spacji i znaku `+`;
- host-spawn-memory-convergence: release identity nie zawiera już żadnego zahardkodowanego numeru wydania; sprawdza zgodność `version.py`, zainstalowanej dystrybucji i `run.py --version`;
- aktywne testy wersji zostały przesunięte do 91.1, a ich zatwierdzone postacie 91.0 zachowano w `tests/archive/`;
- wersja patcha: `16.3.25.5.91.1-chatgpt-plugin-runtime-ci-convergence`.

## Stan v91.0 na master

PR #295 został scalony do master i kod plugin runtime jest obecny. Patch 91.1 nie odtwarza ani nie zastępuje funkcjonalności v91.0; domyka bramki CI/release wymagane, aby linia była poprawnym kandydatem do kolejnego scalenia.

## Granica

Metadata `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` nie są edytowane ręcznie. Każdy kolejny source push poprzedza ich ponowną synchronizację przez kanoniczny workflow repozytorium.

## Źródła zewnętrzne zweryfikowane podczas audytu

- OpenAI Developers — `Package your plugin` i `MCP server and UI quickstart`;
- Agent Plugins Specification 1.0.0 — `plugin.json` oraz `mcp.json`;
- MCP Python SDK v2 — authorization, `TokenVerifier`, `AuthSettings`, resource validation;
- RFC 7662 — token introspection;
- RFC 6749 §2.3.1 — `client_secret_basic` i form-encoding danych klienta.


## Finalization regressions found during live runtime audit

During same-turn Jaźń finalization after PR creation, the active runtime exposed two additional source-level inconsistencies:

- a continuation command such as "pracuj ... aż aktualizacja będzie release candidate i gotowa do scalenia" could be routed to `self_architecture_audit_request` instead of `system_update_execution_request`;
- the response-candidate guard accepts bounded host attestations for `GitHub`, while `host_tool_turn_policy` could omit GitHub for an update-continuation turn unless the current sentence repeated a literal repo/branch/commit token.

The 91.1 source line now treats explicit update-continuation goals as execution, requests GitHub for system-update routes while still obeying the live host capability snapshot, and keeps GitHub optional rather than making an unavailable connector a fatal requirement.

The read-only `SelfArchitectureAuditHandler` also now satisfies the two reflection components already required by `RouteRegistry`, with explicit no-write semantics for reflection grounding/store.

This keeps the tool surface narrow and per-turn while preserving continuation of an already authorized update task.


## Neurocognitive release gate

The update-continuation regression is now part of the executable cognitive architecture audit, not only a standalone unit test. The gate verifies that:

- the dialogue classifier keeps an explicit release-candidate continuation on `system_update_execution_request`;
- `NeurologicalSignalRouter` observes both `architecture` and `correction` and selects `architecture_repair`;
- `web.run` is required when external research is requested;
- `GitHub` is requested/allowed for the system-update route only when the host capability snapshot advertises it, and remains optional rather than a fabricated capability;
- host evidence for both Web and GitHub passes the same per-turn tool policy before finalization.

This is a functional software gate. The neurocognitive terminology remains an engineering analogy and is not a biological-neuron claim.
