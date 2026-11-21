# JSS v127.23.2 — kreator, oficjalna Ollama, CLI i Monitor Jaźni

## Przebieg operatorski

1. **A — Wymagania Studio:** odczyt SYSTEM, Python, zależności i bezpieczeństwa; bez przycisków instalacyjnych. Błędy wymagane nadal blokują przejście.
2. **B — Programy i integracje:** wykrycie zainstalowanej Ollamy, link do oficjalnego instalatora, jawne pobranie modeli (po zgodzie), odczyt API i MCP. Nie powstaje daemon ani drugi serwer.
3. **C — Ustawienia:** wybór modelu z aktualnego `GET /api/tags`, jawna zgoda na zapis. Wybór Pythona musi spełnić istniejący kontrakt `ROOT/.venv` lub zweryfikowaną politykę External. Kreator nie instaluje zależności.
4. **Studio Zależności:** osobna odpowiedzialność za Python, wheelhouse, instalację offline, profil GUI i MCP. Żadna z tych operacji nie jest akcją kreatora.
5. **Usługi i procesy:** `Połącz / Start CLI` przez jeden `Controller.ensure_ollama()`. Zajęty port 11434 powoduje odczyt API, bez przejęcia obcego PID i bez drugiego `ollama serve`. Wolny port pozwala na jawny `Controller.start_service("ollama")`. Stop/restart tylko dla procesu uruchomionego przez Studio z żywym `Popen`.
6. **Stany usług — Monitor Jaźni:** tylko asynchroniczne odczyty. `GET /api/tags` podaje modele dostępne, `GET /api/ps` modele załadowane. Brak `/api/ps` oznacza brak dowodu, **nie** pustą listę załadowanych modeli. Żaden z tych odczytów nie potwierdza generacji ani zaakceptowanej wypowiedzi Jaźni. Własność procesu JSS wynika wyłącznie z aktywnego uchwytu `Popen`; nie dowodzi to własności endpointu HTTP.

## Zasady bezpieczeństwa

- Instalator Ollama: **wyłącznie otwarcie** `https://ollama.com/download/windows` na Windows; JSS nie uruchamia WinGet, nie pobiera i nie wykonuje binariów instalatora. Dotychczasowe podkomendy CLI `install-ollama` oraz `start-ollama` w legacy module odmawiają wykonania z kodem błędu, kierując do oficjalnej instalacji i panelu usług.
- Bez automatycznego instalowania Pythona/Qt/MCP; bez uruchamiania Ollama podczas otwarcia lub zamknięcia kreatora; bez publikowania endpointu w Internecie.
- Dopuszczalne odczytowe adresy `http://127.0.0.1:11434/api/tags` i `/api/ps`, z istniejącym limitem odpowiedzi i timeoutem. Bez przekierowań, proxy, danych uwierzytelnienia i dowolnych adresów URL.
- Prywatna MEMORY, kanoniczny daemon, sesje i konfiguracja innych instalacji pozostają nietknięte.
- Specyfikacja nie twierdzi, że zielone testy CI stanowią dowód rzeczywistej generacji, finalizacji, autobiograficznego recall czy działania lokalnego GPU.

## Regresja i odbiór

Automatyczne testy sprawdzają: brak guzików instalowania w kreatorze; prawidłowy URL producenta; odmowę wykonania dawnych instalatorów; świadomą kolejkę modeli; bezpieczny wybór `/api/ps`; różnicę między modelem dostępnym a załadowanym; brak eskalacji do generacji; brak drugiego `ollama serve` przy zajętym porcie; brak przejęcia obcego procesu; odczytowe działanie monitora.

Do manualnego odbioru na Windows: uruchomić kreator, sprawdzić A/B/C, otworzyć **oficjalny** link, sprawdzić API działającej aplikacji Ollama i listę modeli; w panelu usług sprawdzić „Połącz / Start CLI”; w Monitorze sprawdzić proces, API, modele załadowane oraz upływ ważności dowodów. Nie testować stopu na obcym procesie ani nie uruchamiać prywatnego Test00/MEMORY bez osobnego upoważnienia.

## Źródła pierwotne

- Ollama, oficjalny przewodnik dla Windows: https://docs.ollama.com/windows
- Ollama, oficjalne komendy CLI: https://docs.ollama.com/cli
- Ollama, lista dostępnych modeli: https://docs.ollama.com/api/tags
- Ollama, lista modeli załadowanych: https://docs.ollama.com/api/ps
- Qt/PySide6 QProcess, nieblokujące przetwarzanie procesów: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html
- Qt/PySide6 QTimer, pętla zdarzeń i interwały: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTimer.html
