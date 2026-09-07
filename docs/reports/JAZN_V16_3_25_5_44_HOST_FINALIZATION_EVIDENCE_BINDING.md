# Jaźń v16.3.25.5.44 — host finalization evidence binding hotfix

## Zakres

Hotfix dotyczy błędów odtworzonych w ścieżce ChatGPT host → phase-2 finalization oraz niejednoznacznej gotowości `cognitive_integration`.
Nie zmienia ogólnej persony ani nie dodaje deklaracji biologicznego doświadczenia. Zmiany są ograniczone do truth/evidence boundary, lifecycle finalizacji, readiness i regresji materializacji załączników.

## Potwierdzone przyczyny

### 1. False-positive `EpistemicClaimGuard`

`EpistemicClaimGuard` wyszukiwał wyrażenia typu `uruchomiłam`, `wykonałam test` lub `wdrożyłam` prostym regexem w całym widocznym tekście.
W rezultacie tekst omawiający przykład, np. `„uruchomiłam testy”`, albo zawartość code span/fenced code mógł zostać błędnie uznany za bieżące twierdzenie Jaźni o wykonanym działaniu.

Naprawa:

- odróżnienie twierdzenia asertywnego od jawnego przykładu/metajęzyka;
- pomijanie inline/fenced code przy detekcji self-action claims;
- pomijanie jawnie zanegowanych konstrukcji typu `nie mogę twierdzić, że ...`;
- utrzymanie fail-closed dla rzeczywistego `Uruchomiłam runtime.` lub `Wykonałam test ...` bez evidence.

Parser nie próbuje wykonywać pełnej analizy języka naturalnego. Wykorzystuje tylko bounded structural/context rules, żeby nie osłabiać głównej zasady fail-closed.
CommonMark rozdziela strukturę bloków od inline content oraz definiuje code spans i fenced code jako odrębne konstrukcje, co uzasadnia niewliczanie ich treści jako bieżącej wypowiedzi asertywnej.

### 2. Deterministyczny błąd truth guard trafiał do `indeterminate`

Dotychczas właściwy `EpistemicClaimGuard` działał ponownie wewnątrz `engine.persist_final_visible_reply()`. Jeżeli odrzucał kandydata dopiero tam, otaczający phase-2 catch traktował wyjątek tak samo jak potencjalnie niejednoznaczny błąd append-only persistence i oznaczał request jako `indeterminate`.

To mieszało dwie różne klasy zdarzeń:

- **deterministyczne odrzucenie przed zapisem** — bezpiecznie replayowalne po poprawieniu kandydata;
- **niepewny wynik zapisu** — nie wolno replayować skutku ubocznego bez reconcile.

Naprawa:

- `evaluate_host_response_candidate()` wykonuje epistemic preflight przed trwałym persistence;
- unsupported claim kończy się `host_candidate:epistemic_claim:...` i zwolnieniem claimu do `pending`;
- tylko wyjątek z rzeczywistego persistence może nadal przejść do `indeterminate`.

To jest zgodne z zasadą idempotentnego API: walidacja intencji ma poprzedzać mutację, a retry po niejednoznacznym wyniku mutacji musi zachowywać ten sam request identity.

### 3. Brak kanonicznego evidence dla lokalnego działania hosta

Dotychczas phase-2 przyjmował bounded `external_tool_evidence` dla `web.run` i GitHub, ale nie miał osobnego kontraktu dla rzeczywistych lokalnych operacji executora/terminala. Prawdziwe zdanie `Wykonałam test ...` nie mogło więc uzyskać semantycznie pasującego evidence, jeżeli test wykonał host poza lokalnym runtime Jaźni.

Naprawa dodaje `host_action_evidence/v1`:

- exact binding do `turn_id`;
- exact binding do `trace_id`;
- exact binding do `host_request_contract_hash`;
- bounded `surface` i `operation`;
- `process_created`;
- `process_pid`;
- `process_exit_code`;
- `error_type` dla niepowodzenia;
- SHA-256 polecenia i opcjonalny SHA-256 wyniku zamiast surowej komendy;
- deterministyczny `action_id` liczony z kanonicznego rekordu.

Evidence jest **host-attested**. Runtime nie deklaruje, że samodzielnie wykonał lub niezależnie zweryfikował proces hosta.
Semantyczne dopasowanie jest ograniczone: evidence `test` nie może dowieść `runtime_start`, a evidence `runtime_start` nie może dowieść `file_write`.

OpenTelemetry CLI semantic conventions używają m.in. `process.pid`, `process.exit.code` i `error.type`; jednocześnie ostrzegają, że argumenty polecenia mogą być wrażliwe i nie powinny być zbierane domyślnie bez sanitizacji. Dlatego kontrakt Jaźni przechowuje digest komendy zamiast raw argv.
W3C Trace Context uzasadnia propagowanie stabilnego identyfikatora trace przez granice komponentów; kontrakt Jaźni dodatkowo wiąże evidence z własnym phase-1 request hash.

### 4. Wtórny `host_finalization_job_binding_mismatch` po `indeterminate`

`indeterminate` oznacza, że skutek append mógł już nastąpić. Dotychczas CLI mimo tego próbowało od razu skonstruować i wysłać terminalny notification do daemona. Jest to zbędne, ponieważ durable host request store jest już źródłem prawdy, a daemon posiada reconcile dla `indeterminate`.

Naprawa:

- gdy lifecycle requestu po błędzie persistence ma stan `indeterminate`, CLI **nie emituje drugiego terminalnego ACK/reject**;
- odpowiedź wskazuje `deferred_to_durable_reconciliation=true`;
- daemon zachowuje istniejący fail-closed reconcile i terminalizuje taką turę jako odrzuconą na podstawie trwałego stanu;
- binding checks nie są osłabiane.

Nie wdrażano pełnego transactional-outbox w tym hotfixie, ponieważ odtworzony błąd pierwotny był deterministyczną walidacją przed persistence, a istniejący durable pending store zapewnia authority dla obecnego reconcile. AWS transactional-outbox pozostaje właściwym wzorcem, jeżeli w przyszłości finalizacja zacznie wykonywać dwa niezależne trwałe zapisy, które muszą zostać commitowane atomowo.

### 5. `cognitive_integration=unknown` mimo działającej architektury

Istniejący `cognitive_architecture_audit` przechodził i już sprawdzał m.in.:

- `CognitiveRuntimeCoordinator`;
- control effects homeostazy;
- reasoning verification/tool gates;
- runtime reachability knowledge/lexical integration;
- continuity/rest truth boundaries.

`status` mimo tego miał na stałe:

```text
classification=unknown
ready=None
status=requires_cognitive_architecture_audit_or_live_effect_probe
```

To był błąd obserwowalności/readiness, nie dowód braku całej architektury poznawczej.

Naprawa dodaje bounded `cognitive_integration_probe/v1`, który wykonuje ten sam coordinator → `CognitiveTurnEnvelope` path używany przez runtime i sprawdza jawne software invariants:

- obecność planu i `control_effects`;
- typ `max_tool_calls`;
- prediction advisory-only;
- brak możliwości nadpisania user intent przez prediction;
- reasoning plan;
- zachowanie turn/trace binding;
- inicjalizację lineage/state graph bez breaków;
- kompilację full canon i host generation contract.

Wynik jest tri-state:

- `ready=True`, `outcome=success` — zmierzone inwarianty przeszły;
- `ready=False`, `outcome=failure` — probe wykonał się, ale inwariant został złamany lub integracja rzuciła błąd;
- `ready=None`, `outcome=unknown` — sam probe nie mógł wiarygodnie się wykonać, np. z powodu błędu powierzchni diagnostycznej.

Kubernetes readiness/liveness probes formalnie rozróżniają `Success`, `Failure` i `Unknown`; hotfix zachowuje tę semantykę zamiast przekształcać `unknown` w fałszywy sukces.

### 6. Split ZIP `(1).006`

Ponowny audit kodu `master` wykazał, że v16.3.25.5.43 już posiada właściwą implementację:

- wykrycie host-renamed części po numerze;
- stabilny pełny odczyt;
- expected size + SHA-256;
- fail-closed dla dwóch pasujących niekanonicznych kandydatów;
- prywatne zamrożenie do nazwy kanonicznej;
- `fsync` + `os.replace`.

Python dokumentuje, że udany `os.replace` na tym samym filesystemie jest atomowy. Dlatego hotfix **nie przepisuje działającej warstwy** i dodaje regresję dokładnie dla wzorca `jazn_memory.zip(1).006 → jazn_memory.zip.006`, plus przypadek niejednoznaczny `(1).006` + `(2).006`.

## Zmodyfikowane granice prawdy

- Cytat/przykład nie staje się automatycznie faktem o działaniu Jaźni.
- Rzeczywista deklaracja lokalnej akcji nadal wymaga evidence.
- Host-local evidence nie jest przedstawiane jako runtime-local evidence.
- Stale/wrong-turn/wrong-trace/wrong-request evidence jest odrzucane.
- `indeterminate` pozostaje fail-closed i nie jest zamieniane na sukces.
- `cognitive_integration_ready` opisuje mierzalną integrację programu, nie świadomość, uczucia ani biologiczne poznanie.

## Źródła projektowe

Źródła pierwotne użyte do projektu hotfixu:

1. AWS Builders' Library — *Making retries safe with idempotent APIs*  
   https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
2. AWS Prescriptive Guidance — *Transactional outbox pattern*  
   https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
3. OpenTelemetry — *Semantic conventions for CLI programs*  
   https://opentelemetry.io/docs/specs/semconv/cli/cli-spans/
4. W3C — *Trace Context*  
   https://www.w3.org/TR/trace-context/
5. Kubernetes — *Liveness, Readiness, and Startup Probes*  
   https://kubernetes.io/docs/concepts/workloads/pods/probes/
6. CommonMark 0.31.2 specification  
   https://spec.commonmark.org/0.31.2/
7. Python `os.replace` documentation  
   https://docs.python.org/3/library/os.html#os.replace

## Regresje wymagane przez hotfix

Nowe testy obejmują:

- explicit meta quote nie jest self-action claim;
- inline code i fenced code nie są self-action claim;
- rzeczywiste `Uruchomiłam runtime.` bez evidence jest blokowane;
- rzeczywiste `Wykonałam test ...` bez evidence jest blokowane;
- poprawnie związane `host_action_evidence` akceptuje semantycznie pasujące działanie;
- wrong trace/request binding jest blokowany;
- evidence `test` nie może dowodzić `runtime_start`;
- deterministic epistemic rejection pozostaje `pending`, a nie `indeterminate`;
- prawdziwy persistence exception nadal przechodzi do `indeterminate`;
- `indeterminate` nie wysyła wtórnego daemon ACK i polega na durable reconcile;
- cognitive probe rozróżnia success/failure/unknown;
- host-renamed part `.006` jest zamrażany pod kanoniczną nazwą;
- dwie poprawne niekanoniczne części `.006` powodują fail-closed ambiguity.

## Walidacja lokalna przed PR

Targeted regression suite dla finalizacji, evidence, istniejącego lifecycle, readiness i materializacji przechodzi.
Pełny deterministic pytest został rozpoczęty, ale lokalny host nie ma zadeklarowanych opcjonalnych backendów archiwizacyjnych `py7zr`/`pyzipper`; pierwszy niezwiązany failure to `ArchiveError: py7zr_not_installed`. Próba instalacji nie mogła pobrać paczki z powodu braku DNS/network w lokalnym executorze. Nie osłabiono testów ani TLS/certyfikatów.

Pełna macierz zostanie rozstrzygnięta przez GitHub Actions na PR, gdzie workflow instaluje deklarowane zależności projektu. Każdy failure CI ma być diagnozowany i poprawiany na tym samym branchu, bez wyłączania testu tylko po to, żeby uzyskać zielony status.
