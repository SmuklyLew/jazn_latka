# Current project state

**Snapshot date:** 2026-10-07
**Repository:** `SmuklyLew/jazn_latka`  
**Current master at documentation baseline:** `7b322284e49ed0a08d24d5cd5a56ba567532eba1`
**Current master version:** `16.3.25.5.113-remote-only-chatgpt-ingress-convergence`
**Current implementation candidate:** `16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence` on `update/v16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence`

Ten plik jest krótkim overlayem stanu. Kanoniczną wersję zawsze czytać z `latka_jazn/version.py`, a status implementacji z bieżącego kodu, testów, CI, PR/issue i live runtime evidence.

## 1. Release / control plane

Aktualna linia master to v16.3.25.5.113. v115 jest implementacyjnym kandydatem na osobnym branchu i konwerguje v114 hybrid/adaptive ingress z kompatybilnymi zmianami ChatGPT Desktop/App Binding z v119.2.0.

## v115 — ChatGPT Desktop/App Binding Hybrid Convergence

**Status:** `IMPLEMENTATION CANDIDATE` on
`update/v16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence`.

v115 bazuje na finalnym v114 i zachowuje `HYBRID_ADAPTIVE` jako domyślny
ordinary-chat ingress: verified current-message MCP/app route -> bounded
verified local bootstrap -> fail-closed. `REMOTE_ONLY` pozostaje jawnym trybem
ścisłym, a `OPERATOR_RECOVERY` jedynym trybem z zaakceptowanym host handoffem.

Z gałęzi `upgrade/v119.2.0-chatgpt-desktop-mcp-convergence` forward-portowane
zostały wyłącznie zgodne elementy Desktop/App Binding:

- initialize-era `tools/list` normalizuje cztery canonical `jazn_*` tools do
  `_meta.ui.visibility=["model","app"]` bez deprecated
  `openai/visibility=private`;
- plugin package może użyć samego `--registered-app-id` i wygenerować
  `plugin.json + .app.json` bez sztucznego localhost `mcp.json`;
- remote HTTPS package nadal używa `mcp.json`, a świadomy wariant hybrydowy
  może zawierać oba bindingi;
- `--force` usuwa stale opcjonalne manifesty po zmianie kształtu paczki;
- plugin defaultPrompt pozostaje zgodny z v114 hybrid ingress, idempotentnym
  resume/finalization i `display_exact`.

Nie przeniesiono starego v119 remote-only promptu/polityki, release line
`119.2.0`, niezależnych Memory Studio fixów ani 3-cyfrowego parsera wersji.

Bieżące kontrakty:
`docs/runtime/CHATGPT_HYBRID_ADAPTIVE_INGRESS.md` oraz
`docs/runtime/CHATGPT_PLUGIN_RUNTIME.md`.

## v114 — hybrid/adaptive ChatGPT ingress

**Status:** `IMPLEMENTATION CANDIDATE` on
`update/v16.3.25.5.114-hybrid-adaptive-ingress-convergence`.

v114 zachowuje v113 persistent remote MCP jako trasę preferowaną, ale przywraca
bounded host-local bootstrap ordinary-chat, gdy bieżąca wiadomość nie ma
conversation-ready Jaźń app/toolset, a host faktycznie może utworzyć proces.
Remote readiness wygrywa nad local; local fallback jest dozwolony wyłącznie
przed submittem tury; po submitcie route/request są zamrożone i obowiązuje
resume/finalization bez replayu. Automatic host handoff pozostaje zabroniony w
ordinary chat i jest dostępny tylko w jawnym `operator_recovery`.

Bieżący kontrakt: `docs/runtime/CHATGPT_HYBRID_ADAPTIVE_INGRESS.md`.

## v113 — remote-only ChatGPT ingress

**Status:** `MERGED` / master baseline `7b322284e49ed0a08d24d5cd5a56ba567532eba1`.

v113 ustanowił current-message remote toolset gate i fail-closed remote-only
ordinary ingress. Ten kontrakt pozostaje dostępny jako jawny strict
`REMOTE_ONLY`, ale jego rola jako domyślnego ordinary-chat jest superseded
przez v114.

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


## v108–v111 — conversation runtime decomposition and cutover

**Status:** `REPOSITORY_COMPLETE / STACKED_PRS_UNMERGED`.

PR #318–#321 wdrożyły kolejno diagnostic spine, jawny lifecycle i
`FinalizationService`, `TurnOrchestrator`, a następnie canonical
`ConversationRunner` + `TurnStateMachine` + structured ordinary-dialogue cutover.
Finalny v111 SHA `ee00529cdbd9a4d0a469007db787ed4895667ddf` ma świeży pełny
suite **2107 PASS / 4 platform SKIPPED / 0 FAIL** oraz terminalne SUCCESS dla
Pyright, release-hardening, persistent-runtime E2E Linux/Windows, package cleanroom
i PowerShell. PR #321 pozostaje draftem/niezmergowany.

## v112 — v111 closeout and real-host evidence

**Status:** `IMPLEMENTATION CANDIDATE` on
`upgrade/v16.3.25.5.112-v111-closeout-real-host-evidence-convergence`.

v112 nie zmienia semantyki runtime. Synchronizuje dokumentację po zakończonym v111,
zapisuje rzeczywisty ChatGPT-host E2E oraz podnosi release identity zgodnie z polityką
repozytorium.

Real-host local-executor E2E 2026-10-06: **PASS**. Finalny pakiet v111 z GitHub
Actions został zweryfikowany i zmaterializowany przez `CHATGPT_BOOTSTRAP.py`;
live status osiągnął `system_fully_ready=true`. Jedna wiadomość została wysłana
dokładnie raz. Błędny phase-2 binding został odrzucony fail-closed, następnie ten
sam request został wznowiony bez replayu i zaakceptowany jako
`accepted_visible_turn_ready=true`, `action=display_exact`, z poprawnym
`turn_authority_receipt`.

Pełny zdalny toolset Jaźni nie był callable w tej wiadomości, więc publiczny
Streamable HTTP / Secure MCP Tunnel pozostaje osobnym, nieweryfikowanym external
deployment route. Nie jest potrzebny do zaliczenia wykonanej lokalnej trasy host E2E.

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

1. zakończyć v112 przez canonical metadata sync i terminalne CI na finalnym SHA;
2. nie scalać PR #318–#321 ani v112 bez osobnej zgody użytkownika;
3. utrzymać remote MCP jako oddzielny deployment/capability gate — obecność kodu
   nie jest dowodem callable aplikacji ChatGPT;
4. dla prywatnej MEMORY wygenerować poprawny exact-set package i wykonać osobny
   attach/acceptance zamiast osłabiać istniejące gate;
5. dalsze Memory/Affect/NLP prowadzić wyłącznie przez ich aktualne owner plans po
   zamknięciu tego closeoutu.

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
