# Jaźń — Serce Systemu · etap P1 · 30 października 2026

Źródło: `fix/tpa-chat-resume-durable-receipt-20261030` (`90f37838`) + aktualizacja kanonicznych metadanych na tej gałęzi. Wersja `16.3.25.5.116.0.34.94.6.29`.

## Zaimplementowane

- Jeden dolny panel operatorski: Problemy, Output/Logi, trzy konsolowe zakładki zadań, Historia i Techniczne.
- Filtrowane logi bieżącej sesji, redakcja przez istniejący kontroler, eksport tylko na żądanie.
- Historia odczytuje istniejący magazyn TPA, nie tworzy jego kopii; dowody techniczne mają scope `local_studio_read_only`.
- Oddzielne zadania w pełnowymiarowych zakładkach, bez udawania interaktywnego terminala.
- Zewnętrzny PowerShell i kanoniczny czat CLI jako wyraźnie rozdzielone akcje na Windows.
- Bezpieczny schemat zapisu układu `jazn_heart_layout/v3`, migracja v1/v2, dokowanie i pamięć rozmiarów.
- Wspólne menu i paleta poleceń. Zachowane sześć motywów i wykrywanie zainstalowanych modeli Ollama z gałęzi bazowej.
- Testy Qt dla wspólnego panelu oraz jawnych operacji otwarcia zewnętrznego terminala.

## Pozostałe wymagania / status

P2: wbudowane ConPTY Windows / PTY Linux wraz z parserem terminalowym — **NOT_RUN**. Zewnętrzny PowerShell to nie emulator.

P3: kompleksowy odbiór start/stop/restart wszystkich procesów, testy błędów i prawa własności — **NOT_RUN**.

P4: pełna migracja funkcjonalna 12 Studiów Qt oraz import/restore MEMORY — **NOT_RUN**.

P5: 22 pełne bramki TPA, DPI na fizycznych monitorach, EXE offline/AV — **NOT_RUN**.

Logo: załączony PNG użytkownika nie został jeszcze przeniesiony do zasobów repo (dostępny adapter GitHub zapisuje tekst). **NOT_RUN**.

Wymagane jeszcze kanoniczne `release_metadata_sync`, sprawdzenie wersji, Windows/Linux GUI CI i rzeczywisty odbiór operatorski na końcowym SHA. Nie zatwierdzaj `full_gate` bez dowodów.

Granice: bez modyfikacji MEMORY, aktywnego daemona, sekretów, master i kontraktów finalizacji.
