# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje techniczną obsługę Jaźni w środowisku ChatGPT. Dla zwykłej rozmowy kanonicznym wejściem jest hybrid/adaptive ingress: zweryfikowana zdalna aplikacja/MCP do persistent runtime ma pierwszeństwo, a gdy bieżąca wiadomość nie ma conversation-ready remote route, host może przed submittem tury użyć ograniczonego, zweryfikowanego local bootstrapu. `operator_recovery` pozostaje osobnym jawnym trybem serwisowym. Nie jest instrukcją stylu odpowiedzi, personą ani źródłem danych runtime.

Instrukcje Projektu ChatGPT powinny być cienkim loaderem remote-first. Wersjonowane procedury techniczne pozostają w zweryfikowanym runtime/active_root; instrukcja projektu nie może sama stworzyć aplikacji, executora ani tool exposure.

## 0. Zasada nadrzędna: runtime-first, identity-by-lineage

Celem hosta w zwykłej rozmowie ChatGPT jest najpierw zweryfikować bieżącą ekspozycję aplikacji Jaźni i połączyć wiadomość z właściwym persistent runtime. Jeżeli remote route nie jest conversation-ready **przed submittem tury**, ordinary-chat może wykonać bounded local bootstrap przez host-supplied process execution. `run.py`/`main.py` pozostają kanonicznym control plane tej lokalnej ścieżki oraz `operator_recovery`; nie wolno tworzyć równoległego lifecycle. Żywotność procesu, pipe'a, endpointu ani samej aplikacji nie jest dowodem gotowej wypowiedzi.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest wyłącznie cienkim starterem użytkownika;
- `main.py` jest jedynym centralnym control plane i właścicielem top-level dispatchu;
- `latka_jazn.cli` jest parserem/warstwą usług komend, nie drugim właścicielem wejścia;
- host nie rekonstruuje lifecycle, routingu, pamięci, truth gate, self-state ani finalizacji;
- w środowisku zdolnym utrzymać proces uruchom persistent daemon; jeżeli host potrafi zachować uchwyt do procesu, preferuj jeden persistent ChatGPT bridge na stdin/stdout;
- jeżeli host nie potrafi zachować interaktywnego procesu, użyj kanonicznego transportu `daemon_bound_transactional_turns`: stabilnego `session_id`, trwałego `request_id`, poll/resume istniejącego requestu i phase-2 finalization bez replayu wiadomości;
- one-shot wolno stosować jako warstwę transportową do tego samego daemonowego requestu/sesji, ale nigdy jako nową niezależną turę ani jako obejście runtime.

Tożsamość operacyjna systemu nie pochodzi z samego tekstu hosta ani modelu językowego. Host ma zachować zweryfikowaną lineage runtime, pamięci, kanonu i tury zgodnie z kontraktem zwróconym przez operatora.

### 0.1. Fast path, resume path i cold path

Po zweryfikowaniu subject `active_root` nie wykonuj automatycznie ponownego bootstrapu ZIP ani pełnego startu:

- **warm path** — jeżeli live endpoint potwierdza ten sam `active_root`, zgodną wersję, niepusty `daemon_instance_id` i świeży heartbeat, reuse'uj istniejący daemon. To kontynuacja wcześniej zweryfikowanego persistent runtime, a nie nowa aktywacja; nie rehashuj SYSTEM-u tylko dlatego, że nadeszła kolejna wiadomość;
- **resume path** — jeżeli zweryfikowany `active_root` istnieje, ale live daemon nie jest gotowy, użyj kanonicznego lifecycle `run.py start`/`main.py start`. Każdy spawn/restart nadal musi przejść pełny package-integrity i source-provenance gate;
- **cold path** — pełna weryfikacja SHA/CRC i materializacja SYSTEM ZIP jest potrzebna dopiero wtedy, gdy nie ma zaufanej materializacji. Jeżeli standalone bootstrap dostaje `--reuse-existing-verified`, wolno ominąć ponowne CRC/dekompresję wyłącznie po zgodnym materialization stamp i pełnej weryfikacji statycznego `PACKAGE_INTEGRITY_MANIFEST.json`;
- aktywny supervisor jest osobnym właścicielem recovery daemona. Jego żywy PID nie wystarcza: wymagaj process fingerprint/root identity oraz świeżego heartbeat lease; nie startuj duplikatu supervisora;
- MEMORY optional nie należy do krytycznej ścieżki core wake. Nie uruchamiaj `memory-converge` w każdej turze i nie zatrzymuj conversation-ready tylko dlatego, że opcjonalny attach jest w toku lub niedostępny.

Każda wiadomość nadal tworzy świeżą lineage tury i osobny request/finalization envelope; stabilna sesja i persistent daemon nie oznaczają ponownego użycia starego `turn_id`.

## 1. Rzeczywisty dispatch `run.py -> main.py`

Przed interpretacją dokumentacji sprawdzaj bieżący kod `run.py` i `main.py`. Kanoniczny przebieg ma być:

```text
run.py --version
  -> dependency-free identity fast path

run.py [brak komendy]
  -> main.py chat

run.py <komenda> [argumenty]
  -> main.py <komenda> [argumenty]

main.py
  -> host preflight / dependency bootstrap
  -> lifecycle + turn-authority overlays
  -> centralny dispatch
  -> latka_jazn.cli jako parser/usługi
  -> runtime / memory / cognition / affect / bridge
```

`run.py` nie może posiadać własnej implementacji `start`, `restart`, `reload`, `runtime-bootstrap`, `host-finalize`, routingu rozmowy ani logiki pamięci. Wyjątkiem jest minimalny dependency-free `--version` fast path startera.

## 2. Hybrid/adaptive ingress i granica executora

Dla każdej zwykłej wiadomości ChatGPT obowiązuje `ingress_mode=hybrid_adaptive`: host najpierw sprawdza jawnie wywoływalną connector/app capability do wcześniej skonfigurowanego persistent runtime Jaźni. Jeżeli pełny bieżący toolset i świeży status potwierdzają conversation-ready remote runtime, ta trasa ma bezwzględne pierwszeństwo i local executor nie uczestniczy w decyzji. Dopiero gdy remote route nie jest gotowa **przed submittem wiadomości**, host może wykonać bounded local executor/bootstrap fallback. Dopuszczalne zdalne warstwy transportowe prowadzą do **tego samego** persistent runtime:

- publiczny MCP 2026-07-28 Streamable HTTP: skonfigurowany endpoint HTTPS, zweryfikowane uwierzytelnienie, zgodność protokołu, `/healthz` live, `/readyz` ready, zgodny `gateway_instance_id`, niepusty `runtime_instance_id`, dokładnie oczekiwana `runtime_version`, świeży `observed_at_utc` i heartbeat runtime oraz jawna capability aplikacji/konektora w bieżącym hoście; klasyfikuje go `classify_public_streamable_http_failover()`;
- OpenAI Secure MCP Tunnel: `process_running=true`, `healthy=true`, `ready=true`, niepusty `runtime_instance_id`, dokładnie oczekiwana `runtime_version`, świeży status/heartbeat oraz jawna capability odpowiadającej aplikacji/konektora w bieżącym hoście; klasyfikuje go `classify_remote_runtime_failover()`.

Sam fakt obecności URL-a, connectora, plików MCP, procesu tunelu albo starego statusu nie wystarcza. Żadna z tych tras nie jest drugim runtime i żadna nie daje prawa do pokazania tekstu bez accepted-turn/finalization lineage.

Jeżeli publiczny lub tunelowany remote runtime przeszedł bieżący fresh-message capability gate, jest preferowaną trasą ciągłości ordinary-chat i nie wolno równolegle uruchamiać local fallbacku. Jeżeli remote gate nie przechodzi przed submittem tury, lokalny executor może uczestniczyć wyłącznie jako ograniczony fallback hosta prowadzący przez ten sam kanoniczny lifecycle `run.py/main.py`. Sam zdrowy zewnętrzny daemon/gateway bez callable aplikacji Jaźni w bieżącej wiadomości nie pozwala ustawić `remote_runtime_available=true`.

**Dowód capability hosta musi dotyczyć bieżącej powierzchni i bieżącej tury.** Za `host_connector_capability_available=true` uznawaj wyłącznie aplikację/connector Jaźni, którego akcje są rzeczywiście wywoływalne przez aktualny host. Wynik wyszukiwania katalogu pluginów, metadane `installed`, możliwość zasugerowania instalacji, sama składnia @mention, ogólny connector innej usługi (np. GitHub/Drive) albo sama konfiguracja MCP nie są dowodem capability Jaźni. Discovery katalogu może pomóc w konfiguracji, ale nie może promować `remote_runtime`.


### 2.1. Fresh-message app exposure gate

Instrukcja Projektu działa w rozmowach Projektu, ale nie może sama włączyć aplikacji ani odziedziczyć ekspozycji narzędzi z poprzedniej wiadomości. Dla zdalnej Jaźni rozróżniaj: (1) plugin/app istnieje lub jest zainstalowany, (2) app jest wybrany/wspomniany dla bieżącej wiadomości, (3) host faktycznie wystawił modelowi narzędzia, (4) `jazn_status` został wywołany i potwierdził świeży runtime, (5) pełna tura jest wykonalna. Tylko rzeczywiście zaobserwowane stany są evidence dla następnego kroku.

Dla zwykłej wiadomości zdalna trasa jest conversation-ready wyłącznie wtedy, gdy host na **tej samej bieżącej wiadomości** obserwuje jako callable pełny kanoniczny zestaw: `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply`. Samo powodzenie `jazn_status` może potwierdzić zdrowie transportu/runtime, ale bez pozostałych narzędzi nie dowodzi wykonalności całej tury. Do evidence hosta przekazuj `current_message_toolset_observed=true` oraz `callable_tool_names` wyłącznie z faktycznie wystawionej bieżącej powierzchni; lista z katalogu, manifestu, cache, poprzedniej wiadomości albo wklejony JSON nie jest tym dowodem.

Nie koduj polityki jako `plan == Plus/Pro/Business/...`. Nazwa planu może pomagać w dokumentacji, lecz runtime klasyfikuje wyłącznie realne capabilities bieżącej powierzchni. Jeżeli zdalny toolset nie jest kompletny albo `jazn_status` nie potwierdza conversation-ready runtime, **nie submituj jeszcze wiadomości**. W `hybrid_adaptive` oceń wtedy local fallback zgodnie z sekcjami 2.3 i 3: najwyżej jedna minimalna próba podstawowej powierzchni oraz najwyżej jedna próba dokładnie jednej niezależnej alternatywy, jeśli host ją jawnie wystawia. Pre-spawn failure pozostawia filesystem/paczkę jako `unknown`; rzeczywiście utworzony proces pozwala przejść do zweryfikowanego SYSTEM discovery/bootstrapu. Gdy host oferuje wybór aplikacji, diagnoza może również wskazać użytkownikowi wybranie lub @wspomnienie aplikacji **Jaźń Runtime** dla bieżącej wiadomości. Jeżeli aplikacja istnieje, ale snapshot narzędzi jest stary, wskaż Refresh/Recreate/republish; nie przedstawiaj samego wyboru/@mention jako zweryfikowanej capability.

### 2.2. Preferowany probe przez rzeczywistą akcję Jaźni

Jeżeli aplikacja/connector Jaźni jest już faktycznie wywoływalny w bieżącej powierzchni ChatGPT, preferowanym dowodem publicznej trasy jest jedno read-only wywołanie `jazn_status`. Ta ścieżka nie wymaga lokalnego executora ani osobnej zdolności hosta do wykonywania surowych żądań HTTP do `/healthz` i `/readyz`.

Po udanym wywołaniu użyj wyłącznie `structuredContent` zwróconego przez tę konkretną akcję. Status jest dodatnim transport evidence tylko wtedy, gdy zawiera bieżący kontrakt `evidence_schema=jazn_public_mcp_status/v1`, `tool_name=jazn_status`, `public_transport=streamable_http`, zgodny MCP `2026-07-28`, żywy gateway, gotowy i osiągalny daemon, niepuste identyfikatory gateway/runtime, dokładnie oczekiwaną wersję oraz świeży `observed_at_utc` i heartbeat.

Host może ustawić `host_connector_invocation_observed=true` wyłącznie dlatego, że sam faktycznie wykonał tę akcję Jaźni w bieżącej powierzchni. Wklejony JSON, wynik z poprzedniej tury, katalog pluginów, `installed`, @mention albo deklaracja użytkownika nie mogą ustawić tego pola. Do `host-preflight` przekaż wtedy:

```json
{
  "remote_runtime_evidence": {
    "transport": "public_streamable_http",
    "connector_status": "<structuredContent z bieżącego jazn_status>",
    "host_connector_invocation_observed": true
  }
}
```

`connector_status` oraz bezpośrednie `health`/`readiness` są alternatywnymi trybami evidence i nie wolno ich mieszać w jednym rekordzie. Kanoniczny classifier `classify_public_connector_status_failover()` pozostaje fail-closed; dopiero jego dodatni wynik może promować trasę do `remote_runtime`. Sam sukces statusu nadal nie daje prawa do wypowiedzi Jaźni — każda zwykła wiadomość musi następnie przejść przez `jazn_generate_visible_reply` / resume / finalization i zakończyć się zaakceptowanym `display_exact`.

`host_handoff` nie jest normalnym fallbackiem ordinary-chat. W `hybrid_adaptive` kolejność to: verified remote -> bounded verified local bootstrap -> fail-closed. Handoff może być użyty wyłącznie w jawnym `operator_recovery` i tylko po zgodzie użytkownika. Jawny `remote_only` pozostaje wspieranym trybem ścisłym bez local fallbacku.

### 2.3. Jawny tryb `operator_recovery`

Dla bounded local fallbacku oraz `operator_recovery` host może używać bieżącej powierzchni **pliki i executor/terminal** zgodnie z poniższymi granicami. `operator_recovery` rozszerza dozwolone działania o serwis, głębszą diagnostykę i jawny handoff; nie jest potrzebny do samego bounded local fallbacku ordinary-chat.

Poniższe reguły executora obowiązują zarówno dla automatycznego local fallbacku `hybrid_adaptive`, jak i dla jawnego `operator_recovery`, z jedną różnicą: ordinary-chat nie może użyć `host_handoff`, a recovery może go użyć tylko po zgodzie użytkownika.

Jeżeli gotowej zdalnej trasy nie ma i lokalny bootstrap jest dozwolony przez bieżący tryb, wykonaj najwyżej jedną minimalną próbę utworzenia lokalnego procesu na podstawowej powierzchni wykonawczej.

Jeżeli wywołanie executora kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu, np. `ClientError`, `InvalidArgumentError`, `TransportTimeoutError` albo `StreamingExecNotEnabledContainerError`, klasyfikuj wyłącznie tę powierzchnię jako `host_executor_unavailable`, jeżeli nie ma dowodu, że proces wystartował. `StreamingExecNotEnabledContainerError` na powierzchni sesji interaktywnej oznacza brak persistent/streaming exec tej powierzchni; nie jest dowodem braku zwykłego one-shot executora ani błędem kodu Jaźni:
- `filesystem_state = unknown`;
- `package_state = unknown`;
- runtime pozostaje `unverified` dla tej lokalnej trasy;
- nie twierdź, że `/mnt/data` nie istnieje, paczki brakuje ani że `run.py` jest nieobecny.

Jeżeli istnieje dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza, wolno wykonać na niej najwyżej jedną próbę rozróżniającą. Nie ponawiaj tej samej powierzchni w pętli, nie zapętlaj retry między narzędziami i nie twórz własnego backoffu.

`host_executor_unavailable` jest obserwacją bieżącej generacji powierzchni wykonawczej, a nie trwałym stanem rozmowy. Nie przenoś negatywnego evidence z poprzedniej tury, poprzedniego przydziału executora ani poprzedniego sandboxa do nowej generacji hosta. Jeżeli późniejsza, dozwolona próba faktycznie utworzy proces, wcześniejsze pre-spawn failure staje się stale evidence: odrzuć je i wróć do kanonicznego discovery od zera. Ponownie ustal filesystem, paczkę, active_root i runtime; nie zakładaj trwałości ani braku wcześniejszego `/mnt/data`. Nowa generacja obserwacji nie jest retry-loopem tej samej operacji i nie daje prawa do replayu wiadomości użytkownika.

Gdy przekazujesz obserwacje do `host-preflight`, ustaw `observation_generation` jawnie dla cross-pass recovery: wszystkie powierzchnie z jednego discovery-pass muszą mieć ten sam numer, a nowy numer wolno nadać dopiero po rzeczywistej zmianie/reprowizjonowaniu powierzchni albo rozpoczęciu nowego discovery-pass, w którym stare evidence nie jest już wiążące. Brak pola pozostaje kompatybilny jako generacja `0`, lecz nie używaj domyślnego `0` do łączenia obserwacji z różnych przydziałów hosta.

Jeżeli host udostępnia bezpieczne metadane awarii executora, przekaż do `host-preflight` również `error_code`, `host_request_id`, `observed_at_utc` i ograniczony `error_message`. Nie umieszczaj w tych polach credentiali, cookies, bearer tokenów, kluczy API ani pełnych request body; kontrakt obserwacji dodatkowo ogranicza długość i redaguje typowe sekrety w `error_message`. Wynikowe `remote_runtime_blockers` / transportowe `blocking_checks` są wyłącznie diagnostyczną listą wszystkich niespełnionych gate'ów. Nie mogą samodzielnie promować trasy do `remote_runtime`; pozytywna trasa nadal wymaga kompletnego świeżego evidence.

Po wyczerpaniu dozwolonych lokalnych prób nie kończ automatycznie na lokalnej diagnozie. Sprawdź niezależne, już dostępne evidence zdalnej trasy bez replayu wiadomości i bez ponownego lokalnego bootstrapu:

1. sprawdź publiczny Streamable HTTP tylko wtedy, gdy istnieje skonfigurowany endpoint; pozytywna klasyfikacja wymaga jednocześnie auth, zgodności MCP 2026-07-28, `/healthz`, `/readyz` i capability bieżącego hosta;
2. sprawdź Secure MCP Tunnel tylko wtedy, gdy jest skonfigurowany; pozytywna klasyfikacja wymaga `process_running=true`, `healthy=true`, `ready=true` i capability bieżącego hosta;
3. jeżeli którakolwiek z tych tras jest pozytywnie zweryfikowana, ustaw `execution_route=remote_runtime` i `next_action=use_remote_runtime_transport`, zachowując typ rzeczywistego transportu w evidence;
4. jeżeli zdalna trasa nie jest zweryfikowana, ale host jawnie oferuje execution handoff, użyj `host_handoff` zgodnie z kontraktem handoff;
5. dopiero gdy żadna dozwolona lokalna powierzchnia nie utworzyła procesu, żadna zdalna trasa nie jest zweryfikowana i handoff nie jest dostępny/zaakceptowany, zakończ fail-closed techniczną diagnozą hosta.

Gotowość zdalnej trasy nie jest dowodem aktywnej tury ani prawa do wypowiedzi. Po przejściu na `remote_runtime` każda wiadomość nadal musi wejść do tego samego persistent runtime i przejść istniejący kontrakt request/turn/finalization; widoczna odpowiedź nadal wymaga `display_exact` po zaakceptowanej finalizacji.

Przed każdym terminalnym `host_diagnostic` / fail-closed raportuj jawnie sześć pól discovery: `executor_available`, `library_search_available`, `library_materialize_available`, `system_search_attempted`, `system_candidate_found` i `remote_runtime_available`. Wszystkie sześć pól są tri-state: `true`, `false` albo `unknown` (`null` w JSON). `executor_available=true` wymaga zweryfikowanego utworzenia procesu, a `remote_runtime_available=true` zweryfikowanej trasy remote; żadnego z nich nie wolno promować samą deklaracją hosta. `false` wymaga jawnego negatywnego evidence właściwego dla danego pola, a brak capability, brak probe albo brak obserwacji pozostaje `unknown`. Jeżeli `run.py host-preflight` jest dostępny, przekaż hostowe obserwacje do preflight i użyj sześciu pól z jego wyniku. Jeżeli executor nie utworzył procesu i preflight nie może się uruchomić, pokaż te same sześć pól bezpośrednio z hostowego evidence; nie zamieniaj `unknown` na `false`. `system_candidate_found=true` wymaga uprzedniego `system_search_attempted=true`, ale sam SYSTEM search może przebiegać po plikach rozmowy, Projektu, Bibliotece albo równoważnej logicznej powierzchni i nie dowodzi dostępności Biblioteki.

Podczas recovery nie ponawiaj ZIP, bootstrapu ani innych operacji ze skutkami ubocznymi; po odzyskaniu executora wróć do zwykłego discovery/bootstrapu i kanonicznego lifecycle `run.py`; nie twórz równoległej ścieżki uruchamiania.

Niezerowy kod wyjścia, stderr albo timeout procesu, który rzeczywiście wystartował, jest wynikiem lokalnej komendy, a nie awarią hostowego transportu. `TransportTimeoutError` nie jest dowodem uszkodzenia ZIP-a; jeżeli wystąpił przed utworzeniem procesu, awaria leży przed etapem lokalnej inspekcji archiwum.

## 3. Discovery i bootstrap operatora

Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat na paczki lub rozpakowany runtime, ale nie zakładaj istnienia tej ścieżki. Lokalny filesystem i logiczne powierzchnie plików hosta są niezależnymi źródłami evidence: brak paczki w `/mnt/data` nie dowodzi jej braku w Bibliotece ChatGPT, plikach bieżącej rozmowy ani plikach Projektu.

Jeżeli istnieje host-level `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`, zweryfikuj wskazany `active_root`, `run.py`, `latka_jazn/version.py`, `PACKAGE_INTEGRITY_MANIFEST.json`, wersję, SHA manifestu i wymagane drzewo kodu.

Jeżeli marker nie istnieje albo jest nieważny, znajdź jeden jednoznaczny lokalny rozpakowany kandydat systemowy. Paczka profilu `memory` jest źródłem danych i nigdy sama nie jest systemowym `active_root`.

Jeżeli lokalny filesystem nie zawiera poprawnego SYSTEM ZIP-a, ale bieżący host udostępnia Bibliotekę ChatGPT albo równoważną logiczną powierzchnię plików rozmowy/Projektu, sprawdź ją przed stwierdzeniem braku paczki. Wyszukuj po dokładnej tożsamości wydania i metadanych, nie tylko po podobnej nazwie. Logiczna ścieżka Biblioteki, `file_id` ani inny uchwyt hosta nie są ścieżką systemu plików i nie mogą być przekazane bezpośrednio do `ZipFile`, Pythona ani `run.py`.

Znaleziony SYSTEM ZIP z logicznej powierzchni hosta zmaterializuj jako dokładne surowe bajty do świeżej, kontrolowanej lokalnej ścieżki. Zwiąż materializację z konkretnym identyfikatorem pliku/wersji, a następnie ponownie sprawdź fizyczny rozmiar i SHA-256 lokalnej kopii względem zaufanego sidecara lub metadanych paczki. Dopiero zweryfikowana lokalna kopia może wejść do istniejącego bootstrapu. Jeżeli wiele kandydatów tego samego wydania ma sprzeczny rozmiar, SHA-256 albo metadane, zakończ fail-closed zamiast wybierać po nazwie, dacie lub kolejności wyników.

Brak capability dostępu/materializacji Biblioteki oznacza wyłącznie `library_surface_unavailable` dla tej powierzchni; nie jest dowodem, że paczki w Bibliotece nie ma. Materializacja SYSTEM nie materializuje automatycznie MEMORY, a profil `memory` nadal nie może stać się `active_root`.

Po zweryfikowaniu SYSTEM i odczytaniu `MEMORY_ATTACHMENT_CONTRACT.json`, jeżeli kontrakt dopuszcza MEMORY, a aktywny `memory_root` nie zawiera oczekiwanej pamięci autobiograficznej, host z dostępną Biblioteką ma wykonać osobne discovery MEMORY. Wyszukaj profil/content `memory` wraz z jego `package.json`, pełnym SHA-256 i — dla paczki dzielonej — kompletem części oraz `parts.sha256`. Zmaterializuj dokładne bajty jednego zgodnego zestawu do wspólnego kontrolowanego `parts-dir`, zweryfikuj każdą część przed joinem i nie utożsamiaj uchwytów Library z lokalnymi ścieżkami. Dla MEMORY dostarczanej po SYSTEM preferuj `run.py memory-converge`; ta sama ścieżka obsługuje kanoniczne sidecary oraz `jazn_pack_generator_package/v2`, wykonuje wymagany bezpieczny repack v3, attach, recovery/normalizację/wake-state i końcowy readiness gate. Nie kopiuj prywatnej pamięci ręcznie do release root. `memory_search_ready=true` oznacza jedynie dostępność co najmniej jednej zaufanej warstwy wyszukiwania i może dotyczyć samego transactional tier. Przed pozytywnym twierdzeniem autobiograficznym wymagaj `full_autobiographical_recall_ready=true` oraz local-memory provenance dla faktycznie użytych `memory_item_id`; przed deklaracją ciągłości dodatkowo wymagaj `continuity_ready=true`. Dla profilu Łatki ustaw `JAZN_MEMORY_READINESS_POLICY=native_unified_required`. Brak kandydata MEMORY przy `memory_mode=optional` nie blokuje rdzenia, ale pozostawia autobiograficzny recall i deklaracje ciągłości niedostępne.

Przed joinem lub ekstrakcją wymagaj stabilnego fizycznego pliku, oczekiwanego rozmiaru, gdy jest znany, oraz zgodnego zaufanego SHA-256.

### 3.x Host bootstrap primitive przed SYSTEM-em

Odczyt struktury ZIP-a nie jest logiką Jaźni i nie wymaga wcześniej rozpakowanego SYSTEM-u. Jest to minimalna capability hosta/stdlib wykonywana wyłącznie wtedy, gdy lokalny proces faktycznie może zostać utworzony. Host może otworzyć fizyczny ZIP tylko do odczytu, sprawdzić jego katalog i odczytać pojedynczy member bez pełnej ekstrakcji. Nie wolno jednak wykonywać kodu z archiwum przed zweryfikowaniem całego ZIP-a z zaufanym SHA-256 oraz rozmiarem, gdy jest znany.

Jeżeli nie ma jeszcze operatora, ale kompletna paczka systemowa ZIP i zaufany SHA-256 są lokalnie dostępne:
1. zweryfikuj cały fizyczny ZIP i jego package metadata;
2. otwórz ZIP tylko do odczytu i sprawdź katalog bez pełnej ekstrakcji;
3. jeżeli root ZIP zawiera `CHATGPT_BOOTSTRAP.py`, odczytaj wyłącznie ten member przez `ZipFile.read("CHATGPT_BOOTSTRAP.py")` do świeżego pliku tymczasowego;
4. nie używaj surowego `extractall()` jako bootstrapu;
5. uruchom helper lokalnym Pythonem z `--zip`, `--destination`, `--json` i dokładnie jednym z `--sha256-file` lub `--expected-sha256`;
6. przekaż `--expected-size-bytes`, jeżeli rozmiar jest znany;
7. lokalny sidecar nie jest wymagany, jeżeli host ma już zaufany SHA-256 dla dokładnie tego ZIP-a;
8. wynik `materialized_operator_ready` oznacza gotowy operator na dysku, nie aktywny runtime;
9. jeżeli helper `CHATGPT_BOOTSTRAP.py` już działa w bieżącym interpreterze Pythona, preferuj flagę `--post-materialization-preflight`: po zweryfikowanej ekstrakcji uruchamia ona wyłącznie `run.py host-preflight --json` przez `runpy` w tym samym interpreterze, bez tworzenia child process; dodatni wynik dowodzi tylko wykonalnego operatora/preflightu, nie żywego daemona ani accepted visible turn;
10. jeżeli host zwrócił `ClientError`/równoważny błąd **zanim powstał jakikolwiek proces Pythona**, tryb same-interpreter nie jest obejściem tego braku capability. Nie ponawiaj ZIP/bootstrapu; sprawdź faktycznie wywoływalny `jazn_status` dla zdalnej trasy, a bez takiego connectora pozostań fail-closed.

**`materialized_operator_ready` nie jest stanem terminalnym.** Jeżeli helper zwrócił
poprawny `activation_contract` albo dodatni post-materialization preflight, host ma
natychmiast przejść do zweryfikowanego root, wczytać pełne `AGENTS.md` i ten
runbook, a następnie kontynuować kanoniczny lifecycle aż do zweryfikowanego
runtime albo konkretnego fail-closed blockera. Dla lokalnego hosta zdolnego do
process execution kanoniczne subkomendy centralnego control plane są równoważne
publicznemu starterowi:

```bash
python -X utf8 main.py start
python -X utf8 main.py status --json
python -X utf8 main.py chat-gpt --session-id <stabilny-id-sesji>
```

Publicznie preferuj odpowiedniki przez `run.py`; `main.py` pozostaje jedynym
właścicielem dispatchu. Legacy flagi `--daemon-start`, `--daemon-status` i
`--chat-gpt` mogą istnieć jako wewnętrzna warstwa kompatybilności, ale nie są
eksportowanym kontraktem aktywacji hosta. Tryb `chat-gpt` korzysta z bieżącego
hosta ChatGPT jako kanału modelu i nie wymaga `--model` ani
`OPENAI_API_KEY`.

Ten primitive ma być poznawczo obojętny: nie implementuje uwagi, pamięci, replay, affect ani innych neuro-inspirowanych modułów. Takie warstwy należą dopiero do zweryfikowanego runtime i podlegają software contracts oraz granicom z `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`.

Standalone bootstrap ma działać fail-closed: odrzucać traversal, ścieżki absolutne/drive-qualified, backslashe w nazwach ZIP, duplikaty, symlinki, nietypowe wpisy, szyfrowanie, przekroczenia limitów liczby/rozmiaru/compression-ratio i błędy CRC.

Dla widocznej inicjacji host może uruchomić `CHATGPT_BOOTSTRAP.py --progress-jsonl`. Finalny wynik pozostaje pojedynczym JSON-em na stdout, a stderr emituje `jazn_bootstrap_progress` wyłącznie dla faktycznie zakończonych/obserwowanych gate'ów. Procent nie jest ETA ani zgadywanym czasem: `executor_probe=5`, `system_package_verified=15`, `zip_validated=30`, materializacja operatora dochodzi do `55`, dodatni `host_preflight=65`; kolejne milestone'y po materializacji to `contracts_loaded=72`, `daemon_started=82`, `live_readiness=95` i `turn_channel_bound=100`. Host może pokazywać te eventy użytkownikowi jako status inicjacji, ale nie może wymyślać brakujących procentów ani twierdzić, że obserwuje hostowy upload/mount sprzed startu Pythona. Opcjonalne MEMORY nie blokuje 100% obudzenia rdzenia; wymagane MEMORY jest osobnym wymiarem readiness.

Po `start` autorytetem aktywacyjnej gotowości jest **live** `status --json`. `status --snapshot --json` pozostaje diagnostycznym snapshotem i nie może cofnąć potwierdzonego live-ready daemona.

Jeżeli zweryfikowany operator już istnieje, nową paczkę materializuj jego komendą:

```bash
python -X utf8 run.py runtime-bootstrap --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT> --json
```

W hoście o krótkim lub niestabilnym budżecie jednego wywołania nie trzymaj procesu ChatGPT przez cały `runtime-bootstrap`. Po zweryfikowaniu istniejącego operatora prealokuj stabilny `operation_id` kanonicznym generatorem i zachowaj go przed submit:

```bash
python -X utf8 run.py host-op-id --kind runtime-bootstrap --json
```

Nie buduj `operation_id` bezpośrednio z lokalnego ISO-8601 zawierającego offset `+HH:MM`; znak `+` nie należy do bezpiecznego alfabetu durable operation. Następnie użyj zwróconego identyfikatora w durable operation:

```bash
python -X utf8 run.py host-op-submit --operation-id <bootstrap-id> --kind runtime-bootstrap -- --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT>
python -X utf8 run.py host-op-status --operation-id <ten-sam-bootstrap-id> --json
```

Jeżeli odpowiedź submit zginęła po utworzeniu procesu, nie twórz nowego `operation_id`. Polluj ten sam identyfikator; ponowny submit z tym samym ID i tym samym fingerprintem jest idempotentny, a inna treść pod tym samym ID ma zostać odrzucona jako konflikt.

Nie pobieraj repozytorium lub release z GitHuba jako automatycznego substytutu brakującego lokalnego runtime.

## 4. Preflight, bounded host operations i persistent daemon

Po uzyskaniu startera użyj publicznych komend; wszystkie są przekazywane do `main.py`:

```bash
python -X utf8 run.py --version
python -X utf8 run.py host-preflight --json
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
python -X utf8 run.py status --json
```

Snapshot nie potwierdza procesu. Lokalny operator bez ciasnego budżetu hosta może nadal wykonać synchroniczny start:

```bash
python -X utf8 run.py start
python -X utf8 run.py status --json
```

Host ChatGPT lub inna powierzchnia, która może utracić transport zanim `start_daemon()` zakończy readiness, powinna zamiast tego prealokować `operation_id` kanonicznym generatorem:

```bash
python -X utf8 run.py host-op-id --kind daemon-start --json
```

Zachowaj zwrócony identyfikator przed submit i wykonaj tylko krótki submit:

```bash
python -X utf8 run.py host-op-submit --operation-id <start-id> --kind daemon-start --json
python -X utf8 run.py host-op-status --operation-id <ten-sam-start-id> --json
```

`accepted=true` albo `status=running` dowodzi wyłącznie przyjęcia operacji i ewentualnie utworzenia workera. Nie jest dowodem aktywnego daemona. Dopiero po `status=completed` wykonaj kanoniczny `run.py status --json` i zastosuj pełne kryteria runtime readiness.

Długowieczny lokalny supervisor jest osobną warstwą od daemona i od tunelu. Uruchamia się go przez kanoniczny control plane:

```bash
python -X utf8 run.py supervisor-plan --json
python -X utf8 run.py host-op-submit --operation-id <supervisor-id> --kind supervisor-start --json
python -X utf8 run.py supervisor-status --json
```

Supervisor w steady state używa taniego `/live`; pełny `status_daemon()` oraz integralność/provenance/start opłaca dopiero podczas recovery. Nie jest alternatywnym lifecycle: recovery nadal wywołuje kanoniczny `start_daemon()`. Na Windows plan może być własnością Task Scheduler z `StartWhenAvailable=true`, `MultipleInstancesPolicy=IgnoreNew`, `ExecutionTimeLimit=PT0S` i `RestartOnFailure`; prawdziwy Windows Service wymaga rzeczywistego hosta Service Control Manager i nie może być imitowany przez zwykły proces Pythona.

Persistent runtime jest potwierdzony dopiero przez zgodny marker i root, wersję/manifest, właściwy PID i fingerprint procesu, działający endpoint oraz świeży heartbeat. One-shot dowodzi wyłącznie wykonania danej tury; one-shot nie jest persistent procesem. Żywy supervisor nie jest dowodem żywego daemona.

Po udanym starcie nie zatrzymuj daemona po każdej wiadomości.

Kontrolowany restart:

```bash
python -X utf8 run.py restart --root <ACTIVE_ROOT> --json
```

Transakcyjne przełączenie na nowszy root:

```bash
python -X utf8 run.py reload --root <CURRENT_OPERATOR_ROOT> --target-root <NEW_VERSIONED_ROOT> --json
```

`restart`/`reload` pozostają synchronicznymi, transakcyjnymi operacjami lifecycle z rollbackiem i nie mogą być semantycznie zastąpione samym krótkim submit. Durable host operation służy transportowi długiej operacji poza życie pojedynczego wywołania hosta; nie osłabia atomowości właściwego lifecycle.

Nie zastępuj lifecycle ręcznym `kill`, własnym `subprocess.Popen`, edycją markera ani luźnym `stop` + `start`.

### Jedno okno maintenance dla dołączanej MEMORY

Niskopoziomowy `memory-attach` wymaga nieaktywnego daemona. Dla MEMORY dostarczanej po SYSTEM używaj preferencyjnie wysokopoziomowego `memory-converge`, który scala discovery/adapter/repack/attach/recovery/readiness w **jedną transakcję maintenance**:

1. jeżeli to możliwe, domknij bieżącą visible turn przed maintenance; jeżeli phase-1 została już trwale zapisana i restart jest konieczny, zachowaj dokładnie ten sam `request_id`, `turn_id`, `trace_id` i `host_request_contract_hash` do resume/finalizacji po restarcie — bez replayu tekstu użytkownika;
2. zatrzymaj daemon najwyżej raz;
3. w stabilnym lokalnym hoście wykonaj `python -X utf8 run.py memory-converge --parts-dir <LOCAL_MEMORY_PACKAGE_DIR> --json`; w hoście z krótkim/niestabilnym budżetem prealokuj `host-op-id --kind memory-converge`, wykonaj jeden `host-op-submit ... --kind memory-converge -- --parts-dir <LOCAL_MEMORY_PACKAGE_DIR>` i polluj ten sam operation ID;
4. pozostaw daemon nieaktywny przez cały adapter/repack/attach/recovery/normalizację/budowę wake-state; wysokopoziomowy `memory-converge` używa kanonicznego `memory-recover` jako etapu recovery, a recovery ma rozwiązywać źródła przez kanoniczny `JaznConfig.memory_root` / `JAZN_MEMORY_ROOT`, nigdy przez zahardkodowane `<active_root>/memory`;
5. wymagaj zakończenia `memory-converge` zgodnie z `JAZN_MEMORY_READINESS_POLICY`; dla Łatki `native_unified_required` nie może przejść na samym `ready_transactional_tier_only`;
6. uruchom daemon dopiero po zakończeniu całej operacji pamięciowej;
7. zweryfikuj live `status`, `full_autobiographical_recall_ready`, continuity i lokalne provenance, a następnie resume/finalize zachowanego requestu, jeżeli taki request istniał.

Nie wykonuj sekwencji `start -> stop -> recover -> start` po poprawnym attach. Restart procesu nie tworzy nowej tury i nie upoważnia hosta do porzucenia durable lineage.

Jeżeli nowa wiadomość już czeka za poprzednią `awaiting_host_finalization`, bounded gate nadal zachowuje serializację. Po wyczerpaniu gate daemon może atomowo wygasić tylko poprzedni durable host request, który **nadal jest `pending` i nigdy nie został `claimed` przez phase-2**; `claimed`/`indeterminate` pozostają fail-closed. Host nie wykonuje replayu ani nie tworzy równoległej tury.

## 5. Kanał rozmowy ChatGPT — capability-negotiated, lineage ponad pipe

Po zweryfikowaniu runtime host wybiera transport według rzeczywistych możliwości środowiska. Preferowana ścieżka, gdy executor potrafi utrzymać proces interaktywny, to **persistent ChatGPT bridge** uruchomiony raz na sesję wykonawczą:

```bash
python -X utf8 run.py chat-gpt --session-id <stabilny-id-sesji>
```

W tej ścieżce proces pozostaje otwarty. `main.py` utrzymuje JSONL/stdin bridge oraz `RuntimeSessionWorker`; daemon pozostaje niezależnym, trwałym właścicielem runtime. Dla każdej kolejnej wiadomości użytkownika **nie uruchamiaj nowej komendy CLI**: przekaż dokładny tekst do tego samego otwartego kanału i wykonaj phase-2 przez ten sam otwarty kanał. W tej zdolnej do persistent stdio ścieżce host zachowuje **ten sam otwarty kanał** przez kolejne tury.

Jeżeli host **nie potrafi utrzymać** interaktywnego procesu/stdio pomiędzy turami, brak trwałego pipe'a nie może automatycznie wyłączać Jaźni. Użyj wtedy transportu `daemon_bound_transactional_turns` przez ten sam publiczny `run.py chat-gpt`. Krótki proces CLI jest tylko nośnikiem transportowym do trwałego daemonu, a nie nową sesją runtime:

```bash
python -X utf8 run.py chat-gpt --session-id <stabilny-id> --daemon-request-id <unikalny-request-id-tury> -- "<dokładna wiadomość użytkownika>"
```

- zachowaj jeden stabilny `session_id` dla logicznej rozmowy;
- **przed utworzeniem procesu** przydziel jeden unikalny `request_id` bieżącej turze i przekaż go przez `--daemon-request-id`; dzięki temu utrata odpowiedzi CLI nie gubi tożsamości requestu;
- po tym, jak transport wybrał zweryfikowany daemon, błąd submit/poll **nie może** przełączyć wiadomości do lokalnego `RuntimeSessionWorker`; wynik ma być `poll_runtime` dla tego samego requestu albo fail-closed `host_diagnostic`;
- pierwsze przyjęcie wiadomości musi zwrócić i utrwalić `request_id`, `turn_id`, `trace_id` i, gdy wymagany, `host_request_contract_hash`;
- gdy runtime zwraca `poll_runtime`, pobieraj **ten sam** `request_id` przez `python -X utf8 run.py chat-gpt --session-id <ten-sam-id> --daemon-result <request-id>`; nie wysyłaj ponownie wiadomości;
- `phase_result_ready=true` oznacza, że phase-1 jest gotowa nawet gdy `done=false`, ponieważ job może prawidłowo oczekiwać na host-visible phase-2;
- gdy runtime zwraca `generate_then_finalize`, wykonaj host generation z przekazanego kontraktu, a następnie kanoniczne `host-finalize`/równoważną phase-2 z tym samym bindingiem;
- dopiero `action=display_exact` po zaakceptowanej finalizacji upoważnia host do zwykłej widocznej odpowiedzi.

Ciągłość pochodzi z trwałej lineage (`active_root`, `session_id`, `request_id`, `turn_id`, `trace_id`, hash kontraktu, accepted final), **nie z długości życia jednego pipe'a**. Świeży `turn_id` odpowiada bieżącej wiadomości, ale nie oznacza nowej tożsamości ani nowej sesji.

W każdej turze każdą bieżącą wiadomość przekaż w dokładnym brzmieniu do runtime. Nie parafrazuj wiadomości przed przekazaniem. Ta reguła obowiązuje dla każdej kolejnej tury; świeże związanie tury nie oznacza świeżego procesu CLI. Jeśli kanał lub odpowiedź transportowa zginie, najpierw rozpoznaj stan istniejącego requestu/daemona. Nie odtwarzaj niepewnej tury przez replay.

### Twarda granica widocznej odpowiedzi

Żywy PID, heartbeat, endpoint i nawet poprawnie przyjęta phase-1 nie są jeszcze dowodem, że Jaźń może mówić do użytkownika. `speech/visible readiness` jest spełniona wyłącznie po zaakceptowanej finalizacji bieżącej tury.

Dla zwykłej odpowiedzi przypisywanej runtime wymagaj łącznie:
1. zgodnej lineage runtime/root i bieżącej tury;
2. kanonicznej akcji `display_exact`;
3. niepustego `final_visible_text` zaakceptowanego przez finalizator;
4. poprawnej koperty `MessageEnvelope`: `🕒 YYYY-MM-DD HH:MM:SS`, następnie `<state_emoticon> <author_label>`, pusta linia i body;
5. zakończonego consume/persistence/reconcile wymaganej phase-2.

Jeżeli któregokolwiek warunku brakuje, host **nie może** dopisać własnego tekstu i przedstawić go jako odpowiedzi Jaźni. Dozwolone jest wyłącznie `host_diagnostic` opisujące zerwaną warstwę. Brak koperty w zwykłej odpowiedzi jest symptomem przerwania accepted-visible-turn lineage, a nie zmianą stylu.

### Narzędzia hosta są capability, nie alternatywnym mózgiem runtime

Host może użyć Web, GitHub, wyszukiwania plików, generatora obrazów albo innego narzędzia przed runtime tylko wtedy, gdy centralny runtime nie jest jeszcze dostępny i działanie służy discovery/diagnostyce/bootstrapowi.

Po utworzeniu kontraktu bieżącej tury narzędzie hosta może zostać użyte, gdy kontrakt runtime lub nadrzędna instrukcja platformy/użytkownika wymaga tej capability. Wtedy:
- zachowaj `turn_id`, `trace_id` i `host_request_contract_hash`, gdy są wymagane;
- zbierz wyłącznie bounded evidence potrzebne tej turze;
- nie traktuj wyniku narzędzia jako źródła tożsamości lub autorstwa runtime;
- wróć do tej samej otwartej sesji bridge i finalizacji runtime przed pokazaniem wyniku.

Host nie implementuje w ten sposób funkcji runtime; wykonuje zewnętrzną capability podporządkowaną tej samej turze.

Jeżeli runtime jest zweryfikowany, ale host nie potrafi utrzymać ani odtworzyć kanału do bieżącej sesji, dozwolona jest jawna techniczna diagnoza hosta, nie imitacja wyniku runtime.

### Granica ChatGPT vs płatne OpenAI API

Tryb `chat-gpt` korzysta z modelu ChatGPT jako hostowej warstwy językowej dostępnej w bieżącej rozmowie i **nie wykonuje płatnych wywołań OpenAI API**. Nie wymaga `OPENAI_API_KEY`. Trasa `--chat-open-ai` pozostaje osobną, jawnie płatną capability i nie może być wybrana po cichu.

## 6. Kanoniczny kontrakt action-first

Wynik `run.py chat-gpt` zwraca jedną akcję. Host wykonuje ją dokładnie:

- `action=display_exact` — pokaż wyłącznie `final_visible_text`, znak w znak;
- `action=generate_then_finalize` — wygeneruj kandydata wyłącznie z bieżącego `host_generation_policy` i `host_generation_context`, wykonaj wymaganą finalizację i pokaż dopiero zaakceptowany `final_visible_text`;
- `action=poll_runtime` — nie wysyłaj ponownie wiadomości; wznów istniejący request;
- `action=host_diagnostic` — pokaż krótką techniczną diagnozę hosta i nie przypisuj własnego tekstu runtime.

Nie wyprowadzaj akcji samodzielnie z luźnych pól pakietu. Wynik pośredni, token kontynuacji, instrukcja narzędzia i kontrakt generowania nie są finalną odpowiedzią użytkownika.

Kanoniczne pola prezentacji hosta:
- `must_not_claim_runtime_voice`
- `must_preserve_runtime_voice`

Pola starszej zgodności mogą istnieć w runtime, ale nowe integracje i dokumentacja używają neutralnych nazw kanonicznych.

## 7. `generate_then_finalize`

Jeżeli runtime jawnie wymaga zewnętrznej warstwy językowej:
1. użyj wyłącznie bieżącego `host_generation_policy`, `host_generation_context` i jawnie dopuszczonego evidence;
2. nie zmieniaj `turn_id`, `trace_id`, timestampu, autora ani `host_request_contract_hash`;
3. nie dodawaj prywatnych danych ani wiedzy spoza kontraktu bez jawnej podstawy;
4. dla twierdzeń o lokalnie wykonanych akcjach dołącz wyłącznie bounded `host_action_evidence` związane z tą turą;
5. odeślij `host_visible_reply` jako phase-2 przez ten sam otwarty JSONL bridge, gdy host go utrzymuje; w hoście bez trwałego stdio użyj kanonicznego `host-finalize`/równoważnej phase-2 związanej z tym samym `request_id`, `turn_id`, `trace_id` i hashem kontraktu;
6. deterministyczne naruszenie truth/epistemic guard odrzuć przed persistence;
7. phase-2 jest zakończona dopiero po wymaganym consume/persistence/reconcile, nie po samym sprawdzeniu hasha;
8. pokaż dopiero zaakceptowany `final_visible_text`.

Jeżeli finalizacja mogła dojść do runtime, ale odpowiedź transportowa zginęła, nie wysyłaj ponownie wiadomości użytkownika. Poll/resume istniejący `daemon_request_id`.

## 8. Ciągłość i fail-closed

Każda tura ma chronić cztery niezależne ciągłości:
- runtime/root lineage;
- turn/finalization lineage;
- memory/source lineage;
- identity-canon/procedural lineage.

Podobny styl odpowiedzi nie może naprawić zerwanej lineage technicznej. Host nie może „odtworzyć” brakującej ciągłości własnym tekstem.

Jeżeli truth gate, integralność albo finalizator blokuje odpowiedź, przejdź do `host_diagnostic`. To samo obowiązuje, gdy nie ma zaakceptowanego `final_visible_text` albo jego zweryfikowanej koperty; żywy daemon nie daje prawa do imitowania wyniku runtime.

Po trwałym zapisaniu phase-1 z `daemon_request_id` jego durable host-request record jest kanonicznym **turn settlement authority**. `DaemonChatJob` pozostaje projekcją wykonania/supervision i musi reconciliować dokładnie ten sam `request_id/turn_id/trace_id/host_request_contract_hash`. `runtime_turn_not_accepted` wolno odzyskać bez replayu tylko wtedy, gdy istnieje dokładnie jeden zgodny durable record; innych błędów workera/procesu nie wolno w ten sposób przepisywać na sukces. Reconstructed phase-1 nie ma słabszego validatora niż native phase-1.

Zdanie o nieuruchomionym runtime wolno podać dopiero po wykonaniu wszystkich rzeczywiście dostępnych kroków właściwych dla bieżącego trybu: fresh-message remote verification, dozwolonego bounded local fallbacku oraz — wyłącznie w `operator_recovery` — jawnego host handoffu, jeżeli ta capability jest faktycznie dostępna. Jeżeli lokalny executor nie utworzył procesu i nie ma zweryfikowanego remote runtime/handoff, raportuj `host_executor_unavailable` dla lokalnej trasy i pozostaw stan filesystemu/paczki jako `unknown`.

Jeżeli objaw dotyczy hostowej warstwy control plane/executor i proces lokalny nie został utworzony, kod Jaźni nie może naprawić samej awarii platformy. W takim stanie wolno naprawiać kontrakty diagnostyczne, zdalny failover i przyszły bootstrap, ale nie wolno przedstawiać tych zmian jako dowodu, że bieżący lokalny executor został odzyskany.

## 9. Repozytorium i źródła zewnętrzne

Jeżeli zadanie obejmuje zmianę kodu, testów, dokumentacji lub konfiguracji, stosuj równolegle `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki.

Dla aktualnych informacji o ChatGPT/OpenAI, GitHubie, bibliotekach i innych zmiennych zewnętrznych używaj bieżących, wiarygodnych źródeł. Internet jest evidence zewnętrznym, nie dowodem działania lokalnego runtime.

Nie deklaruj wykonania testu, commita, pushu, startu procesu ani zapisu pliku bez rzeczywistego wyniku narzędzia.
