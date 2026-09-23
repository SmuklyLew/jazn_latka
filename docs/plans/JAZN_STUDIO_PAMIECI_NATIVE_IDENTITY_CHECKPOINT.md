# Studio Pamięci .80.2 — natywne konflikty i tożsamość źródeł

Status: IN_PROGRESS. Nie jest to prywatna akceptacja Test03 ani Final.

Punkt startowy: 584306bbb341242be0f126131ca354097763cf74, czysty worktree, lokalny i zdalny HEAD zgodne; master affabf5618934bd8efb39b0b1d074f7529116643, merge-base równy masterowi, 22 ahead / 0 behind. Istniejącej konwergencji, Test04 i kanonicznego snapshotu nie odtwarzano.

CI checkpointu 584306bb: Stable test contracts, release-hardening, pyright-active-tree-audit, memory-rebuild-v24-windows, persistent-runtime-e2e, package-distribution-cleanroom, javascript-node24-contract, dependency-review SUCCESS. Przy odczycie powershell-terminal-regressions nadal IN_PROGRESS; nie deklarowano pełnego CI PASS. Lokalne szybkie kontrole governance, archiwum, Studia, branch/ref Test04, batch, manifest i FTS: 41 PASS.

## Potwierdzony RED

Nowy tests/test_memory_native_batch_reconstruction.py został zapisany i wypchnięty przed poprawką w 7fb7921c5f64ffeaa72f59c478e97dff0abc0591. Oba przypadki dały FAIL: normal/reverse oraz przeniesienie źródeł i zmiana nazw. Dane są wyłącznie syntetyczne: dwa warianty rozmowy oraz dziennika. Test sprawdza niepusty nierozstrzygnięty konflikt, FK, tożsamość konfliktu i pełny niezmieniony snapshot protokołu.

## Dwie przyczyny i naprawa

1. ChatExportArchiveStore._record_conflict generował uuid4. Tożsamość konfliktu jest teraz uuid5 z przestrzenią nazw kontraktu, hashem źródła, raw tree incoming oraz pełnym semantycznym ConversationPlan (w tym incoming/active tree). Nie zależy od lokalizacji, import UUID ani czasu zapisu. Ponowny zapis identycznej tożsamości nie duplikuje konfliktu; pozostałe błędy SQL nie są ignorowane. Status i reason rozstrzygnięcia pozostają bez zmian.
2. Po tej poprawce wariant przeniesienia nadal dawał RED: ChatGptJsonAdapter używał absolutnej ścieżki readera jako source_member i conversation_members. Dla samodzielnego JSON source_member jest teraz None, a dokument ma semantyczny znacznik $document; dla katalogu członkowie są względni wobec rootu; dla ZIP zachowano wewnętrzne ścieżki członków. Lokalny source locator pozostaje w raporcie. Istniejąca historia baz nie jest migrowana ani przepisywana wstecz.

Nie zmieniono oczekiwań nowego testu po RED, testów starszych, walidatora Test03, listy kolumn snapshotu, progów benchmarku ani automatycznych promocji. Batch i incremental pozostają osobnymi ścieżkami.

Po obu naprawach: 41 PASS w pakiecie native regression, batch reconstruction, batch plan, chat archive, modular, v24 unified i v4 protocol. Wolna wersja .80.2 została sprawdzona względem branchy/tagów/releases i aktualnego mastera przed zmianą semantyki.

## Następne kroki

Dokończyć dodatkowe scenariusze batch (ZIP/katalog, powtórzenia, duże źródła, source locators, zmiana źródła między przygotowaniem a native projection). Uruchomić pełne publiczne/CI gates na finalnym drzewie. Dopiero po stabilnym publicznym CI rozpocząć nowy prywatny Test00 → Test01 → Test02 → Test03 → frozen13 → Test04 → Final. Wszystkie te prywatne etapy nowej wersji są NOT RUN. Benchmark pozostaje zamrożony; istniejące raporty są historyczne.
