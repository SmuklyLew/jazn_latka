# Jaźń v16.3.25.5.89.0 — host executor spawn diagnostics convergence

## Cel

Wydanie zamyka lukę diagnostyczną pomiędzy awarią hosta przed utworzeniem procesu a
awarią Jaźni po faktycznym spawnie procesu.

Nadrzędna granica prawdy:

- `process_created=false` oznacza wyłącznie brak potwierdzonego procesu;
- taki stan nie jest dowodem awarii filesystemu, SYSTEM-u, MEMORY, SQLite, WAL,
  FTS ani recall;
- diagnostyka MEMORY zaczyna się dopiero po potwierdzonym utworzeniu procesu.

## Źródła techniczne

Implementacja była sprawdzana względem dokumentacji pierwotnej:

- Linux `execve(2)`: https://man7.org/linux/man-pages/man2/execve.2.html
- SQLite WAL: https://www.sqlite.org/wal.html
- SQLite FTS5: https://www.sqlite.org/fts5.html
- Docker bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Docker user namespaces: https://docs.docker.com/engine/security/userns-remap/
- Microsoft WSL filesystem guidance:
  https://learn.microsoft.com/en-us/windows/wsl/filesystems
- OpenAI Secure MCP Tunnel:
  https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI MCP servers:
  https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- GitHub Actions artifacts:
  https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow

Źródła te opisują możliwości warstw systemowych i transportowych. Nie pozwalają
wnioskować o nieudokumentowanych szczegółach wewnętrznej infrastruktury hosta
ChatGPT. Dlatego nie przypisujemy ogólnego `ClientError` konkretnej fazie bez
jawnego evidence hosta.

## Pre-spawn failure contract

Nowy classifier rozróżnia:

| error_class | reason_code | retry_class |
|---|---|---|
| ClientError | host_client_error_pre_spawn | ambiguous_host_failure |
| InvalidArgumentError | host_invalid_argument_pre_spawn | non_retryable_request |
| TransportTimeoutError | host_transport_timeout_pre_spawn | transient_transport |
| StreamingExecNotEnabledContainerError | host_streaming_exec_unavailable_pre_spawn | unsupported_surface |
| inne | host_unknown_error_pre_spawn | unknown |

Klasyfikacja opisuje evidence; nie tworzy nieograniczonej pętli retry. Kanoniczny
loader nadal dopuszcza najwyżej jedną rzeczywiście niezależną alternatywną
powierzchnię executora.

`HostExecutorObservation` może teraz przenosić opcjonalne evidence:

- `spawn_phase`;
- `intended_cwd`;
- `command_fingerprint_sha256`;
- `executor_allocation_state`;
- `materialization_state`;
- `mount_preparation_state`.

Pola post-spawn (`pid`, `observed_cwd`, `platform`, UID/GID) są zabronione,
gdy `process_created=false`.

## Post-spawn diagnostics

Nowa komenda:

```text
python -X utf8 run.py host-diagnose --root . --json
```

raportuje wyłącznie metadane procesu i pamięci:

- PID, platformę, cwd, UID/GID i supplementary groups, gdy host je udostępnia;
- skonfigurowany oraz rozwiązany `JAZN_MEMORY_ROOT`;
- źródło wyboru canonical/legacy;
- detekcję pustego canonical placeholder;
- read/write access do rootu i katalogu SQLite;
- native unified readiness probe.

Komenda nie zwraca prywatnych rekordów MEMORY ani fragmentów wspomnień.

## Durable memory convergence

`host-op --kind memory-converge` zachowuje jeden wcześniej przydzielony
`operation_id` podczas kontrolowanego wznowienia.

Aktualna polityka jest celowo węższa od ogólnego retry:

- exit `75` z `memory-converge` oznacza stan pending/resumable i może być
  wznowiony;
- maksymalnie 3 próby;
- backoff: 1 s, 2 s;
- inne niezerowe kody są terminalne w tym workerze;
- błędy spawnu procesu są terminalne i nie są maskowane retry.

Dzięki temu hash/integrity/permission/argument failures nie są automatycznie
ponawiane jako rzekomo przejściowe.

## Sentinel autobiographical recall

Nowa komenda:

```text
python -X utf8 run.py memory-sentinel \
  --root . \
  --manifest /secure/jazn/sentinel-memory.json \
  --json
```

Manifest jest prywatnym wejściem operatora i nie należy do repozytorium.

Przykładowy neutralny format:

```json
{
  "schema_version": "jazn_memory_sentinel/v1",
  "queries": [
    {
      "query": "<private autobiographical probe>",
      "minimum_native_hits": 1
    }
  ]
}
```

Wynik nie powtarza query ani excerptów. Raportuje wyłącznie SHA-256 zapytania,
liczniki, readiness i wynik gate.

Sukces wymaga jednocześnie:

- `full_autobiographical_recall_ready=true`;
- hitów z `gateway_source_kind=native_unified`;
- `autobiographical_source_ready=true`;
- `selected_canonical=true`.

Sam `ready_transactional_tier_only` nie przechodzi sentinel gate.

## CI

Workflow `host-spawn-memory-convergence.yml` uruchamia:

- host contract matrix na Ubuntu, Windows i macOS;
- compileall nowych ścieżek;
- regresje host-preflight, post-spawn, durable retry, memory root i sentinel;
- prawdziwą komendę `run.py host-diagnose`;
- kontrolę wersji wydania;
- na Ubuntu kontrakt Docker bind mount:
  - RW;
  - RO;
  - brakujący source;
  - UID/GID bez prawa zapisu.

Istniejący `persistent-runtime-e2e` ma rozszerzone path filters o nowe moduły i
testy.

## Ograniczenie

Ten patch nie może wymusić, aby host ChatGPT przydzielił lokalny executor.
Jeżeli błąd następuje przed utworzeniem procesu, kod repozytorium nie został
wykonany. W takim przypadku naprawa po stronie Jaźni polega na poprawnym
zaklasyfikowaniu evidence, niewyciąganiu wniosków o MEMORY oraz przejściu do
zweryfikowanego `remote_runtime` / `host_handoff` zgodnie z istniejącym
runbookiem.

Secure MCP Tunnel pozostaje właściwą architekturą dla trwałego prywatnego
runtime, gdy host lokalny jest efemeryczny lub niedostępny; jego dostępność musi
być jednak zweryfikowana przez rzeczywiste capability i readiness evidence, nie
przez samą konfigurację.
