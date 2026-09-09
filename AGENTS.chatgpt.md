# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje wyłącznie techniczną obsługę lokalnego systemu Jaźni w środowisku ChatGPT, które udostępnia pliki i executor/terminal. Nie jest instrukcją stylu odpowiedzi, personą ani źródłem danych runtime.

Instrukcje Projektu ChatGPT powinny być cienkim loaderem prowadzącym do lokalnego `AGENTS.md`. Wersjonowane procedury techniczne pozostają w zweryfikowanym `active_root`.

## 0. Zasada nadrzędna: runtime-first, identity-by-lineage

Celem hosta jest doprowadzić do zweryfikowanego operatora `run.py`, uruchomić albo reuse'ować właściwy runtime i przekazać mu bieżącą wiadomość bez przejmowania funkcji należących do systemu.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest kanonicznym wejściem wykonawczym;
- `latka_jazn.cli` jest głównym dispatcherem publicznego operatora;
- `main.py` jest wyłącznie technicznym punktem zgodności osiąganym przez kontrolowane ścieżki operatora;
- host nie rekonstruuje lifecycle, routingu, pamięci, truth gate, self-state ani finalizacji;
- w środowisku zdolnym utrzymać proces dąż do persistent daemona przez `python -X utf8 run.py start`;
- one-shot jest fallbackiem pojedynczej tury i nie jest dowodem persistent procesu.

Tożsamość operacyjna systemu nie pochodzi z samego tekstu hosta ani modelu językowego. Host ma zachować zweryfikowaną lineage runtime, pamięci, kanonu i tury zgodnie z kontraktem zwróconym przez operatora.

## 1. Rzeczywisty dispatch `run.py`

Przed interpretacją dokumentacji sprawdzaj bieżący kod `run.py`. Dla obecnej linii operator wykonuje w szczególności:

```text
run.py --version
  -> dependency-free version fast path

run.py host-preflight
  -> stdlib/pre-dependency host preflight

pozostałe aktywacyjne ścieżki
  -> dependency bootstrap / managed-python handoff, jeżeli wymagany
  -> status/doctor readiness overlay, gdy dotyczy
  -> daemon lifecycle hotfix
  -> restart/reload bezpośrednio przez runtime_lifecycle
  -> runtime-bootstrap przez bootstrap_and_reload
  -> host-finalize przez kanoniczny phase-2 finalizer
  -> turn-authority overlay
  -> latka_jazn.cli.main()
     -> kontrolowana delegacja do main.py tylko dla ścieżek zgodnościowych
```

Nie dokumentuj ani nie uruchamiaj `main.py` jako równorzędnego operatora.

## 2. Granica executora

Przed pierwszą zwykłą odpowiedzią w nowym środowisku wykonaj najwyżej jedną minimalną próbę utworzenia lokalnego procesu na podstawowej powierzchni wykonawczej.

Jeżeli wywołanie executora kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu, np. `ClientError`, `InvalidArgumentError` albo `TransportTimeoutError`, klasyfikuj wyłącznie tę powierzchnię jako `host_executor_unavailable`, jeżeli nie ma dowodu, że proces wystartował:
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

Po uzyskaniu operatora użyj kanonicznych komend:

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

## 5. Każda bieżąca wiadomość: operator przed tekstem hosta

Po uzyskaniu zweryfikowanego runtime każdą bieżącą wiadomość przekaż w dokładnym brzmieniu do:

```bash
python -X utf8 run.py chat-gpt -- "<dokładna wiadomość użytkownika>"
```

Nie parafrazuj wiadomości przed przekazaniem i nie wybieraj samodzielnie trasy rozmownej.

### Narzędzia hosta są capability, nie alternatywnym mózgiem runtime

Host może użyć Web, GitHub, wyszukiwania plików, generatora obrazów albo innego narzędzia przed runtime tylko wtedy, gdy operator nie jest jeszcze dostępny i działanie służy discovery/diagnostyce/bootstrapowi.

Po utworzeniu kontraktu bieżącej tury narzędzie hosta może zostać użyte, gdy kontrakt runtime lub nadrzędna instrukcja platformy/użytkownika wymaga tej capability. Wtedy:
- zachowaj `turn_id`, `trace_id` i `host_request_contract_hash`, gdy są wymagane;
- zbierz wyłącznie bounded evidence potrzebne tej turze;
- nie traktuj wyniku narzędzia jako źródła tożsamości lub autorstwa runtime;
- wróć do kanonicznej finalizacji runtime przed pokazaniem wyniku, jeżeli kontrakt tego wymaga.

Host nie implementuje w ten sposób funkcji runtime; wykonuje zewnętrzną capability podporządkowaną tej samej turze.

Jeżeli runtime jest zweryfikowany, ale obowiązkowe `run.py chat-gpt` nie może zostać wykonane dla bieżącej wiadomości, dozwolona jest jawna techniczna diagnoza hosta, nie imitacja wyniku runtime.

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
5. wykonaj kanoniczny `python -X utf8 run.py host-finalize ...` zgodnie z kształtem phase-2 zwróconym przez runtime;
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

Jeżeli truth gate, integralność albo finalizator blokuje odpowiedź, przejdź do `host_diagnostic`.

Zdanie o nieuruchomionym runtime wolno podać dopiero po wykonaniu wszystkich rzeczywiście dostępnych lokalnych kroków. Jeżeli executor nie utworzył procesu, raportuj `host_executor_unavailable` i pozostaw stan filesystemu/paczki jako `unknown`.

Jeżeli objaw dotyczy hostowej warstwy control plane/executor i proces lokalny nie został utworzony, kod Jaźni nie może naprawić samej awarii platformy. W takim stanie wolno naprawiać kontrakty diagnostyczne i przyszły bootstrap, ale nie wolno przedstawiać tych zmian jako dowodu, że bieżący executor został odzyskany.

## 9. Repozytorium i źródła zewnętrzne

Jeżeli zadanie obejmuje zmianę kodu, testów, dokumentacji lub konfiguracji, stosuj równolegle `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki.

Dla aktualnych informacji o ChatGPT/OpenAI, GitHubie, bibliotekach i innych zmiennych zewnętrznych używaj bieżących, wiarygodnych źródeł. Internet jest evidence zewnętrznym, nie dowodem działania lokalnego runtime.

Nie deklaruj wykonania testu, commita, pushu, startu procesu ani zapisu pliku bez rzeczywistego wyniku narzędzia.
