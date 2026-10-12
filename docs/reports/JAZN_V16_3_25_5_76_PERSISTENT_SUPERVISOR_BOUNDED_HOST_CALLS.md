# Jaźń v16.3.25.5.76.0 — persistent supervisor and bounded host calls

## Cel

Ta aktualizacja rozdziela timeouty kilku niezależnych warstw, zamiast próbować leczyć je jednym większym limitem czasu:

1. **host/executor ChatGPT** — wywołanie może zakończyć się zanim lokalny proces w ogóle powstanie;
2. **host operation** — proces został utworzony, ale wynik długiej operacji nie musi zmieścić się w życiu jednego wywołania hosta;
3. **persistent Jaźń daemon** — runtime ma własną żywotność, heartbeat, readiness i trwałe requesty rozmowy;
4. **local runtime supervisor** — osobny proces odpowiada za obserwację/recovery daemona;
5. **OpenAI Secure MCP Tunnel** — osobny managed transport, którego liveness/readiness nie jest tożsama z gotowością Jaźni ani capability bieżącej powierzchni ChatGPT;
6. **connector/app capability** — osobna brama hosta, już wymagana od v75.2.

Aktualizacja nie twierdzi, że kod ZIP-a może zapobiec `TransportTimeoutError`, który wystąpił przed utworzeniem procesu. Zmienia skutki takiej awarii: praca, która została już trwale przyjęta przez lokalny system, ma własną tożsamość i może być później odpytywana bez replayu.

## Evidence zewnętrzne

Projekt został porównany z bieżącymi, oficjalnymi źródłami:

### OpenAI Secure MCP Tunnel

- https://github.com/openai/tunnel-client
- https://github.com/openai/tunnel-client/blob/master/plugins/tunnel-mcp/skills/tunnel-mcp/references/runtime-flows.md
- https://github.com/openai/tunnel-client/blob/master/docs/health.md
- https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md

OpenAI rozdziela proces liveness (`/healthz`) od readiness (`/readyz`) i dla długowiecznego lokalnego runtime zaleca `tunnel-client runtimes connect`, a nie `nohup`/`disown`. Sukces managed runtime należy potwierdzać osobnym `runtimes status --json`; pola `process_running`, `healthy` i `ready` są odrębnym evidence. `control_plane_poll_health` jest raportowany oddzielnie od lokalnego health/readiness.

### Microsoft Windows Task Scheduler

- https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-multipleinstancespolicy-settingstype-element
- https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-executiontimelimit
- https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-settings-tasktype-element

Microsoft dokumentuje `MultipleInstancesPolicy=IgnoreNew` jako politykę niedopuszczającą drugiej instancji podczas działania pierwszej. `ExecutionTimeLimit=PT0S` oznacza brak limitu czasu wykonania. `RestartOnFailure` oraz `StartWhenAvailable` są natywnymi ustawieniami Task Scheduler odpowiednimi dla procesu supervisora, który ma żyć poza pojedynczym wywołaniem ChatGPT.

### AWS — idempotency i timeout ambiguity

- https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/

Wzorzec zastosowany tutaj odpowiada zasadzie, że po timeoutcie klient może nie wiedzieć, czy efekt uboczny już zaszedł. Operacja otrzymuje stabilny identyfikator/idempotency key przed próbą wykonania, a retry używa tego samego identyfikatora zamiast tworzyć drugą operację. Recovery daemona używa ograniczonego exponential backoff z jitterem.

## Nowa architektura

```text
ChatGPT / krótko żyjący host call
        |
        | host-op-submit(operation_id)
        v
Durable host operation record
        |
        +--> detached operation worker
                |
                +--> canonical run.py -> main.py -> lifecycle

Windows Task Scheduler / docelowy OS owner
        |
        +--> run.py supervisor-run
                 |
                 +--> cheap /live w steady state
                 +--> full status/start tylko podczas recovery
                 +--> persistent Jaźń daemon

OpenAI tunnel-client managed runtime
        |
        +--> oddzielny remote transport
                 |
                 +--> osobny ChatGPT connector capability gate
```

Żadna z tych warstw nie jest alternatywnym źródłem tożsamości systemu. `run.py -> main.py` pozostaje kanonicznym control plane.

## `latka_jazn/core/host_operations.py`

Dodano trwałe, idempotentne operacje hosta:

- `daemon-start`;
- `runtime-bootstrap`;
- `supervisor-start`.

Rekordy są przechowywane w `workspace_runtime/host_operations`.

### Kontrakt operation ID

`operation_id` jest przydzielany **przed próbą utworzenia procesu**. To pozwala odzyskać stan po niejednoznacznym timeoutcie.

- ten sam ID + ten sam fingerprint polecenia: idempotentny odczyt/retry;
- ten sam ID + inny fingerprint: fail-closed conflict;
- utracona odpowiedź po submit: poll tego samego ID;
- brak automatycznego replayu pod nowym ID.

### Ownership rekordu

Przed spawnem rekord tworzy proces submitujący. Po udanym `Popen()` jedynym właścicielem trwałych przejść stanu jest detached worker.

To usuwa wyścig lost-update, w którym worker mógł przejść do `running`, a rodzic nadpisać świeższy rekord starym `accepted`.

### Canonical lifecycle

Worker nie implementuje lifecycle. Zawsze uruchamia publiczne `run.py`, które przekazuje sterowanie do `main.py`.

## `latka_jazn/core/runtime_supervisor.py`

Supervisor jest lokalnym długowiecznym właścicielem recovery daemona.

### Steady state

Co do zasady używa lekkiego endpointu `/live` z krótkim timeoutem. Nie uruchamia pełnego integrity/provenance/doctor w każdej iteracji.

### Recovery

Jeżeli cheap liveness nie potwierdzi właściwego root/version:

1. wykonuje pełniejszy `status_daemon()`;
2. jeżeli runtime nadal nie jest aktywny, używa istniejącego kanonicznego `start_daemon()`;
3. przy nieudanym recovery używa bounded exponential backoff z deterministycznym jitterem;
4. nie tworzy równoległej implementacji start/reload/rollback.

### Singleton

Supervisor ma własny PID contract. Druga próba uruchomienia nie może nadpisać `state.json` żywego właściciela; kończy się kodem `41` i pozostawia stan aktywnego supervisora nietknięty.

## Windows ownership plan

`run.py supervisor-plan --json` publikuje ustawienia Task Scheduler:

```text
Trigger: AtStartup
StartWhenAvailable: true
MultipleInstancesPolicy: IgnoreNew
ExecutionTimeLimit: PT0S
RestartOnFailure: Count=3, Interval=PT1M
```

Plan nie twierdzi, że zadanie jest już zainstalowane. Nie emuluje również Windows Service przez opakowanie arbitralnego Pythona w `sc.exe`; prawdziwy Windows Service wymaga właściwego kontraktu Service Control Manager.

## CLI

Nowe publiczne komendy przechodzą przez `run.py -> main.py -> latka_jazn.cli`:

```bash
python -X utf8 run.py host-op-submit --operation-id <id> --kind daemon-start --json
python -X utf8 run.py host-op-submit --operation-id <id> --kind runtime-bootstrap -- --parts-dir <dir> --destination <root>
python -X utf8 run.py host-op-status --operation-id <same-id> --json

python -X utf8 run.py supervisor-plan --json
python -X utf8 run.py host-op-submit --operation-id <id> --kind supervisor-start --json
python -X utf8 run.py supervisor-status --json
python -X utf8 run.py supervisor-run
```

`accepted=true` dla host operation nie jest dowodem gotowego runtime. Po zakończeniu startu wymagany pozostaje kanoniczny `run.py status --json` oraz pełne kryteria runtime readiness.

## Stable Test Studio CI ordering

Podczas pierwszego CI znaleziono niezależny wyścig workflow: `sync_catalog` i `validate` mogły startować równolegle. Walidacja mogła więc sprawdzić stary `test_contracts.json`, mimo że osobny job chwilę później poprawnie go synchronizował.

Workflow został zmieniony tak, aby `validate` zależał od `sync_catalog`. Dla branch push checkout walidatora używa aktualnego ref brancha **po** synchronizacji katalogu. Dla PR zachowane są standardowe semantics `github.sha`.

Gate nie został osłabiony: nadal wykonywane są compile Test Studio, self-test, Node24 audit, pełne collect-only, deterministyczny `sync_contract_catalog.py --check` i governance tests.

## Testy

Dodano:

- `tests/test_host_operations_v16325576.py`;
- `tests/test_runtime_supervisor_v16325576.py`;
- `tests/test_bounded_host_race_regressions_v16325576.py`.

Pokrywają m.in.:

- canonical target przez `run.py`;
- zakaz `--root` override;
- wymagane argumenty bootstrapu;
- idempotentny submit i konflikt ID;
- nieblokujący status/poll;
- POSIX `start_new_session`;
- supervisor backoff i Windows ownership plan;
- fail-closed supervisor status;
- parent/worker state race;
- duplicate supervisor state race.

## Granice prawdy

Ta wersja **nie gwarantuje**, że host ChatGPT nigdy nie zwróci `TransportTimeoutError`.

Jeżeli timeout wystąpi przed dowodem utworzenia procesu, lokalny kod Jaźni nie wykonał się i nie może naprawić platformy hosta. Aktualizacja zapewnia natomiast, że:

- długie operacje nie muszą trzymać jednego połączenia hosta do końca;
- już przyjęta operacja ma durable ID i może być odzyskana przez poll;
- daemon i supervisor są oddzielone od jednej tury ChatGPT;
- tunnel jest nadzorowany osobno;
- timeout jednej warstwy nie jest automatycznie interpretowany jako awaria wszystkich pozostałych.

Detached process w jednym sandboxie nie jest gwarancją przeżycia zniszczenia całego hosta/kontenera. Dla lokalnej instalacji Windows właścicielem długowiecznego supervisora powinien być mechanizm systemu operacyjnego (Task Scheduler lub właściwy Windows Service), a nie pojedynczy proces wykonawczy ChatGPT.

## Wersja

`16.3.25.5.76.0-persistent-supervisor-bounded-host-calls`

## Walidacja

Lokalny executor hosta ChatGPT w trakcie tej aktualizacji zwrócił `TransportTimeoutError` przed dowodem utworzenia procesu, dlatego nie przypisuje się lokalnego `pytest`, `compileall` ani smoke jako wykonanych.

Rzeczywista walidacja jest prowadzona przez GitHub Actions. Ten raport należy aktualizować zgodnie z wynikami końcowego CI/PR; statusu zielonego nie wolno deklarować przed zakończeniem jobów.
