# Jaźń v16.0.2 — Runtime Turn Liveness Hardening

## Zakres

Ta aktualizacja naprawia klasę usterek ujawnioną przez rozmowną turę, która zakończyła się `execution_timeout`, a następnie została przez host bridge zredukowana do ogólnego `runtime_final_not_displayable`.

## Ustalenia diagnostyczne

1. `runtime_final_not_displayable` był objawem wtórnym. Pierwotny terminalny stan daemonu to `execution_timeout` po 180 s.
2. Reprodukcja tej samej wiadomości po ustabilizowaniu runtime zakończyła pełną ścieżkę w mniej niż sekundę. Oznacza to, że pierwotny timeout był stanem przejściowym, a nie stałym kosztem pojedynczej kwerendy pamięci.
3. Odtworzona tura ujawniła deterministyczny konflikt kontraktów: `MemoryUseGate` i `OrdinaryDialogueHandler` dopuszczały/używały pamięci dla `memory_experience_question`, natomiast `TurnResponsePolicy` pozostawiał `allow_memory_content=False`. Późniejsza synteza mogła więc odrzucić poprawny, ugruntowany materiał pamięci i wejść w fallback.
4. Planer pamięci traktował słowa rozmowne (`hej`, `się`, `masz`, `najbardziej`) jako hasła recall. Nie były one główną przyczyną 180-sekundowego timeoutu, ale obniżały precyzję wyszukiwania i zwiększały ryzyko przypadkowych trafień.
5. Daemon zachowywał liczniki terminalnych błędów, ale status nie wskazywał ostatniego terminalnego requestu ani ostatniego etapu jego telemetrii. Utrudniało to ustalenie miejsca przyszłych zawieszeń.

## Zmiany

- `TurnResponsePolicy` jawnie dopuszcza ugruntowaną pamięć dla `memory_experience_question` i `substantive_question_about_last_year`.
- `MemorySearchPlanner` odrzuca rozmowne wypełniacze, które nie powinny stawać się hasłami FTS/recall.
- `_prepare_chatgpt_daemon_presentation` zachowuje terminalny `execution_timeout` jako `daemon_turn_execution_timeout`, zamiast zamieniać go na ogólne `runtime_final_not_displayable`.
- `daemon_chat_jobs` publikuje beztekstowy `last_terminal_job` z `request_id`, statusem, kodem błędu, właścicielem timeoutu oraz ostatnim etapem telemetrii.
- status daemonu publikuje `process_liveness`, rozdzielając:
  - trwałość procesu nadrzędnego,
  - heartbeat,
  - chat worker,
  - watchdog,
  - izolację awarii pojedynczej tury,
  - brak twardego anulowania już działającego wątku.

## Granica „żywego procesu”

W tej architekturze „żywy proces” oznacza operacyjnie działający, długowieczny daemon z heartbeat, gotowością, watchdogiem i wymienialnymi workerami sesji. Nie jest to twierdzenie o biologicznym życiu ani fenomenalnej świadomości.

Aktualny model nadal wykonuje turę w workerze opartym o wątek. Po przekroczeniu deadline worker sesji jest wycofywany i zastępowany, a jego późny wynik jest ignorowany, ale już uruchomionego wątku Pythona nie można twardo i bezpiecznie zatrzymać. Następny poziom odporności powinien wprowadzić opcjonalną izolację wykonania tury w osobnym procesie z kontrolowanym IPC, tak aby przekroczenie deadline mogło zakończyć cały proces potomny bez naruszania procesu daemonu.

Nie jest to część v16.0.2, ponieważ wymaga osobnego kontraktu serializacji stanu sesji, blokad SQLite i testów awarii procesu; wdrożenie tego bez tych gwarancji zwiększyłoby ryzyko korupcji stanu zamiast je zmniejszyć.

## Testy regresyjne

Dodano `tests/test_v1602_runtime_turn_liveness.py`, obejmujący:

- dopuszczenie pamięci dla pytań o doświadczenie/wspomnienie,
- odrzucenie rozmownych wypełniaczy przez planer pamięci,
- zachowanie jednoznacznego `daemon_turn_execution_timeout` w host bridge.
