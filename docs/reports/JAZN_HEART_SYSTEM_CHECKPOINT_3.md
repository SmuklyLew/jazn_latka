# Jaźń — Serce Systemu: wznowienie i checkpoint 3 (.94.3)

2026-10-26. Częściowy checkpoint programistyczny PR #423, nie wydanie gotowe do scalenia.

## Odzyskany stan

Źródła Git: `D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics`.
Branch: `fix/jazn-v11603494-system-studio-diagnostics-20261026`.
Początkowy lokalny/zdalny HEAD: `5f80af741a9b50da093ede825bdce2b1c5526615`.
PR #423 pozostaje Draft i bazuje na otwartym, niescalonym PR #422 (.93).
Zdalny master przy odczycie: `9e388555dbba2dc973987270c130e80a3ef806f2`.

Katalog `D:\.AI\codex_tasks\heart-system-20261026` zawiera dowody, skrypty testowe i EXE .94.2; nie jest katalogiem źródłowym Git.
Zachowano niezacommitowaną poprawkę .94.3 (Restart, błędy procesu, wersja/kontrakty/CI/test). Kopia wszystkich zastanych zmian i plików nieśledzonych: `D:\.AI\jazn_checkpoints\heart-resume-20261026-01`.
Lokalny Windows, Python 3.14.4, Qt 6.12.0 i możliwość zapisu potwierdzone narzędziowo. Katalog worktree wymaga uprawnień wykonawcy poza domyślnymi katalogami zapisu czatu; metadane Git były prawidłowe i nie wymagały naprawy.

## Zmiany .94.3

- Zachowana i zweryfikowana poprawka publicznego Restart: opcje wybranego endpointu trafiają do parsera `main.py` bez separatora kompatybilności Start/Stop.
- Niezerowy kod procesu ma jawny powód `process_exit:<code>` w kontrolerze.
- Pełna regresja Ubuntu w release-hardening używa Qt `offscreen` i jawnie sprawdza utworzenie rzeczywistego QApplication przed pełnym pytest. Poprzedni log 121358358397 kończył się abortem QApplication bez tej konfiguracji; macierz Studio już ją miała. Żaden test ani asercja nie został wyłączony.
- CLI audytu pokrycia tur emituje JSON z bezstratnym zapisem Unicode ASCII, przenośnym przez starsze strony kodowe Windows. Dwa nowe warianty testują UTF-8 i CP1250. Bez zmiany reguł accepted-turn i bez ingerencji w strumienie hosta.
- Dwa rzeczywiste scenariusze Tk wykonują wszystkie dotychczasowe asercje w świeżych procesach, zgodnie z publicznym uruchamianiem GUI. W dużej wspólnej sesji drugi Tk() zgłaszał `invalid command name tcl_findLibrary`, historycznie również błędy ładowania tk.tcl; późniejszy GC obiektów Variable trafiał do obcych wątków. Nie poluzowano asercji ani nie dodano pomijania błędów.
- Zatwierdzone poprzedniki zmienionych testów zachowano byte-for-byte w nowych, append-only podkatalogach tests/archive. Katalog kontraktów testowych wygenerowano kanonicznym narzędziem.

## Bieżące wyniki

- Baseline otwartych problemów: 25 PASS, 3 FAIL (2 UTF-8 i MCP). Tk w małym zestawie PASS.
- Po poprawkach: 41 PASS; pełny zestaw Studio i audytu tur: 237 PASS, 1 SKIPPED; izolacja Tk i governance po regeneracji katalogu: 7 PASS.
- Pierwsza pełna regresja wznowienia: **3177 PASS, 3 FAIL, 23 SKIPPED**, 335.73 s. Pozostałe błędy: Tk we wspólnej sesji (następnie poprawiona izolacja), MCP HTTP i brak trzech nowych definicji w katalogu (następnie wygenerowany). Ten wynik nie stanowi zaliczonej pełnej regresji. Log/XML: `resume-regression-1.*` w zewnętrznym katalogu dowodów.
- Pyright Studio i ukierunkowany audyt źródeł: 0 errors/warnings. Pełny audyt wymaga jawnego `--pythonpath` wskazującego interpreter środowiska Studio; próba bez niego raportowała brak opcjonalnych importów (398 błędów konfiguracji środowiska), zachowano oba raporty zamiast obniżać rygor.
- Node 24.20.0: npm ci z istniejącego lockfile bez skryptów, check i probe PASS. Audyt 22 workflow GitHub Actions: PASS, bez zmian SHA akcji.

## MCP: nadal otwarty problem rzeczywistego transportu

Test czarnej skrzynki lokalnego mcp-http nadal FAIL z `mcp_catalog_invalid_http_framing`.
Pomiar .94.3 na wyjściu h11 i `asyncio._ProactorSocketTransport.write` pokazał poprawny `Content-Length: 4677`. Klient surowego TCP odebrał `Transfer-Encoding: chunked` z 4677 bajtami surowego JSON bez ramek chunked. Kontrola syntetycznego HTTP tej samej długości i rozdzielonego zapisu nagłówków/treści była byte-exact.

Granica rozbieżności jest poniżej wywołania transport.write; jej przyczyna nie została jeszcze potwierdzona. Nie przypisujemy jej automatycznie ani Jaźni, ani konkretnemu programowi hosta. Parser nadal odrzuca niepoprawny transport. Nie dodano retry/replay tury, fallbacku ignorującego nagłówki ani fałszywego sukcesu. Dowody w `resume-wire/`, poza repo; zawierają wyłącznie publiczny katalog narzędzi i dane syntetyczne.

## Kontynuacja i granice odbioru

Po tym źródłowym checkpointcie: wygenerować metadane release_metadata_sync, zatwierdzić wyłącznie wynik generatora, sprawdzić idempotencję i push oraz równość lokalnego/zdalnego/PR SHA. Rzeczywisty finalny SHA ma trafić do zewnętrznego raportu, bez samoreferencyjnego hasha w śledzonym dokumencie.

Następnie powtórzyć pełną regresję po naprawie Tk/katalogu, sprawdzić nowy Linux CI, doctor/package-smoke i finalne typy/compile. Dokończyć odbiór rzeczywistego izolowanego Restart, lokalnego modelu/zaakceptowanej tury, kreatora save/reopen, DPI i sześciu aktualnych zrzutów. Pakowanie EXE .94.2 jest historyczne; finalny EXE wymaga czystego, zatwierdzonego źródła. Pełna migracja klasycznych Studio i terminal PTY/ConPTY pozostają osobnymi niedokończonymi funkcjami. Zewnętrzny ChatGPT/MCP i publiczny tunel wymagają oddzielnego rzeczywistego odbioru; nie wystawiono usług publicznie.

Nie zmieniano aktywnych źródeł master, działającego daemona ani prywatnych baz MEMORY. Nie wykonano merge, reset, clean ani force-push.
