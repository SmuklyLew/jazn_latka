# Jaźń — Studio Konfiguracji 1.0 (SYSTEM v16.3.25.5.115.18)

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
