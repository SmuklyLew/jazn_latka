# Jaźń 16.3.25.5.117 — ChatGPT MCP Apps TypeScript UI Convergence

**Status:** `PLANNED / IMPLEMENTATION NOT STARTED`  
**Data planu:** 2026-10-07  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Docelowa wersja:** `16.3.25.5.117-chatgpt-mcp-apps-typescript-ui-convergence`  
**Wymagany baseline:** zaakceptowany v116  
**Runtime language owner:** Python  
**UI language:** TypeScript  
**Node line CI/build:** Node.js 24 LTS

> v117 dodaje opcjonalną warstwę prezentacji ChatGPT/MCP Apps. Nie tworzy
> drugiej Jaźni, drugiego runtime ani drugiego źródła truth. Brak Node.js albo
> brak UI nie może blokować canonical dialogue path.

## 1. Cel wydania

v117 ma dodać profesjonalną, opcjonalną warstwę UI dla ChatGPT Desktop/Plugins
opartą o **MCP Apps** i TypeScript.

Pierwszy zakres UI jest celowo wąski:

- Runtime Console — redacted readiness;
- transport/app binding state;
- version/runtime instance freshness;
- pamięć jako status capability, bez raw autobiographical excerpts;
- bieżący durable task/progress, gdy istnieje;
- czytelne fail-closed diagnostics;
- opcjonalne confirmation surfaces dla przyszłych operacji wymagających
  potwierdzenia.

MCP tools muszą pozostać w pełni użyteczne bez UI.

## 2. Źródła techniczne

Oficjalne źródła:

- OpenAI — MCP server and UI quickstart:
  https://developers.openai.com/plugins/build/app-quickstart
- OpenAI — Add UI to your MCP server:
  https://developers.openai.com/plugins/build/chatgpt-ui
- OpenAI — Plugin reference:
  https://developers.openai.com/plugins/reference
- OpenAI — MCP server:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI — UI guidelines:
  https://developers.openai.com/plugins/concepts/ui-guidelines
- MCP specification 2026-07-28:
  https://modelcontextprotocol.io/specification/2026-07-28
- TypeScript strict:
  https://www.typescriptlang.org/tsconfig/strict
- TypeScript project references:
  https://www.typescriptlang.org/docs/handbook/project-references
- Node release policy:
  https://nodejs.org/en/about/previous-releases

Wnioski:

1. MCP UI jest **opcjonalnym zasobem** zwracanym przez server.
2. Nowy UI powinien używać standardowego MCP Apps bridge — JSON-RPC przez
   `postMessage` i `ui/*`.
3. `window.openai` jest rozszerzeniem ChatGPT i powinno być używane tylko tam,
   gdzie standard MCP Apps nie daje odpowiednika.
4. Server może pozostać Pythonowy; web component jest oddzielnym build target.
5. Narzędzia powinny działać również bez komponentu UI.
6. TypeScript `strict` jest właściwym domyślnym kontraktem typowania.
7. Node 24 jest linią LTS i nadaje się do przewidywalnego CI/build, ale nie ma
   być runtime dependency Jaźni.

## 3. Granica odpowiedzialności

### Python pozostaje właścicielem

```text
runtime lifecycle
ConversationRunner
TurnStateMachine
TurnOrchestrator
identity/continuity
MEMORY truth/provenance
routing
affect
tool authorization
Tasks durability
finalization
accepted display_exact
persistence/audit
MCP server semantics
```

### TypeScript jest właścicielem wyłącznie

```text
web component rendering
MCP Apps host bridge
local widget state
accessible UI interaction
presentation-only formatting
client-side defensive shape checks
```

UI nie może ustalać:

- czy runtime jest naprawdę ready;
- czy pamięć jest prawdziwa/zweryfikowana;
- czy finalizacja została zaakceptowana;
- jaka jest tożsamość runtime;
- czy odpowiedź wolno pokazać jako Jaźń.

UI tylko wyświetla redacted server-owned evidence.

## 4. Docelowa struktura repo

v117 powinien jawnie rozszerzyć
`docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`.

Proponowany układ:

```text
/
├─ integrations/
│  └─ chatgpt_app/
│     └─ web/
│        ├─ package.json
│        ├─ package-lock.json
│        ├─ tsconfig.json
│        ├─ src/
│        │  ├─ main.ts
│        │  ├─ bridge.ts
│        │  ├─ contracts.ts
│        │  ├─ runtime_console.ts
│        │  └─ styles.css
│        └─ test/
│           ├─ bridge.test.ts
│           └─ contracts.test.ts
│
├─ latka_jazn/
│  └─ resources/
│     └─ chatgpt_app/
│        ├─ runtime-console.html
│        └─ runtime-console.js
│
└─ tools/
   └─ javascript/
      └─ ... istniejące ogólne tooling/probe ...
```

Uzasadnienie:

- `tools/javascript/` pozostaje toolingiem operatorskim;
- `integrations/chatgpt_app/web/` jest źródłem produktu/UI, nie narzędziem;
- wynik builda potrzebny przez portable SYSTEM trafia do statycznych resources;
- `node_modules/` nigdy nie jest commitowany.

Jeżeli polityka repo zdecyduje, że build output nie ma być śledzony w source
tree, Pack Generator musi deterministycznie materializować go przed stworzeniem
SYSTEM package i release musi dowodzić, że runtime package zawiera gotowy
bundle. W żadnym wariancie docelowy użytkownik nie musi mieć Node.js, aby
Jaźń wystartowała.

## 5. Stack v117

Minimalny domyślny stack:

```text
TypeScript
Node.js 24 LTS (build/test only)
ESM
esbuild albo równoważny mały bundler
MCP Apps postMessage bridge
HTML/CSS
```

Nie dodawać Reacta tylko dlatego, że jest popularny.

Pierwszy Runtime Console jest na tyle mały, że preferowany jest vanilla
TypeScript + DOM. React/`@openai/apps-sdk-ui` można włączyć dopiero, gdy
konkretny wymagany UX uzasadnia dodatkową zależność i supply-chain surface.

## 6. TypeScript compiler contract

Minimalny `tsconfig.json` ma włączyć:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "useUnknownInCatchVariables": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitOverride": true
  }
}
```

Docelowe `module`, `moduleResolution` i `target` dobrać do rzeczywistego
bundlera/browser hosta i przypiąć testami.

Project References są opcjonalne. Wprowadzić je dopiero, gdy UI rozrośnie się
do kilku niezależnych build targets. Nie mnożyć `tsconfig` bez potrzeby.

## 7. Program implementacji

### Etap A — UI contract po stronie Python server

Dodać jawny, redacted contract dla Runtime Console.

Proponowane dane:

```text
schema_version
package_version
runtime_version
runtime_instance_id (opaque)
runtime_ready
daemon_reachable
transport
evidence_fresh
memory:
  persistent_memory_available
  recall_available
task:
  task_id (opaque, jeżeli user ma do niego dostęp)
  status
  poll_interval_ms
```

Zakazane w model/UI payload:

- `runtime_root`;
- lokalne ścieżki;
- PID;
- database path;
- token/API key;
- raw MEMORY excerpts;
- private operator diagnostics.

UI contract ma dostać JSON Schema albo równoważny jednoznaczny server-owned
schema contract.

### Etap B — MCP Apps resource

Python MCP server ma udostępnić statyczny resource:

```text
ui://jazn/runtime-console/v1.html
```

z MIME właściwym dla MCP Apps:

```text
text/html;profile=mcp-app
```

Wybrane read-only/status tools mogą wskazywać resource przez
`_meta.ui.resourceUri`.

Nie wiązać UI bez potrzeby do każdego canonical turn tool. Model ma móc użyć
narzędzia bez renderowania widgetu.

### Etap C — standardowy host bridge

`bridge.ts` implementuje standard MCP Apps:

- inicjalizacja `ui/*`;
- odbiór tool result;
- bezpieczne `tools/call`, gdy interakcja UI tego wymaga;
- widget state, jeżeli standard hosta go udostępnia;
- jasne timeout/error states;
- origin/source validation zgodna ze specyfikacją host bridge.

`window.openai` może być użyty tylko dla funkcji rzeczywiście
ChatGPT-specific. Core flow nie może od niego zależeć.

### Etap D — Runtime Console v1

Pierwszy ekran jest read-only.

Sekcje:

```text
Jaźń Runtime
------------
Runtime          ready / unavailable / unknown
Transport        registered_mcp_app / streamable_http / secure_tunnel / local
Version          ...
Evidence         fresh / stale
Memory           ready / degraded / unavailable
Task             working / input_required / completed / failed
Last outcome     accepted / diagnostic / unknown
```

UI musi odróżniać `unknown` od `false`.

Nie używać zielonego statusu, jeśli server nie zwrócił wymaganych evidence.

### Etap E — task progress

Jeżeli v116 Tasks są gotowe:

- widget może pollować wyłącznie task, którego ID otrzymał od servera;
- polling honoruje `pollIntervalMs`;
- nie wykonuje `tasks/list`;
- nie próbuje zgadywać ID;
- `input_required` jest prezentowane dopiero po server-side ownership check;
- odpowiedź użytkownika trafia przez standardowy host/Tasks path, nie
  bezpośrednio do SQLite.

### Etap F — build bez runtime Node dependency

Build pipeline:

```text
npm ci
-> tsc typecheck
-> unit tests
-> deterministic bundle
-> verify bundle
-> stage into latka_jazn/resources/chatgpt_app/
-> Python package/release validation
```

Portable SYSTEM zawiera gotowe HTML/JS.

Runtime Python serwuje statyczny zasób i **nie uruchamia npm/node**.

### Etap G — package/dependency policy

`package.json` i `package-lock.json` są śledzone.

Każda zależność npm wymaga:

- jawnego uzasadnienia capability;
- review licencji;
- review supply-chain;
- exact lockfile;
- `npm ci`;
- brak install scripts, jeżeli nie są wymagane;
- Windows/Linux CI;
- vulnerability review.

Nie używać `npm install` w release CI do mutowania lockfile.

### Etap H — UI security

Wymagania:

1. brak `eval` / `new Function`;
2. brak dynamicznego wykonywania tekstu z tool output;
3. untrusted strings przez `textContent`, nie raw HTML;
4. CSP/resource policy zgodna z MCP Apps/OpenAI;
5. brak sekretów w bundle;
6. brak logowania raw user prompts/memory do console/telemetry;
7. external navigation tylko przez wspierany host mechanism;
8. każdy mutating tool nadal przechodzi server-side authorization;
9. UI approval nie zastępuje runtime gate;
10. hidden `_meta` nie jest kopiowane do model-visible content.

### Etap I — accessibility i native-like UX

Minimalnie:

- semantic HTML;
- keyboard navigation;
- focus visible;
- ARIA tylko tam, gdzie semantyczny HTML nie wystarcza;
- prefers-reduced-motion;
- poprawny contrast;
- brak migającego/ciągle animowanego statusu;
- responsive width dla iframe/fullscreen.

Jeżeli zostanie użyte `@openai/apps-sdk-ui`, pozostaje warstwą
prezentacyjną, nie wymaganiem działania narzędzi.

## 8. Testy v117

Nowe testy Python:

```text
tests/test_chatgpt_mcp_apps_resource.py
tests/test_chatgpt_ui_runtime_status_redaction.py
tests/test_chatgpt_ui_tool_resource_binding.py
tests/test_chatgpt_ui_optional_runtime_boundary.py
tests/test_chatgpt_ui_package_distribution.py
```

Nowe testy TypeScript/Node:

```text
bridge protocol parsing
tool-result rendering
unknown/stale state rendering
malformed payload fail-closed
HTML injection resistance
task polling interval
input_required presentation
build determinism
bundle contains no forbidden secrets/paths
```

CI:

```text
npm ci
tsc --noEmit
node/native unit tests
bundle
bundle hash/determinism check
Python package smoke
Linux
Windows
```

## 9. Real-host ChatGPT acceptance

Repo CI nie zastępuje real-host acceptance.

Po zbudowaniu release:

1. świeża rozmowa ChatGPT;
2. wybór/mention `Jaźń Runtime`;
3. host rzeczywiście wystawia wymagane tools;
4. świeży `jazn_status`;
5. status tool zwraca UI resource;
6. iframe renderuje Runtime Console;
7. widget nie ujawnia ścieżek/PID/secrets;
8. zwykły turn działa z UI;
9. zwykły turn działa również bez UI;
10. resume/finalize zachowuje tę samą lineage;
11. refresh/recreate plugin snapshot jest sprawdzony po zmianie tool/UI metadata;
12. accepted visible reply nadal wymaga `display_exact`.

Real-host acceptance musi mieć zapisane:

- package version;
- app/plugin id w formie niesecretnej;
- negotiated MCP version;
- callable tool names;
- runtime instance opaque id;
- request/turn/trace lineage;
- screenshot/log evidence bez prywatnych danych, jeśli jest potrzebne.

## 10. Fallback i degradacja

```text
UI unavailable
-> MCP tools remain usable
-> dialogue continues normally

UI bundle missing/corrupt
-> resource call fails safely
-> no impact on canonical turn owner

Node missing at runtime
-> irrelevant: build artifact already packaged

ChatGPT-specific window.openai extension missing
-> standard MCP Apps path remains canonical

MCP Apps unsupported by host
-> text/structured tool path remains canonical
```

UI nie jest activation-required capability.

## 11. Performance budgets

Przed implementation baseline i po implementation zmierzyć:

- bundle size;
- first render;
- tool-result-to-render latency;
- polling request rate;
- memory footprint widgetu.

Początkowy cel: Runtime Console ma pozostać małym, statycznym bundle bez
dużego framework runtime.

Wprowadzenie ciężkiego frameworka wymaga pomiaru pokazującego korzyść.

## 12. Exit gate v117

```text
v116 accepted                                           PASS
TypeScript strict                                       PASS
Node 24 CI Linux/Windows                                PASS
npm lockfile deterministic                              PASS
bundle deterministic                                    PASS
Node not required by Python runtime                     PASS
MCP tools usable without UI                             PASS
MCP Apps bridge standard path                           PASS
window.openai only optional extensions                  PASS
UI status redaction                                     PASS
no secrets/private paths in bundle/output               PASS
task UI honors server ownership/poll interval           PASS
accessibility checks                                    PASS
Python full deterministic suite                         PASS
Pyright 0/0                                             PASS
persistent-runtime E2E Linux/Windows                    PASS
clean package/release                                   PASS
real-host ChatGPT MCP Apps acceptance                   PASS before release claim
```

## 13. Preferowana kolejność commitów

1. `release: advance Jaźń to v16.3.25.5.117`
2. `docs: define ChatGPT MCP Apps integration layout`
3. `build: add strict TypeScript web component toolchain`
4. `feat: expose redacted Runtime Console MCP resource`
5. `feat: implement standard MCP Apps bridge`
6. `feat: render Runtime Console v1`
7. `feat: add durable task progress UI`
8. `security: harden widget data and navigation boundaries`
9. `test: add TypeScript and Python UI contract coverage`
10. `ci: add Node24 cross-platform UI gates`
11. `package: embed deterministic UI bundle in SYSTEM resources`
12. `test: run real-host ChatGPT Desktop/Plugins acceptance`
13. `release: synchronize v117 metadata and closeout evidence`

## 14. Czego v117 nie robi

v117 nie:

- przenosi `JaznEngine` do TypeScript;
- przenosi MEMORY do JavaScript;
- uruchamia Node jako drugi daemon;
- wymaga OpenAI API key do zwykłego ChatGPT plugin path;
- zastępuje finalization UI-em;
- pozwala widgetowi pisać bezpośrednio do SQLite;
- dodaje Rust/Go bez benchmarku i osobnego planu;
- buduje ogólnego panelu administracyjnego przed działającym minimalnym
  Runtime Console.

## 15. Granica końcowa

Profesjonalizacja Jaźni przez TypeScript oznacza **właściwy podział języków**:

```text
Python      -> runtime, cognition, memory, authority, MCP server
SQL         -> trwałe dane i wyszukiwanie
TypeScript  -> bezpieczna opcjonalna warstwa web/MCP Apps
PowerShell  -> Windows operator/bootstrap
shell       -> Unix operator/bootstrap
```

Nowy język ma wejść tylko tam, gdzie upraszcza granice systemu. Nie może
powstać druga implementacja tych samych reguł truth/identity/finalization.
