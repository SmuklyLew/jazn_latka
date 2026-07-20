# AGENTS.ollama.md — Ollama jako jawny lokalny backend

Ollama jest opcjonalnym lokalnym backendem językowym. Nie jest Jaźnią, pamięcią, kanonem ani źródłem stanu runtime.

## Kanoniczna komenda

```powershell
py -X utf8 main.py --chat-ollama --session-id local-runtime
```

Konfiguracja:

```text
JAZN_OLLAMA_MODEL=<nazwa-modelu>
JAZN_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

## Kontrakt API

- status modeli: `GET /api/tags`;
- generacja rozmowy: `POST /api/chat`;
- lokalny endpoint nie wymaga klucza API;
- model i endpoint muszą być jawnie skonfigurowane;
- brak Ollamy lub modelu prowadzi do prawdomównego fallbacku.

## Granica prawdy

Ollama jest wymienną warstwą językową. Tożsamość, pamięć, routing, walidacja i decyzje o narzędziach należą do runtime Jaźni. Model nie może sam zatwierdzać pamięci L2/L3 ani deklarować wykonania narzędzia bez wyniku runtime.
