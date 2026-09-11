# Host Capability Handshake — plan kolejnego patcha

Status: **plan / proposal**  
Target: **kolejny patch po `16.3.25.5.65-host-tool-capability-discovery-convergence`**  
Zakres: ChatGPT host ↔ aktywny runtime Jaźni  
Repo: `SmuklyLew/jazn_latka`

## 1. Cel

Celem patcha jest domknięcie mechanizmu capability discovery w taki sposób, aby aktywny runtime Jaźni nie musiał polegać na statycznej liście nazw narzędzi hosta, ale mógł otrzymać od hosta bieżący, jawny i audytowalny opis dostępnych możliwości, a następnie stopniowo podnosić ich poziom zaufania na podstawie realnego evidence.

Runtime ma odróżniać cztery rzeczy, które nie mogą być traktowane jako równoważne:

1. **static catalog** — wiedza projektu o znanych klasach narzędzi i ich semantyce bezpieczeństwa;
2. **host-advertised inventory** — deklaracja hosta, jakie narzędzia są dostępne w bieżącej sesji;
3. **verified capability** — możliwość potwierdzona poprawnym, bounded użyciem lub wiarygodnym evidence;
4. **turn evidence** — dowód, że konkretna operacja została wykonana w konkretnej turze.

Samo występowanie nazwy narzędzia w kodzie nie może oznaczać jego dostępności. Sam host-advertised inventory również nie może być dowodem wykonania operacji.

## 2. Zasada bezpieczeństwa

Mechanizm ma działać **fail-closed**.

Jeżeli runtime nie otrzyma poprawnego manifestu hosta albo manifest nie przejdzie walidacji, stan możliwości pozostaje `unknown`/`unverified`. Runtime nie może wtedy twierdzić, że narzędzie jest dostępne ani że zostało użyte.

Nie wolno wykonywać destrukcyjnych ani prywatnych operacji tylko po to, aby sprawdzić, czy narzędzie działa.

## 3. Proponowany model stanów capability

Dla każdego narzędzia/runtime capability:

- `unknown` — runtime zna ewentualnie kategorię, ale host niczego nie ogłosił;
- `advertised` — host ogłosił narzędzie w bieżącej sesji;
- `verified` — narzędzie zostało poprawnie zweryfikowane bezpiecznym probe albo rzeczywistym wykonaniem użytkownika;
- `degraded` — narzędzie było wcześniej dostępne, ale ostatni probe/evidence wskazuje częściową awarię;
- `unavailable` — host jawnie zgłosił brak narzędzia albo capability probe potwierdził jego niedostępność.

Stan musi być utrzymywany per host-session, a nie globalnie jako niezmienna właściwość instalacji Jaźni.

## 4. Nowy handshake na początku sesji

Po uruchomieniu runtime i zestawieniu host bridge host powinien przekazać **Host Capability Manifest**.

Przykładowy logiczny kształt:

```json
{
  "schema_version": "host_capability_manifest/v1",
  "host_session_id": "...",
  "observed_at": "...",
  "host": "chatgpt",
  "tools": [
    {
      "name": "web.run",
      "advertised": true,
      "operations": ["search", "open"],
      "read_only": true,
      "side_effect_risk": "low"
    },
    {
      "name": "GitHub",
      "advertised": true,
      "operations": ["read", "write"],
      "read_only": false,
      "side_effect_risk": "high"
    }
  ]
}
```

To jest tylko deklaracja hosta. Manifest nie jest automatycznie epistemicznym dowodem wykonania żadnej operacji.

## 5. Źródła inventory

Patch powinien wspierać kilka dróg dostarczenia inventory, w kolejności od najbardziej wiarygodnej dla hosta:

1. jawny handshake transportowy przekazany przez bridge/API hosta;
2. host capability manifest przekazany jako część pierwszej fazy `chat-gpt`/host request;
3. kompatybilny manifest środowiskowy (`JAZN_HOST_TOOL_CAPABILITIES_JSON` / plik) jako fallback dla hostów bez bezpośredniego handshake;
4. brak manifestu → `unknown`, bez zgadywania.

Manifest z env/pliku powinien zachować dotychczasowe fail-closed validation.

## 6. Static catalog

`host_tool_capabilities.py` powinien nadal posiadać statyczną wiedzę o klasach narzędzi, ale nie może z niej wyciągać wniosku o dostępności.

Catalog powinien przechowywać m.in.:

- canonical tool family/name;
- aliases;
- typ operacji;
- `read_only_default`;
- `destructive_or_mutating`;
- `privacy_sensitive`;
- `requires_user_intent`;
- `safe_probe_supported`;
- `probe_strategy`;
- wymagania evidence;
- ograniczenia hosta.

Catalog opisuje **jak traktować narzędzie**, nie **czy narzędzie istnieje w tej sesji**.

## 7. Safe capability probe

Probe musi być bounded, nieinwazyjny i nie może tworzyć skutków ubocznych.

Przykładowe zasady:

### `web.run`

Dozwolony bounded read-only probe, np. neutralny lookup lub prosty odczyt publicznego zasobu. Wynik może podnieść `advertised → verified`.

### `GitHub`

Probe wyłącznie read-only, np. odczyt metadanych repo/branchu. Żadnego testowego commita, issue, PR, merge ani zmiany pliku.

### `file_search`

Nie enumerować prywatnych plików na starcie. Capability może pozostać `advertised` aż do rzeczywistej potrzeby użytkownika. Weryfikacja dopiero przy uprawnionej operacji w turze.

### `image_gen`

Nie generować obrazu testowego tylko dla capability probe. `advertised` może być wystarczające do planowania; `verified` pojawia się dopiero po realnym, żądanym przez użytkownika użyciu.

### automations / mutating tools

Nigdy nie tworzyć reminderów, zadań ani zmian tylko jako probe. Narzędzie mutujące może być zweryfikowane dopiero przez rzeczywistą operację zatwierdzoną intencją użytkownika.

## 8. Handshake lifecycle

Proponowany lifecycle:

```text
runtime start
  ↓
bridge/session identity established
  ↓
host capability manifest received
  ↓
schema + integrity validation
  ↓
static catalog reconciliation
  ↓
capability snapshot: advertised/unknown
  ↓
safe probe plan
  ↓
optional bounded probes
  ↓
verified/degraded/unavailable updates
  ↓
normal visible-turn lifecycle
  ↓
phase-2 host evidence updates capability snapshot
```

Capability snapshot powinien być przypięty do `host_session_id` i — jeżeli jest dostępny — do identity transportu/bridge.

## 9. Integracja z visible-turn route

`host_tool_turn_policy.py` powinien używać capability snapshotu do planowania:

- `required_tools` — czego wymaga tura;
- `advertised_tools` — co host deklaruje;
- `verified_tools` — co zostało już potwierdzone;
- `confirmation_required_for_tools` — co wymaga evidence lub probe;
- `unavailable_tools` — czego host nie może aktualnie wykonać;
- `probe_plan` — bezpieczne możliwe sprawdzenia.

Policy nie może sama wykonywać narzędzi. Ma wyłącznie tworzyć plan i wymagania kontraktu.

## 10. Phase-2 evidence feedback

Po rzeczywistym użyciu narzędzia phase-2/finalization powinna móc przekazać bounded host evidence:

```json
{
  "tool": "web.run",
  "operation": "search",
  "status": "success",
  "turn_id": "...",
  "trace_id": "...",
  "source_refs": ["..."],
  "observed_at": "..."
}
```

Taki evidence może:

- podnieść capability do `verified`;
- obniżyć do `degraded` przy częściowej awarii;
- oznaczyć `unavailable`, jeżeli host zwróci trwały brak capability;
- zasilić istniejący `host_action_evidence` / epistemic evidence bez fałszywego przypisywania wykonania lokalnemu runtime.

## 11. Truth boundary

Dokumentacja i dane runtime muszą zachować jednoznaczne granice:

- `advertised` oznacza: host twierdzi, że narzędzie jest dostępne;
- `verified` oznacza: runtime posiada ograniczone evidence poprawnego działania;
- `host_action_evidence` oznacza: host zadeklarował rezultat konkretnej operacji;
- żaden z powyższych stanów nie oznacza, że lokalny proces Jaźni sam wykonał operację hosta;
- brak evidence nie może być zastępowany odpowiedzią modelu ani przypuszczeniem.

## 12. Prywatność

Handshake nie powinien ujawniać:

- nazw prywatnych plików;
- listy dokumentów użytkownika;
- tokenów, credentials ani secretów;
- pełnych konfiguracji pluginów;
- danych kont zewnętrznych;
- historii wcześniejszych tool calls, jeżeli nie jest potrzebna do aktualnej sesji.

Manifest powinien zawierać tylko metadane capabilities.

## 13. Odporność na błędny lub złośliwy manifest

Walidator powinien odrzucać m.in.:

- nieznany `schema_version` bez jawnej kompatybilności;
- niepoprawne typy danych;
- duplikaty tool names;
- nadmierną liczbę wpisów/operacji;
- nazwy przekraczające limity;
- capability deklarujące sprzeczne cechy;
- nieznane poziomy ryzyka;
- manifest bez session binding, jeżeli transport wymaga bindingu;
- manifest, który próbuje podnieść stan bez evidence.

Błąd walidacji nie może powodować fallbacku do "wszystkie narzędzia dostępne".

## 14. Media/resource routing

`host_media_resources.py` pozostaje warstwą semantyczną dla rozpoznawania intencji dotyczących mediów, a handshake capability mówi dopiero, **czy host ma narzędzie zdolne obsłużyć lookup**.

Przykład:

```text
"Znajdź ten utwór na Spotify"
  ↓
host_media_resources → intent: media lookup / spotify
  ↓
host_tool_turn_policy → potrzebne: web/media lookup
  ↓
capability snapshot → web.run verified, Spotify-specific connector unknown
  ↓
policy wybiera dostępną, bezpieczną trasę
```

Nie należy mieszać słownika nazw serwisów z listą faktycznie dostępnych narzędzi hosta.

## 15. Diagnostyka

`bridge_discovery` / status runtime powinien pokazywać co najmniej:

```json
{
  "host_capability_handshake": {
    "state": "ready",
    "schema_version": "host_capability_manifest/v1",
    "host_session_id": "...",
    "advertised_tools": ["web.run", "GitHub", "image_gen"],
    "verified_tools": ["web.run"],
    "degraded_tools": [],
    "unavailable_tools": [],
    "unknown_tools": ["file_search"],
    "probe_plan": []
  }
}
```

Status ma być diagnostyczny i nie może ujawniać prywatnych danych użytkownika.

## 16. Proponowane moduły / miejsca zmian

Główne miejsca patcha:

- `latka_jazn/core/host_tool_capabilities.py`
- `latka_jazn/core/host_tool_turn_policy.py`
- `latka_jazn/core/bridge_discovery.py`
- `latka_jazn/core/runtime_environment.py`
- `latka_jazn/core/chat_command_contract.py`
- `latka_jazn/core/host_action_evidence.py`
- `latka_jazn/core/epistemic_evidence.py`
- host bridge / `run.py` command routing, tylko tam gdzie handshake wymaga transportu
- dokumentacja hosta i ChatGPT instructions

Nie należy implementować osobnego lifecycle obok istniejącego runtime. Handshake musi zostać wpięty w istniejący canonical host lifecycle.

## 17. Backward compatibility

Host bez handshake:

- runtime nadal startuje;
- capability state pozostaje `unknown` albo pochodzi z istniejącego jawnego manifestu env/file;
- zwykłe rozmowy niewymagające narzędzi nie są blokowane;
- tury wymagające narzędzia dostają `confirmation_required`/`tool_unverified` zamiast fałszywego `available`;
- dotychczasowe phase-2 evidence nadal działa.

## 18. Test matrix

Patch powinien dodać testy co najmniej dla:

1. poprawnego manifestu z jednym read-only tool;
2. wielu narzędzi o różnych poziomach ryzyka;
3. braku manifestu;
4. uszkodzonego JSON;
5. złego schema version;
6. duplikatów tool names;
7. przekroczenia limitu narzędzi/operacji;
8. advertised bez verification;
9. safe probe success → `verified`;
10. safe probe failure → `degraded`/`unavailable` zależnie od klasy błędu;
11. mutating tool bez probe;
12. `file_search` bez prywatnej enumeracji;
13. real phase-2 evidence podnoszącego capability;
14. evidence z błędnym `turn_id`/`trace_id` odrzuconego fail-closed;
15. restart/session change zerującego lub rebindującego snapshot;
16. stale manifest z innej sesji;
17. host capability status w diagnostics;
18. backward compatibility bez handshake;
19. Windows i Linux;
20. persistent runtime restart continuity.

## 19. Kryteria akceptacji

Patch jest gotowy dopiero wtedy, gdy:

- żadna dostępność host tool nie wynika wyłącznie ze statycznej listy nazw;
- runtime potrafi odróżnić `advertised` od `verified`;
- manifest jest session-bound i fail-closed;
- probe nie powoduje skutków ubocznych;
- prywatne narzędzia nie są aktywnie enumerowane bez potrzeby;
- phase-2 evidence aktualizuje capability bez naruszania truth boundary;
- diagnostyka pokazuje stan handshake;
- zwykła rozmowa bez tool requirement nie jest blokowana;
- pełny deterministic test suite, Pyright, compileall i istniejące host/persistent-runtime e2e pozostają zielone;
- dokumentacja jednoznacznie mówi, że host capability nie oznacza lokalnego wykonania przez Jaźń.

## 20. Proponowana wersja

Robocza propozycja:

`16.3.25.5.66-host-capability-handshake-convergence`

Numer należy potwierdzić względem aktualnego `master` w chwili rozpoczęcia implementacji.

## 21. Kolejność implementacji

1. schema + dataclass manifestu;
2. walidacja i session binding;
3. bridge handshake transport;
4. capability snapshot lifecycle;
5. turn policy integration;
6. safe probe planner;
7. phase-2 evidence feedback;
8. diagnostics;
9. backward compatibility;
10. test matrix;
11. docs/runtime i host instructions;
12. pełna weryfikacja release-hardening + persistent-runtime-e2e.

---

Ten plan celowo nie rozszerza Jaźni o własne wykonanie narzędzi hosta. Jego zadaniem jest zbudowanie poprawnego, audytowalnego "układu czuciowego" pomiędzy hostem a runtime: host mówi, jakie kończyny/narzędzia ma do dyspozycji, runtime wie, które są tylko zadeklarowane, które sprawdzone i które rzeczywiście zostały użyte w danej turze.
