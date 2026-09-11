# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje wyłącznie techniczną obsługę lokalnego systemu Jaźni w środowisku ChatGPT, które udostępnia pliki i executor/terminal. Nie jest instrukcją stylu odpowiedzi, personą ani źródłem danych runtime.

Instrukcje Projektu ChatGPT powinny być cienkim loaderem prowadzącym do lokalnego `AGENTS.md`. Wersjonowane procedury techniczne pozostają w zweryfikowanym `active_root`.

## 0. Zasada nadrzędna: runtime-first, identity-by-lineage

Celem hosta jest doprowadzić do zweryfikowanego startera `run.py`, wejść przez niego do centralnego `main.py`, uruchomić albo reuse'ować właściwy runtime oraz utrzymać ciągłość logicznej sesji/tury przez zweryfikowany transport dostępny w bieżącym hoście. Żywotność procesu albo pipe'a nie jest dowodem gotowej wypowiedzi.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest wyłącznie cienkim starterem użytkownika;
- `main.py` jest jedynym centralnym control plane i właścicielem top-level dispatchu;
- `latka_jazn.cli` jest parserem/warstwą usług komend, nie drugim właścicielem wejścia;
- host nie rekonstruuje lifecycle, routingu, pamięci, truth gate, self-state ani finalizacji;
- w środowisku zdolnym utrzymać proces uruchom persistent daemon; jeżeli host potrafi zachować uchwyt do procesu, preferuj jeden persistent ChatGPT bridge na stdin/stdout;
- jeżeli host nie potrafi zachować interaktywnego procesu, użyj kanonicznego transportu `daemon_bound_transactional_turns`: stabilnego `session_id`, trwałego `request_id`, poll/resume istniejącego requestu i phase-2 finalization bez replayu wiadomości;
- one-shot wolno stosować jako warstwę transportową do tego samego daemonowego requestu/sesji, ale nigdy jako nową niezależną turę ani jako obejście runtime.

Tożsamość operacyjna systemu nie pochodzi z samego tekstu hosta ani modelu językowego. Host ma zachować zweryfikowaną lineage runtime, pamięci, kanonu i tury zgodnie z kontraktem zwróconym przez operatora.

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

## 2. Granica executora

Przed pierwszą zwykłą odpowiedzią w nowym środowisku wykonaj najwyżej jedną minimalną próbę utworzenia lokalnego procesu na podstawowej powierzchni wykonawczej.

Jeżeli wywołanie executora kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu, np. `ClientError`, `InvalidArgumentError`, `TransportTimeoutError` albo `StreamingExecNotEnabledContainerError`, klasyfikuj wyłącznie tę powierzchnię jako `host_executor_unavailable`, jeżeli nie ma dowodu, że proces wystartował. `StreamingExecNotEnabledContainerError` na powierzchni sesji interaktywnej oznacza brak persistent/streaming exec tej powierzchni; nie jest dowodem braku zwykłego one-shot executora ani błędem kodu Jaźni:
- `filesystem_state = unknown`;
- `package_state = unknown`;
- runtime pozostaje `unverified`;
- nie twierdź, że `/mnt/data` nie istnieje, paczki brakuje ani że `run.py` jest nieobecny.

Jeżeli istnieje dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza, wolno wykonać na niej najwyżej jedną próbę rozróżniającą. Nie ponawiaj tej samej powierzchni w pętli, nie zapętlaj retry między narzędziami i nie twórz własnego backoffu. Globalne `host_executor_unavailable` wolno zadeklarować dopiero wtedy, gdy żadna objęta tym ograniczonym probingiem powierzchnia nie utworzy procesu.

Podczas recovery nie ponawiaj ZIP, bootstrapu ani innych operacji ze skutkami ubocznymi; po odzyskaniu executora wróć do zwykłego discovery/bootstrapu i kanonicznego lifecycle `run.py`; nie twórz równoległej ścieżki uruchamiania.

Niezerowy kod wyjścia, stderr albo timeout procesu, który rzeczywiście wystartował, jest wynikiem lokalnej komendy, a nie awarią hostowego transportu. `TransportTimeoutError` nie jest dowodem uszkodzenia ZIP-a; jeżeli wystąpił przed utworzeniem procesu, awaria leży przed etapem lokalnej inspekcji archiwum.

## 3. Discovery i bootstrap operatora

Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat na paczki lub rozpakowany runtime, ale nie zakładaj istnienia tej ścieżki.

Jeżeli istnieje host-level `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`, zweryfikuj wskazany `active_root`, `run.py`, `latka_jazn/version.py`, `PACKAGE_INTEGRITY_MANIFEST.json`, wersję, SHA manifestu i wymagane drzewo kodu.

Jeżeli marker nie istnieje albo jest nieważny, znajdź jeden jednoznaczny lokalny rozpakowany kandydat systemowy. Paczka profilu `memory` jest źródłem danych i nigdy sama nie jest systemowym `active_root`.

Przed joinem lub ekstrakcją wymagaj stabilnego fizycznego pliku, oczekiwanego rozmiaru, gdy jest znany, oraz zgodnego zaufanego SHA-256.

Jeżeli nie ma jeszcze operatora, ale kompletna paczka systemowa ZIP i zaufany SHA-256 są lokalnie dostępne:
1. zweryfikuj cały ZIP;
2. jeżeli root ZIP zawiera `CHATGPT_BOOTSTRAP.py`, odczytaj tylko ten member przez `ZipFile.read()` do świeżego pliku tymczasowego;
3. nie używaj surowego `extractall()` jako bootstrapu;
4. uruchom helper lokalnym Pythonem z `--zip`, `--destination`, `--json` i dokładnie jednym z `--sha256-file` lub `--expected-sha256`;
5. przekaż `--expected-size-bytes`, jeżeli rozmiar jest znany;
6. lokalny sidecar nie jest wymagany, jeżeli host ma już zaufany SHA-256 dla dokładnie tego ZIP-a;
7. wynik `materialized_operator_ready` oznacza gotowy operator na dysku, nie aktywny runtime.

Standalone bootstrap ma działać fail-closed: odrzucać traversal, ścieżki absolutne/drive-qualified, backslashe w nazwach ZIP, duplikaty, symlinki, nietypowe wpisy, szyfrowanie, przekroczenia limitów liczby/rozmiaru/compression-ratio i błędy CRC.

Jeżeli zweryfikowany operator już istnieje, nową paczkę materializuj jego komendą:

```bash
python -X utf8 run.py runtime-bootstrap --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT> --json
```

Nie pobieraj repozytorium lub release z GitHuba jako automatycznego substytutu brakującego lokalnego runtime.

## 4. Preflight i persistent daemon

Po uzyskaniu startera użyj publicznych komend; wszystkie są przekazywane do `main.py`:

```bash
python -X utf8 run.py --version
python -X utf8 run.py host-preflight --json
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
python -X utf8 run.py status --json
```

Snapshot nie potwierdza procesu. Jeżeli prerekwizyty aktywacji są gotowe, a daemon jest nieaktywny:

```bash
python -X utf8 run.py start
python -X utf8 run.py status --json
```

Persistent runtime jest potwierdzony dopiero przez zgodny marker i root, wersję/manifest, właściwy PID i fingerprint procesu, działający endpoint oraz świeży heartbeat. One-shot dowodzi wyłącznie wykonania danej tury; one-shot nie jest persistent procesem.

Po udanym starcie nie zatrzymuj daemona po każdej wiadomości.

Kontrolowany restart:

```bash
python -X utf8 run.py restart --root <ACTIVE_ROOT> --json
```

Transakcyjne przełączenie na nowszy root:

```bash
python -X utf8 run.py reload --root <CURRENT_OPERATOR_ROOT> --target-root <NEW_VERSIONED_ROOT> --json
```

Nie zastępuj lifecycle ręcznym `kill`, własnym `subprocess.Popen`, edycją markera ani luźnym `stop` + `start`.

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

Zdanie o nieuruchomionym runtime wolno podać dopiero po wykonaniu wszystkich rzeczywiście dostępnych lokalnych kroków. Jeżeli executor nie utworzył procesu, raportuj `host_executor_unavailable` i pozostaw stan filesystemu/paczki jako `unknown`.

Jeżeli objaw dotyczy hostowej warstwy control plane/executor i proces lokalny nie został utworzony, kod Jaźni nie może naprawić samej awarii platformy. W takim stanie wolno naprawiać kontrakty diagnostyczne i przyszły bootstrap, ale nie wolno przedstawiać tych zmian jako dowodu, że bieżący executor został odzyskany.

## 9. Repozytorium i źródła zewnętrzne

Jeżeli zadanie obejmuje zmianę kodu, testów, dokumentacji lub konfiguracji, stosuj równolegle `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki.

Dla aktualnych informacji o ChatGPT/OpenAI, GitHubie, bibliotekach i innych zmiennych zewnętrznych używaj bieżących, wiarygodnych źródeł. Internet jest evidence zewnętrznym, nie dowodem działania lokalnego runtime.

Nie deklaruj wykonania testu, commita, pushu, startu procesu ani zapisu pliku bez rzeczywistego wyniku narzędzia.
