# Jaźń v127.17 — opt-in External Python (pierwszy etap modernizacji)

## Zakres rzeczywiście wdrożony

Nowa polityka operatora jest **opcjonalna**. Bez niej historyczny mechanizm
`ROOT/.venv`, Managed oraz Portable zachowuje dotychczasową ścieżkę.
Nie następuje automatyczna migracja środowisk ani MEMORY.

Po jawnym wyborze `mode=external`:

- `run.py -> main.py` rozpoznaje politykę przed prywatnym `ROOT/.venv`;
- `run_studio.py` i JSS sprawdzają ten sam wskazany interpreter;
- kontrola importuje wyłącznie metadane dystrybucji i `packaging` w
  procesie wybranego Pythona (`-I -B`, limit czasu, bez `pip`);
- brak lub niezgodność wymaganych pakietów blokuje aktywację, bez
  instalacji, aktualizacji, tworzenia `venv`, sieciowego pobierania
  i niejawnego fallbacku;
- diagnostyka potrafi zwrócić `READY`, `BLOCKED`,
  `NOT_CONFIGURED` lub `INVALID`; nie należy ich mylić z
  liveness/readiness daemona, MCP, MEMORY czy finalizacją rozmowy;
- GUI nie udostępnia w External operacji modyfikujących Pythona ani
  instalacji pakietów przez wiersze zależności;
- osobny `mcp_python` w JSS pozostaje dopuszczony jako świadomy wybór
  operatora. Gotowość lokalnego MCP sprawdza oddzielny preflight.

## Jawna konfiguracja

Plik prywatny, nieśledzony przez Git:

`<SYSTEM>/.settings_local/python_environment.json`

Przykładowy dokument (wpisz rzeczywistą, **absolutną** ścieżkę
wybranego interpretera zamiast przykładowej):

```json
{
  "schema_version": "jazn_python_environment/v1",
  "mode": "external",
  "python_executable": "/home/operator/venvs/jazn/bin/python",
  "required_profiles": ["core", "run-studio"],
  "automatic_installation": false,
  "automatic_updates": false,
  "allow_environment_deletion": false
}
```

Na Windows przykładowa ścieżka interpretera:
`D:\\.AI\\.venv\\Scripts\\python.exe`.
Do JSON wpisz ją z podwojonymi backslashami (`\\`) lub z ukośnikami `/`.

`required_profiles` musi zawierać `core`. Dla JSS dodaj
`run-studio`, a dla uruchomienia lokalnego MCP także `mcp-http`,
chyba że MCP używa osobnego, zweryfikowanego interpretera.

W obecnym etapie jawne `mode=managed` i `mode=portable` w tym **nowym**
pliku są odrzucane, ponieważ nie wdrożono jeszcze ich nowego
kontraktu. Istniejące historyczne tryby nadal działają **bez tego pliku**.
Nie deklaruj implementacji trzech trybów na podstawie samego schematu.

## Przeprowadzenie kontroli bez mutacji

W katalogu SYSTEM, z działającym Pythonem:

```text
python -B -X utf8 -c "from latka_jazn.dependencies.environment_manager import inspect_external_environment; from pathlib import Path; import json; print(json.dumps(inspect_external_environment(Path.cwd()), indent=2, ensure_ascii=False))"
```

Kontrola wczytuje `pyproject.toml`, sprawdza zadeklarowane pakiety
w wybranym interpreterze, ale **nie naprawia** braków. `READY` znaczy
wyłącznie, że wybrane profile i wersja CPython zostały zweryfikowane;
nie jest dowodem bezpiecznego źródła wszystkich zewnętrznych pakietów
ani tego, że daemon/Ollama/MCP/MEMORY rzeczywiście działają.

Brak pakietów w External naprawia **wyłącznie operator**, poza Jaźnią,
po własnym audycie pakietów i zależności.

## Bezpieczeństwo i CyberCapture

Nie wyłączaj CyberCapture, nie dodawaj globalnych wykluczeń antywirusa
i nie używaj pakowania lub uruchamiania ukrywającego kod.
Sam fakt posiadania źródeł i zielonego CI nie gwarantuje braku ostrzeżeń.

Dla późniejszej dystrybucji EXE: utrzymuj reprodukowalne buildy,
przejrzyste uruchamianie, osobne artefakty Windows/Linux, hashe
SHA-256, skan przed dystrybucją i — jeśli dostępne — podpisywanie
wydania. Gdy czysty plik zostanie uznany za podejrzany, użyj
oficjalnego kanału weryfikacji producenta ochrony, nie obejścia.

Oficjalne informacje:
- Avast CyberCapture FAQ: https://support.avast.com/pl-pl/article/antivirus-cybercapture-faq
- Avast — dla twórców oprogramowania: https://support.avast.com/en-gb/article/threat-lab-file-whitelist/
- Microsoft — zgłaszanie fałszywych alarmów: https://www.microsoft.com/en-us/wdsi/filesubmission

## Czego v127.17 nie dowodzi

To etap P0 (External), a nie całe zadanie modernizacji. Do dalszych
PR pozostają: pełne wersjonowane Managed/Portable, wspólny resolver
wszystkich instalatorów, bezpieczny GC z manifestem własności,
staging/rollback, pełna macierz Python/Windows/Linux, czysty odbiór JSS,
daemon/Ollama/MCP, wieloturowa finalizacja i release-hardening.

Przed scaleniem wymagane są rzeczywiste testy na aktualnym HEAD,
kanoniczna synchronizacja manifestów/provenance i odbiór z planu
`JAZN_JSS_plan_modernizacji_srodowisk_Python.md`. Nigdy nie usuwaj
`MEMORY`, istniejącego `venv` ani aktywnych markerów podczas migracji.
