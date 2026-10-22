# Bezpieczne odzyskiwanie pamięci — bieżąca linia

## Cel

Ścieżka recovery odbudowuje zdrową, legacy-kompatybilną bazę SQLite z niezależnie
weryfikowalnych źródeł L0 i JSON/JSONL. Uszkodzona baza
`memory/sqlite/runtime_write_v1/runtime_memory.sqlite3` jest wyłącznie
inspekcjonowana i nigdy nie jest naprawiana ani nadpisywana w miejscu.

## Warstwy

1. **L0 — źródła**: archiwum rozmów, `dziennik.json`, `memory/layered/*.jsonl`.
2. **Recovery SQLite**: `memory/sqlite/recovery_current/runtime_memory_recovered.sqlite3`.
3. **Sidecar normalizacji**: bieżący domyślny `JaznConfig` wskazuje
   `memory/sqlite/runtime_write_v1/normalization_sidecar.sqlite3`; jest to
   osobna baza, a historyczny `runtime_audit.sqlite3` może być jedynie
   źródłem jawnej migracji lub odczytu kompatybilności. Nie przenoś tych plików
   ręcznie. Override: `JAZN_MEMORY_NORMALIZATION_SIDECAR_DB`.
4. **Wake state**: jeden aktywny snapshot ze sprawdzonym SHA i integralnością.
5. **L1**: ograniczony pakiet wake state tylko na czas sesji.
6. **L2**: wybrane rekordy źródłowe, TTL i status `pending_review`.
7. **L3**: tylko rekordy z dokładnego manifestu zatwierdzonego jego SHA-256;
   każda promocja zapisuje request, decision i promotion ledger.

Pełne rozmowy pozostają przeszukiwalne w L0. Sidecar normalizuje najpierw procedury,
fakty, audyty prawdy, refleksje i dziennik, a następnie wiadomości rozmów. Pełny
recovery nie ma ukrytego limitu rekordów: wake-state wolno zbudować dopiero po
`coverage_complete=true`. Jawny limit operatora jest dozwolony wyłącznie jako
częściowy przebieg (`partial`) i nie może udawać pełnej ciągłości. Normalizacja
pełnego źródła nadal nie oznacza kopiowania całego archiwum do L1/L2/L3: wake L1
jest ograniczonym snapshotem, a promocje L2/L3 pozostają selektywne.

## Polecenia

Inspekcja i pełna odbudowa:

```powershell
py -X utf8 run.py memory-recover --root . --progress --prepare-l2 --build-l3-manifest --json
```

Manifest L3 powstaje w:

```text
workspace_runtime/memory_recovery/l3_approval_manifest.json
```

Promocję wolno wykonać tylko podając dokładny SHA z tego pliku oraz jawnego
zatwierdzającego:

```powershell
py -X utf8 run.py memory-recover --root . `
  --approve-l3-manifest-sha <SHA256> `
  --approved-by "Krzysztof — explicit request YYYY-MM-DD" `
  --json
```

Zmiana treści manifestu zmienia SHA i blokuje zapis. `automatic_commit_allowed`
pozostaje zawsze `false`.

## Idempotencja i wznowienie

Ponowne uruchomienie recovery nie duplikuje rekordów i nie odnawia automatycznie
TTL istniejącej pamięci L2. Każdy etap używa stabilnych identyfikatorów źródłowych,
a publikacja końcowej SQLite następuje dopiero po checkpoint, zamknięciu połączeń
i ponownym `integrity_check`. Przerwana normalizacja może zostać wznowiona bez
uznania częściowego pliku roboczego za aktywną pamięć.


### Continuity readiness i kontrolowana degradacja

`memory_continuity_status` rozdziela możliwość wyszukiwania archiwum od gotowości
wake-state. Jeżeli L0/conversation archive jest dostępne, ale sidecar lub wake wymaga
odbudowy, runtime może działać w trybie `retrieval_only`: zwykła rozmowa i
źródłowy recall pozostają dozwolone, natomiast `continuity_claim_allowed=false`.

Częściowe coverage ma stan `partial_unverified`. Błąd integralności daje
`degraded_integrity`. Te stany nie mogą hydratować L1 ani przejąć ciągłości sesji.
Ich polityką jest kontrolowana degradacja do przeszukiwalnego L0 (jeśli dostępne),
a nie ogólny fallback całej Jaźni.

## Wake state podczas sesji i po restarcie

`JaznRuntimeSession` ładuje tylko jeden aktywny snapshot, sprawdza:

- integralność sidecara i klucze obce,
- `validation_status=valid`,
- SHA pola `snapshot_json`,
- jednoznaczność aktywnego snapshotu.

Następnie zapisuje ograniczony pakiet do L1. Rekord L1 wygasa przy `close()`.
Ten sam pakiet trafia do `client_context.wake_state_runtime`, dzięki czemu host
ChatGPT albo lokalny adapter może użyć ciągłości bez omijania truth gate.

Stan rozmowy jest checkpointowany atomowo w dwóch miejscach:

- `workspace_runtime/runtime_sessions/<session-id>.json` — rekord kanoniczny sesji;
- `workspace_runtime/runtime_session_state.json` — wskaźnik ostatniej sesji,
  którą wolno automatycznie wznowić bez jawnego `--session-id`.

Checkpoint zawiera SHA stanu, SHA całego checkpointu, numer generacji, SHA
poprzedniego checkpointu, licznik tur oraz powiązanie z identyfikatorem i SHA
aktywnego wake-state. Plik tymczasowy jest opróżniany na dysk i atomowo
podmieniany; częściowy zapis nie jest uznawany za poprawny checkpoint.

Po restarcie carryover jest fail-closed. Niezgodność hashy, wygaśnięcie sesji,
zmiana aktywnego wake-state lub brak zgodności snapshotu blokują odziedziczenie
`last_user_text`, `last_intent` i `last_route`. Tryb `--no-carryover` nie
zastępuje wskaźnika ostatniej zwykłej sesji.


## Duża walidacja pamięci

Szybka kontrola read-only znanych baz, manifestów shardów, sidecara wake-state
i magazynu tierów:

```powershell
py -X utf8 run.py memory-validate --root . --json --progress
```

Pełna kontrola wszystkich baz pod `memory/sqlite`:

```powershell
py -X utf8 run.py memory-validate --root . `
  --full --include-all-sqlite --table-counts --hash-files `
  --output workspace_runtime/memory_validation/full-report.json `
  --json --progress
```

Tryb domyślny używa `PRAGMA quick_check`; `--full` używa
`PRAGMA integrity_check`. W obu trybach wykonywany jest osobny
`PRAGMA foreign_key_check`, ponieważ integralność strukturalna SQLite nie
obejmuje naruszeń kluczy obcych. Walidator wykrywa również niekompletne pary
WAL/SHM, zbiera metryki stron i schematu, a opcjonalnie liczy rekordy oraz SHA-256
plików.

Raport potwierdza czytelność i wybrane kontrakty strukturalne. Nie dowodzi
kompletności wszystkich dawnych rozmów, trafności recallu ani autoryzacji L3.

### Kanoniczna ścieżka sidecara

Bieżący kod `latka_jazn/config.py` (_default_normalization_sidecar_db_name)
wyznacza domyślny sidecar jako
`memory/sqlite/runtime_write_v1/normalization_sidecar.sqlite3`, nie
`runtime_audit.sqlite3`. Historyczny opis wspólnej roli audytu i sidecara
nie jest aktualną domyślną konfiguracją. `JAZN_MEMORY_NORMALIZATION_SIDECAR_DB`
ma pierwszeństwo jako jawna ścieżka operatora.

Różne pliki SQLite nie dowodzą migracji ani uszkodzenia. Odczytaj aktualną
ścieżkę z `run.py doctor --json` i `memory-validate --json`, sprawdź
integralność i role baz bez zapisu. Nie zmieniaj nazwy, nie kopiuj samego
pliku aktywnej bazy i nie dołączaj starego audytu w ciemno.

Od v16.3.25.5.116.0.34.41 status normalizacji rozdziela zmianę wersji
runtime od kontraktu fingerprintu: przy innej wersji `status()` bez pełnej
weryfikacji zwraca `normalization_unverified`, a `deep_verify=True`
porównuje logikę źródeł. Stare snapshoty bez zapisanych fingerprintów
pozostają niezweryfikowane i nie stają się automatycznie `ready`.
Weryfikacja wake-state i completeness pozostają niezależnymi warunkami.

