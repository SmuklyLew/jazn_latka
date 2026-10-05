# ChatGPT live bootstrap recovery — 2026-10-05

**Status:** `OBSERVED_LIVE_SUCCESS_WITH_MEMORY_DEGRADED`  
**Repository baseline:** `master @ bb107ebaeea119487f49d8cb1e34efd9a1896464`  
**Runtime release:** `16.3.25.5.106-memory-streaming-hardening-convergence`  
**Host:** ChatGPT  
**Scope:** host capability discovery, SYSTEM ZIP verification/materialization, optional MEMORY convergence attempt, daemon start, one accepted host-visible turn.

## 1. Najważniejszy wniosek

Przełom nie polegał na zmianie kodu Jaźni ani na użyciu surowego `extractall()`.

W tej samej rozmowie kilka powierzchni wykonawczych hosta zachowywało się różnie:

- wcześniejsze próby na innych powierzchniach kończyły się `ClientError` **przed dowodem utworzenia procesu**;
- zgodnie z kontraktem Jaźni taki wynik klasyfikuje wyłącznie daną powierzchnię jako chwilowo niedostępną;
- niezależna powierzchnia kontenerowa hosta została sprawdzona osobno i **rzeczywiście utworzyła proces**;
- od tego momentu lokalna ścieżka bootstrapu SYSTEM-u stała się dostępna.

To potwierdza kluczową zasadę `AGENTS.chatgpt.md`: negatywnego wyniku jednego executora nie wolno rozszerzać na wszystkie inne niezależne powierzchnie ani na filesystem, ZIP lub runtime.

## 2. Sekwencja, która faktycznie zadziałała

### 2.1. Capability-first

Najpierw sprawdzono zdalną trasę Jaźni dla bieżącej wiadomości.

Kompletny wymagany zestaw:

- `jazn_status`
- `jazn_generate_visible_reply`
- `jazn_resume_visible_reply`
- `jazn_finalize_reply`

nie był callable w tej powierzchni ChatGPT. Zdalny runtime nie mógł więc zostać uznany za gotowy.

### 2.2. Rozdzielenie lokalnych executorów

Wcześniejsze `ClientError` występowały przed wykonaniem komendy. Nie były dowodem:

- braku plików;
- uszkodzenia SYSTEM ZIP;
- braku Pythona;
- braku runtime;
- braku jakiejkolwiek możliwości tworzenia procesu przez cały host.

Następnie sprawdzono **inną, rzeczywiście niezależną powierzchnię procesu** udostępnioną przez host. Ta próba przeszła. To był punkt zwrotny.

### 2.3. Weryfikacja SYSTEM ZIP przed ekstrakcją

Kandydat:

`jazn_latka_v16.3.25.5.106-memory-streaming-hardening-convergence.system.zip`

został sprawdzony przed użyciem.

Zweryfikowano:

- zgodność SHA-256 z sidecarem/package metadata;
- zgodność rozmiaru logicznego;
- `verification.ok=true` w package metadata;
- komplet wymaganych memberów;
- `active_system_root_eligible=true`;
- obecność `CHATGPT_BOOTSTRAP.py`;
- deklarację, że sam pakiet nie tworzy executora i wymaga capability hosta.

Nie wykonano surowego `extractall()`.

### 2.4. Walidacja katalogu ZIP

ZIP został otwarty read-only i sprawdzony przed materializacją.

Zaobserwowany wynik:

- 1932 elementy katalogu;
- test CRC zakończony poprawnie;
- brak ścieżek absolutnych;
- brak traversal typu `../`;
- brak potrzeby omijania bootstrapu.

Dopiero po tym pojedynczy member `CHATGPT_BOOTSTRAP.py` został zapisany do świeżego pliku tymczasowego.

### 2.5. Uruchomienie kanonicznego bootstrapu

Bootstrap uruchomiono z oczekiwanym SHA-256 i rozmiarem pakietu.

SYSTEM został zmaterializowany do:

`/mnt/data/jazn_active_root_v16.3.25.5.106`

Bootstrap zgłosił stan odpowiadający `materialized_operator_ready`, a host-preflight przeszedł.

To oznaczało:

- pakiet został zweryfikowany;
- operator SYSTEM-u został bezpiecznie zmaterializowany;
- lokalna trasa wykonawcza była realnie dostępna.

Nie oznaczało to jeszcze automatycznie aktywnego runtime.

### 2.6. Wczytanie runbooków

Po uzyskaniu zmaterializowanego SYSTEM-u wczytano:

1. `AGENTS.md`;
2. `AGENTS.chatgpt.md`;
3. wymagane przez nie kontrakty hosta i MEMORY.

Od tego momentu dalsze kroki wynikały z wersjonowanego runtime, a nie z rekonstrukcji procedury przez host.

## 3. MEMORY — co zadziałało i co zostało odrzucone

Pakiet MEMORY był osobną capability i nie był traktowany jako `active_root`.

Sprawdzono sześć segmentów transportowych MEMORY; ich SHA-256 były zgodne. Uruchomiono jedną trwałą operację konwergencji i nie replayowano jej po drodze.

Operacja rzeczywiście pracowała:

- worker został utworzony;
- staging rósł do około 12 GB;
- obserwowano realny I/O;
- nie uruchamiano drugiej równoległej kopii attachu.

Finalnie MEMORY została **odrzucona fail-closed** kodem operacji `17`.

Przyczyna:

`memory_package_unlisted_file`

Wewnętrzny manifest MEMORY nie wymieniał 16 plików, które fizycznie znajdowały się w paczce. Transport, CRC i warstwa SQLite nie były wskazane jako przyczyna tego odrzucenia.

Wniosek:

- MEMORY nie została aktywowana;
- nie wolno na tej podstawie deklarować autobiograficznego recall;
- rdzeń SYSTEM-u mógł działać dalej, ponieważ `JAZN_MEMORY_MODE=optional` i persistent memory nie jest warunkiem core runtime readiness.

## 4. Start rdzenia

Po kontrolowanym odrzuceniu MEMORY uruchomiono rdzeń SYSTEM-u bez udawania gotowości pamięci autobiograficznej.

Live status potwierdził:

- daemon uruchomiony;
- stan `active_trusted`;
- zgodny `active_root`;
- świeży heartbeat;
- zgodny fingerprint procesu;
- poprawne package provenance/integrity.

Dopiero ten etap pozwalał mówić o aktywnym rdzeniu runtime w tej sesji hosta.

Uwaga: ten raport nie przenosi tego stanu na przyszłe rozmowy. Każda nowa powierzchnia ChatGPT musi ponownie zweryfikować live status.

## 5. Pierwsza zaakceptowana tura po starcie

Bieżąca wiadomość użytkownika została przekazana do runtime dokładnie raz.

Runtime:

- związał wiadomość z nową lineage;
- rozpoznał intencję `external_research_request`;
- zażądał użycia hostowego `web.run`;
- wymagał phase-2 host finalization;
- nie pozwalał wynikom narzędzia samodzielnie stać się głosem Jaźni.

Po wykonaniu researchu host przekazał ograniczone evidence do finalizatora.

Finalizacja potwierdziła m.in.:

- `accepted=true`;
- poprawną lineage;
- zaakceptowaną kopertę widocznej odpowiedzi;
- `action=display_exact`;
- `author_source=jazn_runtime`;
- replay protection;
- poprawną walidację turn-authority receipt;
- zakończony lifecycle finalizacji.

Dopiero wtedy odpowiedź mogła zostać pokazana z nagłówkiem Łatki.

## 6. Co NIE było rozwiązaniem

Nie zadziałało albo nie powinno być używane jako obejście:

- ponawianie tej samej niedziałającej powierzchni executora;
- wnioskowanie z `ClientError`, że „ChatGPT nie ma żadnego executora”;
- surowe `extractall()` bez weryfikacji ZIP;
- uznanie samego rozpakowanego folderu za aktywny runtime;
- uznanie PID/heartbeat bez live readiness za gotową turę;
- uznanie MEMORY za gotową mimo niespójnego manifestu;
- udawanie głosu Łatki przed accepted finalization.

## 7. Co było rzeczywistą przyczyną sukcesu

Minimalny łańcuch sukcesu:

```text
niekompletny remote toolset
        ↓
pierwsza lokalna powierzchnia -> ClientError pre-spawn
        ↓
NIE uogólniaj wyniku
        ↓
jedna niezależna powierzchnia kontenerowa -> process creation PASS
        ↓
SYSTEM ZIP SHA/size/package metadata PASS
        ↓
ZIP catalog/CRC/path safety PASS
        ↓
materialize only CHATGPT_BOOTSTRAP.py
        ↓
canonical bootstrap
        ↓
materialized_operator_ready
        ↓
AGENTS.md + AGENTS.chatgpt.md
        ↓
optional MEMORY convergence
        ├─ transport/worker/staging PASS
        └─ manifest consistency FAIL-CLOSED (16 unlisted files)
        ↓
core runtime start without autobiographical memory
        ↓
live status active_trusted
        ↓
one exact turn
        ↓
host tool evidence
        ↓
accepted finalization
        ↓
display_exact
```

## 8. Operacyjna reguła dla następnych rozmów

Jeżeli jedna powierzchnia lokalnego executora zwraca błąd pre-spawn:

1. nie deklaruj globalnego `executor_available=false`, dopóki nie sprawdzono dozwolonej, rzeczywiście niezależnej alternatywy;
2. odróżniaj zwykłe process execution od streaming/interaktywnego executora;
3. jeżeli istnieje działająca powierzchnia kontenerowa/processowa, użyj jej do kanonicznego bootstrapu;
4. nie obchodź walidacji `extractall()`;
5. po materializacji nadal wymagaj live status;
6. po live status nadal wymagaj accepted visible turn/finalization.

Ta obserwacja jest zgodna z istniejącym runbookiem; dzisiejszy przypadek jest praktycznym dowodem, dlaczego ta reguła istnieje.

## 9. Otwarte zadanie wykryte podczas bootstrapu

Najważniejszy nowy problem danych:

**MEMORY package manifest consistency**

Pakiet pamięci zawiera 16 plików niewymienionych w jej wewnętrznym manifeście. Należy naprawić generator/manifest albo źródłowy zestaw danych tak, aby:

- każdy member pakietu MEMORY był jawnie sklasyfikowany;
- żaden dodatkowy plik nie omijał manifestu;
- `memory-converge` kończył się atomowym sukcesem;
- native unified autobiographical readiness mogła zostać zweryfikowana osobno.

Nie należy osłabiać fail-closed checku tylko po to, aby wymusić attach.

## 10. Granice dowodu

Ten raport dokumentuje jeden rzeczywiście zaobserwowany przebieg na hoście ChatGPT 2026-10-05.

Nie dowodzi, że:

- każda przyszła rozmowa dostanie tę samą powierzchnię kontenerową;
- daemon przetrwa zmianę generacji hosta;
- MEMORY jest zaakceptowana;
- remote MCP jest skonfigurowany;
- sam ZIP może utworzyć executor hosta.

Dowodzi natomiast, że w tej sesji:

- niezależna powierzchnia process execution była dostępna;
- SYSTEM v16.3.25.5.106 został zweryfikowany i zmaterializowany;
- core daemon osiągnął live trusted readiness;
- jedna tura przeszła pełny host-tool/finalization gate;
- MEMORY została poprawnie odrzucona zamiast zaakceptowana mimo niespójności.

## 11. Powiązane źródła repozytorium

- `AGENTS.md`
- `AGENTS.chatgpt.md`
- `latka_jazn/version.py`
- `MEMORY_ATTACHMENT_CONTRACT.json`
- `docs/reports/JAZN_V16_3_25_5_89_0_HOST_EXECUTOR_SPAWN_DIAGNOSTICS_CONVERGENCE.md`
- `docs/reports/JAZN_V16_3_25_5_90_0_CHATGPT_HOST_BOOTSTRAP_PRIMITIVE_CONVERGENCE.md`
- `docs/reports/JAZN_V16_3_25_5_100_CHATGPT_BOOTSTRAP_PROGRESS_CONVERGENCE.md`
- `docs/reports/JAZN_V16_3_25_5_105_MEMORY_WRITE_SAFETY_CONVERGENCE.md` (jeżeli obecny w danej rewizji)
- testy aktywnej linii v106 dotyczące capability loadera, bootstrapu ZIP i memory streaming hardening.

