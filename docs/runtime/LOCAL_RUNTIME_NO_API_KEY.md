# Lokalny runtime Jaźni bez `OPENAI_API_KEY`

## Trzy różne ścieżki

**ChatGPT-host** oznacza, że bieżący host ChatGPT rzeczywiście udostępnia filesystem/executor
i uruchamia `run.py`. Nie jest to bezkluczowe API do subskrypcji ChatGPT.

**Ollama** jest lokalnym backendem modelowym. Typowy endpoint:
`http://127.0.0.1:11434/api/chat`. Lokalna Ollama nie wymaga `OPENAI_API_KEY`.

**OpenAI API / OpenAI-compatible endpoint** to osobna, jawnie skonfigurowana ścieżka.
Subskrypcja ChatGPT i OpenAI API nie są tym samym transportem.

## Entry point
Publicznym operatorem pozostaje `run.py`.
`main.py` jest warstwą zgodnościową/implementacyjną, chyba że aktualny `AGENTS.md`
jawnie określi inaczej.

## Evidence dla ChatGPT-host
Runtime-backed turn wymaga rzeczywistego wykonania:
verified root → `run.py` → PID/process identity + readiness + heartbeat →
dokładna tura `chat-gpt` → finalization.

Styl Łatki, ZIP, sama obecność kodu lub PID bez weryfikacji nie są dowodem aktywnej Jaźni.

Jeśli host zwraca błąd executora przed powstaniem procesu, runtime pozostaje `unverified`.
Nie oznacza to automatycznie uszkodzenia ZIP-a ani `run.py`.

## Ollama
Przykład PowerShell:

```powershell
ollama serve
$env:JAZN_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:JAZN_OLLAMA_MODEL = "<model>"
python -X utf8 run.py chat-ollama
```

## Setup
`setup.ps1 venv` / `setup.sh venv` tworzy `.venv` bez automatycznej instalacji sieciowej.
Tryb `online` jest jawny. Dla release offline nadal używaj repozytoryjnego wheelhouse/hash-lock.
