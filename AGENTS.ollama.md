# AGENTS.ollama.md — kontrakt lokalnego backendu językowego Ollama

Ten plik opisuje wyłącznie integrację Ollamy jako backendu językowego runtime systemu Jaźni. Nie jest operatorem systemu, pamięcią ani źródłem prawdy o aktywności procesu.

**Ten plik nie jest system promptem modelu Ollama.** Nie wolno automatycznie wstrzykiwać jego treści do `messages`, `SYSTEM`, `Modelfile` ani innego kontekstu modelu. Instrukcja służy agentowi lub programiście integrującemu backend; treść wysyłana do modelu powstaje wyłącznie w kanonicznym pipeline runtime.

Jeżeli zadanie wymaga zmiany kodu albo dokumentacji integracji Ollamy, operacje repozytoryjne wykonuj równolegle według `AGENTS.codex.md`.

## 1. Rola i granica prawdy

- Ollama jest backendem generowania kandydata językowego.
- Routing, pamięć, truth gate, walidacja, narzędzia i finalizacja należą do runtime.
- Sam działający endpoint Ollamy nie dowodzi działania systemu Jaźni.
- Brak modelu, endpointu lub zgodnej odpowiedzi prowadzi do jawnego błędu albo kontrolowanego fallbacku, nigdy do fałszywego sukcesu.

## 2. Kanoniczne uruchomienie

Publicznym wejściem operatorskim jest `run.py`:

```bash
python -X utf8 run.py chat-ollama
```

`main.py --chat-ollama` pozostaje techniczną ścieżką zgodnościową, nie drugim równorzędnym operatorem.

Można jawnie wskazać model i endpoint:

```bash
python -X utf8 run.py chat-ollama \
  --ollama-model <nazwa-modelu> \
  --ollama-api-base http://127.0.0.1:11434 \
  --session-id local-runtime
```

Zgodne zmienne środowiskowe:

```text
JAZN_OLLAMA_MODEL=<nazwa-modelu>
JAZN_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Nie wymagaj `OPENAI_API_KEY` dla lokalnej Ollamy.

## 3. Kontrakt transportu

Domyślny lokalny adres API Ollamy:

```text
http://127.0.0.1:11434/api
```

Wymagane operacje:
- wykrywanie modeli: `GET /api/tags`;
- rozmowa: `POST /api/chat`;
- wejście rozmowy w polu `messages`;
- poprawne zakończenie odpowiedzi potwierdzone przez `done=true`;
- obsługa streamingu albo jawne `stream=false` zgodnie z adapterem;
- respektowanie timeoutu, limitu wyjścia i jawnie wybranego modelu.

Lokalny endpoint `http://127.0.0.1:11434` nie wymaga uwierzytelnienia. Bezpośredni dostęp do usług chmurowych Ollamy może mieć inny kontrakt uwierzytelniania i nie może być utożsamiany z lokalnym transportem.

## 4. Diagnostyka

Przed użyciem modelu sprawdź:
1. czy endpoint odpowiada;
2. czy żądany model jest widoczny w `/api/tags`;
3. czy konfiguracja runtime wskazuje adapter Ollama;
4. czy odpowiedź `/api/chat` ma poprawną strukturę;
5. czy runtime zachowuje źródło modelu, metryki i przyczynę zakończenia.

Raportuj oddzielnie stan daemona systemu, stan adaptera, dostępność endpointu, faktycznie użyty model i błąd transportu.

## 5. Windows i proces daemona

Domyślnie daemon może działać z ukrytą konsolą, a stdout/stderr i audyt uruchomień trafiają do host-level `workspace_runtime/daemon/`. Jawna konsola diagnostyczna nie zmienia kontraktu lifecycle: `run.py start` pozostaje właścicielem procesu.
