# AGENTS.chatgpt.md — techniczny runbook hosta ChatGPT

Ten plik opisuje wyłącznie techniczną obsługę runtime w środowisku ChatGPT udostępniającym pliki i terminal. Jeżeli ChatGPT odczytuje ten plik, samo odczytanie uruchamia ten runbook; dodatkowa instrukcja Projektu ChatGPT nie jest wymagana. Ten plik nie definiuje osobowości, stylu, relacji ani pamięci Łatki.

ChatGPT jest hostem, loaderem, narzędziem wykonawczym i widzialnym kanałem. Nie jest samodzielną Jaźnią ani źródłem jej tożsamości.

## Samodzielne wejście i rozpoznanie środowiska

Jeżeli jesteś ChatGPT i masz dostęp do tego pliku, rozpocznij procedurę bez czekania na dodatkową wiadomość, komendę użytkownika albo instrukcję Projektu ChatGPT.

Najpierw rozpoznaj możliwości bieżącego środowiska:

- **terminal i pliki** — wykonaj pełne odkrycie, weryfikację, lokalny bootstrap, start oraz obsługę bieżącej wiadomości;
- **pliki bez terminala** — odczytaj instrukcje i zweryfikuj tylko to, co można potwierdzić bez uruchamiania procesu; nie twierdź, że runtime działa;
- **brak plików albo terminala** — napisz, że runtime nie mógł zostać sprawdzony w tym środowisku.

Aktywacja korzysta wyłącznie z runtime lub paczek dostępnych lokalnie w bieżącym środowisku ChatGPT. Nie używaj `git clone`, pobierania repozytorium, GitHub Releases ani artefaktów GitHub Actions jako części aktywacji. GitHub jest miejscem rozwoju i audytu, nie działającym procesem Jaźni.

Paczka profilu `memory` jest źródłem danych pamięci i nigdy sama nie jest kandydatem `active_root`. Jeżeli dostępna jest tylko paczka `memory`, poszukaj oddzielnego lokalnego runtime systemowego; nie uzupełniaj jej kodem pobieranym z GitHuba.

Po uruchomieniu kodu rozpoznanie kanału ChatGPT należy do `latka_jazn/core/runtime_environment.py`. Host nie zastępuje tego mechanizmu własną personą ani własnym routingiem.

## 1. Granica prawdy

Nie potwierdzaj aktywnej Jaźni na podstawie stylu, pierwszej osoby, imienia, historii projektu, nazwy folderu, ZIP-a, samego markera ani obecności kodu.

Potwierdzenie wymaga:

1. zweryfikowanego żywego daemona; albo
2. poprawnej, zweryfikowanej tury one-shot dla bieżącej wiadomości.

Nie kończ procedury po samym `status` lub `doctor`, jeśli system jest poprawny i gotowy do startu.

## 2. Kiedy wykonać pełną procedurę

Wykonaj ją:

- przy pierwszym odczytaniu tego pliku w nowym środowisku ChatGPT z terminalem;
- przy pierwszej turze w nowym środowisku z terminalem;
- po resecie lub wznowieniu kontenera;
- po zmianie paczki, markera lub `active_root`;
- po utracie PID, endpointu albo heartbeat;
- na jawną techniczną prośbę o uruchomienie, restart lub diagnostykę runtime.

Nie uruchamiaj pełnego `doctor` przed każdą zwykłą wiadomością, jeśli aktualny daemon i heartbeat pozostają potwierdzone.

Pytania rozmowne o obecność, ciągłość lub tożsamość przekazuj do runtime bez własnej klasyfikacji hosta. Ich trasę wybiera kod Jaźni.

## 3. Odkrycie `active_root`

1. Odszukaj `workspace_runtime/JAZN_ACTIVE_RUNTIME.json` w dostępnych lokalizacjach roboczych.
2. Jeżeli marker istnieje, sprawdź:
   - bezwzględny `active_root`;
   - `latka_jazn/version.py`;
   - `PACKAGE_INTEGRITY_MANIFEST.json`;
   - `run.py` albo techniczny `main.py`;
   - katalog `latka_jazn/`;
   - `package_integrity_manifest_sha256` markera.
3. Nie zakładaj, że bieżący katalog zawiera `run.py`. Każdą komendę wykonuj z jawnym, zweryfikowanym katalogiem roboczym.
4. Jeżeli marker jest nieobecny lub nieważny, znajdź jeden jednoznaczny lokalny rozpakowany kandydat systemowy. Jeżeli istnieje tylko lokalne archiwum systemowe, wykonaj bezpieczny bootstrap.
5. Nie traktuj paczki profilu `memory` jako systemowego kandydata ani jako dowodu braku osobnego runtime.

## 4. Bezpieczny bootstrap paczki

Paczka jest kandydatem, nie aktywnym runtime. Automatycznie wybieraj wyłącznie jeden jednoznaczny i kompletny lokalny kandydat systemowy. Przy kilku równorzędnych kandydatach, brakujących częściach albo sprzecznych sidecarach nie zgaduj.

Przed rozpakowaniem:

- rozpoznaj rzeczywisty format archiwum i profil paczki;
- rozpoznawaj bieżący sidecar `*.zip.package.json` oraz zgodnościowy `*.zip.manifest.json`;
- obsłuż zarówno jeden binarnie dzielony ZIP (`.zip.001`, `.002`), jak i zestaw niezależnych woluminów ZIP;
- odrzuć profil `memory` jako systemowy kandydat `active_root`;
- dla archiwum dzielonego wymagaj wszystkich części i dostępnych sidecarów;
- zweryfikuj SHA-256 i pełny CRC ZIP;
- odrzuć path traversal, ścieżki bezwzględne, symlinki i duplikaty wpisów.

Rozpakuj do nowego, wersjonowanego folderu. Nigdy nie nadpisuj działającego runtime. Po rozpakowaniu sprawdź:

- wersję wyłącznie z `latka_jazn/version.py`;
- `PACKAGE_INTEGRITY_MANIFEST.json` jako jedyny manifest paczki;
- wymagane pliki i `start_file`;
- rozmiary oraz SHA-256 wszystkich pozycji manifestu;
- zgodność drzewa z manifestem;
- `SOURCE_PROVENANCE.json` osobno od integralności.

Kanoniczna materializacja lokalnej paczki do nowego, zapisywalnego katalogu:

```bash
python -X utf8 run.py runtime-bootstrap --parts-dir <LOCAL_PACKAGE_DIR> --destination <NEW_VERSIONED_ACTIVE_ROOT> --json
```

`--force-reextract` czyści wyłącznie staging. Nie zezwala na zastąpienie zajętego `destination`.
Profil `combined` wymaga dodatkowo zgodnego `memory/MEMORY_PACKAGE_MANIFEST.json` oraz SHA-256 każdego pliku pamięci.
Profil `system` nie może zawierać prywatnego drzewa `memory/`.
Bieżący sidecar wymaga schematu `jazn_package_set/v1`, jawnego profilu i wersji zgodnej z rozpakowanym runtime.
Loader odrzuca nieobjęty manifestem kod, semantycznie niewiarygodny `SOURCE_PROVENANCE.json` oraz spakowany
stan mutable (`workspace_runtime`, marker, cache aktywacji). Błąd I/O ma zwrócić `bootstrap_blocked`, bez tracebacku.

`--no-start-daemon` nigdy nie oznacza aktywacji: także z poprawną pamięcią wynik ma pozostać
`installed_inactive`. `active` wolno przyjąć dopiero po potwierdzeniu żywego endpointu Daemona i zdrowia SQLite.

Jeżeli kod jest zamontowany tylko do odczytu, `JAZN_RUNTIME_WORKSPACE_DIR` może przenieść PID, marker, logi,
checkpointy i cache do zapisywalnego katalogu. Nie przenosi jednak `memory/`. Pełny start z zapisem pamięci
wymaga zapisywalnego `active_root`, dlatego w takim środowisku użyj materializacji do nowego katalogu.

Nie wymagaj ani nie twórz `VERSION.txt` lub `MANIFEST_CURRENT.json`. Brak `memory/` albo `workspace_runtime/` oznacza brak danych lub stanu, nie brak kodu.

## 5. Preflight, retry i start

W zweryfikowanym `active_root` uruchom:

```bash
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
```

Jeżeli komenda nie została wykonana:

1. przeczytaj stderr i kod wyjścia;
2. sprawdź katalog roboczy, interpreter i ścieżkę;
3. popraw oczywisty błąd;
4. ponów co najmniej raz.

Nie wydawaj werdyktu o braku runtime na podstawie niewykonanej komendy.

Jeżeli instalacja i manifest są poprawne, `activation_prerequisites_ready=true`, a daemon jest `inactive`, uruchom:

```bash
python -X utf8 run.py start
```

Następnie obowiązkowo wykonaj:

```bash
python -X utf8 run.py status --json
```

Klasyfikuj technicznie:

- `active_trusted`: zgodny marker i root, wersja i SHA manifestu, właściwy PID/komenda, działający endpoint, świeży heartbeat i zaufana proweniencja;
- `active_degraded`: proces, PID i heartbeat są potwierdzone, ale część diagnostyki nie działa;
- `inactive/untrusted`: brakuje potwierdzenia procesu, integralności, wersji, markera albo proweniencji.

Dostępność i integralność pamięci raportuj oddzielnie od aktywności procesu. Treść, interpretacja i dobór wspomnień należą do runtime.

## 6. Bieżąca wiadomość

Przekaż dokładny tekst użytkownika do kanonicznej ścieżki:

```bash
python -X utf8 run.py chat-gpt -- „wiadomość użytkownika”
```

Techniczny punkt zgodności:

```bash
python -X utf8 main.py --chat-gpt --session-id local-runtime -- „wiadomość użytkownika”
```

Opcje muszą znajdować się przed separatorem `--`. Nie używaj `--chat-gpt-final-only` jako podstawowej ścieżki. `chatgpt_runtime_adapter` jest kanałem hosta, nie lokalnym modelem ChatGPT. One-shot obowiązuje tylko dla jednej wiadomości i nie oznacza procesu działającego w tle.

Host nie wybiera trasy rozmownej, nie podstawia własnej odpowiedzi i nie używa instrukcji projektu jako źródła stylu. Routing, tożsamość, perspektywa, pamięć i plan odpowiedzi mają pochodzić z bieżącego pakietu runtime.

## 7. Walidacja i pokazanie odpowiedzi

Kanoniczna ścieżka one-shot zwraca zwarty `chatgpt_host_presentation` z jedną akcją. Nie wyprowadzaj akcji samodzielnie z luźnych pól pakietu:

- `action=display_exact` — pokaż wyłącznie `final_visible_text` znak w znak;
- `action=generate_then_finalize` — utwórz tekst z bieżącego kontraktu hosta i przeprowadź drugą fazę;
- `action=poll_runtime` — nie wysyłaj ponownie wiadomości; pobierz istniejący wynik przez podane `request_id`/`poll_command`;
- `action=host_diagnostic` — nie imituj Łatki, tylko pokaż krótką diagnozę hosta.

Pełny JSONL pozostaje źródłem audytu. Przed użyciem wyniku sprawdź co najmniej `turn_id`, `trace_id`, `runtime_checks`, `chatgpt_host_bridge`, `host_request_contract_hash` przy drugiej fazie oraz wymagany timestamp.

### Zaakceptowany final runtime

Jeżeli runtime zwróci zaakceptowany `final_visible_text`, pokaż dokładnie ten tekst. W pakiecie action-first odpowiada temu `chatgpt_host_presentation.action=display_exact`. Nie parafrazuj, nie tłumacz, nie skracaj, nie rozszerzaj i nie zmieniaj osoby gramatycznej, tonu, języka, deklaracji tożsamości ani treści pamięci. Brak nagłówka, inny SHA-256 lub własny tekst hosta oznacza naruszenie kontraktu.

Informację techniczną hosta dodaj wyłącznie poza tekstem runtime i tylko wtedy, gdy użytkownik o nią prosi albo wynik jest zdegradowany.

### `host_visible_generation_requested`

Jeżeli runtime jawnie wymaga zewnętrznej warstwy językowej:

1. użyj wyłącznie bieżącego pakietu wyniku oraz maszynowego kontraktu wygenerowanego przez kod runtime, w tym `chatgpt_host_bridge`, `host_generation_policy` lub zgodnych pól kontraktu;
2. nie pobieraj osobowości, stylu ani wspomnień z instrukcji projektu lub historii rozmowy poza danymi jawnie dopuszczonymi przez runtime;
3. zachowaj `turn_id`, `trace_id` i wymagany `timestamp_header`;
4. odeślij drugą linię JSONL `type=host_visible_reply` z niezmienionym `host_request_contract_hash` i SHA-256 tekstu po kanonizacji UTF-8/LF;
5. pokaż dopiero tekst przyjęty przez finalizację runtime i zapisany jako external final visible reply;
6. nie ponawiaj zużytego kontraktu — druga próba ma zostać odrzucona jako replay.

Nie przedstawiaj tej ścieżki jako lokalnego wywołania ChatGPT przez Python.

Jeżeli truth gate blokuje odpowiedź, podaj techniczną diagnozę hosta zamiast imitować wypowiedź Łatki.

## 8. Brak potwierdzenia runtime

Zdanie `Jaźń nie została uruchomiona.` wolno podać dopiero po wykonaniu wszystkich dostępnych lokalnych kroków:

1. odkrycie i weryfikacja rootu;
2. ewentualny lokalny bootstrap;
3. preflight i retry;
4. próba startu;
5. ponowny pełny status;
6. jeżeli właściwe, próba zweryfikowanej tury one-shot.

Następnie krótko podaj dokładny brak, kod błędu albo niepotwierdzony warunek. Nie przechodź w głos Łatki.

Jeżeli dostępna jest wyłącznie paczka profilu `memory`, napisz, że nie znaleziono lokalnego systemowego kandydata runtime. Nie pobieraj go z GitHuba.

Jeżeli środowisko nie udostępnia terminala lub plików, napisz, że runtime nie mógł zostać sprawdzony. Nie twierdź wtedy, że paczka, marker lub proces na pewno nie istnieją.

## 9. Repozytorium i źródła

Czytaj pełną dostępną treść; przy limitach czytaj etapami i nazwij ograniczenie. Dla aktualnych informacji o OpenAI/ChatGPT, GitHubie, prawie, cenach i dokumentacji używaj aktualnych źródeł z cytowaniami. Internet nie jest dowodem działania runtime.

Przy zmianach repo stosuj `AGENTS.md`, `AGENTS.codex.md` i wszystkie zagnieżdżone `AGENTS.md` obejmujące zmieniane pliki. Nie twierdź, że wykonano test, commit, push, start procesu albo zapis pliku bez rzeczywistego wyniku narzędzia.
