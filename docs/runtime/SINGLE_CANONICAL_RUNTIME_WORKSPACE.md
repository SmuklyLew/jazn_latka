# Single canonical runtime workspace — fundament v16.0.0, bieżący invariant v16+

## Status dokumentu

Architektura jednego kanonicznego `workspace_runtime` została wprowadzona w release **v16.0.0 / single-canonical-runtime-workspace** i pozostaje obowiązującym invariantem kolejnych linii v16.x. Późniejsze release'y mogą rozszerzać zawartość workspace, ale nie mogą przywrócić per-version mutable workspace ani uzależniać truth state od katalogu konkretnego release'u.

Aktualna linia rozwoju korzysta z tego kontraktu jako fundamentu dla host bridge, daemona, session/checkpoint state, memory attach oraz planowanego ingressu załączników `16.3.25.A.01+ -> 16.3.26`.

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
│   ├── attachment_ingress/          # opcjonalny transient staging/cache od v16.3.26
│   └── ...
├── jazn_latka_vCurrent/
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

## Ingress załączników — invariant dla 16.3.25.A.01+ -> 16.3.26

Planowany host attachment/multimodal ingress ma rozszerzać istniejący kontrakt v16.0.0, a nie tworzyć równoległy mutable root.

- trwałe lub tymczasowe dane techniczne hosta związane z materializacją załącznika, jeśli są potrzebne, należą do host-level `workspace_runtime/attachment_ingress/` lub równoważnego namespace'u pod kanonicznym workspace;
- nie wolno tworzyć `<active_root>/workspace_runtime/attachments` jako nowego per-release stanu;
- sam fakt odebrania pliku nie oznacza promocji do `memory/`, L2 ani L3;
- plik może wejść do trwałej pamięci dopiero przez istniejące truth/provenance/promotion gates;
- `attachment-only`, `text+attachment` i multi-attachment są legalnymi typami wejścia tury i nie mogą wymagać sztucznego tekstu zastępczego;
- staging/cache ma być bounded, identyfikowalny przez SHA/provenance i usuwalny bez naruszania trwałej pamięci;
- model bez capability vision nie może raportować, że „widział” obraz; ścieżka ma fail-closed albo użyć jawnie dostępnego multimodalnego backendu/hosta.

Numeracja `16.3.25.A.xx` jest numeracją etapów planistycznych/checkpointów, nie kanonicznym `PACKAGE_VERSION`. Finalny systemowy release tej pracy ma numer `16.3.26`.

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
