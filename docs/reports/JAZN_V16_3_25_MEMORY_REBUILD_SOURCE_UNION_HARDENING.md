# Jaźń v16.3.25 — Memory Rebuild source-union hardening

Tool revision: **15.3.23.01 — Poprawione narzędzie odbudowy pamięci**  
Package version: **16.3.25-memory-rebuild-source-union-hardening**

## Cel

Memory Rebuild ma odbudowywać jedną kanoniczną `memory_jazn.sqlite3` bez utraty historii rozmów, bez zakładania że najnowszy/największy eksport ChatGPT jest nadzbiorem starszych oraz bez automatycznej promocji L2/L3. Źródłowa historia pozostaje L0/evidence, a aktywacja runtime i akceptacja autobiograficzna są osobnymi etapami.

## Źródła techniczne

1. OpenAI Help Center: `conversations.json` jest plikiem rozmów w eksporcie; duże eksporty mogą zawierać numerowane pliki conversation JSON zamiast jednego pliku.  
   https://help.openai.com/en/articles/9106926-transferring-conversations-from-1-chatgpt-account-to-another-chatgpt-account
2. SQLite WAL: zatwierdzone transakcje mogą znajdować się w pliku `-wal`; WAL jest częścią trwałego stanu i nie wolno odłączać go od aktywnej bazy przez surowe kopiowanie samego `.sqlite3`.  
   https://sqlite.org/wal.html
3. SQLite Online Backup API: po ukończeniu backupu cel jest snapshotem źródła z momentu rozpoczęcia kopiowania.  
   https://www.sqlite.org/backup.html
4. SQLite `PRAGMA integrity_check` nie sprawdza naruszeń kluczy obcych; do tego służy osobne `PRAGMA foreign_key_check`.  
   https://www.sqlite.org/pragma.html#pragma_integrity_check
5. FTS5 ma własne polecenie `integrity-check`, które sprawdza wewnętrzną spójność indeksu.  
   https://sqlite.org/fts5.html#the_integrity_check_command

## Najważniejsze ustalenia z analizy eksportów

Wielokrotne snapshoty tego samego konta nie mogą być traktowane jako liniowy ciąg, w którym ostatni plik zastępuje wszystkie wcześniejsze. Różne snapshoty mogą zawierać odmienne gałęzie tego samego `conversation_id`. Dlatego źródłowy model odbudowy jest zbiorem wariantów semantycznych, a nie wyborem jednego pliku na podstawie daty w nazwie, rozmiaru lub kolejności importu.

`source_union.py` grupuje źródła po `conversation_id` i `semantic_tree_sha256`, zachowuje unikalne warianty, rekonstruuje union `node_id` i relacji parent→child, liczy rozgałęzienia powstające dopiero po połączeniu snapshotów i generuje fingerprint niezależny od kolejności wejścia.

Rozróżniane są trzy bezpieczne klasy i jedna blokująca:

- `single` — jeden wariant;
- `extension_family` — warianty są rozszerzeniami/podzbiorami bez zmiany wspólnych węzłów;
- `branch_union` — warianty mają różne gałęzie, lecz wspólne `node_id` zachowują tę samą treść i parent;
- `conflict` — wspólny `node_id` ma inną treść semantyczną lub innego parenta; taki przypadek wymaga jawnej decyzji projekcji.

## Testy, które pozostają

Numeracja **Test00 → Test01 → Test02 → Test03 → Test04 → Final** pozostaje, ponieważ opisuje kolejne, różne własności systemu i jest zgodna z acceptance chain pamięci. Nie należy scalać tych etapów w jeden „zielony test”.

### Test00 — Source Fidelity + source-set closure

Pozostaje i zostaje rozszerzony. Ma udowodnić byte fidelity każdego źródła, poprawny parse grafów oraz domknięcie wszystkich dostępnych snapshotów. Kanoniczne conversation JSON są głównym grafem. HTML z pełnym `jsonData` może być źródłem kontrolnym; rendered-only HTML jest oznaczany jako LOSSY. Test00 nie tworzy autobiograficznej prawdy.

### Test01 — Kanoniczne bezstratne L0

Pozostaje, ale nie jako historyczny „pierwszy z pięciu DB”. Buduje izolowane L0 z source union. Musi zachowywać pełne warianty, raw payload i proweniencję. `branch_union` jest bezpiecznie zachowany; zmiana treści/parenta tego samego node pozostaje fail-closed.

### Test02 — Normalizacja/projekcje

Pozostaje. Ma sprawdzać tylko pochodne klasyfikacje, indeksy, eligibility/sensitivity i reconciliation raw↔normalized. Nie może modyfikować source mirror/L0 ani automatycznie promować L2/L3.

### Test03 — Deterministyczny rebuild integracyjny

Pozostaje i zostaje wzmocniony. Powinien wykonać co najmniej dwa świeże buildy z różną (w teście: odwróconą) kolejnością snapshotów. Wynik semantyczny, stabilne klucze L0 i source-union fingerprint mają być identyczne. `preserved_union` nie jest nierozwiązanym konfliktem; zmienione wspólne node nadal blokują.

### Test04 — Prywatna akceptacja Recall

Pozostaje jako rzeczywisty acceptance test, którego CI na fixture'ach nie zastąpi. Kategorie: direct, paraphrase, referential/multi-turn, temporal, update/conflict, negative/abstention oraz provenance. Dla system acceptance dochodzi restart continuity. Przypadki prywatne i odpowiedzi wzorcowe pozostają poza Git.

### Final — Freeze

Pozostaje jako osobny etap. Snapshot ma powstawać przez API SQLite, następnie przejść pełny `integrity_check`, `foreign_key_check`, kontrolę FTS5 i sealing manifestów. Finalny snapshot nie powinien wymagać źródłowych `-wal`/`-shm` do odtworzenia zatwierdzonego stanu.

## Testy/założenia wycofane z aktywnego protokołu

Historyczny model pięciu równorzędnych baz Test01/Test02 nie jest już kanonicznym celem; może pozostać wyłącznie jako legacy baseline/migration input. Usunięto również powiązanie testów Studio/settings/host-memory z konkretnym literałem numeru pakietu — test funkcjonalny nie powinien psuć się tylko dlatego, że legalnie podniesiono wersję. Kolejność importu wynikająca z rozmiaru pliku została usunięta z kanonicznego importera; rozmiar jest metadanym transportowym, nie dowodem kompletności.

## Granica prawdy

Zielone Test00–03 dowodzą wierności i deterministycznej rekonstrukcji, nie tego, że Łatka „pamięta”. Test04 dowodzi jakości prywatnego Recall, ale również nie aktywuje runtime. Dopiero osobny Verified Memory Restore/attach oraz runtime acceptance mogą uczynić bazę aktywnym źródłem pamięci Jaźni.
