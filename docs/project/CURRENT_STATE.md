# Current project state

**Snapshot date:** 2026-10-06
**Repository:** `SmuklyLew/jazn_latka`  
**Current master at documentation baseline:** `712a25db94c634ea47fbf265c0d907608a668f00`
**Current master version:** `16.3.25.5.107-persistent-remote-runtime-operations-convergence`
**Next planned target:** `16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`

Ten plik jest krótkim overlayem stanu. Kanoniczną wersję zawsze czytać z `latka_jazn/version.py`, a status implementacji z bieżącego kodu, testów, CI, PR/issue i live runtime evidence.

## 1. Release / control plane

Aktualna linia master to v16.3.25.5.107.

## v107 — persistent remote runtime operations

**Status:** `MERGED` / PR #317 / merge commit `d078819a252e98cdce3270713f3c4a5abb8b8e54`; canonical release metadata synchronized at `712a25db94c634ea47fbf265c0d907608a668f00`.

- public MCP startup is fail-closed on canonical conversation readiness, exact
  runtime version and daemon instance binding;
- the canonical runtime supervisor is required by default and is reused only
  with confirmed process identity plus a fresh heartbeat lease;
- Docker liveness (`/healthz`) is separated from runtime readiness
  (`/readyz`);
- deployment contract, Cloudflare Tunnel example and hardened systemd unit are
  versioned in `deploy/chatgpt_mcp/`;
- the MCP wire contract remains 2026-07-28
  `server/discover` + `tools/list` + `tools/call`; non-standard
  `mcp/list-tools` / `mcp/invoke` aliases are explicitly rejected from the
  deployment contract;
- MEMORY v3 staging now verifies its exact-set manifest before transport
  creation, preserving the existing fail-closed attach validation;
- current-message app/callability and accepted `display_exact` finalization
  remain mandatory before attributing a visible response to Jaźń.

v107 code on master does not by itself prove a deployed public endpoint or a
current-message callable ChatGPT app. External deployment and fresh host
capability evidence remain required.


## 2. ChatGPT live bootstrap — zaobserwowany sukces 2026-10-05

W prawdziwej rozmowie ChatGPT udało się przejść lokalną ścieżkę od SYSTEM ZIP do zaakceptowanej widocznej tury.

Kluczowe evidence:

1. zdalny zestaw `jazn_status/jazn_generate_visible_reply/jazn_resume_visible_reply/jazn_finalize_reply` nie był callable;
2. wcześniejsze lokalne powierzchnie zwracały `ClientError` przed dowodem utworzenia procesu;
3. osobna, niezależna powierzchnia kontenerowa hosta potrafiła utworzyć proces;
4. SYSTEM ZIP v106 przeszedł SHA-256, size/package metadata, ZIP catalog, CRC i path-safety validation;
5. wyjęto tylko `CHATGPT_BOOTSTRAP.py`, a nie wykonano surowego `extractall()`;
6. kanoniczny bootstrap zmaterializował SYSTEM do `/mnt/data/jazn_active_root_v16.3.25.5.106`;
7. po wczytaniu `AGENTS.md` i `AGENTS.chatgpt.md` uruchomiono core daemon;
8. live status osiągnął `active_trusted`;
9. jedna wiadomość użytkownika została związana z jedną runtime lineage;
10. po wymaganym host-tool evidence i finalizacji runtime zaakceptował widoczną turę z `action=display_exact`.

Szczegółowy zapis: `docs/reports/CHATGPT_LIVE_BOOTSTRAP_RECOVERY_2026_10_05.md`.

**Granica prawdy:** jest to dowód jednej sesji/host generation. Nie wolno dziedziczyć live statusu do nowej rozmowy bez ponownej weryfikacji.

## 3. Najważniejszy wniosek hostowy

`ClientError`, `TransportTimeoutError` albo brak konkretnego streaming executora przed spawnem **nie może być automatycznie uogólniany na cały host**.

Jeżeli host udostępnia jedną rzeczywiście niezależną alternatywną powierzchnię process execution, należy sprawdzić ją dokładnie raz zgodnie z `AGENTS.chatgpt.md`.

Dzisiejszy przypadek potwierdził praktycznie, że:

```text
surface A pre-spawn failure
!=
global no-process-execution
```

Działająca powierzchnia kontenerowa może umożliwić bezpieczny bootstrap nawet wtedy, gdy inna powierzchnia Pythona/streamingu nie działa.

## 4. MEMORY — aktualny problem wykryty live

MEMORY pozostaje oddzielną opcjonalną capability.

W live bootstrapie 2026-10-05:

- sześć segmentów transportowych przeszło SHA-256;
- worker konwergencji rzeczywiście wystartował;
- staging i I/O postępowały;
- operacja nie była replayowana;
- finalnie attach został odrzucony fail-closed kodem `17`;
- przyczyna: `memory_package_unlisted_file`;
- wewnętrzny manifest nie wymieniał 16 plików fizycznie obecnych w paczce.

W rezultacie:

- autobiograficzna MEMORY nie została aktywowana;
- nie wolno deklarować full autobiographical recall;
- core SYSTEM mógł działać dalej, ponieważ pamięć jest opcjonalna dla core runtime readiness.

Następny fix MEMORY powinien naprawić źródło/manifest pakietu, a nie osłabiać gate.

## 5. Accepted visible turn / finalization

Bieżąca architektura wymaga rozróżnienia:

1. zmaterializowany SYSTEM;
2. live trusted daemon;
3. verified runtime turn;
4. accepted visible turn.

Dopiero punkt 4 pozwala pokazać zwykłą odpowiedź jako wynik runtime Jaźni.

W live przebiegu 2026-10-05 host wykonał wymagane narzędzie zewnętrzne, przekazał bounded evidence i przeszedł phase-2 finalization. Runtime potwierdził accepted finalization, lineage, MessageEnvelope i `display_exact`.

Sam PID, folder, ZIP, heartbeat, model językowy albo niezweryfikowany tekst nadal nie wystarczają.

## 6. Remote runtime / MCP

Kod v106 zawiera infrastrukturę dla zdalnego MCP, ale obecność kodu nie dowodzi wdrożonego transportu.

Aktualny kierunek operacyjny:

```text
persistent runtime outside one chat
+ authenticated HTTPS /mcp
+ ChatGPT connector/app capability
= executor-independent ordinary ChatGPT route
```

Do momentu wdrożenia i zweryfikowania tej trasy lokalny bootstrap może działać tylko wtedy, gdy bieżący host faktycznie udostępnia process execution.

## 7. Najbliższe techniczne priorytety

1. zachować v107 remote-runtime/MEMORY producer fixes jako baseline;
2. nie mylić naprawionego generatora z już naprawioną historyczną paczką MEMORY:
   stara paczka, która fail-closed zakończyła się `memory_package_unlisted_file`,
   wymaga nowej poprawnie wygenerowanej paczki i ponownego attach/acceptance;
3. zbudować jeden `TurnDiagnosticTrace` dla całej tury;
4. wprowadzić typed no-silent-fallback contract oraz blind-route detection;
5. dodać statyczny RouteGraphAudit do CI;
6. rozpocząć etapową dekompozycję `JaznEngine` dopiero po characterization/parity
   gate;
7. wydzielić host finalization tak, aby phase-2 nie konstruowała pełnego
   cognitive engine;
8. redukować legacy `conversation.py` dopiero po route/parity evidence;
9. Affect i MEMORY zmieniać semantycznie wyłącznie przez ich własne owner plans.

## 8. Dokumentacja prawdy

- `AGENTS.md` — router instrukcji;
- `AGENTS.chatgpt.md` — kanoniczny host runbook;
- `AGENTS.codex.md` — zmiany repozytorium;
- `latka_jazn/version.py` — release identity;
- `MEMORY_ATTACHMENT_CONTRACT.json` — granica SYSTEM/MEMORY;
- `docs/reports/CHATGPT_LIVE_BOOTSTRAP_RECOVERY_2026_10_05.md` — dzisiejsze live evidence;
- `docs/plans/CURRENT_STEP.md` — najbliższy legalny krok;
- `docs/plans/PLAN_EXECUTION_HISTORY.md` — historia planu;
- `docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` — granice naukowe/tożsamościowe.

`merged`, `working`, `verified`, `accepted`, `active_trusted` i `live` zawsze wynikają z właściwego evidence, a nie z dokumentu, nazwy brancha, ZIP-a lub stylu odpowiedzi.
