# JSS — archiwum dowodów testowych

## Własność i zakres

Właścicielem przebiegów pozostaje `tpa_reports.RunStore`. `test_evidence_archive`
dodaje niezmienny manifest, osobne TXT/JSON każdego zarejestrowanego scenariusza,
kopie jawnie wskazanych dowodów i SHA-256. Nie tworzy runtime, modelu ani MEMORY.
Domyślny resolver pozostaje kanoniczny: `.settings_local/operator/` przy aktywnym
lokalnym layoucie; starsze instalacje zachowują dotychczasową lokalizację.
Nie dodano szerokiego wyjątku dla całego `.settings_local`.

Jawny `RunStore(root, evidence_base=absolute_path)` obsługuje zewnętrzny katalog
zapisywalny, również dla izolacji i EXE. Nadal obowiązują ochrona SYSTEM/MEMORY/
workspace oraz odmowa dowiązań. Sam odczyt zewnętrznej historii nie wymaga prawa
zapisu do instalacji.

## Zapis i awaria

`manifest.json` powstaje przed pierwszym testem i zawiera cały wymagany zakres.
Manifestu nie wolno zmieniać. Ustalenie źródła podczas preflight jest oddzielone
od wykonania; po rozpoczęciu wykonania `execution-source.json` wiąże źródło.
Próba przeniesienia wyniku na inne źródło jest odrzucana.

Każde zatwierdzenie tworzy nowy katalog `snapshot-<uuid>/`:

```text
manifest.json
environment.json
summary.json / summary.txt
results/<scenario_id>.json
scenarios/<scenario_id>.txt
evidence/<owned-text-artifact>
integrity.json
```

Dopiero osobny atomowo publikowany `snapshot-<uuid>.json` zatwierdza kompletność
rewizji. Dane są synchronizowane przed publikacją znacznika. Awaria może zostawić
niekompletny katalog lub `.tmp`, ale nie nadpisuje poprzedniej rewizji. Historia
nie wybiera takiego niezatwierdzonego katalogu. Nie ma automatycznej retencji ani
usuwania starych wyników.

Czytnik ponownie sprawdza SHA-256, rozmiary, manifest, kompletność par TXT/JSON,
tożsamość scenariusza i źródła oraz liczniki. Uszkodzenie najnowszej zatwierdzonej
rewizji jest błędem; czytnik nie ukrywa go przez wybór starszego PASS. Integralność
wykrywa niespójność bajtów, nie jest podpisem niezależnego audytora.

## Zwykłe testy pytest / SYSTEM

Adapter `test_evidence_plugin.py` działa wewnątrz istniejącego pytest. Nie jest
drugim wykonawcą ani parserem komend Jaźni. Przykład jawnego włączenia:

```powershell
$env:JAZN_TEST_EVIDENCE_DIR = 'D:/owned-task/evidence-runs'
& '<verified-python.exe>' -X utf8 -m pytest `
  -p tools.jazn_run_studio.test_evidence_plugin `
  --junitxml='D:/owned-task/pytest.xml' `
  -m 'not live_model and not live_mcp'
```

Przykład jest instrukcją, nie dowodem wykonania. Interpreter i katalog muszą być
rzeczywiście wybrane i zweryfikowane dla danego zadania. Wyłączenie live z tej
suite nie usuwa live z rejestru wymaganych odbiorów.

Adapter korzysta z kanonicznego generatora Test Studio. Przed wykonaniem zamraża
zebrane nodeids (wraz z parametryzacją), niezebrane aktywne definicje, 22 TPA oraz
osobne bramki PTY/ConPTY, Windows/Linux, GUI/DPI, finalizacji i finalnego CI.
Niezebrana definicja pozostaje NOT_RUN. Kolekcja z błędem lub bez testów nie jest
PASS. Setup/call/teardown mają trwałe, osobne potwierdzenia; awaria teardown nie
pozostawia PASS z samego call. Potwierdzenia są create-only, redagowane i mają
własne SHA-256. Końcowy snapshot powstaje po zakończeniu pytest i dołącza JUnit,
jeżeli pytest rzeczywiście go zapisał.

Potwierdzenia częściowe po zabiciu pytest pozostają materiałem diagnostycznym;
nie są automatycznie promowane do kompletnego wyniku release. Pełna rekonstrukcja
tych potwierdzeń do widoku historii wymaga dalszego kontraktu recovery.

## Odczyt w JSS

`Katalog testów → Historia wyników TPA` ma jawny wybór katalogu, listę przebiegów,
filtr scenariusza/przyczyny i statusu, osobną pełną bramkę oraz podgląd TXT, JSON,
JUnit i logu. Odczyt i weryfikacja odbywają się w zadaniu roboczym. Nie uruchamiają
testów, modeli, daemona ani naprawy źródłowych raportów. Zgodność SHA bez pewności,
że źródło było czyste, nie jest pokazywana jako aktualny, zweryfikowany wynik.

Porównanie przebiegów przedstawia zmiany statusów i źródła. Eksport ponownie
weryfikuje cały zestaw i zapisuje nowy ZIP bez nadpisywania. Import weryfikuje
wszystkie elementy i hashe przed utworzeniem nowego katalogu. ZIP nie może zawierać
traversal, duplikatów, dowiązań, obcych elementów ani przekroczyć limitów. Import
nie wykonuje kodu z archiwum i nie zmienia źródłowych raportów.

## Granica odbioru

`execution_status` i `full_gate_status` pozostają oddzielne. NOT_RUN, BLOCKED,
SKIPPED, INTERRUPTED, CANCELLED i ERROR nigdy nie zamieniają się w PASS wskutek
braku danych. Snapshot wykonania ma `RELEASE_NOT_ACCEPTED`: sam pytest lub TPA
nie może poświadczyć całej macierzy Windows/Linux/live/manual/final-SHA CI.

Ta implementacja jest fundamentem E1. Otwarta pozostaje pełna integracja wszystkich
wykonawców CI, odtwarzanie częściowych potwierdzeń w GUI,
kompletny read-only indeks oraz dowód responsywności zapisu TPA i odbiór Windows/
Linux. Odczyt, import i eksport GUI są asynchroniczne; synchroniczna ścieżka zapisu
RunStore nadal wymaga pomiaru i ewentualnego przeniesienia poza wątek GUI.
