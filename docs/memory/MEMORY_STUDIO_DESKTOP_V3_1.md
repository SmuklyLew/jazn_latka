# Jaźń Memory Rebuild Studio 3.1 — zintegrowany pulpit operatora

Wydanie kodowe: SYSTEM v16.3.25.5.115.16. Tryb window zachowuje jeden
kanoniczny silnik pamięci, nie wdraża drugiej bazy ani nowego runtime.

## Audyt zrzutów ekranu

Poprzednie okno 3.0.0 miało tylko: Główna, Operacje (wybór komendy i pole
argumentów), Ustawienia (powłoki) i Diagnostyka. Nie udostępniało zawartości
StudioState i StudioWorkflows jako pełnej aplikacji. Samo CLI było rozbudowane,
lecz operator musiał ręcznie konstruować argumenty i ścieżki.

## Co zawiera nowy tryb window

- Pulpit: bieżący projekt, baza i sekwencja pracy.
- Projekt i źródła: wybieranie i tworzenie projektu, skanowanie folderów,
  szczegóły ról i provenance, baseline do porównań.
- Ścieżki i zapis: jeden ekran mapy źródeł, staging, bazy SQLite, benchmarku
  Test04, raportu akceptacji, raportu ciągłości i katalogu finalnego eksportu.
- Baza pamięci: tworzenie/wybór, pełna walidacja, natywny gate recall.
- Import i migracja: kanoniczne źródła ChatGPT ZIP/JSON/HTML, dzienniki,
  muzyka, warstwowa pamięć afektywna, stara baza w trybie plan/migracja.
- Ślady afektywne: read-only obserwacja jawnych deklaracji stanu i powiązań
  z message_id/conversation_id/turn_id/trace_id.
- Kandydaci: ręczny review L1; brak promocji automatycznej do L2/L3.
- Testy 00–Final: pełna sekwencja tego samego ProtocolEngine.
- Odbudowa: preflight, plan, porównanie z baseline, token potwierdzenia
  właściwego zapisu (kanoniczny controller).
- Finalny eksport: eksport z istniejącymi gate'ami i dowodem Test04.
- Ustawienia: warunki walidacji, ochrony danych i mechanizmy odczytu.
- Diagnostyka: ścieżki i status, niezależnie od aktywnego runtime.

Współdzielone usługi to StudioState, StudioWorkflows, ProjectStore,
UnifiedMemoryDatabase i MemoryRebuildApplicationService. Takie same
projekty i baza są dostępne w CLI oraz trybie TUI. Testy, finalizacja i
import NIE są nową implementacją SQL w GUI.

## Gdzie są pliki

Domyślne prywatne projekty: ~/.jazn/memory_rebuild_projects.
Ustawienia narzędzia: memory_rebuild_settings.json z ustawień Studio.
Ustawienia wspólnej powłoki: ~/.jazn/tools/memory_rebuild/ui_settings.json.
Diagnostyka: ~/.jazn/tools/memory_rebuild/runtime/jazn-memory-rebuild.jsonl.
Kanoniczna baza: katalog celu projektu / memory_jazn.sqlite3 lub
jawnie skonfigurowana baza. Weryfikacja protokołów zapisuje artefakty
w katalogu memory/rebuild_tests/protocols.
Źródła nie mogą być tym samym folderem co odbudowa/staging.

## Start z Pythona

Z katalogu repozytorium:
  py -X utf8 .\tools\rebuild_memory.py --ui window studio

Alternatywny launcher:
  $env:JAZN_ROOT = "D:\.AI\jazn_latka_master"
  py -X utf8 .\tools\jazn_memory_studio.py

## Opcjonalny EXE Windows

Na Windows, po samodzielnym zainstalowaniu PyInstaller w wybranym
wirtualnym środowisku:
  pwsh .\tools\windows\build_memory_studio.ps1 -Python "D:\.AI\.venv\Scripts\python.exe"

Skrypt nie instaluje oprogramowania ani nie pakuje prywatnej pamięci.
Wytwarza katalog dist/JaznMemoryStudio z plikiem JaznMemoryStudio.exe.
To klient operatorski wymagający zweryfikowanego folderu Jaźni, nie
samodzielny SYSTEM ani instalator. Build i uruchomienie EXE muszą
zostać wykonane na Windows. Samo istnienie EXE nie dowodzi, że pamięć
jest gotowa albo aktywowana.

## Granice bezpieczeństwa

- Odbudowa wymaga preflight i jawnego tokenu.
- L2, L3 i automatyczna aktywacja pozostają zablokowane.
- Modelowane stany nie dowodzą biologicznego odczuwania.
- Duże protokoły i część operacji czytających działają w jednym workerze;
  dialogi Tk wracają do głównego wątku.
- Wybieranie źródeł i niektóre stare workflow korzystają jeszcze z
  modalnych pickerów na głównym wątku. Skan bardzo dużych źródeł może
  więc wymagać dalszej optymalizacji responsywności.
- Nie pokazujemy fałszywego przycisku STOP: potrzebny jest osobny
  kontrakt cooperative cancellation w ProtocolEngine.
- Brak samoczynnego dołączania starej MEMORY ZIP albo zastępowania bazy.
- Danych prywatnych, SQLite, ZIP-ów ani logów nie commitujemy do repo.

## Minimalna akceptacja

Potrzebne: pełny deterministic pytest, compileall, Pyright, manifest-sync,
Windows GUI smoke, Test00–Final na sztucznych danych, Windows build EXE,
start EXE z JAZN_ROOT oraz próbne sprawdzenie preflight/rollback.
Własny pełny eksport konta powinien być weryfikowany wyłącznie lokalnie.

Źródła techniczne:
Python Tk/Ttk i threading model: https://docs.python.org/3/library/tkinter.html
PyInstaller Windows: https://pyinstaller.org/en/stable/
SQLite backup/WAL: https://www.sqlite.org/backup.html
