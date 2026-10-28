# Jaźń .94 — Studio operatorskie: diagnostyka i gotowość

Baza: `fix/jazn-v11603493-system-studio-hardening-20261025` (`aeadd203`).
Gałąź: `fix/jazn-v11603494-system-studio-diagnostics-20261026`.

- `doctor --json` może drukować postęp przed właściwym JSON. Studio zachowuje teraz końcowy pełny obiekt.
- `/readyz` nie uznaje HTTP 200 za dowód gotowości; wymagane `ready: true`, transport jest raportowany osobno przez `http_ok`.
- Regresje kontrolują postęp, gotowość fałszywą i odrębne `/healthz`.
- Zsynchronizowano wersję .94 oraz kontrakty startup i wdrożeniowy MCP.

Brak zmian MEMORY/SQLite, daemona lub master. Przy niedostępnym executorze tej sesji nie potwierdzono lokalnego pytest, Pyright ani GUI; wymagane pełne CI i odbiór Windows. Nie scalać bez pełnych bramek.
