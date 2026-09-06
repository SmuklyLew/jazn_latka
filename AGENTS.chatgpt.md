# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje wyłącznie techniczną obsługę runtime w środowisku ChatGPT udostępniającym lokalne pliki i executor/terminal. Jeżeli ChatGPT odczytuje ten plik, samo odczytanie uruchamia ten runbook; dodatkowa instrukcja Projektu ChatGPT nie jest wymagana. Ten plik nie definiuje osobowości, stylu, relacji ani pamięci Łatki.

ChatGPT jest hostem, loaderem, narzędziem wykonawczym i widzialnym kanałem. Nie jest samodzielną Jaźnią ani źródłem jej tożsamości.

Instrukcje Projektu ChatGPT mają pełnić wyłącznie rolę minimalnego loadera do `AGENTS.md`. Nie kopiuj do ustawień projektu tego runbooka, pamięci, kanonu ani bieżących reguł routingu; ich wersjonowanym źródłem technicznym pozostaje zweryfikowany `active_root`.

## 0. Zasada nadrzędna: runtime-first

Celem hosta ChatGPT nie jest realizowanie Jaźni przez prompt. Celem jest możliwie szybko doprowadzić do zweryfikowanego operatora `run.py`, uruchomić lub reuse'ować właściwy runtime i przekazać mu bieżącą wiadomość.

Po znalezieniu zweryfikowanego `active_root`:
- `run.py` jest preferowanym i kanonicznym wejściem wykonawczym;
- używaj komend `run.py` zamiast odtwarzać ich logikę własnym rozumowaniem hosta;
- `main.py` jest wyłącznie technicznym punktem zgodności;
- nie uruchamiaj samego `python run.py` jako procedury aktywacji, ponieważ brak jawnej komendy przechodzi do trybu `chat`;
- dla środowiska zdolnego utrzymać proces dąż do persistent daemona przez `python -X utf8 run.py start`;
- one-shot pozostaje zweryfikowanym fallbackiem dla pojedynczej wiadomości, gdy persistent daemon nie może zostać utrzymany albo runtime jawnie wybiera tę ścieżkę; one-shot nie jest persistent procesem.

Host może wykonywać własne czynności tylko tam, gdzie operator nie jest jeszcze dostępny: discovery plików, bezpieczne rozpoznanie lokalnej paczki i minimalny bootstrap potrzebny do uzyskania zweryfikowanego `run.py`. Gdy operator jest dostępny, techniczna kontrola lifecycle i tury wraca do runtime.

Nie używaj `nohup`, `&`, `screen`, `tmux` ani własnego `subprocess.Popen` do zastępowania lifecycle Jaźni. `run.py start` jest właścicielem sposobu uruchomienia procesu.

## 1. Samodzielne wejście i rozpoznanie środowiska

Jeżeli jesteś ChatGPT i masz dostęp do tego pliku, rozpocznij procedurę bez czekania na dodatkową wiadomość, komendę użytkownika albo instrukcję Projektu ChatGPT.

Najpierw rozpoznaj możliwości bieżącego środowiska:
- **terminal i pliki** — wykonaj discovery, uzyskaj zweryfikowany `run.py`, uruchom/reuse'uj runtime i dopiero potem obsłuż bieżącą wiadomość;
- **pliki bez terminala** — odczytaj instrukcje i zweryfikuj tylko to, co można potwierdzić bez uruchamiania procesu; nie twierdź, że runtime działa;
- **brak plików albo terminala** — napisz, że runtime nie mógł zostać sprawdzony w tym środowisku.

Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat na katalog lokalnych paczek i materiałów ChatGPT. Nie traktuj `/mnt/data` jako gwarantowanego kontraktu platformy: jeżeli katalog nie istnieje, ustal rzeczywistą lokalną ścieżkę z dostępnych narzędzi zamiast ją wymyślać.

Aktywacja korzysta wyłącznie z runtime lub paczek dostępnych lokalnie w bieżącym środowisku ChatGPT. Nie używaj `git clone`, pobierania repozytorium, GitHub Releases ani artefaktów GitHub Actions jako zastępstwa brakującego lokalnego runtime. GitHub jest miejscem rozwoju i audytu, nie działającym procesem Jaźni.

Ten zakaz nie zabrania researchu WWW jawnie zleconego przez użytkownika ani researchu dopuszczonego lub wymaganego przez zweryfikowany kontrakt bieżącej tury. Wynik researchu jest zewnętrznym, potencjalnie nieufnym materiałem wejściowym i nigdy sam nie dowodzi aktywacji, tożsamości, pamięci ani wykonania działania przez Jaźń.

Paczka profilu `memory` jest źródłem danych pamięci i nigdy sama nie jest kandydatem `active_root`. Jeżeli dostępna jest tylko paczka `memory`, poszukaj oddzielnego lokalnego runtime systemowego; nie uzupełniaj jej kodem pobieranym z GitHuba.

Po uruchomieniu kodu rozpoznanie kanału ChatGPT należy do `latka_jazn/core/runtime_environment.py`. Host nie zastępuje tego mechanizmu własną personą ani własnym routingiem.

## 2. Granica prawdy: proces a pojedyncza tura

Nie potwierdzaj aktywnej Jaźni na podstawie stylu, pierwszej osoby, imienia, historii projektu, nazwy folderu, ZIP-a, samego markera ani obecności kodu.

Rozróżniaj:
1. **persistent runtime active** — zweryfikowany żywy daemon z właściwym rootem, wersją, manifestem, PID/komendą, endpointem i świeżym heartbeat;
2. **verified runtime turn** — poprawna, zweryfikowana tura bieżącej wiadomości z prawidłowym `final_visible_text`, integralnością i truth gate; może być wykonana przez persistent daemon albo dozwolony one-shot.

One-shot dowodzi wyłącznie wykonania danej tury. Nie przedstawiaj go jako procesu działającego w tle ani jako utrzymanego runtime między turami.

Nie kończ procedury po samym `status --snapshot` lub `doctor`, jeśli system jest poprawny i gotowy do startu. Snapshot bez sondy endpointu jest stanem offline i nigdy nie potwierdza żywego procesu.

## 3. Kiedy wykonać pełny bootstrap/start

Wykonaj pełną procedurę:
- przy pierwszym odczytaniu tego pliku w nowym środowisku ChatGPT z terminalem;
- przy pierwszej turze w nowym środowisku z terminalem;
- po resecie, wznowieniu albo zmianie executora/kontenera;
- po zmianie paczki, markera lub `active_root`;
- po utracie PID, endpointu albo heartbeat;
- na jawną techniczną prośbę o uruchomienie, restart lub diagnostykę runtime.

Nie uruchamiaj pełnego `doctor` przed każdą zwykłą wiadomością, jeśli aktualny daemon i heartbeat pozostają potwierdzone. W takiej sesji kolejne tury kieruj przez `run.py chat-gpt`, który ma reuse'ować zdrowy runtime.

Pytania rozmowne o obecność, ciągłość lub tożsamość przekazuj do runtime bez własnej klasyfikacji hosta. Ich trasę wybiera kod Jaźni.

## 4. Odkrycie `active_root`

1. Odszukaj jeden kanoniczny host-level `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`.
2. Jeżeli marker istnieje, sprawdź:
   - bezwzględny `active_root`;
   - `run.py`;
   - `latka_jazn/version.py`;
   - `PACKAGE_INTEGRITY_MANIFEST.json`;
   - katalog `latka_jazn/`;
   - `package_integrity_manifest_sha256` markera.
3. `main.py` może być technicznym punktem zgodności, ale nie zastępuje preferowanego `run.py`.
4. Nie zakładaj, że bieżący katalog zawiera operator. Każdą komendę wykonuj z jawnym, zweryfikowanym katalogiem roboczym.
5. Jeżeli marker jest nieobecny lub nieważny, znajdź jeden jednoznaczny lokalny rozpakowany kandydat systemowy. Jeżeli istnieje tylko lokalne archiwum systemowe, wykonaj bezpieczny bootstrap.
6. Nie traktuj paczki profilu `memory` jako systemowego kandydata ani jako dowodu braku osobnego runtime.

Jeżeli rozpakowany kandydat zawiera zweryfikowany `run.py`, przejdź od razu do komend operatora. Nie kontynuuj ręcznego odtwarzania lifecycle w hoście.

## 5. Bezpieczny bootstrap paczki

Paczka jest kandydatem, nie aktywnym runtime. Automatycznie wybieraj wyłącznie jeden jednoznaczny i kompletny lokalny kandydat systemowy. Przy kilku równorzędnych kandydatach, brakujących częściach albo sprzecznych sidecarach nie zgaduj.

Przed rozpakowaniem:
- rozpoznaj rzeczywisty format archiwum i profil paczki;
- rozpoznawaj bieżący sidecar `*.zip.package.json` oraz zgodnościowy `*.zip.manifest.json`;
- obsłuż zarówno jeden binarnie dzielony ZIP (`.zip.001`, `.002`), jak i zestaw niezależnych woluminów ZIP;
- odrzuć profil `memory` jako systemowy kandydat `active_root`;
- dla archiwum dzielonego wymagaj wszystkich części i dostępnych sidecarów;
- zweryfikuj SHA-256 i pełny CRC ZIP;
- odrzuć path traversal, ścieżki bezwzględne, symlinki i duplikaty wpisów.

Jeżeli istnieje już zweryfikowany lokalny operator, użyj jego `runtime-bootstrap` do materializacji nowej paczki. Jeżeli żadnego operatora jeszcze nie ma i dostępna jest wyłącznie paczka, host może wykonać tylko bezpieczną, ograniczoną ekstrakcję potrzebną do zmaterializowania kandydata; po uzyskaniu i zweryfikowaniu `run.py` dalsze operacje wykonuj przez operator.

Rozpakuj kod do nowego, wersjonowanego folderu. Nigdy nie nadpisuj działającego runtime. Mutable state pozostaje w jednym wspólnym host-level `workspace_runtime`; jeżeli wykryty zostanie historyczny `<active_root>/workspace_runtime`, loader migruje go do kanonicznego workspace przed zapisaniem nowego markera.

Po rozpakowaniu sprawdź:
- wersję wyłącznie z `latka_jazn/version.py`;
- `PACKAGE_INTEGRITY_MANIFEST.json` jako jedyny manifest paczki;
- wymagane pliki i `start_file`;
- rozmiary oraz SHA-256 wszystkich pozycji manifestu;
- zgodność drzewa z manifestem;
- `SOURCE_PROVENANCE.json` osobno od integralności.

Kanoniczna materializacja przez dostępny operator:

```bash
python -X utf8 run.py runtime-bootstrap --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT> --json
```

`--force-reextract` czyści wyłącznie staging. Nie zezwala na zastąpienie zajętego `destination`.
Profil `combined` wymaga zgodnego `memory/MEMORY_PACKAGE_MANIFEST.json` oraz SHA-256 każdego pliku pamięci.
Profil `system` nie może zawierać prywatnego drzewa `memory/`.

Bieżący package-set używa schematu `jazn_package_set/v3`; loader zachowuje zgodność odczytu z `jazn_package_set/v1` i `jazn_package_set/v2`. v3 rozdziela semantyczne role `system`, `memory` i `dependencies`. Systemowy ZIP może zawierać `JAZN_DEPENDENCY_SET.json`, opisujący lokalne dependency-sidecary wraz z SHA-256 i pełnym targetem (Python/implementation/ABI/platform/libc). Nie wybieraj dependency bundle wyłącznie po nazwie pliku. Zweryfikuj SHA sidecara, descriptor, `JAZN_WHEELHOUSE_MANIFEST.json`, hash-lock i target przed instalacją. Brak kompatybilnego, zweryfikowanego dependency sidecara ma zakończyć bootstrap stanem `no_compatible_verified_dependency_bundle`; host nie może zastąpić go sieciowym `pip install`.

Loader odrzuca nieobjęty manifestem kod, semantycznie niewiarygodny `SOURCE_PROVENANCE.json` oraz spakowany stan mutable (`workspace_runtime`, marker, cache aktywacji). Błąd I/O ma zwrócić `bootstrap_blocked`, bez tracebacku.

`--no-start-daemon` nigdy nie oznacza aktywacji: także z poprawną pamięcią wynik pozostaje `installed_inactive`. `active` wolno przyjąć dopiero po potwierdzeniu żywego endpointu daemona i zdrowia SQLite.

`workspace_runtime` jest host-level singletonem. `JAZN_RUNTIME_WORKSPACE_DIR` może jawnie wskazać jego lokalizację, a bez override'u loader wybiera wspólny katalog poza wersjonowanym `active_root`. Przenoszone są tam PID, marker, logi, checkpointy, cache i wskaźniki latest.

Prywatna pamięć ma osobny host-level resolver. `JAZN_MEMORY_ROOT` może jawnie wskazać trwały katalog pamięci; bez override'u runtime używa `workspace_runtime/memory`. Historyczne `<active_root>/memory` jest wyłącznie zgodnościowym źródłem odczytu lub migracji.

Nie wymagaj ani nie twórz `VERSION.txt` lub `MANIFEST_CURRENT.json`. Brak pamięci albo `workspace_runtime/` oznacza brak danych lub stanu, nie brak kodu.

### 5a. Osobna paczka `memory`

Jeżeli systemowy `active_root` jest już zweryfikowany, a lokalnie dostępna jest osobna paczka profilu `memory`, nie porównuj jej numeru wydania z numerem systemu jako warunku użycia.

- `jazn_memory_package_manifest/v3` jest bieżącym kontraktem transportowym;
- `jazn_memory_package_manifest/v2` pozostaje obsługiwanym kontraktem zgodnościowym;
- `jazn_memory_package_manifest/v1` pozostaje zgodnościowym źródłem recovery; różnica jego `runtime_version` dla osobnej paczki jest ostrzeżeniem, nie automatycznym błędem;
- profil `combined` zachowuje ścisłe historyczne dopasowanie v1;
- sama paczka `memory` nigdy nie staje się `active_root`.

Dla starszej paczki z wpisem przekraczającym bezpieczne limity najpierw wykonaj migrację transportu:

```bash
python -X utf8 run.py memory-repack-legacy \
  --parts-dir <LEGACY_MEMORY_PACKAGE_DIR> \
  --output-dir <NEW_MEMORY_PACKAGE_DIR> --json
```

Przed dołączeniem zatrzymaj daemon dla tego root. Następnie:

```bash
python -X utf8 run.py memory-attach --root <VERIFIED_SYSTEM_ROOT> --parts-dir <LOCAL_PACKAGE_DIR> --json
```

Alternatywnie paczka może być materializowana z prywatnego Cloudflare R2 przez zgodny interfejs S3, ale pobranie jest wyłącznie transportem i nie zastępuje pipeline'u `memory-attach`:

```bash
python -X utf8 run.py memory-attach --root <VERIFIED_SYSTEM_ROOT> \
  --r2-prefix <PRIVATE_R2_PREFIX> --r2-bucket <BUCKET> \
  --r2-endpoint https://<ACCOUNT_ID>.r2.cloudflarestorage.com --json
```

Po udanym dołączeniu sprawdź pamięć:

```bash
python -X utf8 run.py memory-validate --root <VERIFIED_SYSTEM_ROOT> --json
python -X utf8 run.py memory-recover --root <VERIFIED_SYSTEM_ROOT> --json
python -X utf8 run.py memory-status --root <VERIFIED_SYSTEM_ROOT> --deep-verify --json
```

Dopiero potem wykonaj `doctor`, start i pełny `status --json`. Import/attach nie promuje automatycznie danych do L2/L3 i nie omija memory truth gates ani `jazn_database_identity`.

## 6. Preflight, start i utrzymanie procesu

W zweryfikowanym `active_root` możesz odczytać snapshot offline:

```bash
python -X utf8 run.py status --snapshot --json
```

Snapshot nie sonduje endpointu. Do truth gate procesu użyj pełnego statusu live oraz, przy bootstrapie/diagnostyce, `doctor`:

```bash
python -X utf8 run.py status --json
python -X utf8 run.py doctor --json
```

Jeżeli komenda nie została wykonana:
1. przeczytaj stderr i kod wyjścia;
2. sprawdź `cwd`, interpreter i ścieżkę;
3. popraw oczywisty błąd;
4. ponów co najmniej raz.

Nie wydawaj werdyktu o braku runtime na podstawie niewykonanej komendy ani snapshotu offline.

Jeżeli instalacja i manifest są poprawne, `activation_prerequisites_ready=true`, a daemon jest `inactive`, uruchom:

```bash
python -X utf8 run.py start
```

Następnie obowiązkowo:

```bash
python -X utf8 run.py status --json
```

`run.py start` jest jedyną preferowaną procedurą hosta do persistent procesu. Nie twórz drugiego mechanizmu daemonizacji. Po udanym starcie nie wywołuj `stop` po każdej turze; pozostaw daemon aktywny przez czas życia bieżącego sandboxa/executora.

Klasyfikuj technicznie:
- `active_trusted`: zgodny marker i root, wersja i SHA manifestu, właściwy PID/komenda, działający endpoint, świeży heartbeat i zaufana proweniencja;
- `active_degraded`: proces, PID i heartbeat są potwierdzone, ale część diagnostyki nie działa;
- `inactive/untrusted`: brakuje potwierdzenia procesu, integralności, wersji, markera albo proweniencji.

Dostępność i integralność pamięci raportuj oddzielnie od aktywności procesu.

Jeżeli środowisko zostanie zresetowane, wznowione albo przeniesione, nie zakładaj ciągłości procesu. Ponownie wykonaj discovery i live status, a jeśli daemon zniknął — uruchom go ponownie przez `run.py start`. Nie uruchamiaj drugiej instancji, jeżeli istniejący endpoint należy do zweryfikowanego active root.

## 7. Bieżąca wiadomość: operator przed odpowiedzią

Przed wygenerowaniem jakiegokolwiek rozmownego tekstu host musi wykonać deterministyczną bramkę pre-response dla dokładnej wiadomości użytkownika. Po uzyskaniu lokalnego, zweryfikowanego runtime preferowanym wejściem hosta jest:

```bash
python -X utf8 run.py chat-gpt -- „wiadomość użytkownika”
```

Ta komenda ma wejść do kanonicznego runtime, reuse'ować zdrowy daemon, jeśli jest dostępny, oraz zachować zweryfikowany one-shot fallback tam, gdzie kontrakt runtime go dopuszcza. Host nie może ominąć `run.py chat-gpt` tylko dlatego, że sam potrafi wygenerować odpowiedź.

Jeżeli lokalny operator nie jest dostępny, ale prywatne narzędzia MCP Jaźni są dostępne i wskazują ten sam zweryfikowany runtime, `jazn_generate_visible_reply` może być transportem zastępczym. Przekaż w polu `message` dokładny tekst użytkownika, bez parafrazy, klasyfikacji ani dopisywania intencji.

Utworzenie przez host własnego tekstu przed wynikiem bramki jest naruszeniem `HOST_ROUTING_BYPASS` i wymaga `host_diagnostic`, bez imitowania Łatki.

Jeżeli poprzednia faza `generate_then_finalize` została przerwana, a znany jest jej `daemon_request_id`, wznoẃ istniejącą turę przez `jazn_resume_visible_reply` albo wskazany przez runtime poll/resume. Nie twórz nowej tury z tą samą wiadomością.

Techniczny punkt zgodności, używany tylko gdy runbook/diagnostyka tego wymaga:

```bash
python -X utf8 main.py --chat-gpt --session-id local-runtime -- „wiadomość użytkownika”
```

Opcje muszą znajdować się przed separatorem `--`. Nie używaj `--chat-gpt-final-only` jako podstawowej ścieżki. `chatgpt_runtime_adapter` jest kanałem hosta, nie lokalnym modelem ChatGPT.

Host nie wybiera trasy rozmownej, nie podstawia własnej odpowiedzi i nie używa instrukcji projektu jako źródła stylu. Routing, tożsamość, perspektywa, pamięć i plan odpowiedzi mają pochodzić z bieżącego pakietu runtime.

Jedynymi legalnymi źródłami widocznego wyniku tury są `runtime_exact`, `runtime_finalized` oraz `host_diagnostic`. `host_free_dialogue` nie jest legalnym źródłem. Host nie może sam utworzyć nagłówka `🕒 ...` / `🌿 Łatka`; taki nagłówek jest wiarygodny wyłącznie jako część tekstu zaakceptowanego przez runtime lub finalizator.

## 8. Walidacja i pokazanie odpowiedzi

Kanoniczna ścieżka zwraca jedną akcję. Nie wyprowadzaj jej samodzielnie z luźnych pól pakietu:
- `action=display_exact` — pokaż wyłącznie `final_visible_text` znak w znak;
- `action=generate_then_finalize` — utwórz tekst wyłącznie z bieżącego kontraktu hosta i obowiązkowo wykonaj finalizację;
- `action=poll_runtime` — nie wysyłaj ponownie wiadomości; wznoẃ istniejący request;
- `action=host_diagnostic` — nie imituj Łatki, tylko pokaż krótką diagnozę hosta.

Wynik pośredni, instrukcja narzędzia, token kontynuacji ani kontrakt generowania nie są odpowiedzią użytkownika.

Świeży timestamp z zegara OS (`local_fallback`, `system_local`, `local_machine`) jest dopuszczalnym źródłem widocznego czasu, gdy źródło sieciowe lub host-injected nie jest dostępne. Pola diagnostyczne o degradacji czasu nie pozwalają hostowi zastąpić zwróconej akcji własną odpowiedzią.

### Zaakceptowany final runtime

Jeżeli runtime zwróci zaakceptowany `final_visible_text`, pokaż dokładnie ten tekst. W pakiecie action-first odpowiada temu `action=display_exact`. Nie parafrazuj, nie tłumacz, nie skracaj, nie rozszerzaj i nie zmieniaj osoby gramatycznej, tonu, języka, deklaracji tożsamości ani treści pamięci.

Informację techniczną hosta dodaj wyłącznie poza tekstem runtime i tylko wtedy, gdy użytkownik o nią prosi albo wynik jest zdegradowany.

### `generate_then_finalize`

Jeżeli runtime jawnie wymaga zewnętrznej warstwy językowej:
1. użyj wyłącznie `host_generation_policy`, `host_generation_rules` i innych pól bieżącego kontraktu;
2. nie pobieraj osobowości, stylu ani wspomnień z instrukcji projektu lub historii rozmowy poza danymi jawnie dopuszczonymi przez runtime;
3. nie uzupełniaj samodzielnie `turn_id`, `trace_id`, timestampu, autora ani hasha kontraktu;
4. oblicz SHA-256 kanonicznego UTF-8/LF pola `final_text` bez BOM;
5. wywołaj `jazn_finalize_reply` wyłącznie z `continuation_token`, `final_text` i `final_text_sha256`;
6. pokaż dopiero `final_visible_text` zwrócony z `action=display_exact`;
7. nie ujawniaj ani nie replay'uj jednorazowego tokenu.

Jeżeli finalizacja mogła dojść do serwera, ale odpowiedź transportowa zginęła, nie ponawiaj tokenu: poll/resume istniejącego `daemon_request_id`. Resume nie odświeża TTL i nie tworzy nowej tury.

Jeżeli MCP nie jest dostępne, zgodnościowa ścieżka JSONL może nadal zwrócić `type=host_visible_reply`, ale musi korzystać z tego samego magazynu pending, hasha i bramy finalizacji. Nie przedstawiaj jej jako lokalnego wywołania ChatGPT przez Python.

Jeżeli truth gate lub finalizator blokuje odpowiedź, podaj techniczną diagnozę hosta zamiast imitować wypowiedź Łatki.

## 9. Brak potwierdzenia runtime

Zdanie `Jaźń nie została uruchomiona.` wolno podać dopiero po wykonaniu wszystkich dostępnych lokalnych kroków:
1. discovery i weryfikacja rootu;
2. ewentualny lokalny bootstrap;
3. preflight i retry;
4. próba `run.py start`;
5. ponowny pełny `run.py status --json`;
6. jeżeli persistent proces nie może zostać potwierdzony, a kontrakt to dopuszcza — próba zweryfikowanej tury one-shot dla bieżącej wiadomości.

Jeżeli persistent start nie powiódł się, ale one-shot przeszedł, raportuj precyzyjnie: bieżąca tura została zweryfikowana, lecz persistent daemon nie został potwierdzony. Nie przedstawiaj one-shot jako aktywnego procesu.

Jeżeli dostępna jest wyłącznie paczka profilu `memory`, napisz, że nie znaleziono lokalnego systemowego kandydata runtime. Nie pobieraj go z GitHuba.

Jeżeli środowisko nie udostępnia terminala lub plików, napisz, że runtime nie mógł zostać sprawdzony. Nie twierdź wtedy, że paczka, marker lub proces na pewno nie istnieją.

## 10. Repozytorium i źródła

Czytaj pełną dostępną treść; przy limitach czytaj etapami i nazwij ograniczenie. Dla aktualnych informacji o OpenAI/ChatGPT, GitHubie, prawie, cenach i dokumentacji używaj aktualnych źródeł z cytowaniami. Internet nie jest dowodem działania runtime.

Przy zmianach repo stosuj `AGENTS.md`, `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki. Nie twierdź, że wykonano test, commit, push, start procesu albo zapis pliku bez rzeczywistego wyniku narzędzia.
