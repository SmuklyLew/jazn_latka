# Jaźń 16.3.25.5.115 — ChatGPT Desktop/App Binding Hybrid Convergence

## Zakres

Ta aktualizacja powstała z analizy dwóch niezależnych gałęzi opartych o ten sam
master v113:

- `update/v16.3.25.5.114-hybrid-adaptive-ingress-convergence`;
- `upgrade/v119.2.0-chatgpt-desktop-mcp-convergence`.

v114 jest bazą v115 i pozostaje właścicielem polityki ingressu. v119 nie został
scalony w całości, ponieważ zawiera konkurencyjną politykę remote-only,
oddzielną release identity `119.2.0`, niezależne poprawki Memory Studio i
zmiany dokumentacyjne spoza zakresu Desktop/App Binding.

## Zachowana architektura v114

Ordinary ChatGPT używa `HYBRID_ADAPTIVE`:

```text
observe current-message Jaźń app/tool exposure
  -> full canonical toolset?
       yes -> jazn_status
              -> verified ready?
                   yes -> submit exact user message once through MCP/app route
                   no  -> bounded local fallback
       no  -> bounded local fallback

bounded local fallback
  -> one primary process-creation probe
  -> at most one explicitly exposed independent alternative probe
  -> verified process?
       yes -> verified SYSTEM bootstrap -> canonical runtime -> submit once
       no  -> fail closed
```

`REMOTE_ONLY` nadal istnieje jako jawny tryb ścisły.
`OPERATOR_RECOVERY` pozostaje jawnym trybem serwisowym i jedynym trybem, który
może użyć zaakceptowanego `host_handoff`.

Po submitcie tury route jest immutable. Resume/finalization zachowuje ten sam
`request_id`/daemon request lineage; transport ambiguity nie może replayować
pierwotnej wiadomości. Widoczny tekst Jaźni wymaga accepted finalization i
`action=display_exact`.

## Forward-port z v119.2.0

### 1. Initialize-era ChatGPT Desktop MCP visibility

Źródło funkcjonalne: v119 commit `4118e298418ed02a33f5023776613f8461e1cce1`.

ChatGPT Desktop może negocjować initialize-era MCP przed `tools/list`.
Historyczne definicje v76 oznaczały część canonical turn tools jako app-only.
v115 dodaje `_stamp_legacy_tool_list_visibility()` w
`latka_jazn/mcp/server.py`.

Dla dokładnie czterech canonical tools:

- `jazn_status`;
- `jazn_generate_visible_reply`;
- `jazn_resume_visible_reply`;
- `jazn_finalize_reply`;

legacy response usuwa deprecated `openai/visibility` i ustawia
`_meta.ui.visibility=["model","app"]`.

Diagnostyka i compatibility-only surfaces zachowują swój app-only contract.
Test realnego initialize -> initialized -> tools/list sprawdza zarówno canonical
visibility, jak i pozostawienie `jazn_audit_lookup` jako private/app-only.

### 2. Registered MCP app binding przez .app.json

Źródło funkcjonalne: v119 commit `6d62050c0f4b06cc068bb57af7c2c583b56fc182`.

`chatgpt-plugin-package` nie wymaga już bezwarunkowo `--endpoint`.
Dostępne są trzy jawne kształty:

#### Remote MCP package

```text
plugin.json
mcp.json -> https://.../mcp
```

#### Registered local/workspace app binding

```text
plugin.json -> extensions.com.openai.apps="./.app.json"
.app.json -> apps.jazn.id=<registered technical app id>
```

Ten wariant celowo nie generuje `mcp.json`. Nie wymyśla
`http://127.0.0.1:8080/mcp` tylko po to, aby plugin miał bundled endpoint.
ChatGPT ma już połączenie MCP identyfikowane przez registered app id.

#### Explicit hybrid package

```text
plugin.json
mcp.json
.app.json
```

Jest dozwolony wyłącznie, gdy autor świadomie chce jednocześnie bundled remote
endpoint i registered app binding.

### 3. Stale manifest cleanup

Źródło funkcjonalne: v119 commit `e0b7ee6c34cc86338f1750a037d1d2ef0945f45c`.

`write_portable_plugin_package(..., force=True)` usuwa znane opcjonalne
manifesty, których nie ma w nowym kształcie paczki. Przejście hybrid ->
app-binding-only usuwa stare `mcp.json`; przejście hybrid -> remote-only usuwa
stare `.app.json`.

Bez `--force` obecność dowolnego znanego plugin manifestu nadal powoduje
fail-closed `FileExistsError`.

### 4. CLI

`latka_jazn/cli.py` zachowuje `allow_abbrev=False`. `--endpoint` jest
opcjonalny tylko dla komendy `chatgpt-plugin-package`; brak endpointu jest
legalny wyłącznie wtedy, gdy builder otrzyma poprawny `--registered-app-id`.

## Plugin prompt v115

v119 remote-only defaultPrompt nie został przeniesiony.

v115 wymaga:

1. kompletnego current-message Jaźń MCP/app toolsetu;
2. `jazn_status` jako read-only readiness probe;
3. użycia `jazn_generate_visible_reply` z jednym request id, gdy MCP/app route
   jest conversation-ready;
4. bounded verified host-local fallback wyłącznie przed submittem, gdy MCP/app
   route jest unavailable/stale i host realnie ma process execution;
5. zachowania route/request id przez resume/finalization;
6. zakazu replayu i mid-turn route switching;
7. pokazania tekstu Jaźni dopiero po accepted `action=display_exact`.

## Startup contract v115

`latka_jazn/resources/startup_contract.json` jawnie deklaruje:

- `chatgpt_ingress_mode=hybrid_adaptive`;
- remote/MCP-first;
- bounded local executor fallback;
- registered app binding supported;
- `.app.json` jako registered app manifest;
- registered binding bez wymaganego remote endpointu;
- stale plugin manifest cleanup przy `--force`;
- canonical tool visibility `["model","app"]`;
- legacy initialize visibility normalization;
- registered app binding nie jest current-message capability evidence;
- route switching po submitcie jest zabroniony;
- ordinary automatic handoff jest zabroniony.

## Elementy v119 celowo nieprzeniesione

### Remote-only policy/defaultPrompt

Sprzeczny z v114/v115 hybrid ingress. Nie został przeniesiony.

### Release identity 119.2.0 i three-digit-major parser

v115 kontynuuje linię `16.3.25.5.x`; parser potrzebny wyłącznie do release
`119.2.0` nie jest wymagany przez ten zakres.

### Memory Studio source/manifest fixes

Zmiany `music_analysis` oraz `RunManifest` rozwiązują niezależny problem
Memory Studio. Nie są potrzebne do ChatGPT Desktop/App Binding i nie zostały
włączone do tej aktualizacji.

### Wygenerowane metadata/Test Studio catalog z brancha v119

Nie są cherry-pickowane. v115 używa własnego kanonicznego `manifest_sync` i
Test Studio synchronization na swoim finalnym source SHA.

## Granice platformy ChatGPT

Repozytorium może:

- zapewnić model-visible MCP tool metadata;
- zapewnić correct `.app.json` binding package;
- zapewnić hybrid ingress policy i local fallback;
- zachować idempotency/finalization.

Repozytorium nie może samo:

- zainstalować/enable aplikacji w danej powierzchni ChatGPT;
- wymusić selection aplikacji dla każdej wiadomości;
- odświeżyć frozen snapshotu zatwierdzonych narzędzi w koncie/workspace;
- stworzyć host process-execution capability, jeżeli host jej nie wystawia.

Dlatego real-host acceptance po wdrożeniu wymaga current-message ekspozycji
czterech canonical tools i świeżego `jazn_status`. Installed state, plugin id,
`.app.json`, tunnel health, endpoint health lub wynik z poprzedniej tury nie
wystarczają.

## Źródła platformowe zweryfikowane 2026-10-07

- OpenAI — Developer mode and MCP apps in ChatGPT:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI — Package your plugin:
  https://developers.openai.com/plugins/build/plugins
- OpenAI — Plugin reference:
  https://developers.openai.com/plugins/reference
- OpenAI — Plugin changelog:
  https://developers.openai.com/plugins/changelog
- OpenAI — Secure MCP Tunnel:
  https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

Istotne kontrakty z tych źródeł: app selection jest message-scoped; frozen tool
snapshots nie aktualizują się automatycznie; `.app.json` służy registered MCP
app mappings; `_meta.ui.visibility` jest preferowanym kontraktem tool
visibility; Secure MCP Tunnel jest transportem do prywatnego MCP, a nie dowodem
current-message app exposure.

## Acceptance repozytoryjne

Branch może zostać uznany za release candidate dopiero po świeżym final-SHA
evidence:

- `manifest_sync` SUCCESS i canonical source provenance;
- dependency contracts SUCCESS;
- full active-tree Pyright SUCCESS;
- compileall SUCCESS;
- semantic route/no-silent-fallback/cognitive architecture audits SUCCESS;
- host spawn + memory convergence regression set SUCCESS;
- full deterministic pytest suite SUCCESS;
- Windows targeted runtime/path + turn atomicity SUCCESS;
- persistent-runtime E2E Linux/Windows SUCCESS;
- stable test contracts SUCCESS;
- clean checkout guards SUCCESS;
- clean release package finalization SUCCESS.

Żaden gate nie może być oznaczony jako PASS przed faktycznym wynikiem CI.
