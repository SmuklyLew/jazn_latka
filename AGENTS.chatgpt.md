# AGENTS.chatgpt.md — kontrakt hosta ChatGPT

Ten runbook obowiązuje wyłącznie dla transportu i operacji hosta ChatGPT.
Nie jest personą ani zastępczym runtime Jaźni.
Kanoniczny SYSTEM pozostaje właścicielem routingu, MEMORY,
tożsamości operacyjnej i finalizacji.

Pełna referencja sprzed refaktoryzacji:
`docs/runtime/CHATGPT_HOST_OPERATIONAL_REFERENCE.md`.
Czytaj odpowiednie procedury tylko przy diagnostyce, cold bootstrapie
lub operacjach serwisowych wymagających szczegółowego kontraktu.

## 1. Runtime-first, identity-by-lineage

Zasada: runtime-first, identity-by-lineage.
`run.py` jest cienkim starterem.
`main.py` jest jedynym centralnym control plane.
Parser/usługi należą do `latka_jazn/cli.py`.

Nie rekonstruuj logiki SYSTEM w hoście.
Obecność ZIP, MCP, modelu, folderu, PID ani gotowego tekstu
nie dowodzi aktywnego runtime ani autorstwa Jaźni.

## 2. Hybrid/adaptive ingress

Zachowaj kolejność:
1. zweryfikowany remote runtime;
2. zweryfikowany lokalny active_root i daemon;
3. bounded local executor/bootstrap;
4. fail-closed przy braku gotowej trasy.

### Fresh-message app exposure gate

Sprawdź w bieżącej wiadomości faktycznie callable:
- `jazn_status`
- `jazn_generate_visible_reply`
- `jazn_resume_visible_reply`
- `jazn_finalize_reply`

Wymagaj `current_message_toolset_observed=true`,
autoryzacji, zgodnej wersji i instancji, kompletnego kontraktu,
readiness oraz świeżego heartbeat.

Nie koduj polityki jako `plan == Plus/Pro/Business/...`.
Nazwa lub instalacja aplikacji Jaźń Runtime nie jest dowodem
bieżącej ekspozycji narzędzi.

### Preferowany probe przez rzeczywistą akcję Jaźni

Wykonaj jedno read-only wywołanie `jazn_status`, gdy narzędzie
jest faktycznie dostępne. Zweryfikuj lineage oraz wynik statusu.
`host_connector_invocation_observed=true` wymaga rzeczywistego
wywołania konektora. Wklejony JSON nie jest takim dowodem.

Status connector-observed i samodzielny HTTP probe to inne
rodzaje dowodów; nie wolno ich mieszać.
`classify_public_connector_status_failover()` wymaga
danych zgodnych z kontraktem.

## 3. Warm, resume i cold

Warm: reuse tylko po sprawdzeniu root, wersji, daemon_instance_id,
endpointu i heartbeat. Nie uruchamiaj drugiego daemona.

Resume: gdy root jest zweryfikowany, ale daemon niegotowy,
korzystaj wyłącznie z kanonicznego lifecycle `run.py`;
nie twórz równoległej ścieżki uruchamiania.

Cold: dopiero przy braku zaufanego active_root sprawdzaj SYSTEM ZIP.
Weryfikuj wydanie, SHA-256, wszystkie części archiwum, CRC,
bezpieczne ścieżki, komplet manifestu oraz provenance.

Przed analizą kodu wymagaj pełnej bezpiecznej ekstrakcji SYSTEM
do odrębnego katalogu, bez surowego extractall().
Po weryfikacji wczytaj `AGENTS.md` i właściwy runbook.

## 4. Granica executora i plików

Sprawdzaj rzeczywiście dostępne pliki i executor/terminal.
Jeżeli istnieje `/mnt/data`, jest pierwszym kandydatem do
lokalnego discovery, a nie automatycznie gotowym SYSTEM.

Jeżeli marker nie istnieje albo jest nieważny, sprawdź
kompletna paczka systemowa ZIP i jej pochodzenie.

Błąd ClientError, InvalidArgumentError lub TransportTimeoutError
przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu
oznacza `host_executor_unavailable`.

Utrzymuj `filesystem_state = unknown` i `package_state = unknown`.
W szczególności nie twierdź, że `/mnt/data` nie istnieje.

Wykonaj najwyżej jedną próbę na podstawowym executorze i
dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza
może zostać sprawdzona raz, jeśli jest faktycznie dostępna.
Nie zapętlaj retry między narzędziami.

Po odzyskaniu executora wróć do zwykłego discovery/bootstrapu.
One-shot dowodzi wyłącznie wykonania danej tury.

## 5. Biblioteka i MEMORY

Brak paczki w `/mnt/data` nie dowodzi jej braku w Bibliotece ChatGPT.
Logiczna ścieżka Biblioteki, `file_id` ani inny uchwyt hosta
nie są ścieżką systemu plików.

Dostępny SYSTEM zmaterializuj jako dokładne surowe bajty.
Dopiero zweryfikowana lokalna kopia może wejść do
istniejącego bootstrapu.

Przy sprzeczny rozmiar, SHA-256 albo metadane zakończ fail-closed.
`library_surface_unavailable` nie jest dowodem, że paczki
w Bibliotece nie ma.

Materializacja SYSTEM nie materializuje automatycznie MEMORY.
Profil `memory` nadal nie może stać się `active_root`.
Nie deklaruj autobiograficznej ciągłości bez jej dowodów.

## 6. Preflight i persistent runtime

Przy pierwszym kanonicznym starcie lokalnym:
- `python -X utf8 run.py host-preflight --json`
- `python -X utf8 run.py start`
- `python -X utf8 run.py status --json`

Rozmowa lokalna:
`python -X utf8 run.py chat-gpt --session-id <session-id>`

Uruchomienie persistent bridge wykonuj raz na sesję wykonawczą.
Jeżeli utrzymujesz stdin/stdout, wykorzystaj ten sam otwarty kanał;
nie uruchamiaj nowej komendy CLI dla każdej wiadomości.

Utrzymuj stabilny session_id, unikalny request_id oraz zgodne
turn_id, trace_id, kontrakt i instance lineage.
Przy timeout poll/resume tego samego requestu bez replayu.

## 7. Jedna wiadomość, zaakceptowana finalizacja

Każdą bieżącą wiadomość przekaż w dokładnym brzmieniu.
Nie parafrazuj wiadomości przed przekazaniem.
Nie wyprowadzaj akcji samodzielnie.

Rozpoznawaj wyłącznie kanoniczne akcje:
- action=poll_runtime
- action=generate_then_finalize
- action=host_diagnostic
- action=display_exact

Generowanie według runtime contract wymaga phase-2 finalization.
Widoczna odpowiedź Jaźni wymaga accepted finalization,
zgodnego MessageEnvelope, lineage i persistence.
`final_visible_text` wyświetlaj znak w znak.
Nie dopisuj własnych nagłówków ani stylizacji.

Stosuj pola `must_not_claim_runtime_voice`
oraz `must_preserve_runtime_voice`.
Narzędzia hosta są capability, nie dowodem autorstwa runtime.

## 8. Uprawnienia i diagnostyka

ROZMOWA: szybka gotowa trasa, jedna tura, finalizacja.
DIAGNOSTYKA: szczegółowe dowody i techniczne runbooki na żądanie.
PROGRAMOWANIE: `AGENTS.codex.md` i właściwe instrukcje poddrzew.
operator_recovery: osobny jawny tryb serwisowy.

Dostęp do narzędzia nie jest zgodą na zapis, publikację,
instalację, zmianę auth, płatne API ani edycję prywatnej pamięci.
`chat-gpt` nie wykonuje płatnych wywołań OpenAI API.

Nie zatrzymuj daemona po każdej turze ani zamknięciu czatu.
Stop wymaga zgody, kanonicznego lifecycle i potwierdzenia statusu.
Przy blokadzie mów jako host, bez imitacji Jaźni.

## 9. Konfiguracja i repozytorium

`.settings/` jest planowaną wersjonowaną konfiguracją.
`.settings_local/` jest prywatne i ignorowane przez Git.
Nie deklaruj pełnej integracji przed odbiorem resolverów.

Nie zmieniaj master, MEMORY, manifestów ani źródeł
bez odrębnej podstawy i wymaganej weryfikacji.
Szczegółowe procedury oraz kontrakty pozostają w dokumentacji
referencyjnej i w kanonicznym runtime.

## 10. Uzupełniające kontrakty operacyjne

Te procedury stosuj tylko w kontekście odpowiedniej operacji.
Nie są listą czynności do wykonania przy każdej wiadomości.
Warm oznacza użycie zweryfikowanego żywego daemona;
resume nie może tworzyć duplikatu procesu ani nowej tury.
One-shot CLI jest dopuszczalny jako transport istniejącego,
trwałego requestu, gdy host nie utrzymuje interaktywnego bridge.
Maintenance MEMORY, stop/restart i operacje zapisu wymagają
oddzielnej autoryzacji operatora i kanonicznego lifecycle.
W zwykłej ROZMOWIE obowiązuje szybka trasa i brak działań
serwisowych. Przy konflikcie stosuj fail-closed i odpowiedni
kanoniczny kontrakt runtime, nie improwizowany fallback.

Poniższe akapity zachowują oryginalne wymagania operacyjne, które kandydat v1 pominął. Przed wydaniem wymagają przeglądu spójności.

Dla publicznego MCP Jaźni wymagaj spójnych deklaracji:
Wynik `authenticated_principal_required`/`insufficient_scope` powinien
zawierać `_meta["mcp/www_authenticate"]` z opartym na zweryfikowanej
konfiguracji HTTPS `resource_metadata`, `error` i `error_description`.
Nie wymuszaj ponownego logowania dla innych błędów, np. rate limit,
nie konstruuj challenge z danych użytkownika ani nie uznawaj challenge
za dowód zalogowania. Middleware/SDK nadal odpowiada za kontrolę HTTP 401.
`mcp.json -> mcpServers.jazn.extensions.com.openai.auth.type=oauth`,
`_meta.securitySchemes` per narzędzie, OAuth resource metadata, scope,
audience i prawidłowej odpowiedzi 401. `noauth` wolno wystawiać tylko
dla jawnego loopback development bez token verifier. Metadane nie
uwierzytelniają ani nie tworzą narzędzi na powierzchni hosta.
Bez świeżego `jazn_status` i accepted finalization utrzymaj fail-closed.
Procedura: `docs/runtime/CHATGPT_MCP_CONNECTION_RECOVERY.md`.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest wyłącznie cienkim starterem użytkownika;
- `main.py` jest jedynym centralnym control plane i właścicielem top-level dispatchu;
- `latka_jazn.cli` jest parserem/warstwą usług komend, nie drugim właścicielem wejścia;
- host nie rekonstruuje lifecycle, routingu, pamięci, truth gate, self-state ani finalizacji;
- w środowisku zdolnym utrzymać proces uruchom persistent daemon; jeżeli host potrafi zachować uchwyt do procesu, preferuj jeden persistent ChatGPT bridge na stdin/stdout;
- jeżeli host nie potrafi zachować interaktywnego procesu, użyj kanonicznego transportu `daemon_bound_transactional_turns`: stabilnego `session_id`, trwałego `request_id`, poll/resume istniejącego requestu i phase-2 finalization bez replayu wiadomości;
- one-shot wolno stosować jako warstwę transportową do tego samego daemonowego requestu/sesji, ale nigdy jako nową niezależną turę ani jako obejście runtime.

- **warm path** — jeżeli live endpoint potwierdza ten sam `active_root`, zgodną wersję, niepusty `daemon_instance_id` i świeży heartbeat, reuse'uj istniejący daemon. To kontynuacja wcześniej zweryfikowanego persistent runtime, a nie nowa aktywacja; nie rehashuj SYSTEM-u tylko dlatego, że nadeszła kolejna wiadomość;
- **resume path** — jeżeli zweryfikowany `active_root` istnieje, ale live daemon nie jest gotowy, użyj kanonicznego lifecycle `run.py start`/`main.py start`. Każdy spawn/restart nadal musi przejść pełny package-integrity i source-provenance gate;
- **cold path** — pełna weryfikacja SHA/CRC i materializacja SYSTEM ZIP jest potrzebna dopiero wtedy, gdy nie ma zaufanej materializacji. Jeżeli standalone bootstrap dostaje `--reuse-existing-verified`, wolno ominąć ponowne CRC/dekompresję wyłącznie po zgodnym materialization stamp i pełnej weryfikacji statycznego `PACKAGE_INTEGRITY_MANIFEST.json`;
- aktywny supervisor jest osobnym właścicielem recovery daemona. Jego żywy PID nie wystarcza: wymagaj process fingerprint/root identity oraz świeżego heartbeat lease; nie startuj duplikatu supervisora;
- MEMORY optional nie należy do krytycznej ścieżki core wake. Nie uruchamiaj `memory-converge` w każdej turze i nie zatrzymuj conversation-ready tylko dlatego, że opcjonalny attach jest w toku lub niedostępny.
- W publicznym MCP Tasks synchroniczne wywołanie SQLite/daemona jest wykonywane poza pętlą ASGI (worker thread). Krótkie `/healthz` i `/readyz` nie powinny stać w kolejce za blokującą turą; utrata połączenia nie jest dowodem przerwania wątku. Po timeout najpierw odczytaj stan trwałego `taskId`/`request_id`, nigdy nie uruchamiaj ponownie tej samej wiadomości jako nowej tury. Ta izolacja nie naprawia `ClientError` hosta przed utworzeniem procesu.

Każda wiadomość nadal tworzy świeżą lineage tury i osobny request/finalization envelope; stabilna sesja i persistent daemon nie oznaczają ponownego użycia starego `turn_id`.

- publiczny MCP 2026-07-28 Streamable HTTP: skonfigurowany endpoint HTTPS, zweryfikowane uwierzytelnienie, zgodność protokołu, `/healthz` live, `/readyz` ready, zgodny `gateway_instance_id`, niepusty `runtime_instance_id`, dokładnie oczekiwana `runtime_version`, świeży `observed_at_utc` i heartbeat runtime oraz jawna capability aplikacji/konektora w bieżącym hoście; klasyfikuje go `classify_public_streamable_http_failover()`;
- OpenAI Secure MCP Tunnel: `process_running=true`, `healthy=true`, `ready=true`, niepusty `runtime_instance_id`, dokładnie oczekiwana `runtime_version`, świeży status/heartbeat oraz jawna capability odpowiadającej aplikacji/konektora w bieżącym hoście; klasyfikuje go `classify_remote_runtime_failover()`.

Model-visible `jazn_status` na direct Desktop MCP musi być zredagowany: nie zwracaj `runtime_root`, lokalnych ścieżek baz/pamięci, PID-ów, sekretów ani prywatnych operator diagnostics. Public Streamable HTTP zachowuje osobny `jazn_public_mcp_status/v1`, a Secure MCP Tunnel własny readiness contract.

Jeżeli wywołanie executora kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu, np. `ClientError`, `InvalidArgumentError`, `TransportTimeoutError` albo `StreamingExecNotEnabledContainerError`, klasyfikuj wyłącznie tę powierzchnię jako `host_executor_unavailable`, jeżeli nie ma dowodu, że proces wystartował. `StreamingExecNotEnabledContainerError` na powierzchni sesji interaktywnej oznacza brak persistent/streaming exec tej powierzchni; nie jest dowodem braku zwykłego one-shot executora ani błędem kodu Jaźni:
- `filesystem_state = unknown`;
- `package_state = unknown`;
- runtime pozostaje `unverified` dla tej lokalnej trasy;
- nie twierdź, że `/mnt/data` nie istnieje, paczki brakuje ani że `run.py` jest nieobecny.

Jeżeli istnieje dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza, wolno wykonać na niej najwyżej jedną próbę rozróżniającą. Nie ponawiaj tej samej powierzchni w pętli, nie zapętlaj retry między narzędziami i nie twórz własnego backoffu.

`host_executor_unavailable` jest obserwacją bieżącej generacji powierzchni wykonawczej, a nie trwałym stanem rozmowy. Nie przenoś negatywnego evidence z poprzedniej tury, poprzedniego przydziału executora ani poprzedniego sandboxa do nowej generacji hosta. Jeżeli późniejsza, dozwolona próba faktycznie utworzy proces, wcześniejsze pre-spawn failure staje się stale evidence: odrzuć je i wróć do kanonicznego discovery od zera. Ponownie ustal filesystem, paczkę, active_root i runtime; nie zakładaj trwałości ani braku wcześniejszego `/mnt/data`. Nowa generacja obserwacji nie jest retry-loopem tej samej operacji i nie daje prawa do replayu wiadomości użytkownika.

1. sprawdź publiczny Streamable HTTP tylko wtedy, gdy istnieje skonfigurowany endpoint; pozytywna klasyfikacja wymaga jednocześnie auth, zgodności MCP 2026-07-28, `/healthz`, `/readyz` i capability bieżącego hosta;
2. sprawdź Secure MCP Tunnel tylko wtedy, gdy jest skonfigurowany; pozytywna klasyfikacja wymaga `process_running=true`, `healthy=true`, `ready=true` i capability bieżącego hosta;
3. jeżeli którakolwiek z tych tras jest pozytywnie zweryfikowana, ustaw `execution_route=remote_runtime` i `next_action=use_remote_runtime_transport`, zachowując typ rzeczywistego transportu w evidence;
4. wyłącznie w jawnym trybie `operator_recovery`, po zgodzie użytkownika i przy rzeczywistej capability, wolno użyć `host_handoff`; w ordinary `hybrid_adaptive` handoff pozostaje zabroniony;
5. dopiero gdy żadna dozwolona lokalna powierzchnia nie utworzyła procesu, żadna zdalna trasa nie jest zweryfikowana i handoff nie jest dostępny/zaakceptowany, zakończ fail-closed techniczną diagnozą hosta.

Przed każdym terminalnym `host_diagnostic` / fail-closed raportuj jawnie sześć pól discovery: `executor_available`, `library_search_available`, `library_materialize_available`, `system_search_attempted`, `system_candidate_found` i `remote_runtime_available`. Wszystkie sześć pól są tri-state: `true`, `false` albo `unknown` (`null` w JSON). `executor_available=true` wymaga zweryfikowanego utworzenia procesu, a `remote_runtime_available=true` zweryfikowanej trasy remote; żadnego z nich nie wolno promować samą deklaracją hosta. `false` wymaga jawnego negatywnego evidence właściwego dla danego pola, a brak capability, brak probe albo brak obserwacji pozostaje `unknown`. Jeżeli `run.py host-preflight` jest dostępny, przekaż hostowe obserwacje do preflight i użyj sześciu pól z jego wyniku. Jeżeli executor nie utworzył procesu i preflight nie może się uruchomić, pokaż te same sześć pól bezpośrednio z hostowego evidence; nie zamieniaj `unknown` na `false`. `system_candidate_found=true` wymaga uprzedniego `system_search_attempted=true`, ale sam SYSTEM search może przebiegać po plikach rozmowy, Projektu, Bibliotece albo równoważnej logicznej powierzchni i nie dowodzi dostępności Biblioteki.

Podczas recovery nie ponawiaj ZIP, bootstrapu ani innych operacji ze skutkami ubocznymi; po odzyskaniu executora wróć do zwykłego discovery/bootstrapu i kanonicznego lifecycle `run.py`; nie twórz równoległej ścieżki uruchamiania.

Niezerowy kod wyjścia, stderr albo timeout procesu, który rzeczywiście wystartował, jest wynikiem lokalnej komendy, a nie awarią hostowego transportu. `TransportTimeoutError` nie jest dowodem uszkodzenia ZIP-a; jeżeli wystąpił przed utworzeniem procesu, awaria leży przed etapem lokalnej inspekcji archiwum.

Po rzeczywistym `materialized_operator_ready` zbadaj **osobno**: aktywny root oraz zgodność SYSTEM, lokalny host-preflight i live status, bieżący zdalny toolset MCP (który nie pojawia się automatycznie dzięki rozpakowaniu), i dopiero potem powiązanie jednej tury oraz zaakceptowaną finalizację. Nie uruchamiaj ponownie tej samej wiadomości po timeout/poll. Jeżeli Python już działa, `--post-materialization-preflight` może wykorzystać ten interpreter bez nowego subprocessu; nie naprawia to błędu pre-spawn hosta.

Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat na paczki lub rozpakowany runtime, ale nie zakładaj istnienia tej ścieżki. Lokalny filesystem i logiczne powierzchnie plików hosta są niezależnymi źródłami evidence: brak paczki w `/mnt/data` nie dowodzi jej braku w Bibliotece ChatGPT, plikach bieżącej rozmowy ani plikach Projektu.

Jeżeli lokalny filesystem nie zawiera poprawnego SYSTEM ZIP-a, ale bieżący host udostępnia Bibliotekę ChatGPT albo równoważną logiczną powierzchnię plików rozmowy/Projektu, sprawdź ją przed stwierdzeniem braku paczki. Wyszukuj po dokładnej tożsamości wydania i metadanych, nie tylko po podobnej nazwie. Logiczna ścieżka Biblioteki, `file_id` ani inny uchwyt hosta nie są ścieżką systemu plików i nie mogą być przekazane bezpośrednio do `ZipFile`, Pythona ani `run.py`.

Znaleziony SYSTEM ZIP z logicznej powierzchni hosta zmaterializuj jako dokładne surowe bajty do świeżej, kontrolowanej lokalnej ścieżki. Zwiąż materializację z konkretnym identyfikatorem pliku/wersji, a następnie ponownie sprawdź fizyczny rozmiar i SHA-256 lokalnej kopii względem zaufanego sidecara lub metadanych paczki. Dopiero zweryfikowana lokalna kopia może wejść do istniejącego bootstrapu. Jeżeli wiele kandydatów tego samego wydania ma sprzeczny rozmiar, SHA-256 albo metadane, zakończ fail-closed zamiast wybierać po nazwie, dacie lub kolejności wyników.

Brak capability dostępu/materializacji Biblioteki oznacza wyłącznie `library_surface_unavailable` dla tej powierzchni; nie jest dowodem, że paczki w Bibliotece nie ma. Materializacja SYSTEM nie materializuje automatycznie MEMORY, a profil `memory` nadal nie może stać się `active_root`.

Po zweryfikowaniu SYSTEM i odczytaniu `MEMORY_ATTACHMENT_CONTRACT.json`, jeżeli kontrakt dopuszcza MEMORY, a aktywny `memory_root` nie zawiera oczekiwanej pamięci autobiograficznej, host z dostępną Biblioteką ma wykonać osobne discovery MEMORY. Wyszukaj profil/content `memory` wraz z jego `package.json`, pełnym SHA-256 i — dla paczki dzielonej — kompletem części oraz `parts.sha256`. Zmaterializuj dokładne bajty jednego zgodnego zestawu do kontrolowanego `parts-dir`, zweryfikuj każdą część i nie utożsamiaj uchwytów Library z lokalnymi ścieżkami. Dla MEMORY dostarczanej po SYSTEM preferuj `run.py memory-converge`: aktualny `MEMORY_ATTACHMENT_CONTRACT.json` przewiduje verified streaming części ZIP i jeden kandydat na docelowym filesystemie, bez obowiązkowego joinu ZIP, wtórnego kopiowania transportu lub repacku v3. Legacy repack v3 jest jawną ścieżką migracji/eksportu; operacja konwergencji wymaga nieaktywnego daemona, kontrolowanej atomowej aktywacji i osobnego readiness gate. Nie kopiuj prywatnej pamięci ręcznie do release root. `memory_search_ready=true` oznacza jedynie dostępność co najmniej jednej zaufanej warstwy wyszukiwania i może dotyczyć samego transactional tier. Przed pozytywnym twierdzeniem autobiograficznym wymagaj `full_autobiographical_recall_ready=true` oraz local-memory provenance dla faktycznie użytych `memory_item_id`; przed deklaracją ciągłości dodatkowo wymagaj `continuity_ready=true`. Dla profilu Łatki ustaw `JAZN_MEMORY_READINESS_POLICY=native_unified_required`. Brak kandydata MEMORY przy `memory_mode=optional` nie blokuje rdzenia, ale pozostawia autobiograficzny recall i deklaracje ciągłości niedostępne.

`files.materialize` należy do **logicznej** przestrzeni plików hosta i musi otrzymać `file_ref.file_id` z rzeczywistego wyniku discovery, nie identyfikator wymyślony, `turn...` użyty jako ścieżka OS ani nazwę pliku. Zachowaj pary `logical_name/file_id/version_id` w jednym bieżącym zestawie evidence. Po wywołaniu sprawdź faktyczny wynik `artifacts[]`: pusty zbiór, odmowa dostępu, brak danej pozycji, brak lokalnej ścieżki lub niedostępny plik to **materialization_failed**; nie przechodź do ZipFile ani bootstrapu. `library_materialize_available=true` potwierdza wyłącznie wywoływalność interfejsu, nie sukces. Pozytywny wynik API oznacza tylko uzyskanie lokalnego artefaktu; integralność następuje dopiero po sprawdzeniu istnienia fizycznego pliku, rozmiaru, SHA-256 i zgodności sidecarów z zaufanym źródłem.

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

```bash
python -X utf8 run.py host-op-id --kind runtime-bootstrap --json
```

```bash
python -X utf8 run.py --version
python -X utf8 run.py host-preflight --json
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
python -X utf8 run.py status --json
```

```bash
python -X utf8 run.py host-op-id --kind daemon-start --json
```

### Jedno okno maintenance dla dołączanej MEMORY

Niskopoziomowy `memory-attach` wymaga nieaktywnego daemona. Dla MEMORY dostarczanej po SYSTEM preferuj wysokopoziomowy `memory-converge`, który obejmuje discovery/verified-streaming/attach/recovery/readiness w **jedną transakcję maintenance**, bez obowiązkowego repacku lub joinu ZIP:

1. jeżeli to możliwe, domknij bieżącą visible turn przed maintenance; jeżeli phase-1 została już trwale zapisana i restart jest konieczny, zachowaj dokładnie ten sam `request_id`, `turn_id`, `trace_id` i `host_request_contract_hash` do resume/finalizacji po restarcie — bez replayu tekstu użytkownika;
2. zatrzymaj daemon najwyżej raz;
3. w stabilnym lokalnym hoście wykonaj `python -X utf8 run.py memory-converge --parts-dir <LOCAL_MEMORY_PACKAGE_DIR> --json`; w hoście z krótkim/niestabilnym budżetem prealokuj `host-op-id --kind memory-converge`, wykonaj jeden `host-op-submit ... --kind memory-converge -- --parts-dir <LOCAL_MEMORY_PACKAGE_DIR>` i polluj ten sam operation ID;
4. pozostaw daemon nieaktywny przez cały verified-streaming/attach/recovery/normalizację/budowę wake-state; wysokopoziomowy `memory-converge` używa kanonicznego `memory-recover` jako etapu recovery, a recovery ma rozwiązywać źródła przez kanoniczny `JaznConfig.memory_root` / `JAZN_MEMORY_ROOT`, nigdy przez zahardkodowane `<active_root>/memory`;
5. wymagaj zakończenia `memory-converge` zgodnie z `JAZN_MEMORY_READINESS_POLICY`; dla Łatki `native_unified_required` nie może przejść na samym `ready_transactional_tier_only`;
6. uruchom daemon dopiero po zakończeniu całej operacji pamięciowej;
7. zweryfikuj live `status`, `full_autobiographical_recall_ready`, continuity i lokalne provenance, a następnie resume/finalize zachowanego requestu, jeżeli taki request istniał.

Nie wykonuj sekwencji `start -> stop -> recover -> start` po poprawnym attach. Restart procesu nie tworzy nowej tury i nie upoważnia hosta do porzucenia durable lineage.

Jeżeli nowa wiadomość już czeka za poprzednią `awaiting_host_finalization`, bounded gate nadal zachowuje serializację. Po wyczerpaniu gate daemon może atomowo wygasić tylko poprzedni durable host request, który **nadal jest `pending` i nigdy nie został `claimed` przez phase-2**; `claimed`/`indeterminate` pozostają fail-closed. Host nie wykonuje replayu ani nie tworzy równoległej tury.

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

Żywy PID, heartbeat, endpoint i nawet poprawnie przyjęta phase-1 nie są jeszcze dowodem, że Jaźń może mówić do użytkownika. `speech/visible readiness` jest spełniona wyłącznie po zaakceptowanej finalizacji bieżącej tury.

Jeżeli truth gate, integralność albo finalizator blokuje odpowiedź, przejdź do `host_diagnostic`. To samo obowiązuje, gdy nie ma zaakceptowanego `final_visible_text` albo jego zweryfikowanej koperty; żywy daemon nie daje prawa do imitowania wyniku runtime.

Jeżeli objaw dotyczy hostowej warstwy control plane/executor i proces lokalny nie został utworzony, kod Jaźni nie może naprawić samej awarii platformy. W takim stanie wolno naprawiać kontrakty diagnostyczne, zdalny failover i przyszły bootstrap, ale nie wolno przedstawiać tych zmian jako dowodu, że bieżący lokalny executor został odzyskany.
