# Jaźń — Studio Konfiguracji 1.0 (SYSTEM v16.3.25.5.115.18.1)

## Przeznaczenie

Osobny operator Tkinter zapewnia cztery strony: **Pulpit**, **Mapa ścieżek**, **Konfiguracja**, **Diagnostyka**. Korzysta z kanonicznych resolverów istniejącego SYSTEM, workspace i MEMORY. Nie jest drugim runtime ani silnikiem pamięci.

### Bezpieczne granice

- Przegląd ścieżek jest wyłącznie do odczytu. Obecność PID lub markera nie dowodzi aktywnego daemona.
- Studio edytuje jedynie profil *przyszłego* uruchomienia, a nie globalne środowisko OS czy pliki pracującego daemona.
- Waliduje ścisłą listę kluczy, enumeracje i ścieżki; odrzuca sekrety, dowolne klucze oraz katalog SYSTEM jako cel konfiguracji.
- Zapis wykonuje przez plik tymczasowy, fsync, os.replace i oczekiwany hash SHA-256; poprzednią wersję zachowuje w operator.previous.json.
- Nie modyfikuje SQLite, MEMORY, markerów, historii zaakceptowanych tur ani ustawień działającego procesu.

## Pliki

| Przeznaczenie | Ścieżka |
| --- | --- |
| Backend walidacji i zapisów | latka_jazn/tools/configuration_studio.py |
| Interfejs graficzny | latka_jazn/tools/configuration_studio_ui.py |
| Launcher Python/EXE | tools/jazn_config_studio.py |
| Profil | [workspace_runtime]/configuration_studio/profiles/operator.json |
| Backup poprzedniego profilu | [workspace_runtime]/configuration_studio/profiles/operator.previous.json |
| Launcher z profilem | tools/windows/Start-JaznWithConfig.ps1 |
| Budowa EXE | tools/windows/build_configuration_studio.ps1 |
| EXE po kompilacji | dist/JaznConfigurationStudio/JaznConfigurationStudio.exe |

Workspace i aktywna MEMORY są rozwiązywane przez istniejące funkcje runtime. Ostateczne fizyczne lokalizacje zależą od katalogu instalacji oraz zmiennych środowiskowych. Nie należy ręcznie przekładać MEMORY między katalogami na podstawie samego widoku Studio.

## Praca z aplikacją

Z katalogu SYSTEM:

~~~powershell
py -X utf8 .\tools\jazn_config_studio.py
py -X utf8 .\tools\jazn_config_studio.py --paths-json
py -X utf8 .\tools\jazn_config_studio.py --smoke
~~~

Po zapisaniu profilu następuje wyłącznie przygotowanie pliku. Dopiero jawny start nowego procesu zastosuje jego wartości do środowiska potomnego:

~~~powershell
pwsh -File .\tools\windows\Start-JaznWithConfig.ps1 -Profile "D:\.AI\workspace_runtime\configuration_studio\profiles\operator.json" -DryRun
pwsh -File .\tools\windows\Start-JaznWithConfig.ps1 -Profile "D:\.AI\workspace_runtime\configuration_studio\profiles\operator.json"
~~~

Przed uruchomieniem launcher sprawdza schema, listę kluczy i położenie profilu, a po zakończeniu przywraca środowisko swojego procesu. Nie restartuje automatycznie działającej Jaźni. Profil nie jest aktywny bez uruchomienia nowego procesu. Weryfikacja nie obejmuje działania LLM ani odbudowy prywatnej pamięci.

## EXE i testy

Na Windows z uprzednio zainstalowanym PyInstaller:

~~~powershell
pwsh .\tools\windows\build_configuration_studio.ps1 -Python "D:\.AI\.venv\Scripts\python.exe"
~~~

Build używa --onedir, nie pakuje SYSTEM ani prywatnej MEMORY. W celu uruchomienia EXE poza repo wskaż JAZN_ROOT na istniejący katalog SYSTEM. GitHub Actions wykonuje testy Python 3.12 i 3.14, Tk GUI smoke, rzeczywisty build Windows, uruchomienie EXE z obcego CWD i próbę -DryRun launchera. Artefakt można uznać za gotowy dopiero po zaliczeniu tych etapów.

### Kontrole

~~~powershell
py -X utf8 -m compileall -q latka_jazn/tools/configuration_studio.py latka_jazn/tools/configuration_studio_ui.py tools/jazn_config_studio.py
py -X utf8 -m pytest -q tests/test_configuration_studio.py tests/test_configuration_studio_gui_windows.py
py -X utf8 run.py doctor --json
~~~

### Źródła

- Python Tkinter threading model: https://docs.python.org/3/library/tkinter.html
- Python pathlib Path.resolve: https://docs.python.org/3/library/pathlib.html
- PyInstaller Windows / onedir: https://pyinstaller.org/en/stable/
- Instrukcje repozytorium: AGENTS.md, AGENTS.codex.md, docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md

## Bezpieczeństwo i akceptacja patcha v115.18.1

- Każdy profil jest odczytywany jako jeden snapshot JSON, z odrzucaniem powtórzonych kluczy.
  Launcher PowerShell odbiera już zwalidowany JSON z Python i nie otwiera po raz drugi
  pliku profilu. Zmiana na dysku po walidacji nie podmieni wartości uruchomienia.
- Edycja profilu używa międzywątkowego i międzyprocesowego
  `runtime_sqlite_write_guard` Jaźni jako blokady na czas CAS / backup / podmiany.
  To tylko reuse blokady plikowej; profil pozostaje JSON, nie bazą SQLite.
- Profil z kolizją cache słownikowego / ustawień z aktualną lub wskazaną MEMORY
  zostaje odrzucony; dodatkowo chronione są katalogi `core_state`,
  `daemon`, `supervisor`, `conversation_state` i `runtime_sessions`.
- Mapa ścieżek korzysta z `default_project_root()`, `resolve_settings_path()`
  i `polish_nlp_data_root()`, zamiast na stałe wpisanych ścieżek.
- Gdy profil zmienia `JAZN_MEMORY_ROOT` lub `JAZN_RUNTIME_WORKSPACE_DIR`,
  a w bieżącym workspace znajduje się znacznik aktywnego runtime,
  launcher odmawia uruchomienia. Znacznik nie dowodzi aktywności;
  przed jego bezpiecznym usunięciem operator musi zweryfikować proces.
- GUI ostrzega o niezapisanych zmianach, oferuje przywrócenie poprzedniego profilu
  oraz kopiuje polecenie z bezwzględną ścieżką do launchera PowerShell.
- `restore_previous_profile` modyfikuje wyłącznie profil po potwierdzeniu
  zgodności SHA; nie jest operacją rollback bazy MEMORY ani runtime.
- Test Windows obejmuje także komendę `run.py --version` z uruchomienia
  przez profil. Nie jest to test rozmowy z LLM ani prywatnej MEMORY.

### Ograniczenia

To nadal kontroler profili **przyszłych procesów**, a nie konfigurator
żywego daemona. Zmienione ścieżki pamięci nie migrują danych. Zmiana profilu
nie gwarantuje poprawności żadnego zewnętrznego backendu Ollama/MCP ani
akceptacji widocznej tury. Przed produkcyjnym importem prywatnych danych
wymagana jest osobna akceptacja operatora i testy izolowane.

### Dokumentacja normatywna

- Python os.replace: https://docs.python.org/3/library/os.html#os.replace
- Python Tkinter threading: https://docs.python.org/3/library/tkinter.html#threading-model
- Microsoft PowerShell ConvertFrom-Json: https://learn.microsoft.com/powershell/module/microsoft.powershell.utility/convertfrom-json
- SQLite concurrency: https://www.sqlite.org/lockingv3.html
- PyInstaller operating systems: https://pyinstaller.org/en/stable/
