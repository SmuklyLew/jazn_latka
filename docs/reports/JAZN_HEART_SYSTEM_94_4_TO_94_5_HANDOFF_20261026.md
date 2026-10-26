# Jaźń — Serce Systemu: checkpoint .94.4 i przekazanie prac .94.5

Data: 2026-10-26. **Checkpoint organizacyjny, nie nowa wersja SYSTEM, nie release-ready.**
Ten plik rozpoczyna zależną gałąź do dalszych napraw i odbioru; nie modyfikuje runtime, MEMORY ani aplikacji.

## Zweryfikowane odniesienia

- Repozytorium: `SmuklyLew/jazn_latka`.
- Źródło (zamrożony punkt bazowy): `fix/jazn-v11603494-system-studio-diagnostics-20261026`, SHA `045e90785e23a6244401f45e8e96a81eff041406`, SYSTEM `16.3.25.5.116.0.34.94.4`.
- Rodzic: Draft PR [#423](https://github.com/SmuklyLew/jazn_latka/pull/423), bazujący na niescalonej gałęzi .93 / PR [#422](https://github.com/SmuklyLew/jazn_latka/pull/422).
- Bieżąca gałąź zadania: `fix/jazn-v11603494-5-heart-system-mcp-windows-acceptance-20261026`, od SHA rodzica powyżej.
- Docelowy numer **następnego patcha kodowego**, do zweryfikowania przy implementacji: `16.3.25.5.116.0.34.94.5`. Nie przyznawaj nowej wersji samemu dokumentowi.
- Pełny raport rodzica: `docs/reports/JAZN_HEART_SYSTEM_CHECKPOINT_4.md` i `docs/tools/JAZN_HEART_SYSTEM.md`.

## Co potwierdza zdalne repozytorium na starcie

- Na SHA bazowym wszystkie 36 kontroli GitHub Actions zakończyły się `success` (w tym pełna regresja Ubuntu, Windows targeted, Pyright, MCP fixture, bezpieczeństwo i metadane). Nie oznacza to wszystkich testów live.
- W logu `verify (ubuntu-latest)` dla rodzica: `3197 passed, 16 skipped, 1 warning`.
- Zmiany .94.4 obejmują Pulpit z projekcją kanonicznego statusu oraz unieważnianiem przestarzałych pozytywnych wskazań po błędnym/negatywnym wyniku; istnieją testy `tests/test_heart_system_dashboard*.py`.
- Uruchamianie `run_studio.py`, motyw Violet Night, kreator A/B/C, panel usług, panele operatora i zgodne `main.py`/`run.py` istnieją w .94.4; ich zakres opisuje dokumentacja rodzica.
- Raport lokalnego odbioru .94.3 wskazuje `3179 PASS, 1 FAIL, 23 SKIPPED` na Windows. Jedyny FAIL dotyczył ramkowania lokalnego HTTP/MCP. Nie ma niezależnie potwierdzonego końcowego pełnego przebiegu Windows .94.4.
- W .94.3 raportowano natywny Windows GUI/EXE smoke, 1794 pliki pakietu, działający kreator save/reopen, izolowany Start/no duplicate/Restart/Stop oraz syntetyczną zaakceptowaną turę z dowodem wywołania lokalnej Ollamy `/api/chat`; to **nie** potwierdza hosta ChatGPT ani pełnej gotowości .94.4.

## Priorytety kontynuacji

1. **Odzyskanie lokalnego stanu:** najpierw sprawdź istniejące worktree oraz lokalne niezatwierdzone pliki z przerwanej sesji; nie kasuj ani nie resetuj. Lokalny kod źródłowy poprzedniej pracy znajdował się w `D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics`; katalog `D:\.AI\codex_tasks\heart-system-20261026` przechowywał dowody i EXE. Dla nowej gałęzi załóż oddzielny worktree dopiero po sprawdzeniu, że nie koliduje z istniejącym.
2. **MCP Windows:** zdiagnozuj utratę poprawnego ramkowania HTTP. W syntetycznym eksperymencie serwer wysyłał `Content-Length`, a klient widział `Transfer-Encoding: chunked` bez ramek. Przyczyna pomiędzy transportem a obserwacją klienta **nie została ustalona**. Testy różnicowe stosu/hosta są wymagane; nie rozluźniaj parsera i nie przedstawiaj zniekształconego HTTP jako sukcesu.
3. **Finalny odbiór .94.5:** pełna lokalna regresja Windows i Linux CI dla własnego HEAD, testy GUI/DPI, kreatora, Start/Restart/Stop, no-duplicate, rzeczywistej Ollamy i zachowanej finalizacji, czysty build EXE z zatwierdzonego SHA, raport inwentarza.
4. **Integracje:** osobno zweryfikuj lokalny MCP, zdalny transport/auth, Cloudflare i dopiero potem ChatGPT end-to-end (narzędzia, lineage, accepted visible turn). Nie zakładaj dostępu do modeli OpenAI przez subskrypcję ChatGPT bez API.
5. **Studio Developer:** oceń i rozwij pełną konsolę PTY/ConPTY, kontrolowany terminal, integrację klasycznych Studiów i katalog testów. Aktualne trzy konsole są konsolami zadań, nie pełnym terminalem.
6. **Higiena:** aktualizuj opis nowego Draft PR i raporty; nie oznaczaj ukończenia funkcji bez rzeczywistych testów.

## Kontrakty bezpieczeństwa i pracy

- Przed kodem przeczytaj w całości `AGENTS.md`, `AGENTS.codex.md` i właściwe zagnieżdżone instrukcje. Przy zmianie kodu użyj następnej poprawnej wersji według kanonu repozytorium.
- `main.py` pozostaje jedynym centralnym control plane; `run_studio.py` jest cienkim launcherem; zachowaj `run.py`, TTY, runtime, pamięć i finalizację.
- Nie modyfikuj aktywnej instalacji `jazn_latka_master`, działającego daemona, prywatnej MEMORY ani sekretów. Testuj na izolowanych workspace.
- Bez merge do `master` ani gałęzi rodzica, bez force-push i ukrywania FAIL/SKIP. Po każdym spójnym etapie commit + push + potwierdzenie zdalnego SHA.
- Po zmianie śledzonych plików synchronizuj `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` wyłącznie kanonicznym `release_metadata_sync`/workflow, bez ręcznego edytowania.
- Dla kolejnego kodowego patcha przed zakończeniem zmień `latka_jazn/version.py` i odpowiednie kontrakty, uruchom testy/CI. Ten dokument **nie jest takim patchem**.
- Zależny Draft PR powinien celować w gałąź PR #423, nie bezpośrednio w `master`. Wymaga osobnego review i nie jest release-ready.

## Warunki zakończenia następnego etapu

Raport powinien wymienić: aktualną bazę i HEAD, lokalny/zdalny SHA, stan lokalnego drzewa, dokładne testy PASS/FAIL/SKIP, środowisko i prawdziwe artefakty, wyniki MCP/LLM/GUI oraz otwarte bramki. Brak możliwości uruchomienia lokalnego Windows należy jawnie oznaczyć.
