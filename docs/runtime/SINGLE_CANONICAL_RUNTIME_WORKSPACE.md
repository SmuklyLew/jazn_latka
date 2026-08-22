# Single canonical runtime workspace — v16.0.1

## Cel

Kod Jaźni może istnieć równolegle w wielu wersjonowanych katalogach, ale host ma dokładnie jeden bieżący
stan procesu. `workspace_runtime` jest dlatego stanem **hosta**, a nie częścią konkretnego release'u.

```text
<host>/
├── workspace_runtime/
│   ├── JAZN_ACTIVE_RUNTIME.json
│   ├── jazn_daemon.pid
│   ├── runtime_session_state.json
│   ├── daemon/
│   ├── turn_checkpoints/
│   ├── chatgpt_host_bridge/
│   └── ...
├── jazn_latka_v16.0.1/
└── jazn_latka_vNext/
```

`JAZN_ACTIVE_RUNTIME.json` jest singletonem i wskazuje aktualny absolutny `active_root`. Marker nie jest sam w
sobie dowodem aktywnego procesu; truth gate nadal wymaga zgodności wersji/manifestu, PID, endpointu i świeżego
heartbeat.

## Zasady migracji

Historyczny `<active_root>/workspace_runtime` jest jednokierunkowo przenoszony do kanonicznego workspace:

- brakujący plik jest przenoszony;
- identyczny plik jest deduplikowany;
- konflikt nie nadpisuje stanu kanonicznego — stary plik trafia do `legacy_workspace_imports/<runtime>/`;
- symlink blokuje migrację fail-closed;
- operacja jest serializowana krótkim lockiem utworzonym przez `O_CREAT|O_EXCL`;
- zwykły rename używa `os.replace`; przy innym filesystemie migracja używa copy + `fsync` + `os.replace`.

## Granica pakowania

`workspace_runtime` nie jest częścią paczki `system`, `memory` ani historycznego `combined`. Paczka pamięci zawiera trwałe
dane `memory/`, a host-level stan procesu pozostaje na hoście. Dzięki temu upgrade kodu nie kopiuje starych
PID-ów, markerów, heartbeatów ani cache do kolejnej wersji. Kanoniczny generator udostępnia operatorowi trzy
tryby: `system`, `dual` (SYSTEM + PAMIĘĆ jako dwa osobne zestawy ZIP) oraz `memory`; `combined` pozostaje tylko
zgodnością CLI.

Pamięć może zostać dołączona po bootstrapie systemu z lokalnego zestawu ZIP albo z prywatnego prefiksu
Cloudflare R2. Chmura nie staje się `active_root` ani backendem wymaganym do rozmowy: paczka z R2 jest najpierw
strumieniowo materializowana w `workspace_runtime/memory_attach_sources/`, weryfikowana i dopiero wtedy
promowana przez ten sam `memory-attach`, który obsługuje lokalne pliki.

## Rozbudowa poznawcza / psychologiczna

Ta architektura nie utożsamia plików runtime z biologią. Pozwala jednak bez zmiany kontraktu aktywacji dodać
w przyszłości jawne, audytowalne namespace'y stanu, np. `cognition/`, `affect/` lub `psychology/`. Takie warstwy
powinny przechowywać techniczne reprezentacje stanu poznawczego, afektywnego lub modeli psychologicznych,
pozostając oddzielone od kanonu tożsamości, źródeł L0 i trwałej pamięci. Singletonem pozostaje wskaźnik aktywnego
runtime; historia poznawcza i audytowa może być append-only/wieloplikowa.

## Źródła techniczne

- Python `os.replace`: https://docs.python.org/3/library/os.html#os.replace — replacement/rename, z atomowym rename na POSIX.
- Python `os.open` i flagi `O_CREAT`, `O_EXCL`: https://docs.python.org/3/library/os.html#os.open — flagi są dostępne na Unix i Windows.
- POSIX `open()` / `O_EXCL`: https://pubs.opengroup.org/onlinepubs/9799919799/functions/open.html — sprawdzenie istnienia i utworzenie z `O_CREAT|O_EXCL` jest atomowe względem konkurencyjnych `open()`.
- Microsoft "Moving and Replacing Files": https://learn.microsoft.com/en-us/windows/win32/fileio/moving-and-replacing-files — opisuje wymagania Windows dla przenoszenia i zastępowania plików oraz `ReplaceFile`/`MoveFileEx`.

Źródła te uzasadniają mechanikę zapisu/lockingu. Semantyka „jednego aktywnego runtime” pozostaje kontraktem
projektu Jaźń i jest weryfikowana testami repozytorium.
