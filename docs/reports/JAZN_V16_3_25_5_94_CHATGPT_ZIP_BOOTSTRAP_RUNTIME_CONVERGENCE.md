# Jaźń v16.3.25.5.94 — ChatGPT ZIP bootstrap runtime convergence

## Cel

Wydanie domyka lukę pomiędzy trzema odrębnymi stanami: ChatGPT widzi/materializuje SYSTEM ZIP, zweryfikowany operator istnieje w rozpakowanym folderze oraz host faktycznie posiada trasę wykonawczą do uruchomienia lub obsługi runtime.

Badanie z 2026-10-01 wskazało, że sam ZIP nie może nadać bieżącej powierzchni ChatGPT executora ani connectora MCP. Aktualizacja nie próbuje obchodzić tej granicy.

## Zmiana

- `CHATGPT_BOOTSTRAP.py` po bezpiecznej materializacji zwraca `activation_contract` z osobnym opisem ścieżki lokalnej i zdalnej.
- `--post-materialization-preflight` uruchamia wyłącznie `run.py host-preflight --json` przez `runpy` w tym samym już działającym interpreterze. Nie używa `subprocess`, nie tworzy child process i nie deklaruje uruchomionego daemona.
- Pack Generator publikuje `/mcp`, `jazn_status`, `jazn_generate_visible_reply`, preferowany `public_streamable_http` oraz zachowuje `package_can_create_host_executor=false` i `remote_runtime_route_ready_from_package_alone=false`.
- Runbook rozróżnia host, który już wykonuje bootstrap Python, od hosta, który zwraca `ClientError` zanim powstanie jakikolwiek proces.

## Docelowy przebieg

```text
SYSTEM ZIP
  -> trusted SHA-256 + expected size
  -> bounded ZIP inspection / CRC / path limits
  -> verified extraction to fresh destination
  -> materialized_operator_ready
  -> activation_contract
       | local Python already executing
       |   -> same-interpreter host-preflight (no child process)
       |   -> normal run.py/main.py lifecycle only if host capabilities permit
       |
       | no local Python execution
       |   -> actually callable Jaźń connector/app
       |   -> jazn_status
       |   -> verified remote_runtime
       |   -> jazn_generate_visible_reply / resume / finalization
       |
       | neither route verified
       -> fail-closed host diagnostic
```

## Granice

`--post-materialization-preflight` nie pomaga, gdy błąd hosta występuje przed uruchomieniem Pythona. W takim przypadku kod wewnątrz ZIP-a nie może sam się wykonać. Obecność `/mcp`, tunelu, URL-a lub kodu serwera także nie dowodzi, że bieżący ChatGPT posiada wywoływalny connector Jaźni.

`materialized_operator_ready` nadal nie jest persistent runtime ani prawem do odpowiedzi jako Jaźń. Widoczna wypowiedź wymaga istniejącej lineage tury i zaakceptowanego `display_exact`.

## Walidacja

Nowy `tests/test_chatgpt_zip_bootstrap_runtime_convergence.py` sprawdza activation contract, same-interpreter preflight bez child process, pola MCP i identity v16.3.25.5.94. Pełne testy, Pyright, package-smoke i release-hardening muszą zostać potwierdzone przez CI dla finalnego HEAD brancha.
