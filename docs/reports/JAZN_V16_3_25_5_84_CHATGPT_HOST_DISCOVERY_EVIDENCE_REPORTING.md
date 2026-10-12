# Jaźń v16.3.25.5.84 — ChatGPT host discovery evidence reporting

## Problem

Po fail-closed typu `host_executor_unavailable` wcześniejszy kontrakt potrafił zachować poprawną granicę prawdy (`filesystem_state=unknown`, `package_state=unknown`), ale nie rozstrzygał jawnie, czy host miał capability Biblioteki, czy rzeczywiście wykonał search SYSTEM-u, czy znalazł kandydata ani czy zdalny runtime był zweryfikowany. Dwa technicznie różne przypadki mogły więc wyglądać podobnie w widocznym `host_diagnostic`.

## Zmiana

`run.py host-preflight` raportuje teraz zawsze sześć pól diagnostycznych:

- `executor_available` — `true` wyłącznie, gdy bieżąca generacja evidence zawiera powierzchnię, która rzeczywiście utworzyła proces;
- `library_search_available` — host-reported tri-state `true` / `false` / `null`;
- `library_materialize_available` — host-reported tri-state `true` / `false` / `null`;
- `system_search_attempted` — host-reported tri-state, oznaczający search SYSTEM-u na logicznej powierzchni Library/file;
- `system_candidate_found` — host-reported tri-state wyniku tego searchu;
- `remote_runtime_available` — `true` wyłącznie z istniejącej, zweryfikowanej klasyfikacji remote runtime, nigdy z luźnej deklaracji hosta.

`null` oznacza brak wystarczającego evidence i nie jest utożsamiany z `false`. `system_candidate_found=true` wymaga `system_search_attempted=true`, a jawnie wykonany SYSTEM search wymaga `library_search_available=true`.

Cienki loader i `AGENTS.chatgpt.md` wymagają tego samego zestawu przed terminalnym `host_diagnostic`. To jest istotne dla awarii pre-spawn: kiedy lokalny Python nie może się uruchomić, sam runtime nie może wygenerować raportu, więc host ma pokazać te same pola bezpośrednio z własnego evidence, pozostawiając brakujące wartości jako `unknown`.

## Zakres

- `latka_jazn/bootstrap/chatgpt_host_discovery_evidence.py` — tri-state contract i walidacja hostowych obserwacji Library/SYSTEM;
- `latka_jazn/bootstrap/chatgpt_host_preflight*.py` — propagacja i sześć pól w machine-readable output;
- `AGENTS.chatgpt.md` — obowiązkowe raportowanie przed terminalnym fail-closed;
- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` — skrócony odpowiednik dla pre-bootstrap failure;
- `tests/test_chatgpt_host_discovery_evidence_reporting.py` — regresje fail-closed, unknown-vs-false, anti-spoof remote i spójność SYSTEM search;
- `latka_jazn/version.py` — bump do 16.3.25.5.84.

## Evidence zewnętrzne

OpenAI dokumentuje, że Projekty przechowują własne pliki i instrukcje, a połączone aplikacje/narzędzia mogą być używane w czatach projektu zależnie od dostępności planu i workspace. To wspiera jawne rozdzielenie „capability hosta dostępna” od „wynik searchu”.

- OpenAI Help Center, “Projects in ChatGPT”: https://help.openai.com/en/articles/10169521-projects-in-chatgpt

MCP Streamable HTTP rozróżnia warstwę transportu i sesji od samej obecności konfiguracji; dlatego `remote_runtime_available` pozostaje polem pochodnym z istniejących zweryfikowanych classifierów zamiast z deklarowanego booleana.

- Model Context Protocol TypeScript SDK, `streamableHttp`: https://ts.sdk.modelcontextprotocol.io/v2/api/%40modelcontextprotocol/node/streamableHttp.html

## Granica odpowiedzialności

Patch nie sprawia, że host bez executora nagle uzyskuje executor lub Library. Usuwa niejednoznaczność diagnostyczną: brak capability, brak próby searchu, brak kandydata i brak zweryfikowanego remote runtime stają się odrębnymi obserwacjami zamiast jednego ogólnego fail-closed.
