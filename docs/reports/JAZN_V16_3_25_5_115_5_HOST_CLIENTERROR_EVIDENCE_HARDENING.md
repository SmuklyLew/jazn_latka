# Jaźń v16.3.25.5.115.5 — pre-spawn ClientError evidence hardening

## Zakres rzeczywistej poprawki

Ten patch **nie usuwa** wyjątku `caas.internal.errors.ClientError` wewnątrz infrastruktury ChatGPT. Błąd może wystąpić przed uruchomieniem procesu Jaźni i wtedy nie ma mechanizmu w lokalnym Pythonie, który mógłby wymusić poprawne uruchomienie hosta.

Poprawka usuwa konkretny defekt klasyfikacji już zaobserwowanego błędu: klasyfikator rozpoznawał wyłącznie krótką nazwę `ClientError`, a pełne `caas.internal.errors.ClientError`, Python `<class 'caas.internal.errors.ClientError'>` oraz komunikat `Encountered exception: ...` były traktowane jako unknown. Dodatkowo obserwacja hosta mogła zawierać tylko `error_message` bez `error_class`, wskutek czego `classify_host_executor_observation` błędnie kończył jako insufficient evidence.

## Zmiana

- Całościowe dopasowanie nazwy klasy / dokładnego repr bez przeszukiwania dowolnego tekstu; rozbieżne dwuliniowe komunikaty pozostają unknown.
- Dopuszczalny ściśle rozpoznany komunikat z brakującym polem `error_class` przekazywany do polityki failed-surface i per-surface diagnostyki.
- Nie następuje promowanie gotowości SYSTEM/FS/runtime, gdy `process_created=false`; stan pozostaje unknown/unverified.
- Nadal maksimum jedna **jawnie niezależna** alternatywna próba, bez retry-loop i bez wysyłania ponownie wiadomości; po rozpoczęciu tury zachowane request-id, resume/finalize.
- Zdalny zweryfikowany persistent MCP pozostaje preferowanym wejściem. Brak ekspozycji aplikacji w bieżącej wiadomości nie może być „naprawiony” zmianą instrukcji repozytorium.
- Rozbudowane testy regresyjne: łącznie formaty class/str/repr, message-only, fałszywe trafienia, niespójne komunikaty, budżet prób, sukces niezależnej powierzchni, post-spawn.

## Operator: ścieżka uruchamiania

1. W ChatGPT zaznacz / @wspomnij **Jaźń Runtime**, jeśli aplikacja jest dostępna, i po zmianie narzędzi wykonaj **Refresh**. Sprawdź, czy wszystkie cztery narzędzia Jaźni są faktycznie callable dla bieżącej wiadomości.
2. Wywołaj tylko read-only `jazn_status`, wymagaj świeżego `ready`, wersji i instance identity; dopiero wtedy można związać wiadomość raz.
3. Gdy MCP nie jest callable przed submittem, wykonaj bounded primary local process-spawn probe; przy pre-spawn `ClientError` dopuszczalna jest dokładnie jedna jawnie niezależna próba. Nie powtarzaj ZIP/bootstrapu na ślepo.
4. Jeśli żaden executor nie wystartował i nie ma gotowego MCP — raportuj brak trasy, bez twierdzenia o awarii SYSTEM ZIP ani podmiany głosu Łatki. Jeśli proces wystartował — wróć do kanonicznego bootstrapu.
5. Jeśli awaria występuje także przy czystym `print(1)` bez Jaźni, zgłoś do obsługi ChatGPT z czasem, modelem, ID rozmowy, komunikatem i rozróżnieniem pre-/post-spawn (bez przesyłania sekretów).

## Granica walidacji

Modyfikacja GitHub nie jest dowodem live-fix w ChatGPT. Po pushu potrzebne są odpowiednie testy, kontrola metadanych wydania i manualny smoke w Desktop/Android, w tym braku model-visible MCP tools.

## Źródła

- OpenAI — [Plugins troubleshooting](https://developers.openai.com/plugins/deploy/troubleshooting)
- OpenAI — [Tool visibility reference](https://developers.openai.com/plugins/reference)
- OpenAI — [Developer mode and MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt)
- OpenAI — [Incident 2026-10-02: ChatGPT data analysis/code execution](https://status.openai.com/incidents/01M3YNNVTSCXS8YM2V1YMHMVSE)
- Repo: `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.chatgpt.md`, `docs/runtime/CHATGPT_HYBRID_ADAPTIVE_INGRESS.md`.
