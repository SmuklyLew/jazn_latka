# Jaźń w GitHub Codespaces — ręczny test daemona

Ten profil umożliwia uruchomienie kodu Jaźni na **tymczasowej** maszynie Codespaces (Python 3.12). Nie uruchamia daemona automatycznie, nie publikuje portu MCP, nie importuje prywatnej pamięci i nie tworzy połączenia ChatGPT. Należy go uruchamiać na osobnym branchu; `master` pozostaje nietknięty do czasu review/PR.

## Uruchomienie

1. Na stronie repozytorium wybierz branch zawierający ten plik, następnie **Code → Codespaces → Create codespace on ...**. GitHub może naliczać minuty i pamięć maszynową; sprawdź dostępny bezpłatny limit przed utworzeniem.
2. Codespaces wykonuje jednorazowy `postCreateCommand`: tworzy odrębne virtualenv w ignorowanym przez Git `workspace_runtime/codespaces-venv`, instaluje kanoniczny profil `.[mcp-http]` i pokazuje wersję. To dowód przygotowania środowiska, **nie** dowód działającego daemona.
3. W terminalu Codespace, z katalogu głównego projektu:

```bash
PY=workspace_runtime/codespaces-venv/bin/python
"$PY" -X utf8 run.py host-preflight --json
"$PY" -X utf8 run.py doctor --json
"$PY" -X utf8 run.py start
"$PY" -X utf8 run.py status --json
```

Jeżeli `start` albo `status` raportuje problem, zachowaj pełny kod błędu w prywatnych logach i **nie** deklaruj gotowości. Wymagany jest świeży live status, identyfikator zgodnej instancji, poprawny root/wersja i heartbeat. Program może uruchomić swój rdzeń bez OpenAI API, ale **bez backendu LLM lub wywoływalnego hosta ChatGPT nie uzyska kanału generowania odpowiedzi ChatGPT**. W Codespaces nie masz też automatycznie dostępu do lokalnej Ollamy z Windows.

## Zatrzymanie i koszty

```bash
"$PY" -X utf8 run.py stop
```

Zatrzymaj też Codespace z interfejsu GitHub, aby ograniczyć zużycie godzin. Codespaces nie jest stabilnym, nieprzerwanym hostingiem produkcyjnym; zasoby i stan mogą być wyłączane lub usuwane według zasad usługi.

## MCP i prywatność

- Port **8080 nie jest automatycznie przekazywany ani wystawiany publicznie**. `mcp-http --loopback-dev` jest wyłącznie do lokalnego testowania, nie do publicznego `https://.../mcp`.
- Zewnętrzne połączenie z ChatGPT wymaga osobno publicznego HTTPS, poprawnego OAuth/TokenVerifier, host/origin policy, instalacji i wywoływalności wszystkich czterech narzędzi `jazn_*` oraz dwóch zaakceptowanych tur. Nie zmieniaj portu na **Public** bez kompletnego produkcyjnego uwierzytelniania i testu bezpieczeństwa.
- Nie kopiuj do repozytorium `memory/`, SQLite, ZIP-ów pamięci, sekretów, API keys ani logów. Opcjonalną MEMORY dołączaj wyłącznie osobnym zweryfikowanym procesem.
- `postCreateCommand` wymaga dostępu sieciowego do pobrania zależności. Nie instaluje modeli LLM ani nie używa OpenAI API.

Źródła:
- GitHub: https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository
- GitHub: https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
- Projekt: [połączenie ChatGPT MCP](../docs/runtime/CHATGPT_MCP_CONNECTION_RECOVERY.md), [deployment](../deploy/chatgpt_mcp/README.md), [AGENTS](../AGENTS.md)
