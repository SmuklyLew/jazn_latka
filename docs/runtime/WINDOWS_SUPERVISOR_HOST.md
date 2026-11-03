# Windows: trwały supervisor Jaźni

`run.py supervisor-run --windows-service` obsługuje rzeczywisty protokół Windows
Service Control Manager: dispatcher, rejestrację handlera, statusy START_PENDING,
RUNNING, STOP_PENDING i STOPPED oraz kontrolę STOP, SHUTDOWN i INTERROGATE.
Nie jest to emulacja usługi przez zwykły proces Pythona.

Adapter wywołuje istniejący `run_supervisor` ze współdzielonym zdarzeniem stop.
Nie dodaje drugiego runtime, recovery ani finalizacji. Zatrzymanie supervisora
nie zatrzymuje daemona; do jego zatrzymania służy osobna kanoniczna operacja.
Status RUNNING w SCM oznacza obsługę kontroli przez host usługi, a nie gotowość
daemona, MEMORY, modelu lub zaakceptowanej rozmowy.

## Przygotowanie

Użyj bezwzględnej ścieżki zweryfikowanego interpretera z gotowymi zależnościami
profilu core. Nie wybieraj aliasu menedżera instalacji `python` ani interpretera
znajdującego się wyłącznie w profilu użytkownika niedostępnym dla konta usługi.
Przed rejestracją sprawdź zwykły start i diagnostykę z tego interpretera.

Publiczne `run.py supervisor-plan --root <ROOT> --json` zwraca
`windows_configuration`: nazwę związaną z kanonicznym ROOT, argv hosta SCM,
poprawnie cytowany ImagePath, argumenty `sc.exe create/queryex`, XML zadania
startowego i wymagania uprawnień. To odczytowy plan: niczego nie rejestruje,
nie uruchamia, nie zatrzymuje i nie potwierdza instalacji.

Wybierz jeden mechanizm: usługę SCM albo zadanie Harmonogramu zadań.
Nie rejestruj obu dla tego samego ROOT. Istniejący supervisor nadal chroni
własność procesu przez kanoniczny PID, fingerprint i ROOT.

## Usługa SCM

Po osobnej zgodzie operatora administrator może wykonać zweryfikowane
`create_service_argv`. Pole `binPath=` wskazuje `run.py supervisor-run
--windows-service` z dokładnym ROOT; nie zastępuj go zwykłym `supervisor-run`.
Plan wybiera `NT AUTHORITY\LocalService`, własny proces i start delayed-auto.
Nie nadpisuj istniejącej rejestracji bez sprawdzenia jej własności.

Przyznaj kontu usługi minimalne prawa odczytu/wykonania SYSTEM i Pythona oraz
zapisu do jawnie wybranego workspace. Sprawdź kanoniczną konfigurację ROOT
i wybór MEMORY w kontekście tego konta; nie kopiuj niejawnie sekretów ani
prywatnej pamięci z interaktywnego profilu. Plan nie zmienia ACL i nie konfiguruje
automatycznie restartów hosta przez SCM. Politykę awarii usługi trzeba osobno
uzgodnić i przetestować; backoff daemona pozostaje w kanonicznym supervisorze.

Bezpośrednie wywołanie hosta SCM z terminala kończy się WinError 1063 i odmową,
bez uruchamiania zastępczego supervisora. Błędy pracy i kod 41 duplikatu nie są
zamieniane w pomyślne zatrzymanie. STOP_PENDING trwa do zakończenia pracy
supervisora; host nie deklaruje STOPPED przy wciąż działającym workerze.

## Alternatywa: Harmonogram zadań

`task_xml` jest definicją zadania z BootTrigger, kontem LocalService
(`S-1-5-19`), IgnoreNew, StartWhenAvailable, brakiem limitu czasu, brakiem
zależności od baterii/sieci oraz trzema restartami co minutę. Akcja wskazuje
bezwzględny interpreter, `run.py supervisor-run` i ROOT, a katalog roboczy to ROOT.

Po zgodzie operatora zapisz XML poza SYSTEM i zarejestruj go narzędziem
administracyjnym Harmonogramu zadań lub jego API. Przy rejestracji przez COM
użyj TASK_LOGON_SERVICE_ACCOUNT (`5`); nie wpisuj `ServiceAccount` do XML
LogonType, którego opublikowany schemat Microsoftu nie dopuszcza. Konto w XML
jest wbudowanym kontem usługowym, bez hasła i bez tokena sesji interaktywnej.
Sama poprawność XML nie potwierdza rejestracji ani uruchomienia po restarcie.

## Odbiór

Wymagane pozostają testy rzeczywistej rejestracji, praw konta, startu/stopu SCM,
odłączenia terminala i JSS, awarii, ochrony przed duplikatem, recovery daemona
oraz uruchomienia po restarcie Windows. Natywny test odmowy poza SCM i testy
adaptera nie zastępują tego odbioru. Instalacja, zmiana polityki awarii,
restart komputera i wdrożenie wymagają odpowiedniej zgody operatora.

Źródła kontraktów: [SCM dispatcher](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-startservicectrldispatcherw),
[handler usługi](https://learn.microsoft.com/en-us/windows/win32/services/service-control-handler-function),
[sc.exe create](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/sc-create),
[schemat Task Scheduler](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[konto usługi w Task Scheduler](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype).
