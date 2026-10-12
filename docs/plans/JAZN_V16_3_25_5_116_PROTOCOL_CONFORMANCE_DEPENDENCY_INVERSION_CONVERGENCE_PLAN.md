# Jaźń 16.3.25.5.116 — Protocol Conformance + Dependency Inversion Convergence

**Status:** `PLANNED / IMPLEMENTATION NOT STARTED`  
**Data planu:** 2026-10-07  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Docelowa wersja:** `16.3.25.5.116-protocol-conformance-dependency-inversion-convergence`  
**Wymagany baseline implementacyjny:** zaakceptowany v115 — `update/v16.3.25.5.115-chatgpt-desktop-app-binding-hybrid-convergence`  
**Zweryfikowany source commit v115:** `64b2b131177c565b248591a50cd5dd983d079601`  
**Release-metadata HEAD v115:** `41f4fc351ed50cc3ab31e64c7ff4aba406159616`  
**Master w chwili utworzenia planu:** `7b322284e49ed0a08d24d5cd5a56ba567532eba1` / v113

> Ten dokument jest planem implementacji. Jego obecność na `master` nie oznacza,
> że v115 został scalony, v116 został wdrożony ani że jakikolwiek runtime jest
> aktywny. Implementacja v116 musi rozpocząć się z zaakceptowanego potomka v115
> albo po jego kontrolowanym włączeniu do głównej linii.

## 1. Cel wydania

v116 ma domknąć dwa obszary, które po v115 pozostają technicznym długiem:

1. **zgodność protokołu i bezpieczeństwo transportu MCP 2026-07-28**, w tym
   oficjalny conformance suite, pełny kontrakt Tasks i jawne związanie tasków z
   uwierzytelnionym callerem;
2. **dokończenie dekompozycji runtime**, tak aby wydzielone koordynatory nie
   zależały od całego `JaznEngine`, a `runtime_daemon.py` przestał być
   monolitycznym modułem z late monkey-patchingiem.

v116 nie zmienia znaczenia Jaźni, kanonu tożsamości, MEMORY truth/provenance,
Affect authority ani accepted-visible-turn boundary.

## 2. Niezmienniki

W całej aktualizacji obowiązują:

```text
run.py -> main.py                       jeden centralny control plane
one user input -> one logical turn      brak replayu
one request lineage                     request_id/turn_id/trace_id zachowane
accepted display_exact                  jedyna podstawa widocznej odpowiedzi Jaźni
Python runtime                          jedyny canonical runtime
MCP / ChatGPT / Ollama                  adaptery, nie ownerzy tożsamości
MEMORY provenance                       bez osłabiania
local Node absence                      nie blokuje core runtime
```

Nie wolno wprowadzić drugiego lifecycle, drugiego session ownera ani drugiej
finalizacji.

## 3. Źródła techniczne i wnioski

Plan opiera się na bieżących, oficjalnych materiałach:

- MCP 2026-07-28 specification:
  https://modelcontextprotocol.io/specification/2026-07-28
- MCP 2026-07-28 changelog:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx
- oficjalny MCP Conformance Suite:
  https://github.com/modelcontextprotocol/conformance
- Tasks extension 2026-07-28:
  https://github.com/modelcontextprotocol/ext-tasks/blob/main/specification/2026-07-28/tasks.md
- MCP Python SDK roadmap:
  https://github.com/modelcontextprotocol/python-sdk/blob/main/ROADMAP.md

Najważniejsze fakty implementacyjne:

1. MCP 2026-07-28 jest stateless na poziomie protokołu; wersja i capabilities
   należą do każdej prośby w `_meta`.
2. `server/discover` zastępuje handshake dla nowej ery, ale server może nadal
   obsługiwać starsze rewizje jako dual-era.
3. `tools/list`, `resources/list`, `resources/read` i pozostałe cacheable
   results wymagają prawidłowego `ttlMs` oraz `cacheScope`.
4. Tasks są oficjalnym extension `io.modelcontextprotocol/tasks`, nie core.
5. Task IDs muszą mieć odpowiednią entropię, a **każde** `tasks/get`,
   `tasks/update` i `tasks/cancel` musi przejść authentication +
   authorization.
6. Task `input_required` używa `tasks/get -> inputRequests` oraz
   `tasks/update -> inputResponses`; nie jest tym samym co zwykły MRTR retry
   pierwotnego `tools/call`.
7. Frozen requirements conformance dla 2026-07-28 nie traktują extensions jako
   Tier-1-scored. Ponieważ Jaźń świadomie deklaruje Tasks, projekt musi mieć
   ostrzejszy gate niż upstream minimum.
8. MCP Python SDK v2 obsługuje core 2026-07-28, ale Tasks extension pozostaje na
   jego roadmapie. Dlatego v116 **nie może** usunąć własnego adaptera Tasks tylko
   dlatego, że transport HTTP przejdzie na oficjalny SDK.

## 4. Docelowa architektura po v116

```text
ChatGPT / Desktop / public MCP / Secure MCP Tunnel / local host
                         |
                         v
                 MCP / host adapters
                         |
                         v
                 ConversationRunner
                         |
                 TurnStateMachine
                         |
                 TurnOrchestrator
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
   MemoryPort        RoutingPort        AffectPort
       |                 |                  |
       +-----------+-----+------------------+
                   |
                   v
            ResponsePipeline
                   |
            ValidationPipeline
                   |
            FinalizationService
                   |
            Persistence / Audit
```

Koordynatory nie mogą dostawać całego `JaznEngine`, jeżeli potrzebują tylko
jednego wąskiego kontraktu.

## 5. Program implementacji

### Etap A — baseline, characterization i release checkpoint

Przed zmianą kodu:

1. rozwiązać finalny SHA zaakceptowanego v115;
2. sprawdzić `git status`, branch, HEAD, version i provenance;
3. wykonać komplet aktualnych v115 gate'ów;
4. zachować characterization tests dla:
   - direct registered MCP app,
   - public Streamable HTTP,
   - Secure MCP Tunnel,
   - local bounded fallback,
   - generate/resume/finalize,
   - Tasks working/completed/failed/cancelled/input_required;
5. utworzyć restore point;
6. podnieść wersję dopiero w pierwszym commicie implementacyjnym v116.

### Etap B — oficjalny MCP Conformance CI

Dodać osobny workflow, proponowana nazwa:

```text
.github/workflows/mcp-conformance.yml
```

Workflow ma:

1. używać Node.js 24 LTS;
2. instalować **przypiętą i przeglądniętą** wersję
   `@modelcontextprotocol/conformance`, nie ruchome `latest`;
3. uruchamiać Jaźń MCP na izolowanym loopback fixture;
4. wykonać frozen requirement gate:
   ```text
   npx @modelcontextprotocol/conformance server      --url http://127.0.0.1:<port>/mcp      --requirements 2026-07-28
   ```
5. uruchomić dodatkowy active-suite run dla rozszerzeń 2026-07-28;
6. nie stosować expected-failures do funkcji, które Jaźń deklaruje jako
   wspierane;
7. zachować raport jako CI artifact;
8. wykonywać gate na Linux i co najmniej jeden Windows job dla naszego
   transportu/bridge.

**Projektowy gate Tasks:** scenariusze Tasks mogą być upstreamowo
`extension/not_scored`, ale dla v116 ich failure ma blokować release, jeżeli
Jaźń reklamuje `io.modelcontextprotocol/tasks`.

### Etap C — Task principal ownership i autoryzacja

Aktualny losowy `taskId` pozostaje server-generated i nieprzewidywalny.
Dodatkowo trwały rekord ma dostać jawne ownership metadata bez przechowywania
tokenu:

```text
owner_subject
owner_transport
authorization_revision
```

Planowane zmiany:

- `latka_jazn/mcp/task_resume.py`
  - rozszerzyć `McpTaskRecord`;
  - rozszerzyć schema SQLite;
  - dodać migration z wersjonowaniem;
  - `create_or_get(..., owner_subject=..., owner_transport=...)`;
  - dodać subject-aware read/update/cancel;
- `latka_jazn/mcp/http_tasks_bridge.py`
  - przekazywać zweryfikowanego principal do każdej operacji taskowej;
  - odrzucać cross-principal access kodem autoryzacyjnym, bez ujawniania
    istnienia obcego taska;
- stdio/registered-app path
  - zachować osobny trusted-host identity contract;
  - nie mieszać public OAuth subject z lokalną tożsamością operatora.

Legacy rows bez `owner_subject` po migracji:

- nie są automatycznie przypisywane pierwszemu callerowi;
- public remote access fail-closed;
- ewentualna adopcja przez trusted local route musi być jawna, testowana i
  audytowana.

### Etap D — pełny task input transport

Obecne fail-closed `task_input_runtime_transport_not_implemented` ma zostać
zastąpione rzeczywistym kanałem runtime.

Wprowadzić wąski kontrakt, np.:

```python
class TaskInputGateway(Protocol):
    def submit_task_input(
        self,
        *,
        daemon_request_id: str,
        task_id: str,
        input_responses: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
```

Reguły:

1. `tasks/update` przyjmuje tylko klucze aktualnie występujące w
   `inputRequests`;
2. runtime musi potwierdzić przyjęcie inputu przed zwróceniem complete ACK;
3. oryginalna wiadomość użytkownika nie jest replayowana;
4. `request_id/turn_id/trace_id` pozostają te same;
5. task nie przechodzi z `input_required` do `working`, dopóki runtime nie
   potwierdzi wejścia;
6. generic telemetry nie zapisuje raw `inputResponses`; zapisuje co najwyżej
   bounded key-set, typ operacji, outcome i lineage;
7. duplicate `tasks/update` musi być idempotentny albo jednoznacznie
   odrzucony;
8. cancellation nie może udawać zatrzymania backendu bez potwierdzenia.

### Etap E — dependency inversion koordynatorów

Obecne moduły, które istnieją już jako seams, mają przestać przyjmować cały
`JaznEngine`, jeżeli nie jest on faktycznie ich kontraktem:

- `MemoryCoordinator`;
- `DialogueRouter`;
- `AffectCoordinator`;
- `ResponsePipeline`;
- `ValidationPipeline`;
- `TurnOrchestrator`.

Dodać wąskie porty/protokoły, np. pod:

```text
latka_jazn/core/ports/
    memory.py
    routing.py
    affect.py
    generation.py
    validation.py
    persistence.py
```

albo — jeżeli liczba typów pozostanie mała — w jednym
`latka_jazn/core/runtime_ports.py`.

Zasady:

- port opisuje capability, nie implementację;
- `RuntimeCompositionRoot` jest jedynym miejscem składania konkretnych usług;
- koordynator nie importuje `JaznEngine`;
- `JaznEngine` pozostaje czasową compatibility facade;
- żaden port nie przejmuje session/turn/finalization ownership;
- test architektoniczny ma wykrywać ponowne wprowadzenie forbidden imports.

### Etap F — kontrolowane rozbicie runtime_daemon.py

Nie wykonywać big-bang rewrite.

Pierwsza fala ekstrakcji:

```text
latka_jazn/core/runtime_daemon/
    models.py
    job_store.py
    process_control.py
    heartbeat.py
    security.py
    status.py
    handler.py
    client.py
    finalization_gate.py
```

Stary `latka_jazn/core/runtime_daemon.py` pozostaje compatibility facade
re-exportującą publiczne symbole do czasu zakończenia migracji.

Priorytet:

1. wyciągnąć pure models i serializację;
2. wyciągnąć job persistence;
3. wyciągnąć auth/security i HTTP helpers;
4. wyciągnąć status/heartbeat;
5. wyciągnąć process start/stop/status client;
6. wyciągnąć host-finalization queue/gate;
7. dopiero potem odchudzić handler/server.

### Etap G — usunięcie late monkey-patchingu

Obecny koniec `runtime_daemon.py` redefiniuje `write_json_atomic`, podmienia
`JaznDaemonHandler._json_response` i dynamicznie wrapuje status functions.

v116 ma zastąpić to jawnym przepływem:

```text
payload builder
-> sanitize_status_payload()
-> explicit serializer/response writer
```

oraz:

```text
start/status/stop
-> internal implementation
-> explicit sanitized public projection
```

Zakazane po exit-gate:

- redefinicja tej samej publicznej funkcji w dalszej części modułu;
- runtime assignment do metod klasy w celu zmiany canonical behavior;
- global wrapper injection zależny od import order.

Compatibility alias może istnieć tylko jawnie i mieć test.

### Etap H — optional capability CI

Dodać osobny gate dla:

```text
.[memory-cloud]
.[memory-cloud-server]
```

Minimalnie:

- Linux Python 3.12;
- Windows Python 3.12 tam, gdzie dependency jest wspierane;
- testy crypto/snapshot/cloud sync;
- import/probe bez sieci tam, gdzie test nie wymaga zewnętrznego backendu.

`2 skipped` z core suite z powodu braku PyNaCl nie jest błędem core, ale nie
może być jedyną weryfikacją memory-cloud.

### Etap I — Pyright zero-warning policy

Naprawić istniejący warning dotyczący dynamicznego `__all__` bez wyłączania
reguły globalnie.

Target:

```text
Pyright active tree:
errors   = 0
warnings = 0
```

Nie dodawać broad suppressions tylko dla osiągnięcia zera.

## 6. Testy wymagane przez v116

Nowe rodziny testów:

```text
tests/test_mcp_official_conformance_contract.py
tests/test_mcp_task_principal_binding.py
tests/test_mcp_task_cross_principal_denial.py
tests/test_mcp_task_input_transport.py
tests/test_mcp_task_input_idempotency.py
tests/test_runtime_dependency_inversion_contract.py
tests/test_runtime_daemon_facade_parity.py
tests/test_runtime_daemon_no_monkey_patch.py
tests/test_memory_cloud_optional_ci_contract.py
```

Do tego wszystkie istniejące:

- full deterministic pytest;
- compileall;
- full active-tree Pyright;
- route/no-silent-fallback audit;
- persistent runtime E2E Linux/Windows;
- Windows atomicity/timeout;
- clean package/release;
- Test Studio synchronization;
- release metadata sync.

## 7. Security acceptance

Release jest blokowany, jeżeli występuje którekolwiek z poniższych:

```text
task cross-principal read/update/cancel possible      FAIL
guessable task ids                                   FAIL
raw auth token persisted                             FAIL
raw task input leaked into generic telemetry         FAIL
task input ACK before runtime acceptance             FAIL
original user message replay during resume/input     FAIL
mid-turn route switch                                FAIL
accepted-visible text without finalization           FAIL
public status leaks local paths/PIDs/secrets          FAIL
```

## 8. Performance i obserwowalność

v116 nie optymalizuje przez zmianę języka.

Mierzyć przed/po:

- daemon startup/resume latency;
- per-turn latency;
- task poll overhead;
- SQLite task-store contention;
- memory recall latency;
- status endpoint latency;
- peak memory;
- liczba fallbacków i retry.

Ekstrakcja modułów ma zachować parity. Optymalizacja jest osobnym commitem i
wymaga benchmark evidence.

## 9. Rollback

Każda fala ekstrakcji musi zachowywać compatibility facade.

Rollback może przywrócić poprzedni wiring, ale nie wolno rollbackiem:

- osłabić task authorization;
- przywrócić replay;
- ominąć finalization;
- uznać niezweryfikowanego remote route za ready;
- wyłączyć provenance/identity gates.

## 10. Exit gate v116

```text
v115 acceptance baseline                               PASS
official MCP requirements 2026-07-28                  PASS
Jaźń-claimed Tasks conformance                         PASS
task principal isolation                               PASS
task input_required -> tasks/update -> runtime         PASS
no original-message replay                             PASS
coordinators no longer depend on whole JaznEngine      PASS
runtime_daemon compatibility facade parity             PASS
late monkey-patching on canonical daemon path          0
memory-cloud optional capability CI                    PASS
compileall                                             PASS
Pyright errors                                         0
Pyright warnings                                       0
full deterministic pytest                              PASS
persistent-runtime E2E Linux/Windows                   PASS
Windows atomicity/timeouts                             PASS
release-hardening                                      PASS
manifest/provenance sync                               PASS
clean release package                                  PASS
```

## 11. Kolejność commitów implementacyjnych

Preferowana sekwencja:

1. `release: advance Jaźń to v16.3.25.5.116`
2. `test: add official MCP conformance gate`
3. `security: bind durable MCP tasks to authenticated principals`
4. `feat: route task input responses into canonical runtime`
5. `refactor: introduce narrow runtime service ports`
6. `refactor: detach coordinators from JaznEngine`
7. `refactor: extract daemon models and durable job store`
8. `refactor: extract daemon security status and client surfaces`
9. `refactor: remove daemon late monkey patching`
10. `ci: verify optional memory cloud capabilities`
11. `fix: close active-tree Pyright warning`
12. `release: synchronize v116 metadata and closeout evidence`

Każdy commit musi przechodzić targeted tests; szeroki suite jest obowiązkowy
przed oznaczeniem release candidate.

## 12. Granica końcowa

v116 ma uczynić Jaźń **łatwiejszą do zweryfikowania i utrzymania**, nie bardziej
skomplikowaną. Sukcesem nie jest liczba nowych klas, tylko:

- mniejszy zakres zależności;
- jawny ownership;
- zgodny protokół;
- bezpieczne durable Tasks;
- brak magicznego import-order behavior;
- mierzalne CI evidence.
