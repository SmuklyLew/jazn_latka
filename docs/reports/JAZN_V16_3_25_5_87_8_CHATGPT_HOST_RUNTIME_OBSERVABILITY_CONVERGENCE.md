# Jaźń v16.3.25.5.87.8 — ChatGPT host/runtime observability convergence

## Cel

Ta aktualizacja implementuje wnioski z raportu diagnostycznego dotyczącego `ClientError`, host executora i persistent `remote_runtime` dla v16.3.25.5.87.7. Nie próbuje maskować ani „naprawiać” platformowego błędu, który występuje przed utworzeniem procesu. Rozszerza evidence tak, aby następne wystąpienie było możliwe do rozróżnienia oraz aby wszystkie niespełnione gate'y zdalnego runtime były widoczne jednocześnie.

## Granica odpowiedzialności

Błąd hosta przed `process_created=true` nadal klasyfikuje wyłącznie daną powierzchnię jako `host_executor_unavailable`. Filesystem, paczka i runtime pozostają niezweryfikowane. Kod Jaźni nie może utworzyć capability ChatGPT, opublikować aplikacji MCP ani naprawić wewnętrznego provisioningu executora OpenAI.

Zewnętrzna dokumentacja OpenAI rozdziela te warstwy:

- Developer mode / MCP apps: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- Secure MCP Tunnel: https://developers.openai.com/apps-sdk/guides/secure-mcp-tunnel

Lokalny prywatny MCP wymaga zdalnego endpointu albo Secure MCP Tunnel, a tunnel pozostaje transportem; host nadal musi expose'ować właściwą app/connector capability.

## Zmiany

1. `HostExecutorObservation` przechowuje bounded `error_code`, `error_message`, `host_request_id` i `observed_at_utc`.
2. `error_message` jest normalizowany, ograniczony do 1024 znaków i redaguje typowe nagłówki auth/cookie, bearer tokeny, sekrety/tokeny przypisane przez `=` lub `:` oraz klucze `sk-...`.
3. Aggregate payload eksportuje te pola bez zmiany semantyki `process_created`.
4. Public Streamable HTTP publikuje pełne `blocking_checks` dla wszystkich niespełnionych warunków, zachowując istniejący priorytetowy `reason_code`.
5. Secure MCP Tunnel publikuje granularne blokery `process_running`, `healthy`, `ready`, connector capability, runtime binding/version i freshness.
6. Preflight propaguje blocker matrix do `remote_runtime_blockers`; brak remote evidence jest jawny jako `remote_runtime_evidence_missing`.
7. Pozytywna trasa z niepustą listą blockerów jest odrzucana jako sprzeczny stan.
8. `AGENTS.chatgpt.md` opisuje nowe bounded evidence i zakaz umieszczania sekretów.
9. Dodano osobny zestaw regresji bez modyfikowania historycznych aktywnych testów.

## Zachowana kompatybilność

- `reason_code` pozostaje kompatybilny i nadal wskazuje pierwszy priorytetowy powód.
- `blocking_checks` / `remote_runtime_blockers` są addytywne i diagnostyczne.
- Sam boolean `remote_runtime_transport_available=true` nadal nie może awansować niezaufanego wejścia bez zweryfikowanego transport evidence.
- Fail-closed dla pre-process `ClientError` / `TransportTimeoutError` pozostaje bez zmian.
- Brak connector capability nadal wystarcza do zablokowania `remote_runtime`, nawet przy zdrowym tunelu.

## Walidacja release

Branch podlega istniejącym workflow `persistent-runtime-e2e` oraz `release-hardening`: compileall, Pyright, deterministic pytest, Windows/Linux dependency matrix, runtime/MCP regressions i synchronizacja kanonicznych release metadata. `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` nie są edytowane ręcznie.
