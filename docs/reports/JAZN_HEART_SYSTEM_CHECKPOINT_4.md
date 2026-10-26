# Jaźń — Serce Systemu: Pulpit i aktualność diagnozy (.94.4)

2026-10-26. Częściowy checkpoint rozwojowy; Draft PR #423, bez merge. Źródła pozostają w `D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics`, na istniejącej gałęzi .94.

## Zweryfikowany punkt poprzedni .94.3

Lokalny/origin/PR HEAD `886e8e52f6b2d3b480b0b2217351a76f8da621cc`, czysty worktree. Wszystkie **36 kontroli GitHub SUCCESS**, w tym pełna regresja Ubuntu i Windows targeted. Idempotencja release_metadata_sync: synchronized=true dla 3424 plików. Doctor i system package-smoke PASS; status w pustym workspace zwrócił poprawnie brak aktywnego daemona (exit 1), a oba testy startu Studio PASS.

Druga pełna regresja Windows .94.3: **3179 PASS, 1 FAIL, 23 SKIPPED**, 401.93 s. Jedyny FAIL: rzeczywisty test HTTP MCP. Bez kodu Jaźni dwa proste procesy TCP odtwarzają zamianę Content-Length na Transfer-Encoding: chunked bez kodowania chunked; wielkość liter nagłówka nie zmienia wyniku. Nie obchodzono tej usterki transportu. Nadal wystąpiły ostrzeżenia Variable.__del__ innych klasycznych testów Tk; izolacja dwóch scenariuszy Konfiguracji usuwa ich FAIL, ale nie stanowi dowodu usunięcia wszystkich ostrzeżeń Tk.

Pierwszy rzeczywisty Restart podczas równoległej dużej regresji nie uzyskał gotowości nowego endpointu i poprawnie wykonał rollback. Zachowano ten niezaliczony odbiór. Następny odbiór bez równoległej regresji: Start PASS, ponowny Start zachował PID/instance ID, Restart PASS z nowym PID/instance ID, status potwierdził root/endpoint/tożsamość/heartbeat/conversation_ready, Stop PASS. Jedno syntetyczne żądanie lokalnego czatu uzyskało accepted final, a GUI potwierdziło wyświetlenie; pending_request_id=null. Konfiguracja wskazywała gemma3:latest; sama konfiguracja i accepted turn nie zastępują osobnego dowodu wywołania konkretnego modelu. Nie korzystano z prywatnej MEMORY.

Rzeczywisty kreator na kanonicznym stagingu: wymagania PASS, przejście A/B/C, zapis za zgodą, odczyt modelu i scope, ponowne otwarcie bez niepotrzebnego kreatora PASS. Sześć stron sfotografowano jako rzeczywiste widgety Qt na platformie windows. EXE .94.3 z powyższego czystego SHA: build PASS, inwentarz **1794 plików** PASS, rzeczywisty gui-smoke exit 0. To dowody .94.3, nie automatyczny odbiór następnej wersji.

## Implementacja .94.4

- Pulpit dostaje projekcję publicznego statusu: wersja SYSTEM, integralność i osobne pochodzenie źródeł, techniczny stan MEMORY, wybrany adapter/model oraz ostatnia zakończona operacja i przejście do problemów.
- Kompletna konfiguracja modelu, null adapter, integralność SYSTEM, pamięć i accepted turn pozostają różnymi faktami. Żadne pole konfiguracji modelu nie potwierdza generacji; dostępność MEMORY nie potwierdza recall lub autobiograficznej ciągłości. Prywatne ścieżki baz, tokeny i cała surowa odpowiedź nie trafiają do projekcji.
- Naprawiono aktualizację po negatywnym statusie: wcześniej kontroler publikował evidence tylko po exit 0. Po exit 1 prawidłowy JSON nadal aktualizuje obserwację, zachowując niepowodzenie zadania. Niepoprawny/brakujący JSON unieważnia stare pozytywne wskazania. Pierwotny timeout/błąd procesu nie jest zastępowany błędem parsowania.
- Wartości wybranego SYSTEM są redagowane i renderowane jako PlainText; nie interpretują markup z zewnętrznego rootu.
- Dodano nowe regresje kontraktów, rzeczywistego procesu statusu i widgetów Qt. Nie zmieniano istniejącego aktywnego testu ani historycznych snapshotów. Wersja i kontrakty startowe/deployment podniesione razem, bez zajmowania .95.

## Walidacja i dalsze bramki

Pierwszy zestaw etapu: **37 PASS**. Pełny zestaw Studio i audytu tur: **247 PASS, 1 SKIPPED**. Kontrakty/governance/Start Studio: **39 PASS**. Pyright Studio 0 errors/warnings, pełny Pyright **1369 plików, 0 błędów, 0 ostrzeżeń**. Katalog wygenerowany kanonicznie, compileall aktywnych plików, diff --check, audyt Actions oraz Node 24 npm ci/check/probe PASS. Faktyczne końcowe wyniki, SHA lokalny/zdalny/PR i wznowienie znajdują się w zewnętrznym katalogu dowodów; ten raport nie przypisuje sobie przyszłego self-referencyjnego SHA.

Przed kontynuacją: zatwierdzić źródła, wygenerować oba metadane wyłącznie release_metadata_sync, zatwierdzić wynik, --check, push i sprawdzić finalny HEAD oraz CI. Dalszy odbiór obejmuje .94.4 full regression, doctor/package-smoke, aktualne GUI/DPI, test finalnego EXE i końcową macierz funkcji. MCP Windows wymaga naprawienia rzeczywistej warstwy transportu hosta; zewnętrzny ChatGPT/MCP nie został zaakceptowany. Pełna migracja klasycznych edytorów i emulacja PTY/ConPTY nadal nie są deklarowane jako ukończone.

Aktywny master, jego daemon i prywatne bazy nie były modyfikowane. Wszystkie operacje usług i zapisu kreatora dotyczą wyłącznie świeżych ścieżek testowych.
