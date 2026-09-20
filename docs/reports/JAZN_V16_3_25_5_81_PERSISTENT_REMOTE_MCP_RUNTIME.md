# Jaźń v16.3.25.5.81 — Persistent Remote MCP Runtime

## Cel

Aktualizacja rozwija istniejącą architekturę v73–v79 zamiast dodawać pojedynczy
szkielet.  MCP jest transportem do jednego persistent runtime Jaźni, a nie
alternatywnym runtime.

## Podstawa protokołu

Implementacja jest projektowana pod MCP 2026-07-28: stateless core, jawne
per-request capabilities, cacheable list/read results, standardowe nagłówki
Streamable HTTP i Tasks jako extension `io.modelcontextprotocol/tasks`.

## Zakres

- modern MCP server reklamuje Tasks dopiero na ścieżce 2026-07-28;
- task handle jest trwały i mapuje się na istniejący daemon_request_id;
- registry Tasks jest SQLite w `workspace_runtime/mcp_tasks.sqlite3`;
- historyczne JSON task records są migrowane leniwie bez usuwania;
- resources/read są prywatnie cacheable, listy publicznie cacheable;
- public Streamable HTTP i Secure MCP Tunnel są dwiema trasami do tego samego runtime;
- remote failover pozostaje fail-closed i wymaga niezależnego auth/protocol/health/readiness/host-capability evidence;
- local executor failure nie może być przedstawiony jako awaria ZIP/runtime.

## Granica MRTR

Warstwa taskowa potrafi reprezentować `input_required`, ale obecne visible-turn
tools Jaźni nie emitują jeszcze takiego stanu. `tasks/update` nie udaje
konsumpcji odpowiedzi przez runtime: bez jawnego runtime input transport kończy
fail-closed.  Pełny host-input transport należy dodać przed oznaczeniem MRTR jako
aktywnej capability wykonawczej.

## Źródła

- MCP 2026-07-28 specification/blog;
- Tasks extension SEP-2663;
- Streamable HTTP SEP-2243;
- OpenAI ChatGPT developer mode / remote MCP guidance;
- MCP Python SDK v2 documentation and known Tasks-extension gap.

## Truth boundary

Żaden endpoint, task handle, tunnel process ani heartbeat samodzielnie nie jest
dowodem accepted visible turn.  Widoczna odpowiedź nadal wymaga istniejącej
lineage i finalizacji Jaźni.
