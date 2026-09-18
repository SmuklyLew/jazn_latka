# Jaźń v16.3.25.5.79.0 — host executor epoch recovery

## Cel

Ta aktualizacja nie próbuje naprawiać infrastruktury hosta ChatGPT z poziomu paczki Jaźni. Pre-spawn `TransportTimeoutError` pozostaje obserwacją granicy host/executor, a nie diagnozą ZIP-a, Pythona, `run.py` ani daemona.

Zmiana usuwa dwa praktyczne problemy ujawnione 18 września 2026:

1. negatywne evidence `host_executor_unavailable` mogło zostać potraktowane zbyt trwale mimo późniejszego odzyskania/reprowizjonowania powierzchni wykonawczej;
2. ręcznie budowany `operation_id` mógł zawierać znak `+` z lokalnego offsetu ISO-8601, mimo że durable-operation regex go zabrania.

## Implementacja

- `HostExecutorObservation.observation_generation` identyfikuje logiczną generację hostowej powierzchni wykonawczej;
- agregacja wybiera wyłącznie najwyższą zaobserwowaną generację i nie miesza starego failure/success z nową powierzchnią;
- diagnostyka per-surface publikuje `observation_generation`;
- produkcyjny parser `chatgpt_host_preflight_parse.py` przenosi `observation_generation` z hostowego JSON do `HostExecutorObservation`, z kompatybilnym domyślnym `0`;
- `generate_operation_id()` tworzy identyfikator w UTC, z dozwolonego alfabetu, z entropią hex;
- publiczne `run.py host-op-id --kind ... --json` pozwala prealokować identyfikator przed side-effecting submit;
- `AGENTS.chatgpt.md` i cienki loader jawnie mówią, że `host_executor_unavailable` nie jest stanem sticky między generacjami hosta;
- recovery po odzyskaniu executora wraca do discovery od zera i ponownie weryfikuje filesystem/paczkę/runtime;
- zasada „ten sam request/operation id po ambiguous transport, bez replayu wiadomości” pozostaje bez zmian.

## Granica prawdy

Nowa generacja obserwacji nie oznacza automatycznego retry tej samej operacji. W obrębie jednej generacji nadal obowiązuje bounded probe: jedna powierzchnia podstawowa i najwyżej jedna rzeczywiście niezależna alternatywa. Po utracie odpowiedzi po możliwym submit nadal wolno wyłącznie poll/resume tego samego `operation_id` / `request_id`.

## Remote runtime

Executor-independent ingress z v78 pozostaje preferowaną długoterminową trasą ciągłości, gdy managed Secure MCP Tunnel jest rzeczywiście gotowy i bieżący host ChatGPT udostępnia odpowiadającą connector/app capability. Ta aktualizacja nie fabrykuje connectora ani tunelu.

Źródła zewnętrzne użyte do weryfikacji architektury:
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI tunnel-client: https://github.com/openai/tunnel-client
- Python subprocess: https://docs.python.org/3/library/subprocess.html

## Testy regresji

Nowy test `tests/test_chatgpt_host_executor_epoch_recovery.py` pokrywa:
- bezpieczny UTC `operation_id` i brak `+`;
- odrzucenie naive datetime i złej entropii;
- obecność publicznego `host-op-id`;
- stale failure -> nowy success bez fałszywego degraded/sticky state;
- stary success -> nowy failure bez dziedziczenia poprzedniej dostępności;
- odrzucenie ujemnej generacji;
- zachowanie `observation_generation` przez produkcyjny parser host-preflight;
- zgodność środowiska `release-hardening` z kanonicznym audytem Pyright przez instalację extra `mcp-http` przed analizą aktywnego drzewa;
- kontrakty runbooka i cienkiego loadera.

Metadane `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` nie są edytowane ręcznie. Zgodnie z runbookiem muszą zostać zsynchronizowane przez kanoniczny workflow repozytorium.
