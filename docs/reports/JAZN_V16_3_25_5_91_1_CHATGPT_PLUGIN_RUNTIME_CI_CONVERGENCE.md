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
