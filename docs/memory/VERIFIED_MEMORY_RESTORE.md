# Zweryfikowane przywracanie pamięci Łatki

## Cel

Narzędzie łączy istniejący Memory Rebuild/Test 04 z aktywną linią runtime:

```text
Memory Rebuild L0
→ walidacja Testu 04
→ conversation_archive_v1 + staging_v1 + FTS
→ recovery_current
→ normalizacja
→ wake-state
→ ręczny przegląd L2
→ dokładny manifest L3
→ pełna walidacja
→ doctor
→ start i status
```

Nie uruchamia automatycznej promocji L2/L3. Nie traktuje archiwum, wake-state ani
bazy SQLite jako dowodu aktywnej Jaźni.

## Pliki

```text
latka_jazn/tools/verified_memory_restore.py
tools/Invoke-JaznVerifiedMemoryRestore.ps1
tests/test_verified_memory_restore.py
```

## Warunki wejściowe

- ukończony Test 04;
- `summary.sanitized.json` z kompletem wymaganych wyników `passed`;
- pięć poprawnych baz pod `<Test04Root>/memory/sqlite`;
- daemon zatrzymany przed publikacją albo jawne `-StopDaemon`;
- prywatne dane pozostają poza Git.

Test 04 celowo ma `system_activation_ready=false`. Narzędzie nie zmienia tego
wyniku. Jest on tylko zweryfikowanym wejściem do osobnego procesu operatorskiego.

## 1. Walidacja bez zapisu

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode Validate `
  -Root . `
  -Test04Root "D:\PRIVATE\jazn_memory_test_04" `
  -Test04Summary ".\workspace_runtime\memory_sqlite_test_04\<run-id>\summary.sanitized.json"
```

## 2. Staging bez publikacji

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode Prepare `
  -Root . `
  -Test04Root "D:\PRIVATE\jazn_memory_test_04" `
  -Test04Summary ".\workspace_runtime\memory_sqlite_test_04\<run-id>\summary.sanitized.json"
```

Wynik powstaje pod:

```text
workspace_runtime/verified_memory_restore/<run-id>/staged_runtime/
```

Aktywna pamięć nie jest zmieniana.

## 3. Publikacja, recovery, normalizacja i wake-state

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode Prepare `
  -Root . `
  -Test04Root "D:\PRIVATE\jazn_memory_test_04" `
  -Test04Summary ".\workspace_runtime\memory_sqlite_test_04\<run-id>\summary.sanitized.json" `
  -Publish `
  -StopDaemon `
  -ConfirmPublish PUBLISH_VERIFIED_MEMORY
```

Przed publikacją powstaje backup. Błąd recovery lub walidacji powoduje próbę
przywrócenia backupu. Daemon nie jest uruchamiany.

Draft L2:

```text
workspace_runtime/verified_memory_restore/<run-id>/l2_review_draft.json
```

## 4. Ręczny przegląd L2

W kopii draftu ustaw dla każdego kandydata:

```json
"decision": "approved"
```

albo:

```json
"decision": "rejected"
```

Nie zmieniaj identyfikatorów, treści ani hashy źródłowych.

Zapieczętowanie:

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode SealL2 `
  -Root . `
  -L2Draft ".\workspace_runtime\verified_memory_restore\<run-id>\l2_review_draft.json" `
  -L2Manifest ".\workspace_runtime\verified_memory_restore\<run-id>\l2_review_manifest.json" `
  -ReviewedBy "Krzysztof — ręczny przegląd 2026-07-30"
```

Pole `manifest_sha256` z wyniku jest wymagane w następnym kroku.

## 5. Zapis zatwierdzonego L2 i budowa L3

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode ApplyL2 `
  -Root . `
  -L2Manifest ".\workspace_runtime\verified_memory_restore\<run-id>\l2_review_manifest.json" `
  -L2ManifestSha256 "<SHA256>" `
  -ReviewedBy "Krzysztof — ręczny przegląd 2026-07-30"
```

Kanoniczny manifest L3 powstaje pod:

```text
workspace_runtime/memory_recovery/l3_approval_manifest.json
```

## 6. Jawna promocja L3 i aktywacja

```powershell
& .\tools\Invoke-JaznVerifiedMemoryRestore.ps1 `
  -Mode Activate `
  -Root . `
  -L3Manifest ".\workspace_runtime\memory_recovery\l3_approval_manifest.json" `
  -L3ManifestSha256 "<SHA256>" `
  -ApprovedBy "Krzysztof — explicit L3 approval 2026-07-30" `
  -ConfirmActivation ACTIVATE_VERIFIED_MEMORY
```

Kolejność jest twarda:

1. dokładna walidacja SHA L3;
2. zapis request/decision/promotion ledger;
3. pełny `memory-validate`;
4. końcowy `doctor`;
5. `run.py start`;
6. `run.py status --json`;
7. wymagane potwierdzenie `active_trusted`.

## Uruchomienie Testu 04 z wrappera

Wrapper ma opcjonalne `-RunTest04`, które wywołuje istniejący
`Invoke-JaznMemorySqliteTest04.ps1`. Zachowuje on własny kontrakt brancha i
prywatnych manifestów. Gdy Test 04 został już wykonany, nie używaj tej flagi.

## Ograniczenia

- Konwerter tworzy jeden shard każdej rodziny i blokuje publikację po
  przekroczeniu 480 MiB.
- Konwersja odtwarza aktywny kanoniczny snapshot rozmów z `archive_chats.sqlite3`.
  Historyczne ZIP-y i katalog importów pozostają nadrzędnym L0.
- Znak NUL jest zachowany w źródłowym blobie tekstu, ale w indeksie FTS jest
  zastępowany znakiem U+FFFD.
- Narzędzie nie zapisuje prywatnych danych do repozytorium.
