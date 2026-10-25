# Kontynuacja Studio Jaźni po .63 — 2026-10-24

## Punkt źródłowy

- Źródło: Draft PR #412, `codex/jazn-run-studio-completion-20261024`, HEAD `0522069a463db60d339fb0cda0e94a9134b7b38f`.
- Nowa gałąź: `fix/jazn-studio-p1-p5-continuation-20261024`; nie scalamy PR #412 ani tej gałęzi.
- Snapshot GitHub Actions z dnia 2026-10-24: piętnaście odnalezionych workflow przypisanych do HEAD .63 zakończono SUCCESS, w tym Windows/Linux Qt Studio, PowerShell, release-hardening, cleanroom, persistent E2E i MEMORY Windows.
- Udane workflow odnoszą się do .63, nie są dowodem akceptacji P1–P5 po zmianach na tym branchu.

## P1: mały etap bezpieczeństwa UI (.64)

Poprawka widoku Qt MEMORY przyjmuje wyłącznie krótkie, strukturalne kody diagnostyczne w wybranych polach błędów i blokad; surowe wyjątki oraz ścieżki prywatnych plików nie trafiają do tych pól. Stan `blocked` pozostaje oddzielony od sukcesu. Nowy test obejmuje zarówno czyste kody, jak i ścieżki Windows/Linux, raporty i błędy zadań w Qt. Nie modyfikowano prywatnej MEMORY ani aktywnego runtime.

## Kryteria nadal otwarte

- P1: niezależny final-source metadata/catalog CHECK, pełny test suite i dalsza akceptacja Memory/Configuration/Test Studio. Zielone CI .63 nie zamyka wszystkich kryteriów P1.
- P2: kompletne natywne strony wspólnego Studio (usługi/logi, Dependency/Python, Pack), dostępność i DPI; pozostaje częściowe.
- P3: pełna migracja dwunastu aplikacji z zachowaniem operacji i rollback; pozostaje częściowa/niezaczęta według istniejącej macierzy.
- P4: przyjęte rzeczywiste tury z Ollamą i recovery na źródle .64 — NOT RUN. Bez dostępu do lokalnego Ollama użytkownika nie można zaliczyć.
- P5: końcowy Windows/Linux EXE, offline wheelhouse i zewnętrzny SYSTEM z .64 — NOT RUN. Historyczne buildy nie są dowodem.
- Otwarta bazowa usterka lokalnego MCP: `mcp_catalog_invalid_http_framing`; nie wolno jej ukryć ani osłabić asercji.

Synchronizację `PACKAGE_INTEGRITY_MANIFEST.json` / `SOURCE_PROVENANCE.json` należy wykonać tylko generatorem kanonicznym. Nie edytować tych plików ręcznie. Bez raportu z kanonicznego sync i nowego CI gałąź nie jest release candidate.
