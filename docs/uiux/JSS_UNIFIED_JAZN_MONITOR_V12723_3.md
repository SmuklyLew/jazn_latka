# JSS v127.23.3 — jeden Monitor Jaźni, jedna obserwacja

## Zakres wydania

JSS i samodzielny `jazn_monitor.py` korzystają z **tej samej implementacji**
`tools.jazn_monitor.window.MonitorWindow` i kanonicznego,
tylko-odczytowego `tools.jazn_monitor.probe.snapshot`. JSS nie uruchamia
osobnego procesu Monitora, lecz otwiera jeden egzemplarz okna we własnym
procesie Qt. Samodzielny launcher pozostaje dla środowisk bez JSS, ale
istniejący per-ROOT `QLockFile` chroni przed dwiema instancjami obserwatora
tej samej instalacji. W razie konfliktu JSS nie przejmuje obcego procesu:
wyświetla bezpieczny komunikat operatorski.

### Jeden widok stanu

**Monitor Jaźni** zawiera zakładki:
- **Usługi:** Daemon Jaźni, Runtime Core, Ollama, MCP lokalne, Supervisor,
  JSS, MEMORY oraz MCP HTTPS (ten ostatni bez niezależnego dowodu pozostaje
  NIEZWERYFIKOWANY).
- **Procesy Jaźni:** PID, parent PID, obciążenie i dowód tożsamości,
  wyłącznie po kanonicznej weryfikacji instancji.
- **Zadania:** diagnostyka statusów i kodów błędów bez prywatnych wiadomości.
- **Finalizacja:** osobny wynik; `/live` ani `/ready` nie potwierdzają
  zaakceptowanej finalizacji tury.

Panel **Usługi i procesy** służy do jawnego Start/Stop/Restart. Jego
kolumna statusu i gotowości lustrzanie prezentuje **ten sam**
`jazn_monitor_snapshot/v1` przekazany przez sygnał Qt z Monitora Jaźni
(`tools.jazn_run_studio.monitor_bridge`). Zdarzenia operacyjne
`Controller` mogą służyć do logowania i decyzji o uprawnieniu do
operacji, ale po pierwszej obserwacji **nie zastępują** stanu monitora.
Przycisk „Odczytaj” korzysta z tego samego jednego obserwatora.

## Fail-closed i granice dowodów

- Każda obserwacja musi mieć schemat `jazn_monitor_snapshot/v1`,
  `observation_only=true` i dokładnie zgodny `selected_root`.
- Po **45 s** bez nowego poprawnego odczytu panel JSS przechodzi do
  NIEZWERYFIKOWANEGO; stary zielony wynik nie jest utrzymywany.
- PID w panelu jest pokazany tylko z `verified_instance`; sam PID nie
  dowodzi żywego lub zaufanego runtime.
- `/api/tags` pokazuje listę zainstalowanych modeli Ollama,
  `/api/ps` modele załadowane; brak `/api/ps` jest brakiem dowodu,
  nie potwierdzeniem pustej listy. Odczyt nie uruchamia generacji.
- MCP HTTPS nie może być oznaczony jako gotowy tylko dlatego, że lokalny
  MCP działa. Potrzebne są odrębne dowody HTTPS, OAuth, hosta i runtime.
- MEMORY ready wymaga właściwych dowodów recall i continuity. Brak
  dostępnej prywatnej pamięci nie może zmieniać statusu na gotowy.
- Monitor nie zatrzymuje ani nie uruchamia daemona, Ollamy lub MCP.
  Zamknięcie okna Monitora nie zatrzymuje procesów ani JSS.
- JSS używa `service_refresh_seconds` dla jednej częstotliwości
  odczytu. Odświeżanie jest asynchroniczne; już uruchomiony odczyt nie
  jest ponawiany równolegle. Po zamknięciu okna automatyczny odczyt ustaje,
  natomiast stare obserwacje wygasają. Ręczne „Odczytaj” jest jawne.

## Granica samodzielnego launchera

Samodzielny `jazn_monitor.py` pozostaje publicznym **alternatywnym**
punktem wejścia, nie drugim monitorem JSS. Integracja JSS nie powiela
jego ikon tray, nie ustawia `quitOnLastWindowClosed(false)` i nie
rejestruje drugiej pętli zdarzeń. Identyczny lock per ROOT ogranicza
równoległe okna obserwacyjne. Gdy samodzielny monitor już jest aktywny,
użytkownik musi zamknąć tamto okno przed otwarciem zintegrowanego widoku
JSS; brak niejawnego zabijania, przejmowania PID i IPC.

## Testy i odbiór

Automatycznie:
- zachować dawne testy samodzielnego monitora i kontrolera procesów;
- sprawdzić właściwe wyświetlanie jednego `MonitorWindow` w JSS;
- odrzucać snapshot z obcego ROOT lub obcym schematem;
- sprawdzić TTL, brak PID-only ready, niepromowanie MCP HTTPS;
- sprawdzić `/api/tags` i `/api/ps`, brak automatycznej generacji;
- potwierdzić ręczne otwieranie tego samego okna oraz brak drugiego procesu.

Manualnie na Windows z poprawnym ROOT:
- otworzyć „Monitor Jaźni” z pulpitu i nagłówka: to ten sam widok;
- porównać zakładki usług/procesów/zadań/finalizacji z tabelą usług;
- bezczynność powyżej TTL nie może pozostawić zielonego stanu;
- potwierdzić, że zamknięcie monitora nie zatrzymuje daemona ani JSS;
- potwierdzić, że inna instancja monitora blokuje otwarcie drugiej;
- nie uruchamiać Test00 ani prywatnej MEMORY bez oddzielnej zgody.

## Oficjalne materiały referencyjne

- Qt Model/View i wspólne dane: https://doc.qt.io/qtforpython-6/overviews/qtwidgets-model-view-programming.html
- Qt Signals/Slots: https://doc.qt.io/qtforpython-6/overviews/qtcore-signalsandslots.html
- Qt QTimer: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTimer.html
- Ollama API modeli dostępnych: https://docs.ollama.com/api/tags
- Ollama API modeli załadowanych: https://docs.ollama.com/api/ps
