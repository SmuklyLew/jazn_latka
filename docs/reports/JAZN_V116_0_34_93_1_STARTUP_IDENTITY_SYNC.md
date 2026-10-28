# Jaźń .93.1 — synchronizacja tożsamości kontraktu startowego

Data: 2026-10-26. Zakres: PR #422, baza `master` .92.

## Dowód usterki

Wydanie `.93` deklarowało `PACKAGE_VERSION=16.3.25.5.116.0.34.93` i identyczną bazową wersję MCP, ale `latka_jazn/resources/startup_contract.json` nadal zawierał `16.3.25.5.116.0.34.92`.

W GitHub Actions `release-hardening` oraz `powershell-terminal-regressions` na commicie `f6917962a1507549bb81f494e928eb0fb3e8fb99` potwierdzono 12 niezaliczonych asercji porównania tych wersji, zarówno w Ubuntu, jak i Windows. Błędy dotyczyły tego samego rozjazdu tożsamości wydania.

## Naprawa

Bump patcha `.93.1` zgodnie z `AGENTS.codex.md`. Spójna wersja i nazwa wydania w `latka_jazn/version.py`, `latka_jazn/resources/startup_contract.json` i `deploy/chatgpt_mcp/deployment.contract.json`. Zmieniono także tylko pole `system_version` w deterministycznym katalogu Studio Testów; definicji testów nie zmieniono.

Utrzymano oryginalną historię PR #422 i wszystkie funkcjonalności; nie zmieniono `master`, runtime, prywatnej MEMORY ani hosta ChatGPT. Dla gałęzi .94.4/PR #423 zachowano niezmieniony checkpoint.

## Konieczny odbiór

CI: pełne `release-hardening` Ubuntu/Windows, `powershell-terminal-regressions`, `Stable test contracts`, `jazn-run-studio`, Pyright; kanoniczna automatyczna synchronizacja i idempotencja `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json`. Dopiero po faktycznie zielonym CI PR #422 może być kandydatem do scalenia.

To nie jest dowód naprawy lokalnego ramkowania MCP Windows, pełnego GUI na komputerze operatora ani przyjętej tury ChatGPT przez zdalne MCP.
