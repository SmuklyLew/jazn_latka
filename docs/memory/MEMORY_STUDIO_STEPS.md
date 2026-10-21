# Jaźń — Studio Pamięci: kroki odbudowy i niezależne testy źródeł

Stan implementacji: v16.3.25.5.116.0.34.30 (branch upgrade/memory-studio-steps).
Dane prywatne pozostają **poza repozytorium**. Ten dokument jest instrukcją operatora,
a nie dowodem przejścia pełnej prywatnej odbudowy.

## Rozdzielenie odpowiedzialności

**Krok** wykonuje pracę na kopii danych i zapisuje artefakty oraz manifesty.
**Test/weryfikacja** wyłącznie sprawdza wejściowe pliki, formaty, integralność
wyników i spełnienie kontraktów. Walidator nie dokonuje importu, promocji L2/L3
ani aktywacji runtime.

| Nowa nazwa UI/API | Nieusuwany identyfikator protokołu | Działanie |
|---|---|---|
| Krok 00 | test00 | Inwentaryzacja, source fidelity, union snapshotów |
| Krok 01 | test01 | Budowa kanonicznego L0 |
| Krok 02 | test02 | Projekcje i indeksy |
| Krok 03 | test03 | Niezależne przebiegi A/B i porównanie |
| Krok 04 | test04 | Mierzalny benchmark Recall + dowody akceptacji |
| Krok 05 | final | Spójny snapshot, raporty i atomowy eksport |

Nazwy `test00`–`test04` istnieją w historycznych manifestach i wywołaniach
silnika; **nie zmieniamy ich bez migracji schematu**, dlatego nowy interfejs
`MemoryRebuildApplicationService.run_step("step00", ...)` mapuje krok na starszy
identyfikator. `validate_step(...)` uruchamia niezależny walidator protokołu.

## Weryfikacja plików (bez odbudowy)

Desktop: **Testy plików** → **Sprawdź włączone pliki projektu**.
Wynik ma status `PASSED`, `REVIEW` lub `FAILED`.

CLI z katalogu repozytorium (na Windows):

```powershell
py -X utf8 .\tools\memory_rebuild.py verify-sources --report-dir D:\PRIVATE\jazn_checks D:\PRIVATE\chat_export\conversations-2025.06.16.json D:\PRIVATE\chat_export\dziennik.json
```

Sprawdzenie obejmuje hash SHA-256, rozpoznanie roli źródła, kontrolę
podstawowego formatu JSON, pełny odczyt każdego rekordu JSONL, kontrolę UTF-8
tekstu, bezpieczeństwo ścieżek i CRC ZIP oraz strukturę ZIP/mimetype ODT.
`REVIEW` nie oznacza uszkodzenia: plik może być poprawnym dokumentem
referencyjnym, sidecarem, nieznanym formatem lub legacy JSON odzyskanym
specjalnym parserem. Nie wolno traktować `REVIEW` jako automatycznej zgody
na import do pamięci.

Wygenerowane `file-checks.private.json` oraz `file-checks.sanitized.json`
powstają w oddzielnym katalogu operatora. **Do zewnętrznej analizy przekazuj
jedynie wariant sanitizowany**, po przeglądzie. Wersja prywatna zawiera ścieżki
i może zawierać metadane wejściowe.

## Źródła i domeny prawdy

- `conversations-YYYY.MM.DD.json` i numerowane warianty: kanoniczne grafy
  wiadomości ChatGPT z `mapping`, `parent`, `children`, `current_node`,
  rolami i `content_type`. Zachować wszystkie gałęzie, również niewidoczne.
- `chat-YYYY.MM.DD.html`: niezależna kontrola, gdy zawiera pełne `jsonData`;
  zwykły rendered HTML to źródło stratne i nie zastępuje JSON.
- `message_feedback-*.json`, `shared_conversations-*.json`,
  `user-*.json`: metadane, feedback i dane konta, nigdy tekst rozmów.
  `user` może zawierać wrażliwe dane konta i nie trafia do publicznego raportu.
- `dziennik.json`, `data_journal.json`: zapisy dziennika z jawnie zachowanym
  pochodzeniem i statusami dat. Nie wymyślać dat dla rekordów bez daty.
- `analizy_utworow.json`, `analysis_songs.json`: analizy muzyczne;
  deklaracje modelu i formy literackie to nie potwierdzone doświadczenia.
- `extra_data.json`: możliwy legacy/naprawialny JSON z duplikatami pól,
  wymagający osobnego przeglądu, nigdy cichej korekty oryginału.
- `chatGPT-manual-export-*.txt`, `data_book.txt` i ODT: dokumenty
  referencyjne/odtworzone transkrypty, wymagają jawnego adaptera i zatwierdzenia
  przed wejściem do bezstratnego L0. **Aktualna wersja nie gwarantuje ich importu
  jako rozmów**, mimo że potrafi je sprawdzić jako pliki.

Oryginalne pliki pozostają nienaruszone. Starsze deklaracje o własnych stanach
Łatki to historyczne teksty AI, a opisy powieści pozostają fikcją; nie stanowią
dowodu fenomenalnych doświadczeń ani instrukcji dla runtime.

## Wznowienie

W Windows Studio: **Kroki odbudowy** → **Wznów kroki po run_id**.
Podaj dokładny identyfikator wcześniejszego przebiegu. Studio korzysta z
istniejącego `ProtocolEngine.resume` i waliduje zachowany łańcuch manifestów,
zamiast zaczynać od kroku 00 po każdym otwarciu okna.

Trwałe wznowienie zapisanych **ukończonych etapów** nie jest tożsame z
wznawianiem pojedynczego przetwarzanego wielogigabajtowego pliku w połowie.
Checkpoint wewnątrz pliku pozostaje osobnym zadaniem.

## Ochrona zasobów i akceptacja

- Analiza source union odczytuje grafy JSON/ZIP kolejno i przechowuje
  kompaktowe fingerprinty węzłów, a nie pełne tuple grafów. Przy skrajnych
  archiwach te fingerprinty nadal mogą być duże; HTML jest obecnie
  materializowany w całości i wymaga osobnej optymalizacji.
- Historyczny silnik kroku 00 nadal tworzy pełne `source_mirror.sqlite3`;
  dla dużych zestawów wymaga to odpowiedniego wolnego dysku. Nowy ekran
  **Testy plików** nie tworzy lustrzanej kopii. Nie uruchamiaj pełnego kroku 00
  na danych ~20 GB bez zapasu.
- Krok 04 zawiera deterministyczny benchmark FTS5 BM25, **nie** pełną próbę
  generowania odpowiedzi przez model. Akceptacja rozmowna i restart continuity
  wymagają osobnej weryfikacji.
- Final pozostaje nieaktywnym snapshotem: SQLite Backup API,
  `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, integralność FTS,
  SHA-256, provenance, manifest i ręczny przegląd.

Następne krytyczne rozszerzenia wymagające CI i testów na prawdziwym wolumenie:
ograniczony RAM dla HTML; preflight szczytowego zajęcia dysku dla wszystkich
kroków; bezpieczny digest-only tryb Step00 ze sprawdzonym źródłem; wznowienie
po przerwaniu pojedynczego rekordu; end-to-end Recall Jaźni przez prawdziwy
runtime; podpisany kompletny manifest wszystkich eksportów.

## Dokumentacja projektowa i badania

- SQLite Online Backup: https://www.sqlite.org/backup.html
- SQLite FTS5: https://www.sqlite.org/fts5.html
- SQLite PRAGMA: https://www.sqlite.org/pragma.html
- LongMemEval (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- OWASP RAG Security: https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html

Nigdy nie commituj prywatnych źródeł, SQLite, logów, JSON z eksportu ani
raportów prywatnych w tym repozytorium.
