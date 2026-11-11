# JSS — centrum operatorskie, procesy, TPA i ergonomia (2026-11-11)

Status: **częściowo wdrożone, PR roboczy; bez zatwierdzenia wydania ani pełnego odbioru**.
Baza: PR #474, gałąź `fix/v127-4-root-venv-single-interpreter-20261111`.
Ten dokument przechowuje pełen zakres wymagań; implementacja i PASS wymagają osobnych dowodów.

## 1. Granice architektury

- `main.py` jest jedynym control plane. `run.py` to cienki starter;
  `run_studio.py` to klient GUI. Żaden przycisk nie tworzy drugiego lifecycle.
- Zachowaj `ROOT/.venv`; nie przejmuj managed environments ani Pythona innego projektu.
- Zamknięcie JSS nie zatrzymuje już działającego daemona.
- Nie instaluj bibliotek/programów ani nie pobieraj modeli bez jawnej zgody.
- MEMORY nie jest utożsamiana z gotowością core; nie kopiuj i nie modyfikuj
  prywatnych baz, markerów runtime, sekretów ani aktywnych plików.
- Nie uznawaj samego PID/otwartego portu za gotowość.
  Wymagaj root/wersji, identity, endpointu, heartbeat i właściwego statusu rozmowy.
- Brak klucza płatnego API nie blokuje lokalnego backendu Ollama.

## 2. TPA — brak przecieku ustawień operatora do syntetycznych pytest

Zgłoszone na Windows: 22/22 gotowych, plan regresyjny 18 PASS/4 FAIL;
te same cztery zestawy poza TPA: 31/31 PASS.

- Operator/source verification i live acceptance zachowują dotychczasową izolację.
- Uruchomienie pytest w kolejce TPA musi otrzymać osobne środowisko procesu,
  bez `JAZN_STUDIO_ACCEPTANCE_PROFILE`, `JAZN_OPERATOR_STATE_ROOT`,
  `JAZN_MEMORY_REBUILD_SETTINGS` i `JAZN_MEMORY_REBUILD_PROJECTS`.
- Zachowaj `JAZN_MEMORY_MODE=off`, prywatne tymczasowe rooty,
  usunięte sekretne zmienne, jawny allowlist testów i wersjonowany raport.
- Nie omijaj kontroli checkpoint/endpoint w `ChatClient`; nie odtwarzaj tury
  drugi raz i nie promuj symulacji do live PASS.
- Regression test: użyj rzeczywistej kolejki `TPARunner` + QProcess + pytest
  dla `chat-reconnect`, `config-persistence`, `studio-memory-rebuild`,
  `studio-python-runtime`. Wyniki `full_gate` pozostają `NOT_RUN`.
- Ponów cztery scenariusze TPA na Windows, następnie 22 regresje na nowym SHA.
  Zachowaj oryginalny raport 18/4 i JUnit, bez nadpisywania przebiegu.

## 3. Stany usług

- Usuń ręczny przycisk „Odśwież”.
- Wprowadź selektor automatycznego odczytu: **1, 10, 30, 60 sekund**
  (domyślnie 30 s). Widoczny monitor polluje, ukryty nie polluje.
- Odczyt jest asynchroniczny, niedestrukcyjny; nie uruchamia usług.
  Trwałość/zaufanie dowodów pozostaje oceniana niezależnie od interwału.
- Nie pokazuj zielonego statusu tylko dlatego, że ostatnio odpowiedział port.
- Dalszy etap: zapamiętanie preferencji częstotliwości w lokalnych ustawieniach
  i testy przeciążenia oraz opóźnionego zakończenia proby.

## 4. Pulpit — docelowy pojedynczy, bezpieczny start

Pulpit powinien być pierwszym ekranem statusowym z czytelnymi blokami:
SYSTEM, integralność, runtime, model/Ollama, MCP, MEMORY/ciągłość, błędy i procesy.

Jedyny główny przycisk **„Uruchom Jaźń”** uruchamia kanoniczną operację,
z jawnym postępem etapów:
1. Zweryfikuj root/wersję/manifest/provenance i zapisany profil.
2. Zweryfikuj `ROOT/.venv`, wymagane profile i konfigurację.
   Braki zgłoś, nie pobieraj automatycznie.
3. Sprawdź Ollama, model, politykę pamięci i lokalne MCP (opcjonalne).
4. Sprawdź żywy daemon i supervisor po tożsamości oraz heartbeat.
   Jeśli istnieje zgodny daemon, użyj go ponownie; nigdy nie twórz duplikatu.
5. Przy braku zgodnego daemona wykonaj kanoniczne preflight/start/status
   przez `main.py`/publiczne `run.py` i pokaż rzeczywiste wyniki.
6. Sprawdź gotowość rozmowy i — tylko gdy operator wybrał —
   wykonaj osobny test generacji i zaakceptowanej finalizacji.
7. Zatrzymaj workflow przy błędzie. Zachowaj przyczynę, nie przechodź
   do następnej operacji i nie twórz fałszywego „Działa”.

To **nie** jest przycisk „Start All” omijający zgody, kontrolę tożsamości,
wymagania konfiguracji, MEMORY ani bezpieczeństwo tunelu.

- Dalsza implementacja wymaga nowego kanonicznego kontraktu
  `startup_coordinator` w centralnym control plane i klienta JSS.
- Kryteria: idempotencja, brak drugiego daemona, odzyskanie po błędzie
  i połączenie z rzeczywistym modelem Ollama.
- Pulpit: usuń „Kreator konfiguracji...” i „3. Przejdź do rozmowy”.
  Wykorzystaj czytelne elementy „Stanu środowiska” ze starego Studio Startu.

## 5. Monitor procesów

- Zamiast samego statusu „usługi” pokaż tabelę **Procesy** na wzór
  menedżera zadań: nazwa/rola, PID, CPU, RAM, czas życia, port,
  owner/instancja, readiness/heartbeat i ostatnia obserwacja.
- Domyślnie uruchamiaj tylko **monitorowanie** przy starcie JSS,
  nie procesy Jaźni, Ollama, MCP, cloudflared ani supervisora.
- Użyj odczytu `psutil.process_iter(attrs=...)` lub bezpiecznego adaptera
  OS; dostęp do cudzych procesów może być ograniczony.
- Zbieranie metryk w workerze, nie na wątku Qt. Wynik nigdy nie upoważnia
  do przyjęcia własności, stop/restart ani do ACK odpowiedzi.
- Zapewnij ten sam kontrakt przez kanoniczną komendę CLI `main.py`/
  `run.py`, z wyjściem tekstowym i `--json`, bez nowego entrypointu lifecycle.
- Kryteria: brak zwieszeń GUI, brak płatnych usług, brak wycieku
  ścieżek/argumentów procesów i brak fałszywych statusów readiness.

## 6. Okna, zakładki i Narzędzia Operatora

- Każda zawartość robocza powinna dać się zamknąć na karcie oraz odłączyć
  do niezależnego okna/docka. Nie niszcz w trakcie aktywnego jobu.
- Implementuj na `QTabWidget`/`QTabBar` + `QDockWidget` z jedną właścicielską
  instancją widoku (bez duplikowania jego stanów i połączeń).
- Zamknięcie karty ma ukrywać/odłączać widok, nie zatrzymywać daemona.
  Odtworzenie układu nie może wskazać obcej instancji.
- Usuń duplikat „Pokaż panel”. W trybie jednolitego workspace panel operatora
  otwiera i zamyka przycisk **„Narzędzia Operatora”**, z informacją o problemach
  i zadaniach w tooltipie.
- Terminal PTY, raporty oraz historia muszą zachować swoje mechanizmy ownership.

## 7. Ustawienia

Wprowadź profesjonalny układ kart/sekcji z jednolitymi etykietami,
wskazówkami, walidacją, wyszukiwaniem i stanem „zapisano/nie zapisano”:
- **Środowisko:** ROOT, Python `.venv`, ścieżki, dependency profile.
- **Runtime i procesy:** model startu, port, supervisor, heartbeat.
- **Model/Ollama:** wykryte modele i oddzielne testowanie generacji.
- **MCP i Cloudflare:** lokalny port, auth, HTTPS, tunel, bez auto-publikacji.
- **MEMORY:** tryb, dostępność, dowód recall/continuity, bez bezpośredniej edycji baz.
- **Bezpieczeństwo i pliki:** lokalna ścieżka sekretów, uprawnienia, provenance.
- **Wygląd i workspace:** motyw, kolor, DPI, zakładki, dokowanie, odświeżanie.
- **Diagnostyka:** logi, TPA i wyniki kontroli.

Zachowaj dotychczasowy kontrakt zapisu CAS, backup i brak wpływu
zmiany konfiguracji na już działające procesy.

## 8. Bramy odbioru

- [ ] TPA: nowe testy izolacji kolejki PASS na Windows.
- [ ] TPA: ponowienie czterech FAIL i pełnej regresji 22/22 na aktualnym SHA.
- [ ] Stany usług: selektor 1/10/30/60 i brak przycisku; Qt GUI PASS.
- [ ] Pulpit: przebudowa wizualna, statusy i jeden główny workflow startu.
- [ ] Procesy: automatyczny odczyt po starcie JSS + CLI main-first.
- [ ] Okna: zamykanie kart, odłączanie, przywrócenie układu.
- [ ] Ustawienia: sekcje, wyszukiwanie, walidacja, persistence.
- [ ] SYSTEM: wersja patcha i kanoniczny release_metadata_sync.
- [ ] CI: wszystkie wymagane aktualne checks na dokładnym commit SHA.
- [ ] Windows JSS: daemon, dwie tury Ollama, reconnect/resume, finalization.
- [ ] Full acceptance: osobne 22 operator gates z dowodami.

Nie merge'uj PR do master przed rzeczywistym zaliczeniem bram.
