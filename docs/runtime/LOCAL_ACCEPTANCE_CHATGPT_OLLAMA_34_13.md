# Lokalny test Jaźni po zielonym PR — v16.3.25.5.116.0.34.13

Branch: `fix/v16.3.25.5.116.0.34.13-chatgpt-ollama-final-connection-hardening`.
Base: `bcf9ecce3d0e239b32613fde7de66e5c42d1f468` (poprzednia gałąź, PR #389).
Nie scalaj, nie zastępuj istniejącego master i nie podłączaj produkcyjnej MEMORY podczas pierwszych testów.

## Windows PowerShell

Otwórz PowerShell w katalogu z istniejącym repo, np. `D:\.AI\jazn_latka_master`.
Przed przejściem na branch sprawdź `git status --short`; jeśli są lokalne modyfikacje, zrób backup lub osobny `git worktree`, nie używaj `git reset --hard`.

Najbezpieczniej utworzyć osobny worktree:

```powershell
Set-Location 'D:\.AI\jazn_latka_master'
git fetch origin
git worktree add 'D:\.AI\jazn_34_13_test' 'origin/fix/v16.3.25.5.116.0.34.13-chatgpt-ollama-final-connection-hardening'
Set-Location 'D:\.AI\jazn_34_13_test'
git rev-parse HEAD
git status --short
```

Jeśli `git worktree add` nie akceptuje zdalnej gałęzi jako detached, użyj:

```powershell
git worktree add --detach 'D:\.AI\jazn_34_13_test' 'origin/fix/v16.3.25.5.116.0.34.13-chatgpt-ollama-final-connection-hardening'
```

Użyj środowiska Python z zainstalowanymi zależnościami Jaźni, np. `D:\.AI\.venv\Scripts\python.exe` (to przykład zgodny z historią konfiguracji, nie gwarancja istnienia na bieżącej maszynie).

```powershell
$py = 'D:\.AI\.venv\Scripts\python.exe'
& $py --version
& $py -X utf8 -m compileall -q latka_jazn tests main.py run.py
& $py -X utf8 -m pytest -q tests/test_ollama_endpoint_evidence.py tests/test_chatgpt_openai_ollama_connection_recovery.py
& $py -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check
& $py -X utf8 run.py doctor --json
& $py -X utf8 run.py package-smoke --profile system --json
```

W razie braku zależności skorzystaj z kanonicznego setup/preflight repozytorium; nie zakładaj, że lokalny folder `.venv` jest w katalogu projektu.

## Żywy test Ollamy (bez OpenAI API key)

```powershell
ollama --version
ollama list
Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
$models = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
$chosen = $models.models | Select-Object -First 1 -ExpandProperty name
$body = @{model=$chosen;stream=$false;messages=@(@{role='user';content='Odpowiedz krótko po polsku'})} | ConvertTo-Json -Depth 8
Invoke-RestMethod 'http://127.0.0.1:11434/api/chat' -Method Post -ContentType 'application/json' -Body $body
& $py -X utf8 run.py chat-ollama --ollama-model $chosen --ollama-api-base 'http://127.0.0.1:11434' --session-id 'jazn-34-13-local-test'
```

Nie należy interpretować `done=true` z Ollamy jako dowodu poprawnej finalizacji całej Jaźni. Do testu ChatGPT potrzebne jest osobne, autoryzowane, rzeczywiście dostępne MCP HTTPS lub Secure MCP Tunnel i komplet czterech narzędzi `jazn_*`. Nie wystawiaj `127.0.0.1:11434` publicznie.

## Akceptacja

- Dokładny SHA brancha oraz wszystkie wymagane checks na ostatnim SHA mają wynik `success`; żaden wymagany check nie ma `failure` ani `pending`.
- `doctor` i `package-smoke` przechodzą.
- Ollama `/api/tags` widzi wymagany tag, `/api/chat` zwraca poprawną ukończoną odpowiedź.
- Rozmowa `chat-ollama` zachowuje sesję, historię i finalizację w wielu turach.
- Zdalny ChatGPT po podłączeniu MCP potwierdza `jazn_status`, pozostałe callable tools, accepted `display_exact` i prawidłowy resume tego samego request_id.

Rollback lokalnego testu: zakończ rozmowę, wróć do `D:\.AI\jazn_latka_master`, a po upewnieniu się, że testowy worktree nie ma niezapisanych zmian: `git worktree remove 'D:\.AI\jazn_34_13_test'`.

Źródła: https://docs.ollama.com/api/chat ; https://docs.ollama.com/api/tags ; https://developers.openai.com/plugins/build/mcp-server ; https://developers.openai.com/plugins/build/auth
