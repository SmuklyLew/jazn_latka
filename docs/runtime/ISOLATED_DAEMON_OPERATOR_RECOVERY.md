# Odmowa wznowienia izolowanego JSS

Zwykłe otwarcie `run_studio.py --isolated-acceptance` wymaga dotychczasowej
pełnej weryfikacji wznowienia. Martwy marker nie jest dowodem gotowości.
Odmowa podaje kanoniczny `active_state_reason`, stan procesu, tożsamości,
heartbeat i niepotwierdzone bramki integralności oraz pochodzenia.

## Diagnostyka bez przejmowania procesu

Przy zachowaniu tego samego ROOT i ustawień endpointu:

```powershell
python -X utf8 run_studio.py --root '<testowy-SYSTEM>' --isolated-acceptance --run status
python -X utf8 run_studio.py --root '<testowy-SYSTEM>' --isolated-acceptance --run supervisor
```

Dostępne są też odczyty `doctor`, `version`, `preflight`, `model`, `memory`
oraz kontrola zależności `--check`. Nie przyjmują runtime jako zaufanego,
nie otwierają sesji rozmowy i nie uruchamiają naprawy. `status` zachowuje
szczegóły błędu i ścieżki logów; zdarzenia startu znajdują się w katalogu
`daemon/process_events.jsonl` wybranego workspace. Brak zdarzenia końca
procesu i pusty stderr nie rozstrzygają przyczyny jego zakończenia.

Duży raport kanoniczny może przekroczyć rotacyjny bufor logów JSS. Dlatego
ostatni wiersz statusu `JSS_DAEMON_DIAGNOSTIC` zawiera ograniczony JSON z czasem
pomiaru, wybranym ROOT, wersją, PID, instancją, stanem procesu, kodem przyczyny,
oddzielnymi dowodami gotowości i ścieżką dziennika zdarzeń. Jest emitowany
również dla negatywnego statusu z kodem wyjścia 1. Nie zmienia wyniku komendy
ani nie potwierdza zaakceptowanej wypowiedzi runtime.

Nazwy pól tego wewnętrznego raportu są stałe. Redakcja sekretów obejmuje wartości
przed serializacją JSON, również przy eksporcie i po późniejszym wczytaniu nowych
sekretów. Zwykły tekst procesu potomnego nadal przechodzi pełną redakcję tekstową;
sam prefiks `JSS_DAEMON_DIAGNOSTIC` nie nadaje mu zaufania ani gotowości.

## Jawny start przez kanoniczny control plane

Po sprawdzeniu diagnozy operator może wykonać:

```powershell
python -X utf8 run_studio.py --root '<testowy-SYSTEM>' --isolated-acceptance --run start
```

To jawne żądanie startu. JSS sprawdza zgodność workspace z profilem odbioru.
Jeżeli marker istnieje, wymagane są jego ważność, zgodny ROOT, integralność
SYSTEM i provenance. Dopuszczone są tylko pełne zaufane wznowienie albo
potwierdzony martwy PID przy nieaktywnym procesie i niedostępnym endpoincie.
Żywy, obcy, ponownie użyty lub nierozstrzygnięty PID prowadzi do odmowy.

JSS deleguje start do istniejącego `run.py → main.py`; kanoniczny lifecycle
ponownie odpowiada za integralność, konflikt portu, własność instancji i wynik.
Walidator recovery nie usuwa markera, tokenów ani nierozstrzygniętych requestów.
Nie tworzy drugiego lifecycle i nie zatrzymuje żadnego procesu.

Po udanym starcie ponownie wykonaj `--run status`, a następnie otwórz JSS
bez `--run`. Nadal wymagana jest pełna bramka `validate_resumed_daemon`.
Stop, restart, package-smoke i GUI nie omijają tej bramki wskutek nowej ścieżki
diagnostycznej. Operacje odnoszą się wyłącznie do testowego profilu; nie
przenoś zmiennych jego workspace lub MEMORY do launchera produkcyjnego.

Testy syntetyczne tego przepływu nie zastępują natywnego odbioru awarii,
zamknięcia JSS, wylogowania, restartu Windows ani pełnych scenariuszy TPA.
