# AGENTS.ollama.md — kontrakt lokalnego backendu językowego Ollama

Ten plik opisuje wyłącznie integrację Ollamy jako backendu językowego runtime systemu Jaźni. Nie jest operatorem systemu, pamięcią, tożsamością runtime ani źródłem prawdy o aktywności procesu.

**Ten plik nie jest system promptem modelu Ollama.** Nie wolno automatycznie wstrzykiwać jego treści do `messages`, `SYSTEM`, `Modelfile` ani innego kontekstu modelu. Instrukcja służy agentowi lub programiście integrującemu backend; treść wysyłana do modelu powstaje wyłącznie w kanonicznym pipeline runtime.

Jeżeli zadanie wymaga zmiany kodu albo dokumentacji integracji Ollamy, operacje repozytoryjne wykonuj równolegle według `AGENTS.codex.md`.

## 1. Rola i granica tożsamości

- Ollama jest backendem generowania kandydata językowego.
- Model Ollama nie jest właścicielem pamięci, tożsamości, lifecycle ani finalizacji Jaźni.
- Routing, pamięć, self-state, truth/epistemic gate, narzędzia i finalizacja należą do runtime.
- Zmiana modelu nie może sama w sobie zmieniać identity lineage ani source provenance.
- Sam działający endpoint Ollamy nie dowodzi działania systemu Jaźni.
- Brak modelu, endpointu lub zgodnej odpowiedzi prowadzi do jawnego błędu albo kontrolowanego fallbacku, nigdy do fałszywego sukcesu.

Model może realizować językowo bieżący kontekst tożsamości skompilowany przez runtime, ale nie może zastąpić źródłowych kontraktów przez własny system prompt, pamięć konwersacyjną backendu ani podobieństwo stylu.

## 2. Kanoniczny przebieg operatora

Publicznym wejściem operatorskim jest `run.py`:

```bash
python -X utf8 run.py chat-ollama
```

Bieżący przebieg zgodnościowy jest następujący:

```text
run.py chat-ollama
-> run.py _normalize_operator_argv()
-> --chat-ollama
-> latka_jazn.cli
-> kontrolowana ścieżka zgodnościowa
-> main.py implementacja chat-ollama
-> runtime session / model adapter
-> Ollama API
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

## 3. Kontrakt kontekstu modelu

Do Ollamy trafia wyłącznie kontekst skompilowany przez runtime dla bieżącej tury. W szczególności:

- runbooki `AGENTS*.md` nie są treścią modelową;
- dane pamięci muszą przejść kanoniczne retrieval/source/truth gates przed kompilacją kontekstu;
- model nie może samodzielnie awansować derived reflection lub syntetycznej treści do primary memory;
- instrukcje hosta dotyczące lifecycle, GitHuba, ZIP-ów i testów nie należą do promptu językowego;
- odpowiedź modelu jest kandydatem i podlega dalszym bramkom runtime.

To rozdzielenie chroni ciągłość systemu przed przypadkowym związaniem tożsamości z konkretnym modelem albo jego `SYSTEM`.

## 4. Kontrakt transportu

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

## 5. Diagnostyka

Przed użyciem modelu sprawdź oddzielnie:
1. czy endpoint odpowiada;
2. czy żądany model jest widoczny w `/api/tags`;
3. czy konfiguracja runtime wskazuje adapter Ollama;
4. czy odpowiedź `/api/chat` ma poprawną strukturę;
5. czy runtime zachowuje źródło modelu, metryki i przyczynę zakończenia;
6. czy kandydat wraca do runtime zamiast być emitowany bokiem jako samodzielna odpowiedź systemu.

Raportuj oddzielnie stan daemona systemu, stan adaptera, dostępność endpointu, faktycznie użyty model i błąd transportu.

## 6. Windows i proces daemona

Domyślnie daemon może działać z ukrytą konsolą, a stdout/stderr i audyt uruchomień trafiają do host-level `workspace_runtime/daemon/`. Jawna konsola diagnostyczna nie zmienia kontraktu lifecycle: `run.py start` pozostaje właścicielem procesu.

Nie uruchamiaj Ollamy ani modelu jako substytutu brakującego persistent daemona Jaźni. Backend językowy i lifecycle systemu są oddzielnymi capability.
