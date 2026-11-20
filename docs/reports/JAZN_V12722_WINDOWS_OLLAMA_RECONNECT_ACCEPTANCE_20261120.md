# Jaźń v12722 — Windows/Ollama: rzeczywisty odbiór reconnect (20 listopada 2026)

**Stan dowodów:** `TERMINAL_RECONNECT_PASS`; `SQLITE_TURN_AUDIT_PENDING`; `DAEMON_RESTART_CONTINUITY_NOT_TESTED`. Ten raport odróżnia zaobserwowaną odpowiedź od zweryfikowanej transakcji zapisu i trwałości po restarcie.

- Wersja testowanej instalacji: `16.3.25.5.116.0.34.94.6.127.22`.
- Instalacja testowa: `D:\.AI\jazn_latka_v12722_monitor` (Windows, osobny root).
- Daemon: `http://127.0.0.1:8788`, PID `35396` potwierdzony przez wcześniejszy odczyt `/live`; stan `active_trusted`.
- Poprzednia instalacja v12721: `D:\.AI\jazn_latka_v12721`, port `8787`; podczas odbioru nie zatrzymano ani nie zresetowano jej sesji.
- Adapter: Ollama `gemma3:latest`, `http://127.0.0.1:11434`.
- Klient: `run.py chat-ollama --daemon-port 8788 --ollama-model gemma3:latest --ollama-api-base http://127.0.0.1:11434 --session-id local-v12722-reconnect-acceptance`.
- Sesja: `local-v12722-reconnect-acceptance`; `no_carryover=false`.
- Materiał dowodowy: transkrypt z lokalnego Windows przekazany przez operatora w rozmowie ChatGPT; nie jest to niezależny log zapisany przez GitHub CI.

## Scenariusz i faktyczne wyniki

| Etap | Lokalny czas Warszawa | Obserwacja | Wynik |
|---|---|---|---|
| 1. Użytkownik podaje syntetyczny znacznik `MALINA-628` | 2026-11-20 17:40:48 CET | Łatka: `MALINA-628.` | **PASS (visible terminal)** |
| 2. Pytanie o znacznik w poprzedniej wiadomości | 2026-11-20 17:41:06 CET | Łatka: `MALINA-628.` | **PASS (visible terminal)** |
| 3. `/exit` | Po drugim kroku | `exit_reason=user_exit_command`, `shutdown_when_loop_exits=false`, właściciel sesji `persistent_daemon` | **PASS — klient odłączony** |
| 4. Ponowne uruchomienie tego samego klienta z tym samym `session-id` i portem | Przed krokiem 5 | `runtime_session.session_id=local-v12722-reconnect-acceptance` | **PASS — ponowne podłączenie** |
| 5. Pytanie o znacznik podany przed odłączeniem | 2026-11-20 17:41:57 CET | Łatka: `MALINA-628.` | **PASS (visible terminal)** |
| 6. Powtórny `/exit` | Po trzeciej odpowiedzi | `exit_reason=user_exit_command` i brak deklaracji zatrzymania daemona | **PASS — klient odłączony** |

Żadna z trzech widocznych odpowiedzi nie została opatrzona `runtime_turn_rejected` ani `local_runtime_final_not_accepted`. W wersji v12721 analogiczne pytanie po reconnect kończyło się `runtime_turn_not_accepted` / `classified_non_dynamic_response`; obecny wynik dowodzi naprawy **tego konkretnego scenariusza** przy utrzymaniu daemona pomiędzy klientami.

## Stan dalszego odbioru

| Kryterium | Stan | Granica |
|---|---|---|
| Widoczna odpowiedź i dokładność znacznika po reconnect | `PASS` | Dowód operatorski z terminala |
| Ciągłość tej samej sesji między dwoma klientami | `PASS` | Ten sam `session-id`, bez restartu daemona |
| `runtime_turn_completed` w audit SQLite dla trzech tur | `NOT_VERIFIED` | Brak dostępu do bazy operatora z GitHub/ChatGPT |
| Kontrola SHA-256 i lineage `request_id/turn_id/trace_id` w audycie | `NOT_VERIFIED` | Wymaga poniższego odczytu |
| Trwałość zapisu rozmowy po restarcie procesu daemon | `NOT_TESTED` | Nie zatrzymywać daemona na potrzeby tego raportu |
| `full_autobiographical_recall_ready` i MEMORY continuity | `NOT_VERIFIED` | Test sesji nie jest testem pełnej MEMORY |
| Natywne nazwy EXE w Windows Task Manager | `NOT_IMPLEMENTED` | Zaplanowana **oddzielna** aktualizacja Windows launcherów |

## Następny krok: bezpieczny odczyt technicznego audytu SQLite

Wskazany audit SQLite jest w kodzie jawnie **niekanoniczną telemetrią** (`turn_execution.py::persist_audit`) — jego rekordy dowodzą zdarzeń wykonania i statusu etapów, nie zastępują osobnego sprawdzenia `MessageEnvelope`, accepted finalization ani zapisów conversation/session. Nie modyfikować bazy, `-wal`, `-shm`, markera ani `workspace_runtime`.

Odczyt należy wykonać na hoście Windows w katalogu działającej instalacji. Używa wyłącznie `mode=ro` i `PRAGMA query_only=ON`. Ograniczenie czasu obejmuje trzy tury z 17:40–17:42 CET (16:40–16:42 UTC). Wynik nie zawiera wiadomości ani odpowiedzi.

```powershell
$python = "D:\.AI\.venv\Scripts\python.exe"

@'
import sqlite3, json, hashlib
from pathlib import Path

root = Path(r"D:\.AI\jazn_latka_v12722_monitor")
db = (root / "workspace_runtime" / "core_state" / "memory_runtime"
      / "sqlite" / "runtime_write_v1" / "runtime_audit.sqlite3")
session = "local-v12722-reconnect-acceptance"
if not db.is_file():
    raise SystemExit("BRAK BAZY: " + str(db))

con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=3.0)
try:
    con.execute("PRAGMA query_only=ON")
    rows = con.execute("""
        SELECT created_at_utc, event_type, payload_json,
               payload_sha256, trace_id, turn_id
        FROM audit_runtime_events
        WHERE created_at_utc >= ?
          AND created_at_utc < ?
          AND event_type IN (
            'runtime_turn_completed',
            'runtime_turn_rejected',
            'runtime_turn_failed',
            'runtime_turn_awaiting_host_finalization'
          )
        ORDER BY created_at_utc, audit_event_id
        LIMIT 200
    """, ("2026-11-20T16:40:00", "2026-11-20T16:44:00")).fetchall()

    matched = []
    for timestamp, kind, raw, expected_hash, trace_id, turn_id in rows:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("session_id") != session:
            continue
        diag = data.get("turn_diagnostics") or {}
        stages = data.get("stages") or {}
        canonical = data.get("canonical_persistence") or {}
        stage = stages.get("canonical_persistence_commit") or {}
        item = {
            "created_at_utc": timestamp,
            "event_type": kind,
            "request_id": data.get("request_id"),
            "turn_id": turn_id,
            "trace_id": trace_id,
            "audit_payload_sha256_ok": hashlib.sha256(raw.encode("utf-8")).hexdigest() == expected_hash,
            "diagnostic_outcome": diag.get("outcome"),
            "failure_reason_code": diag.get("failure_reason_code"),
            "canonical_commit_complete": canonical.get("commit_complete"),
            "canonical_commit_stage_status": stage.get("status"),
            "canonical_committed_total": canonical.get("committed_total"),
            "canonical_rejected_total": canonical.get("rejected_total")
        }
        matched.append(item)
        print(json.dumps(item, ensure_ascii=False, indent=2))
    print("LICZBA_TUR_RUNTIME_COMPLETED:",
          sum(x["event_type"] == "runtime_turn_completed" for x in matched))
    print("LICZBA_ODRZUCEN:",
          sum(x["event_type"] in ("runtime_turn_rejected", "runtime_turn_failed") for x in matched))
    print("REKORDY_W_BADANYM_OKNIE:", len(matched))
finally:
    con.close()
'@ | & $python -B -X utf8 -
```

Oczekiwane: trzy odrębne `request_id` z `runtime_turn_completed`, zgodne `turn_id/trace_id`, prawidłowe `audit_payload_sha256_ok`; brak `runtime_turn_rejected` dla tych tur. Nie kwalifikować całego testu jako `PERSISTENCE_ACCEPTED` wyłącznie na podstawie tych zdarzeń — zgodność zapisu sesji/konwersacji i zaakceptowanego finalnego envelope podlega odrębnemu sprawdzeniu.

Odczyt bazy w trybie WAL może sporadycznie napotkać `SQLITE_BUSY`; w takim wypadku zgłosić to jako niezweryfikowany stan audytu i nie wymuszać checkpointu ani zatrzymania runtime.

## Dalsza praca

Po potwierdzeniu powyższego audytu i lineage rozpocząć **osobny branch i Draft PR** na natywne launchery Windows (`Jazn-Daemon.exe`, `Jazn-Monitor.exe`; dla workerów i Studio po zweryfikowaniu faktycznej architektury procesów). Nie zmieniać `python.exe` w miejscu ani PID/fingerprint działających instancji. Przed akceptacją wymagane testy lifecycle, recovery, auto-start, aktualizacja i rollback Windows oraz realny Menedżer zadań.

Źródła techniczne:
- [Python — sqlite3 URI read-only](https://docs.python.org/3/library/sqlite3.html#how-to-work-with-sqlite-uris)
- [SQLite — Write-Ahead Logging](https://www.sqlite.org/wal.html)
- [PyInstaller — Windows version resources](https://pyinstaller.org/en/stable/usage.html)
