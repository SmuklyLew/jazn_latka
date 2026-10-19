# Jaźń v16.3.25.5.116.0.34.13 — Endpoint evidence i acceptance ChatGPT/Ollama

Wydanie następcze wobec gałęzi PR #389, niezależny branch `fix/v16.3.25.5.116.0.34.13-chatgpt-ollama-final-connection-hardening`.

## Naprawione

- HTTP 200 z nieprawidłowym JSON lub niekompletnym `done` od Ollamy pozostaje `invalid_provider_response`, a nie „serwer niedostępny”.
- Niepoprawny JSON lub niepoprawna struktura `/api/tags` jest błędem kontraktu odpowiedzi przy zachowanej informacji o dostępności HTTP.
- Status HTTP 4xx/5xx dowodzi otrzymania odpowiedzi od endpointu, ale nie dowodzi gotowości backendu ani poprawnej generacji.
- Tylko błędy transportu/timeout oznaczają endpoint unreachable; błąd budżetu kontekstu nie zmienia bieżącego statusu endpointu.
- Nowe, wyizolowane testy sprawdzają każdy przypadek bez żywego modelu; osobny test end-to-end wymaga rzeczywistego operatora.

## Granice

Błędy hosta ChatGPT przed utworzeniem procesu nie są naprawialne przez systemowy ZIP. Wdrożenie i autoryzacja MCP pozostają działaniami poza repozytorium. Nie wykonano live call MCP ani połączenia z komputerem użytkownika. Brak OpenAI API key jest możliwy dla lokalnego Ollama, ale nie znosi wymogów podłączenia odpowiednio zabezpieczonego MCP.

## Testy

- `tests/test_ollama_endpoint_evidence.py`, `tests/test_chatgpt_openai_ollama_connection_recovery.py`.
- `pytest` non-live, `compileall`, Pyright, Test Studio catalog check, release-hardening, Windows PowerShell, cleanroom, MCP conformance, persistent-runtime-e2e (obowiązkowe na końcowym SHA).
- Lokalny operator: `docs/runtime/LOCAL_ACCEPTANCE_CHATGPT_OLLAMA_34_13.md`.

## Istotna poprawka dokumentacji historii .34.12

Wbrew pierwotnemu sformułowaniu .34.12 część aktywnych testów release identity była modyfikowana po pierwszym commicie. Ich źródła przechowuje historyczny snapshot na gałęzi źródłowej.

## Źródła

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/tags
- https://developers.openai.com/plugins/build/mcp-server
- https://developers.openai.com/plugins/build/auth
