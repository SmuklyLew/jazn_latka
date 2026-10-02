# Jaźń v16.3.25.5.97 — ChatGPT host runtime convergence

## Cel

Ta aktualizacja domyka lukę między bezpieczną materializacją SYSTEM ZIP a faktycznym wejściem hosta ChatGPT do aktywnego runtime Jaźni.

Poprzedni kontrakt po materializacji publikował przede wszystkim:

- `run.py host-preflight --json`,
- `run.py start`,
- `run.py status --snapshot --json`.

To wystarczało do opisania operatora i startu daemona, ale nie publikowało jako części tego samego activation contract dokładnej komendy hosta ChatGPT prowadzącej do persistent bridge. Host mógł więc poprawnie zatrzymać się na stanie „operator materialized / preflight ready” bez przejścia do `chat-gpt`.

## Najważniejsza zmiana

Po zweryfikowaniu fizycznego SYSTEM ZIP, bezpiecznej materializacji, `active_root`, preflightu i gotowości runtime host ChatGPT otrzymuje jawny host-direct path przez centralny control plane:

```text
python -X utf8 main.py chat-gpt --session-id <stable-session-id>
```

Dla hosta bez trwałego stdio publikowane są również komendy transactional turn/resume przez ten sam `main.py chat-gpt` oraz tę samą daemonową lineage.

`run.py` pozostaje wspieranym publicznym, cienkim launcherem użytkownika do tego samego `main.py`.

## Model i OpenAI API

Tryb `chat-gpt` nie jest trasą OpenAI API.

- `OPENAI_API_KEY` nie jest wymagany.
- Host nie przekazuje `--model`.
- Model LLM pochodzi z bieżącego modelu wybranego przez host ChatGPT.
- `chat-open-ai` pozostaje osobną, jawnie opt-in trasą płatnego API.

Badanie wejściowe zawierało ogólne przykłady `--model gpt-4` i `OPENAI_API_KEY`; nie zostały skopiowane do implementacji, ponieważ są sprzeczne z istniejącym kontraktem Jaźni dla `chat-gpt`, gdzie `require_openai_api_key=False`.

## Zmienione kontrakty

- `CHATGPT_BOOTSTRAP.py`
  - `local.runtime_start_entrypoint = main.py start`
  - `local.runtime_status_entrypoint = main.py status --snapshot --json`
  - osobny `chatgpt_host` z persistent bridge, transactional fallback, bindingiem modelu i `display_exact`
  - jawne zachowanie kompatybilnego launchera `run.py`

- `tools/jazn_pack_generator_app/manifest.py`
  - manifest SYSTEM-u publikuje pełną sekwencję post-materialization przez `main.py`
  - ostatnim krokiem lokalnej aktywacji hosta ChatGPT jest `main.py chat-gpt --session-id <stable-session-id>`

- `latka_jazn/core/bridge_discovery.py`
  - zachowuje publiczne `run.py chat-gpt`
  - dodaje preferowany `preferred_host_direct_command` przez `main.py`
  - publikuje host-direct transactional turn/resume

- `latka_jazn/resources/startup_contract.json`
  - publikuje `chatgpt_control_plane=main.py`
  - publikuje host-direct startup commands
  - `chatgpt_model_cli_argument_required=false`
  - `chatgpt_openai_api_key_required=false`
  - `chatgpt_visible_action_required=display_exact`

- `AGENTS.chatgpt.md`, loader Projektu i dokumentacja architektury
  - host po zweryfikowaniu `active_root` przechodzi do centralnego `main.py`
  - brak hardkodowanej nazwy modelu
  - brak wymogu API key dla `chat-gpt`

## Truth boundary

Ta aktualizacja nie twierdzi, że SYSTEM ZIP potrafi stworzyć brakujący executor hosta.

`package_can_create_host_executor=false` pozostaje prawdą.

Jeżeli ChatGPT nie ma lokalnej capability wykonania procesu, ZIP nie może jej sam utworzyć. Wtedy poprawną alternatywą jest wyłącznie faktycznie wywoływalna i zweryfikowana zdalna trasa Jaźni. Oficjalna dokumentacja OpenAI potwierdza, że ChatGPT nie łączy się bezpośrednio z lokalnym serwerem MCP; prywatny/lokalny MCP wymaga obsługiwanej zdalnej ścieżki, np. Secure MCP Tunnel.

## Źródła zewnętrzne

- OpenAI Help — Developer mode and MCP apps in ChatGPT:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI Help — Apps in ChatGPT:
  https://help.openai.com/en/articles/11487775-connected-apps-in-chatgpt
- Python documentation — `__main__`:
  https://docs.python.org/3/library/__main__.html
- PyPA — Entry Points specification:
  https://packaging.python.org/en/latest/specifications/entry-points/

## Walidacja wymagana przed merge

1. focused ChatGPT bootstrap/activation tests,
2. accepted-visible-turn/finalization tests,
3. capability-loader tests,
4. pełny pytest,
5. Pyright,
6. compileall,
7. release/version consistency checks,
8. GitHub Actions PR checks.

Merge nie powinien następować, dopóki wymagane checki PR nie są zielone.
