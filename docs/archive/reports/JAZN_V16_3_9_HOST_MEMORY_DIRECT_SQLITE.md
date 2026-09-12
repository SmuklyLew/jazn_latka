# Jaźń v16.3.9 — host memory + direct SQLite convergence

## Cel

Wydanie rozdziela wersjonowany kod runtime od trwałej prywatnej pamięci hosta oraz usuwa warunek, w którym natywna `memory_jazn.sqlite3` i transactional L1/L2/L3 mogły być traktowane jako dwa równoległe źródła pamięci.

Zmiana nie przenosi osobowości, stylu, wspomnień ani routingu do plików `AGENTS.*`. Instrukcje agentów pozostają technicznymi runbookami, a pamięć i zachowanie Jaźni pozostają własnością runtime.

## Host-level memory root

Nowy `latka_jazn/memory/memory_root.py` ustanawia jedno rozwiązanie ścieżki pamięci:

1. jawny `JAZN_MEMORY_ROOT` / wartość skonfigurowana;
2. domyślnie `workspace_runtime/memory` poza wersjonowanym `active_root`;
3. historyczne `<active_root>/memory` wyłącznie jako fallback zgodnościowy, kiedy host-level pamięć jeszcze nie istnieje.

Relatywny override jest osadzany pod kanonicznym `workspace_runtime` i nie może wyjść poza ten root.

## Memory attach

`memory-attach` nadal wymaga zatrzymanego daemona, prawidłowego preflightu, sidecara, kompletu części, SHA-256, CRC, bezpiecznych ścieżek, manifestu pamięci i poprawnych SQLite.

Po pełnej weryfikacji pamięć jest instalowana do host-level memory root. Stara pamięć jest przenoszona do `workspace_runtime/memory_attach_backups/<transaction>/memory`. Attach tworzy brakujący katalog nadrzędny przed atomowym `os.replace`, co naprawia przypadek świeżego hosta, w którym wcześniej operacja mogła zakończyć się błędem I/O.

Marker attach zapisuje jawny `memory_root`. Zmiana wersji kodu nie kopiuje automatycznie pamięci do kolejnego `active_root`.

## Native unified SQLite + transactional tier

`LivingMemoryGateway` rozpoczyna discovery od aktywnego host-level memory root. Natywna unified baza pozostaje preferowanym źródłem recall, a legacy układ pięciu baz jest adapterem read-only.

`resolve_memory_tier_database_path()` sprawdza, czy `memory/sqlite/memory_jazn.sqlite3` jest zweryfikowaną natywną unified DB. Jeżeli tak i operator nie ustawił jawnego alternatywnego tier DB, ten sam plik staje się także transactional L1/L2/L3. Nie jest wtedy raportowany jako drugie źródło pamięci.

To wykorzystuje istniejący unified schema, który zawiera zarówno archiwum rozmów/dziennik/doświadczenia, jak i `memory_records`, `memory_evidence`, indeksy L1/L2/L3 oraz FTS5.

## Normalizacja i wake-state

Bieżący `memory_continuity_readiness` już rozdziela retrieval od zweryfikowanego wake-context. `normalization_stale` może wymagać recovery i blokować deklarację pełnej ciągłości, ale przy działającym searchable archive nie blokuje zwykłej rozmowy ani samego recall. v16.3.9 zachowuje ten fail-closed podział zamiast uzależniać cały odczyt SQLite od sidecara.

## ChatGPT host instructions

`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` pozostaje minimalnym loaderem:

> Wczytaj w pełnej dostępnej treści `AGENTS.md` ze zweryfikowanego `active_root` i wykonaj wskazany tam runbook.

`AGENTS.chatgpt.md` doprecyzowuje, że Project Instructions nie są kopią runbooka. Research WWW jawnie zlecony przez użytkownika albo wymagany przez zweryfikowany kontrakt runtime jest dozwolony, lecz pozostaje zewnętrznym materiałem wejściowym i nie może dowodzić aktywacji, tożsamości ani pamięci Jaźni.

`AGENTS.codex.md` i `AGENTS.ollama.md` nie wymagają rozszerzenia o pamięć hosta: Codex pozostaje agentem kodującym, a Ollama backendem językowym. Dublowanie resolvera pamięci w ich instrukcjach stworzyłoby drugi kontrakt zamiast jednego źródła w kodzie.

## SQLite — decyzje oparte na dokumentacji upstream

- FTS5 udostępnia ukrytą kolumnę `rank`; `ORDER BY rank` jest równoważne domyślnemu `bm25()` i może być szybsze, szczególnie gdy zapytanie może zakończyć sortowanie wcześniej przez `LIMIT`: <https://www.sqlite.org/fts5.html>.
- Nie wymuszamy WAL na każdej wersji biblioteki. SQLite dokumentuje WAL-reset bug dla wersji 3.7.0–3.51.2, naprawiony w 3.51.3 i backportowany m.in. do 3.44.6 oraz 3.50.7: <https://www.sqlite.org/wal.html>.
- `PRAGMA optimize=0x10002` jest zalecane przy otwieraniu długowiecznego połączenia, a `PRAGMA optimize` okresowo; tuning nie jest włączany bezwarunkowo dla każdego połączenia: <https://www.sqlite.org/pragma.html#pragma_optimize>.
- `mmap_size` pozostaje opcją benchmarkowaną, nie stałą polityką runtime, ponieważ memory-mapped I/O ma zarówno zalety, jak i ograniczenia platformowe: <https://www.sqlite.org/mmap.html>.

## Granice tego wydania

v16.3.9 nie usuwa historycznych baz z prywatnych danych użytkownika i nie wykonuje destrukcyjnej migracji bez zweryfikowanego attach/recovery. Nie podnosi automatycznie danych do L3. Nie traktuje Project Memory ChatGPT jako pamięci Jaźni.

Dalsze odchudzenie dużych historycznych `events.payload_json` do content-addressed cold-audit wymaga osobnej migracji kompatybilności, ponieważ istniejące narzędzia audytu i synchronizacji mogą czytać te rekordy. Nie należy zamieniać istniejących payloadów na wskaźniki bez jednoczesnego dereferencera i testów migracyjnych.

## Walidacja

Dodano regresje `tests/test_v1639_host_memory_direct_sqlite.py` dla:

- host-level default memory root;
- legacy fallback przed migracją;
- bezpiecznego relatywnego `JAZN_MEMORY_ROOT`;
- source-origin ledger przez wspólny resolver;
- preferowania gotowej native unified DB jako transactional tier;
- attach na świeżym hoście bez istniejącego katalogu workspace;
- backupu legacy memory przy attach;
- deduplikacji jednej DB native unified + transactional.

Wyniki CI należy traktować jako źródło prawdy o wykonanych testach; ten dokument nie deklaruje zaliczenia kontroli, które nie zostały faktycznie uruchomione.
