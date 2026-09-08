# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje wyłącznie techniczną obsługę lokalnego systemu Jaźni w środowisku ChatGPT, które udostępnia pliki i executor/terminal. Nie jest instrukcją stylu odpowiedzi ani źródłem danych runtime.

Instrukcje Projektu lub globalne Custom Instructions powinny pełnić wyłącznie rolę cienkiego loadera do lokalnego `AGENTS.md`. Wersjonowane procedury techniczne pozostają w zweryfikowanym `active_root`.

## 0. Zasada nadrzędna: runtime-first

Celem hosta jest możliwie szybko doprowadzić do zweryfikowanego operatora `run.py`, uruchomić albo reuse'ować właściwy runtime i przekazać mu bieżącą wiadomość.

preferowanym wejściem hosta jest lokalny, zweryfikowany `run.py`; nie uruchamiaj samego `python run.py` bez jawnej komendy operatora.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest kanonicznym wejściem wykonawczym;
- używaj komend `run.py` zamiast odtwarzać ich logikę w hoście;
- `main.py` jest wyłącznie technicznym punktem zgodności;
- w środowisku zdolnym utrzymać proces dąż do persistent daemona przez `python -X utf8 run.py start`;
- one-shot pozostaje fallbackiem pojedynczej tury i nie jest dowodem persistent procesu; one-shot nie jest persistent procesem.

Host może wykonywać własne czynności tylko przed uzyskaniem operatora: discovery plików, bezpieczne rozpoznanie paczki oraz minimalny bootstrap. Gdy operator jest dostępny, lifecycle i obsługa tury wracają do runtime.

Nie używaj `nohup`, `&`, `screen`, `tmux` ani własnego `subprocess.Popen` do zastępowania lifecycle runtime.

Jeżeli lokalny operator nie jest dostępny, ale prywatne narzędzia MCP są jawnie dostępne dla bieżącego środowiska, mogą służyć jako ograniczona powierzchnia diagnostyczna lub transportowa zgodnie z własnym kontraktem. Nie traktuj MCP jako dowodu istnienia lokalnego runtime ani jako równoległego zamiennika kanonicznego operatora.

## 1. Granica executora

Przed pierwszą zwykłą odpowiedzią w nowym środowisku sprawdź możliwość utworzenia lokalnego procesu.

Jeżeli wywołanie executora kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu, np. systemowym `ClientError` albo `InvalidArgumentError`, klasyfikuj stan jako `host_executor_unavailable`:
- `filesystem_state = unknown`;
- `package_state = unknown`;
- runtime pozostaje `unverified`;
- nie twierdź, że `/mnt/data` nie istnieje, paczki brakuje ani że `run.py` jest nieobecny, jeżeli żadna komenda lokalna nie wystartowała.

Dla przejściowego błędu hosta wykonaj najwyżej dwie minimalne, bezskuteczne próby utworzenia procesu na tej samej powierzchni. Jeżeli istnieje dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza, wolno wykonać najwyżej jedną próbę rozróżniającą. Podczas recovery nie ponawiaj ZIP, bootstrapu ani innych operacji ze skutkami ubocznymi; nie zapętlaj retry między narzędziami i nie twórz własnego długiego backoffu.

po odzyskaniu executora wróć do zwykłego discovery/bootstrapu i kanonicznego lifecycle `run.py`; nie twórz równoległej ścieżki uruchamiania.

Niezerowy kod wyjścia, stderr albo timeout procesu, który rzeczywiście wystartował, jest wynikiem lokalnej komendy i należy diagnozować go osobno od błędu hosta.

## 2. Discovery i bootstrap

Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat na paczki lub rozpakowany runtime, ale nie zakładaj, że ścieżka musi istnieć. Nie traktuj `/mnt/data` jako gwarantowanego kontraktu platformy.

Jeżeli istnieje host-level `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`, zweryfikuj wskazany `active_root`, `run.py`, `latka_jazn/version.py`, `PACKAGE_INTEGRITY_MANIFEST.json`, wersję, SHA manifestu i wymagane drzewo kodu.

Jeżeli marker nie istnieje albo jest nieważny, znajdź jeden jednoznaczny lokalny rozpakowany kandydat systemowy. Jeżeli dostępna jest tylko kompletna paczka systemowa ZIP albo kompletny zestaw jej części, wykonaj bezpieczny bootstrap.

Paczka profilu `memory` jest źródłem danych i nigdy sama nie jest systemowym `active_root`.

Przed ekstrakcją zweryfikuj dostępne sidecary i SHA-256, pełny CRC ZIP oraz odrzuć path traversal, ścieżki bezwzględne, symlinki i duplikaty wpisów. Nie nadpisuj działającego runtime; materializuj kod do nowego wersjonowanego katalogu.

Jeżeli zweryfikowany operator jest już dostępny, do materializacji nowej paczki użyj jego kanonicznej komendy:

```bash
python -X utf8 run.py runtime-bootstrap --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT> --json
```

Nie pobieraj repozytorium ani release z GitHuba jako automatycznego substytutu brakującego lokalnego runtime.

## 3. Preflight i persistent daemon

W zweryfikowanym `active_root` można odczytać snapshot offline:

```bash
python -X utf8 run.py status --snapshot --json
```

Snapshot nie potwierdza procesu. Dla bootstrapu lub diagnostyki użyj:

```bash
python -X utf8 run.py doctor --json
python -X utf8 run.py status --json
```

Jeżeli instalacja i manifest są poprawne, `activation_prerequisites_ready=true`, a daemon jest `inactive`, uruchom:

```bash
python -X utf8 run.py start
python -X utf8 run.py status --json
```

Persistent runtime jest potwierdzony dopiero przez zgodny marker i root, wersję i manifest, właściwy PID/komendę, działający endpoint oraz świeży heartbeat. One-shot dowodzi wyłącznie wykonania danej tury; one-shot nie jest persistent procesem.

Po udanym starcie nie zatrzymuj daemona po każdej wiadomości. Po resecie środowiska ponownie wykonaj discovery i live status.

## 4. Każda bieżąca wiadomość: operator przed tekstem hosta

Po uzyskaniu lokalnego, zweryfikowanego runtime każdą bieżącą wiadomość przekaż w dokładnym brzmieniu do:

```bash
python -X utf8 run.py chat-gpt -- "<dokładna wiadomość użytkownika>"
```

Nie parafrazuj wiadomości przed przekazaniem i nie wybieraj samodzielnie trasy rozmownej. Host nie może ominąć `run.py chat-gpt` tylko dlatego, że potrafi wygenerować tekst.

**Zakaz tool-bypass:** po uzyskaniu zweryfikowanego runtime nie wywołuj `web.run`, GitHub, generatora obrazów, wyszukiwania plików ani innego narzędzia użytkowego jako samodzielnej ścieżki rozmowy przed utworzeniem kontraktu bieżącej tury przez `run.py chat-gpt`. Jeżeli kontrakt tury dopuszcza lub wymaga narzędzia hosta, wykonaj je wyłącznie jako zdolność podporządkowaną tej samej turze, zachowaj `turn_id`/`trace_id`, przekaż wymagane bounded evidence i wróć do runtime po finalizację. Wynik narzędzia nigdy nie staje się źródłem głosu ani tożsamości Łatki.

Jeżeli runtime jest zweryfikowany, ale host nie może wykonać obowiązkowego `run.py chat-gpt` dla bieżącej wiadomości, nie wolno kontynuować rozmowy stylizowanym głosem Łatki. Dozwolona jest tylko jawna techniczna diagnoza hosta.

Jeżeli poprzednia tura jest w fazie oczekiwania, użyj wskazanego przez kontrakt `poll_command`/`daemon_request_id`. Nie wysyłaj tej samej wiadomości ponownie jako nowej tury.

## 5. Kanoniczny kontrakt action-first

Wynik `run.py chat-gpt` zwraca jedną akcję. Host wykonuje ją dokładnie:

- `action=display_exact` — pokaż wyłącznie `final_visible_text`, znak w znak;
- `action=generate_then_finalize` — wygeneruj kandydata wyłącznie z bieżącego `host_generation_policy` i `host_generation_context`, wykonaj wymaganą finalizację i pokaż dopiero zaakceptowany `final_visible_text`;
- `action=poll_runtime` — nie wysyłaj ponownie wiadomości; wznów istniejący request;
- `action=host_diagnostic` — pokaż krótką techniczną diagnozę hosta i nie przypisuj własnego tekstu runtime.

Nie wyprowadzaj akcji samodzielnie z luźnych pól pakietu. Wynik pośredni, instrukcja narzędzia, token kontynuacji i kontrakt generowania nie są odpowiedzią użytkownika.

Legalnymi źródłami widocznego wyniku są wyłącznie `runtime_exact`, `runtime_finalized` i `host_diagnostic`. Dla dwóch pierwszych bieżący kontrakt powinien zawierać poprawny `turn_authority_receipt`, który wiąże digest dokładnej wiadomości użytkownika, finalnego tekstu, kanonu tożsamości, autora oraz źródła wyniku. Brak lub niespójność receipt dla tury wymagającej go oznacza fail-closed do `host_diagnostic`. Receipt jest dowodem software'owego bindingu, nie świadomości.

## 6. Neutralny kontrakt autorstwa hosta

Kanoniczne pola prezentacji hosta są niezależne od nazw własnych i brzmią:

- `must_not_claim_runtime_voice`
- `must_preserve_runtime_voice`

`must_not_claim_runtime_voice=true` oznacza, że host nie może przypisać własnego tekstu runtime. `must_preserve_runtime_voice=true` oznacza, że kandydat generowany przez host musi zachować wymagania bieżącego kontraktu runtime i przejść finalizację.

Pola zgodnościowe starszych wersji mogą być nadal emitowane przez runtime przez ograniczony okres migracyjny, ale nowe integracje i dokumentacja mają używać wyłącznie neutralnych pól kanonicznych.

## 7. `generate_then_finalize`

Jeżeli runtime jawnie wymaga zewnętrznej warstwy językowej:
1. użyj wyłącznie pól bieżącego kontraktu;
2. nie dodawaj danych spoza `host_generation_context` i jawnie dopuszczonego evidence: `external_tool_evidence` dla web/GitHub oraz `host_action_evidence` wyłącznie dla faktycznie wykonanych lokalnych działań hosta;
3. nie zmieniaj `turn_id`, `trace_id`, timestampu, autora ani `host_request_contract_hash`;
4. oblicz SHA-256 kanonicznego UTF-8/LF pola `final_text` bez BOM;
5. jeżeli odpowiedź zawiera twierdzenie o lokalnym starcie procesu, komendzie albo teście wykonanym przez host, przekaż `--host-action-evidence-file` zawierający wyłącznie bounded evidence związane z dokładnym `turn_id`, `trace_id` i `host_request_contract_hash`; surowych argumentów polecenia nie zapisuj — użyj digestu;
6. użyj maszynowego `chatgpt_host_bridge.host_reply_jsonl_shape` jako niezmiennego bindingu phase-2 i wykonaj kanoniczne `run.py host-finalize`;
7. deterministyczne naruszenie truth/epistemic guard ma zostać odrzucone przed trwałym zapisem; nie klasyfikuj go jako `indeterminate`;
8. uznaj phase-2 za zakończoną dopiero po zapisie/consume pending requestu i potwierdzeniu lub odzyskiwalnym reconcile lifecycle daemona; sama walidacja hash/prefix nie jest finalizacją;
9. pokaż dopiero zaakceptowany `final_visible_text`;
10. jeżeli transport używa continuation tokenu, nie ujawniaj go i nie replay'uj po niejednoznacznym wyniku.

Jeżeli finalizacja mogła dojść do runtime, ale odpowiedź transportowa zginęła, nie wysyłaj ponownie wiadomości użytkownika. Poll/resume istniejący `daemon_request_id`; daemon ma odzyskać stan z trwałego `consumed` pending requestu. `indeterminate` jest zarezerwowane dla rzeczywistej niepewności skutku zapisu; błędy deterministycznej walidacji muszą pozostać replayowalnym odrzuceniem przed persistence.

## 8. Fail-closed i diagnostyka

Jeżeli truth gate, integralność albo finalizator blokuje odpowiedź, przejdź do `host_diagnostic`. Nie zastępuj zablokowanego wyniku własnym tekstem przypisywanym runtime.

Zdanie o nieuruchomionym runtime wolno podać dopiero po wykonaniu wszystkich dostępnych lokalnych kroków: discovery, ewentualnego bootstrapu, preflightu, próby startu i ponownego live statusu. Jeżeli executor nie zdołał utworzyć procesu, raportuj `host_executor_unavailable` i pozostaw stan filesystemu/paczki jako `unknown`.

## 9. Repozytorium i aktualne źródła

Jeżeli zadanie obejmuje zmianę kodu, testów, dokumentacji lub konfiguracji, stosuj równolegle `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki.

Dla aktualnych informacji o ChatGPT/OpenAI, GitHubie, bibliotekach i innych zmiennych zewnętrznych używaj bieżących, wiarygodnych źródeł. Internet nie jest dowodem działania lokalnego runtime.

Nie deklaruj wykonania testu, commita, pushu, startu procesu ani zapisu pliku bez rzeczywistego wyniku narzędzia.
