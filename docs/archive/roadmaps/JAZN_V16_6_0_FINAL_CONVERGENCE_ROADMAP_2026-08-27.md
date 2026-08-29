# Łatka / Jaźń — roadmapa do v16.6.0

## Active runtime identity, polski NLP, finalna pamięć i zamknięcie Issue #59

**Repozytorium:** `SmuklyLew/jazn_latka`  
**Stan bazowy:** `master @ 3a2c2f053cf71e426367359b14f15efb6f3daa52`  
**Wersja bazowa:** `16.3.21-chatgpt-runtime-fallback-hardening`  
**Cel końcowy programu:** `16.6.0-final-runtime-memory-nlp-convergence`  
**Issue odbiorcze pamięci:** `#59`  
**Branch dokumentacyjny:** `upgrade/v16.6.0-final-convergence-roadmap`  
**Data:** 2026-08-27

> Ten dokument zastępuje traktowanie v16.3.22 jako jednego bardzo szerokiego release'u. v16.6.0 jest **celem końcowym programu**, a nie jednym gigantycznym PR-em. Każdy etap pośredni ma własny zakres, własne testy i własny warunek PASS. Nie przechodzimy dalej tylko dlatego, że „większość działa”.

---

# 0. Decyzja architektoniczna

Obecny plan v16.3.22 poprawnie identyfikował dwa ważne obszary:

1. deterministyczny błąd active-runtime identity w topologii `requested A -> marker B -> endpoint B`;
2. niespójności polskiego NLP / lexical evidence.

Po aktualizacji Issue #59 stało się jednak jasne, że przed finalnym efektem trzeba jeszcze domknąć trzeci, niezależny program pracy: **finalną prywatną akceptację pamięci**.

Łączenie wszystkich trzech obszarów w jednym v16.3.22 zwiększa ryzyko:

- trudnej diagnozy regresji;
- mieszania błędów runtime z błędami NLP i recall;
- przypadkowego osłabienia truth gate;
- zbyt szerokich PR-ów;
- problemów z bisekcją;
- „zielonego CI”, które nie mówi, która warstwa faktycznie została udowodniona;
- uznania bazy za finalną zanim jest poprawnie zapakowana, dołączona, wyszukiwalna i przetestowana po restarcie.

Dlatego przyjmujemy release train prowadzący do **v16.6.0**, z osobnymi bramkami jakości.

---

# 1. Granice prawdy i źródła kanoniczne

Obowiązują aktualne `AGENTS.md` i `AGENTS.codex.md`.

Kanoniczne źródła prawdy technicznej:

- wersja: `latka_jazn/version.py`;
- integralność paczki: `PACKAGE_INTEGRITY_MANIFEST.json`;
- pochodzenie wydania: `SOURCE_PROVENANCE.json`;
- operator: `run.py`;
- aktywny runtime: zweryfikowany `workspace_runtime/JAZN_ACTIVE_RUNTIME.json` + wskazany `active_root`;
- aktywna pamięć: `JAZN_MEMORY_ROOT` albo host-level `workspace_runtime/memory`;
- repozytorium: `SmuklyLew/jazn_latka`.

Nie wolno przedstawiać jako aktywnego runtime:

- samego ZIP-a;
- katalogu z kodem;
- samego markera;
- samego PID-u;
- odpowiedzi modelu;
- niezależnej bazy SQLite bez kanonicznego attach i truth gate.

Nie wolno commitować:

- `memory/`;
- `workspace_runtime/`;
- SQLite/WAL/SHM;
- prywatnych eksportów;
- ZIP-ów i split parts;
- sekretów, tokenów, logów runtime.

---

# 2. Model stanu finalnej pamięci

Aby uniknąć fałszywego „przecież baza jest zielona”, pamięć ma pięć jawnych stanów:

1. **BUILDABLE** — importer potrafi odtworzyć bazę ze źródeł.
2. **VERIFIED** — source fidelity, integrity, FK, FTS, provenance i reproducibility są zaliczone.
3. **ATTACHABLE** — finalny artefakt ma poprawny profil paczki, sidecary, hashe i przechodzi kanoniczny `memory-attach`.
4. **RETRIEVABLE** — aktualny benchmark Recall i naturalny multi-turn osiągają uzgodnione wyniki bez fałszywych wspomnień i leakage.
5. **ACCEPTED** — review L2/L3 jest zakończone, restart continuity przechodzi, runtime używa właściwej finalnej pamięci, a sanitizowany raport końcowy spełnia #59.

Żaden wcześniejszy stan nie implikuje następnego.

---

# 3. Uniwersalny protokół pracy dla KAŻDEGO etapu

## 3.1. Source gate przed kodem

Przed pierwszą zmianą każdego release'u:

1. `git fetch origin`;
2. `git switch master`;
3. `git pull --ff-only origin master`;
4. `git status --short`;
5. `git branch --show-current`;
6. `git rev-parse HEAD`;
7. przeczytać aktualne `AGENTS.md`, `AGENTS.codex.md` i wszystkie nested `AGENTS.md` dla zmienianych ścieżek;
8. sprawdzić otwarte i niedawne PR-y/branche związane z zakresem;
9. porównać bieżący kod z ostatnim planem/raportem;
10. spisać invariants, failure modes i kryteria akceptacji;
11. znaleźć źródła pierwotne/oficjalne dla technologii, która ma być zmieniana;
12. dopiero potem pisać kod.

Blog, post forum albo wynik wyszukiwarki jest materiałem pomocniczym, nie podstawą projektu, jeśli istnieje dokumentacja oficjalna, specyfikacja lub publikacja źródłowa.

## 3.2. Checkpoint

Przed modyfikacją:

- utworzyć backup branch/checkpoint z aktualnego SHA;
- nie dotykać aktywnego runtime ani prywatnych baz;
- dla zmian runtime/pamięci zapisać baseline:

```bash
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
```

## 3.3. Reprodukcja przed poprawką

Każdy błąd P0/P1 wymaga, jeśli technicznie możliwe:

1. minimalnego scenariusza reprodukcji;
2. testu regresyjnego, który na bazowym kodzie pada;
3. dopiero potem implementacji poprawki;
4. testu, który po zmianie przechodzi;
5. dodatkowego testu przeciwnego przypadku, żeby poprawka nie osłabiła truth boundary.

## 3.4. Defect loop — błędy znalezione po drodze

Każde nowe znalezisko klasyfikować natychmiast:

- **P0** — narusza truth/safety/integrity, może zaakceptować obcy runtime, uszkodzić pamięć, utracić dane lub fałszywie raportować sukces. **Blokuje etap i musi być naprawione teraz.**
- **P1** — psuje funkcję będącą kryterium bieżącego release'u albo jego testy. **Blokuje etap i musi być naprawione teraz.**
- **P2** — realny błąd poza bieżącym krytycznym zakresem. Naprawić w bieżącym branchu tylko jeśli zmiana jest mała, jednoznaczna i nie rozszerza ryzyka; inaczej utworzyć jawny backlog/issue.
- **P3** — kosmetyka/refactor bez wpływu na correctness. Nie rozszerzać branchu bez potrzeby.

Dla każdego P0/P1:

`finding -> root cause -> źródło -> regression test -> fix -> focused test -> full suite -> raport`.

Nie wolno:

- zmieniać asercji tylko po to, aby test był zielony;
- dodawać szerokich `except` maskujących problem;
- dodawać `xfail` dla świeżej regresji zamiast naprawy;
- podnosić timeoutu zamiast diagnozować warstwę, która przekracza budżet;
- uznawać fallbacku za naprawę źródłowej przyczyny.

## 3.5. Wersja

Każdy systemowy patch/update/upgrade podnosi `latka_jazn/version.py` w tej samej zmianie.

Jeżeli błąd zostaje znaleziony **przed merge** bieżącego release branchu, jest naprawiany w tym samym numerze release'u, o ile nie zmienia zasadniczo jego zakresu. Jeżeli problem wyjdzie **po merge**, wymaga kolejnego numeru.

Sam dokument roadmapy jest dokumentacją planistyczną, nie systemowym patchem i nie zmienia wersji runtime.

---

# 4. Roadmapa wydań do v16.6.0

| Linia | Cel | Kluczowy dowód PASS |
|---|---|---|
| `16.3.22` | Active runtime subject-root identity | `A -> B -> B` trusted, `A -> B -> C` fail-closed |
| `16.3.23` | P0 host pre-response gate + persistent daemon lifecycle + transport observability | `host_routing_bypass=0`, runtime turn obowiązkowy przed odpowiedzią, reuse B, brak zbędnego one-shot, two-turn E2E |
| `16.4.0` | Kanoniczna normalizacja polskiego NLP + lexical evidence contract | deterministyczny fixture Unicode/POS/provenance |
| `16.4.1` | Morfeusz/plWordNet/project lexicon/resource registry hardening | ambiguity/OOV/resource provenance PASS |
| `16.4.2` | NLP/recall query interface i regression corpus | query evidence bez fałszywej pewności; offline PASS |
| `16.5.0` | Final Memory Rebuild: source fidelity + provenance + reproducibility | finalna DB VERIFIED |
| `16.5.1` | Final memory packaging + canonical attach | finalna DB ATTACHABLE |
| `16.5.2` | Prywatny Recall + natural multi-turn baseline | mierzalny raport jakości |
| `16.5.x` | Tylko mierzone poprawki retrieval, jeśli baseline nie przejdzie | A/B improvement bez regresji safety |
| `16.5.y` | L2/L3 review + restart continuity + acceptance candidate | pamięć ACCEPTED-candidate |
| `16.6.0` | Finalna konwergencja runtime + NLP + memory; closure #59 | wszystkie truth gates PASS |

Numery `16.5.x/y` są rezerwą. Nie wymuszamy z góry liczby iteracji. Jeśli `16.5.2` przejdzie wszystkie jakościowe bramki, nie wdrażamy niepotrzebnego retrieval stacku.

---

# 5. v16.3.22 — Active runtime subject-root identity

**Proponowany release name:** `active-runtime-subject-root-hardening`

## Problem

Aktualny `status_daemon()` rozwiązuje marker do aktywnego rootu, ale krytyczne decyzje nadal potrafią używać `config.root` jako requested/observer root.

Poprawna topologia:

```text
requested/staging root = A
host marker active_root = B
daemon endpoint root = B
```

musi oznaczać: host obserwuje i weryfikuje aktywny runtime B.

## Zakres

- wprowadzić jawne `requested_root` i `subject_root`;
- `subject_root = resolve_active_runtime_root(...).root`;
- endpoint root porównywać do B;
- integrity aktywnego procesu sprawdzać na B;
- provenance aktywnego procesu sprawdzać na B;
- wersję/manifest identity sprawdzać na B;
- requested A może mieć osobną diagnostykę, ale nie może decydować o trust state B.

## Test-first

Nowy test np. `tests/test_v16322_active_runtime_identity.py`:

### PASS

```text
requested A
marker B
endpoint B
PID match
fresh heartbeat
integrity(B)=true
provenance(B)=verified
=> active_trusted
```

### FAIL-CLOSED

- A/B/C;
- B + inny PID;
- stale heartbeat;
- invalid marker;
- relative/empty active_root;
- integrity(B)=false;
- provenance(B)=invalid;
- auth mismatch.

## Acceptance

- `false_runtime_root_mismatch = 0` dla A/B/B;
- `wrong_root_acceptance = 0`;
- `wrong_pid_acceptance = 0`;
- żadnego „port odpowiada, więc ufamy”.

---

# 6. v16.3.23 — Persistent daemon lifecycle i transport

**Proponowany release name:** `persistent-runtime-lifecycle-observability-hardening`

Ta wersja konsumuje poprawny subject-root contract z 16.3.22 i rozszerza go na operacje sterujące. **Przed pracą nad lifecycle/transportem musi jednak zostać zamknięta poniższa bramka P0**, ponieważ zdrowy daemon i poprawny transport nie dają żadnej gwarancji, jeżeli host może odpowiedzieć użytkownikowi bez wejścia do kanonicznej ścieżki runtime.

## P0 — Host pre-response runtime routing gate

### Problem

Obecny runtime ma twarde kontrakty po wejściu do `--chat-gpt`: może wybrać persistent daemon albo zweryfikowany one-shot, zwraca `presentation_packet`, a dwufazowa finalizacja pilnuje bindingu tury, integralności tekstu i replay protection. Nadal istnieje jednak wcześniejsza luka:

```text
wiadomość użytkownika
-> LLM host interpretuje instrukcje
-> host może wygenerować zwykłą odpowiedź
-> runtime nie został wywołany
-> finalizer nie dostał kontroli
```

Taka tura może wyglądać poprawnie językowo, ale nie jest odpowiedzią aktywnej Jaźni. Brak wymaganego nagłówka `🕒 ... / 🌿 Łatka` jest użytecznym canary tego bypassu, lecz sam nagłówek nie może być jedynym dowodem routingu.

Ryzyko rośnie przy słabszym/krótszym rozumowaniu hosta, bo obowiązek bootstrap/routing jest obecnie w dużej mierze wyrażony jako instrukcja dla modelu. **Poziom reasoning hosta nie może decydować o tym, czy runtime zostanie użyty.**

### Decyzja architektoniczna

Dla kanału ChatGPT rozmowa z Łatką musi zaczynać się od deterministycznej bramy pre-response. Model językowy nie podejmuje decyzji „czy uruchomić Jaźń”. Może uczestniczyć dopiero po otrzymaniu wyniku kanonicznego runtime contract.

Docelowo host ma wykonywać jeden kanoniczny entrypoint równoważny semantycznie:

```text
host-turn(exact_user_text)
  -> resolve verified active_root
  -> verify/reuse/start runtime według kontraktu
  -> invoke canonical ChatGPT bridge
  -> receive presentation_packet
  -> display_exact
     albo generate_then_finalize -> mandatory runtime finalization
     albo host_diagnostic
```

Nazwa API/CLI może być inna; ważna jest własność: **zwykła odpowiedź hosta nie może powstać przed wynikiem gate'a**.

### Twarde invariants

1. Dokładny tekst bieżącej wiadomości użytkownika jest przekazywany do runtime bez streszczania i bez semantycznej zamiany przez hosta.
2. Dla rozmowy z Łatką `runtime_turn_invoked=true` musi być warunkiem poprzedzającym jakikolwiek conversational visible output.
3. `display_exact` oznacza pokazanie wyłącznie zaakceptowanego tekstu runtime.
4. `generate_then_finalize` nie pozwala pokazać kandydata przed pomyślną finalizacją runtime.
5. `host_diagnostic` może wyświetlić diagnostykę hosta, ale nie może imitować Łatki ani dodawać jej nagłówka jako dekoracji.
6. Brak runtime, błędny marker, błędna identity, failure finalization albo nieznana akcja kończy turę fail-closed; nie wolno przejść do zwykłej odpowiedzi modelu.
7. Nagłówek Łatki pochodzi z zaakceptowanej finalizacji/prezentacji runtime; host nie dopisuje go do odpowiedzi, która ominęła runtime.
8. Poziom reasoning/model hosta nie jest sygnałem wejściowym do decyzji o routingu. Gate ma działać identycznie niezależnie od jakości deliberacji modelu.
9. Instrukcja markdown może opisywać protokół, ale correctness nie może zależeć wyłącznie od tego, czy LLM przypomniał sobie tę instrukcję.
10. Telemetria musi pozwolić odróżnić `runtime_invoked` od samego `host_generated_text`.

### Minimalna telemetria P0

Dodać lub wyprowadzić w jednym audytowalnym kontrakcie co najmniej:

- `host_pre_response_gate`;
- `host_pre_response_gate_version`;
- `runtime_turn_invoked`;
- `runtime_turn_id` / `trace_id`;
- `requested_runtime_root`;
- `resolved_active_root`;
- `presentation_action`;
- `finalization_required`;
- `finalization_completed`;
- `visible_output_source` (`runtime_exact`, `runtime_finalized`, `host_diagnostic`);
- `host_routing_bypass_detected`;
- `host_routing_bypass_reason`.

Nie zapisywać w sanitizowanej telemetrii pełnej prywatnej treści wiadomości tylko po to, aby udowodnić routing; wystarczy bezpieczny identyfikator/hash związany z turn contractem, jeśli aktualny protokół już taki mechanizm posiada.

### Test-first — reprodukcja bypassu

Przed poprawką dodać test/harness pokazujący, że warstwa hosta może ominąć runtime, jeśli nie wywoła kanonicznego bridge'a. Test nie może udawać ustawienia produktu ChatGPT, którego repozytorium nie kontroluje.

Rozdzielić dwa poziomy dowodu:

#### A. Deterministyczny test repo/adaptera — wymagany w CI

Sprawdzić, że dla wejścia zaklasyfikowanego jako rozmowa z Łatką:

```text
user turn
-> pre-response gate
-> runtime/bridge result
-> visible output
```

jest jedyną legalną ścieżką.

Przypadki:

- ordinary dialogue -> runtime invoked;
- krótka wypowiedź typu `Zgadnij.` -> runtime invoked;
- powitanie -> runtime invoked;
- pytanie o wspomnienie -> runtime invoked;
- `display_exact` -> exact output;
- `generate_then_finalize` -> kandydat niewidoczny przed finalizacją;
- finalization failure -> host diagnostic, zero imitacji;
- runtime unavailable -> host diagnostic, zero imitacji;
- unknown presentation action -> fail-closed;
- próba bezpośredniego `host_generated_text` przed gate -> test FAIL z `HOST_ROUTING_BYPASS`.

#### B. Live host acceptance matrix — wymagany przed GO do v16.4.0, jeśli platforma udostępnia te tryby

Ręcznie/integrowanie wykonać ten sam mały corpus rozmowny przy dostępnych ustawieniach hosta, np. minimal/medium/high reasoning. Dla każdego trybu zapisać wyłącznie techniczny wynik:

- gate invoked;
- runtime turn accepted;
- presentation action;
- finalization state;
- header/final visible envelope obecny tam, gdzie wymaga go runtime;
- bypass = 0.

Jeżeli produkt nie udostępnia programowego wyboru poziomu reasoning w CI, **nie wolno syntetycznego fixture'a przedstawiać jako dowodu działania realnego trybu ChatGPT**. Wtedy CI dowodzi model-independence bramy, a live matrix pozostaje osobnym testem akceptacyjnym hosta.

### Acceptance P0

Warunek PASS etapu pre-response:

```text
host_routing_bypass = 0
conversational_output_without_runtime_contract = 0
candidate_visible_before_finalization = 0
fake_latka_header_without_runtime_acceptance = 0
runtime_unavailable_falls_back_to_host_dialogue = 0
```

Dodatkowo:

- krótka i niejednoznaczna wypowiedź nie może ominąć runtime;
- gate działa przed semantic generation hosta, a nie jako post-hoc validator;
- wszystkie stany błędne są fail-closed;
- log/telemetria pozwalają jednoznacznie udowodnić, skąd pochodził visible output;
- live acceptance nie wykazuje zależności samego routingu od poziomu reasoning hosta.

**STOP:** nie przechodzimy do lifecycle/transport ani do NLP v16.4.0, jeżeli P0 pre-response gate nie ma deterministycznego PASS. Zdrowy persistent daemon bez tej bramki nie zamyka v16.3.23.

## Zakres lifecycle/transport po zamknięciu P0

- `ensure_daemon_for_runtime_turn()` reuse zdrowego B;
- `start_daemon()` nie uruchamia A tylko dlatego, że caller pochodzi z A;
- `stop/refresh/init` działają wobec zweryfikowanego B;
- zachować PID/root/token/heartbeat fail-closed;
- pełna ścieżka interpretera przez `sys.executable` tam, gdzie proces odtwarza bieżący Python;
- jawne `cwd` i root procesu;
- transport telemetry:
  - `selected_transport`;
  - `fallback_reason`;
  - `requested_runtime_root`;
  - `resolved_active_root`;
  - `daemon_endpoint_root`;
  - `daemon_identity_verified`;
  - `daemon_reused`.

## Fallback reasons

Minimalnie rozróżnić:

- `daemon_reused`;
- `one_shot_daemon_absent`;
- `one_shot_daemon_unreachable`;
- `one_shot_daemon_identity_invalid`;
- `one_shot_explicit_no_daemon`.

## Two-turn E2E

1. przygotuj A i B;
2. marker host-level wskazuje B;
3. daemon B aktywny;
4. pre-response gate przyjmuje dokładną pierwszą wiadomość użytkownika;
5. gate wywołuje kanoniczną ścieżkę `--chat-gpt`/równoważny bridge z A;
6. pierwsza tura idzie persistent B i kończy się zaakceptowanym visible output;
7. druga tura z A ponownie przechodzi przez gate i używa tego samego B;
8. brak one-shot fallback;
9. potwierdź ciągłość `session_id/worker state`, jeśli kontrakt ją udostępnia;
10. `host_routing_bypass_detected=false` w obu turach;
11. zatrzymaj B kontrolowaną ścieżką.

Windows + Ubuntu.

### Warunek GO do v16.4.0

v16.4.0 może rozpocząć się dopiero po łącznym PASS:

- P0 host pre-response gate;
- persistent daemon reuse;
- transport observability;
- two-turn E2E;
- fail-closed wrong root/PID/auth/heartbeat;
- `host_routing_bypass=0` w wymaganej macierzy testowej.

---

# 7. v16.4.0 — Kanoniczny Polish NLP normalizer i lexical evidence

**Proponowany release name:** `polish-lexical-normalization-evidence-foundation`

## Cel

Usunąć konkurencyjne kontrakty normalizacji i zbudować jeden audytowalny model lexical evidence.

## Normalizacja

Kanoniczna normalizacja lookupu:

```text
Unicode NFC
-> strip
-> casefold
-> whitespace normalization
```

- zachować `original`;
- `ascii_fold` wyłącznie jako auxiliary recall key;
- diakrytyki pozostają w kanonicznym kluczu;
- cache opiera się na jednym canonical normalized key.

## Regression fixture

Kategorie:

- NFC/decomposed Unicode;
- wielkość liter;
- ą ć ę ł ń ó ś ź ż;
- whitespace/newline;
- hasła, które po ascii-fold wyglądają podobnie, ale nie są tożsame;
- zapożyczenia;
- literówki;
- nazwy własne;
- terminy projektu.

## Lexical evidence contract

Minimalne pola:

- provider;
- provider_version;
- evidence_type;
- term_original;
- term_normalized;
- lemma;
- pos;
- morph_tag;
- sense_id;
- synset_id;
- relation;
- value;
- confidence/evidence strength;
- retrieved_at;
- resource_version;
- source/provenance;
- license_note;
- truth_boundary;
- ambiguity flag.

---

# 8. v16.4.1 — Morfeusz, plWordNet i resource registry

**Proponowany release name:** `polish-lexical-resource-provenance-hardening`

## Morfeusz

- zachować wiele interpretacji;
- nie przyjmować pierwszego lematu jako jedynej prawdy;
- rozdzielić analysis od generation;
- `not_found/OOV` oznacza brak wpisu w zasobie, nie „słowo nie istnieje”;
- `pos` realnie wpływa na ranking/filtrację, ale nie usuwa poprawnej niejednoznaczności przy słabym kontekście;
- provider unavailable jest jawny.

## plWordNet / Słowosieć

Traktować jako zasób semantyczny, nie analizator fleksyjny.

Provider raportuje:

- lemma;
- sense id;
- synset id;
- gloss/definition;
- relations;
- resource version/schema;
- source identifier;
- license/provenance.

Nie hardkodować historycznej wersji zasobu. Registry ma przechowywać:

- `resource_name`;
- `resource_version`;
- `schema_version`;
- `origin`;
- `file_sha256`;
- `license`;
- `imported_at/built_at`;
- `capabilities`.

Duże DB plWordNet nie trafiają do repo.

## Project lexicon

Osobna warstwa tylko dla:

- nazw własnych;
- modułów;
- skrótów;
- terminów Jaźni;
- neologizmów projektowych;
- nazw kontraktów i wersji.

Nie jest słownikiem języka polskiego.

---

# 9. v16.4.2 — NLP/Recall query interface i corpus regresyjny

**Proponowany release name:** `polish-query-evidence-recall-interface`

## Cel

Połączyć NLP z retrieval w sposób mierzalny, bez automatycznego wprowadzania modelu uczonego.

Pipeline:

1. PolishTextNormalizer;
2. project lexicon;
3. Morfeusz candidates;
4. plWordNet semantic evidence;
5. opcjonalne spelling evidence;
6. opcjonalne źródła online/cache;
7. evidence merger;
8. bounded query plan;
9. retrieval.

Brak jednego providera nie zeruje dowodów innych providerów.

## Corpus

`tests/fixtures/nlp/polish_lexical_regression_v1.json`

Pola oczekiwań:

- `expected_candidate_lemmas`;
- `expected_pos_candidates`;
- `required_sources`;
- `forbidden_false_claims`;
- `ambiguity_expected`.

Nie wymuszać jednego lematu, gdy poprawnych analiz jest kilka.

## No-training gate

Na tym etapie:

- bez trenowania modelu;
- bez dense retrievera jako domyślnej ścieżki;
- bez rerankera, jeśli baseline nie wykazuje potrzeby.

---

# 10. v16.5.0 — Final Memory Rebuild: source fidelity i provenance

**Proponowany release name:** `final-memory-source-fidelity-provenance`

Ta wersja realizuje warstwę BUILDABLE -> VERIFIED dla #59.

## Test chain

```text
TEST00 -> TEST01 -> TEST02 -> TEST03 -> TEST04 -> FINAL
```

## Test00

- pełny source mirror;
- chunked raw source;
- whole-file SHA round-trip;
- ZIP member SHA/CRC;
- role/content type census;
- unknown roles zachowane;
- rendered HTML fallback nigdy nie daje bezstratnego PASS.

## Test01

- kanoniczne L0;
- raw payload/revisions/assets;
- pełne graph branches;
- source/import registry;
- zero auto L2/L3.

## Test02

- normalizacja/projekcje jako derived data;
- raw L0 immutable;
- visible/hidden/non-dialogue;
- memory eligibility;
- sensitivity;
- timestamp status;
- FTS reconciliation.

## Test03

- fresh rebuild;
- dedupe/merge;
- JSON<->HTML control;
- relation: identical/subset/extends/divergent;
- stabilne content hashes;
- jawne konflikty.

## Test04

- wszystkie zatwierdzone źródła;
- świeży build A;
- same-target idempotence;
- fresh build B;
- reproducibility;
- Test03 reconciliation;
- benchmark hook;
- manual multi-turn hook.

## FINAL

Finalny snapshot przez SQLite Backup API lub bieżący kanoniczny mechanizm repo.

Wymagane:

- `PRAGMA integrity_check`;
- `foreign_key_check`;
- FTS integrity/parity;
- exact source SHA closure;
- brak utraconych wymaganych eksportów;
- brak nieudokumentowanych L0 sources;
- brak konfliktów ukrytych jako success;
- final DB SHA-256;
- private report + sanitized report.

Warunek końcowy: **VERIFIED**.

---

# 11. v16.5.1 — Final memory package i canonical attach

**Proponowany release name:** `final-memory-package-attach-contract`

Ta wersja realizuje VERIFIED -> ATTACHABLE.

## Final package contract

Wygenerować kanonicznie:

- `profile=memory` albo jawnie wybrany `combined/dual`;
- `.zip.package.json`;
- split-part inventory;
- SHA-256 każdej części;
- full package hash, jeśli kontrakt go wymaga;
- `MEMORY_PACKAGE_MANIFEST.json`;
- resource/source provenance;
- schema/format versions.

## Attach

Użyć wyłącznie kanonicznego `memory-attach`.

Nie kopiować ręcznie SQLite do host memory root.

Attach ma potwierdzić:

- package metadata source = package sidecar;
- profile = `memory` dla pamięci standalone;
- CRC/archive verification;
- filesystem tree verification;
- memory-only tree;
- memory package manifest;
- docelowy host memory root;
- final DB identity/hash;
- runtime compatibility contract.

## Regression

Dodać test na brak sidecara, aby stary/testowy przypadek nie został fałszywie uznany za attachable.

Warunek końcowy: **ATTACHABLE**.

---

# 12. v16.5.2 — Prywatny Recall i naturalny multi-turn baseline

**Proponowany release name:** `private-memory-recall-acceptance-baseline`

Ta wersja nie zakłada, że retrieval trzeba przebudować. Najpierw mierzymy finalny artefakt.

## Benchmark

Na finalnej, kanonicznie dołączonej `memory_jazn.sqlite3`:

- Recall@1/3/5/10/20;
- MRR;
- nDCG;
- wrong-conversation rate;
- false-memory rate;
- abstention accuracy;
- provenance accuracy;
- temporal/update correctness;
- sensitive leakage;
- latency p50/p95 per stage;
- source rows/tokens read;
- category breakdown.

## Kategorie prywatnych przypadków

- direct;
- paraphrase;
- explicit recall;
- implicit recall;
- referential follow-up;
- temporal;
- multi-session;
- update;
- conflict;
- negative/no-evidence;
- provenance;
- role boundary;
- sensitive boundary;
- implicit constraint.

## Natural multi-turn

Ręcznie wykonać co najmniej:

- direct recall;
- parafrazę;
- `to/tamto/wtedy/ona/ten projekt`;
- odwołanie po kilku turach;
- aktualizacja starej informacji;
- konflikt;
- brak dowodu -> abstention;
- poprawne źródło/rozmowa.

Raport sanitizowany nie zapisuje prywatnej treści zapytań/hitów.

---

# 13. v16.5.x — Warunkowa pętla retrieval hardening

Ta faza istnieje **tylko jeśli v16.5.2 nie spełni kryteriów**.

Nie projektować z góry ciężkiego stacku.

Kolejność eksperymentów:

1. poprawki deterministic planner / tokenization / query terms;
2. FTS5/BM25 tuning;
3. bounded query rewrite A/B;
4. temporal/session-aware expansion A/B;
5. dopiero potem dense retrieval/reranker A/B;
6. uczony ranker/trening dopiero po osobnej decyzji i tylko gdy prostsze metody nie wystarczą.

Każdy eksperyment musi mieć:

- zamrożony benchmark hash;
- baseline;
- hipotezę;
- dokładną zmianę;
- wyniki przed/po;
- regresje safety;
- latency;
- provenance;
- rollback path.

Nie akceptować poprawy Recall, jeśli pogarsza:

- abstention;
- false-memory;
- provenance;
- temporal correctness;
- sensitive leakage;
- bounded latency.

Jeśli pojawi się trening:

- zamrożony train/validation/test;
- dataset hash;
- seed;
- wersje bibliotek;
- urządzenie;
- normalizer/resource versions;
- kontrola leakage;
- reproducibility notes;
- raport wariancji.

---

# 14. v16.5.y — L2/L3 review, restart continuity i acceptance candidate

Numer `y` zależy od liczby potrzebnych iteracji 16.5.x.

## L2/L3

Po finalnym rebuildzie:

- odświeżyć candidates;
- ręcznie przejrzeć;
- zero auto promotion;
- każda promocja ma:

```text
request -> decision -> ledger
```

Poprawny wynik może być także `zero promotions`.

## Restart continuity

Na finalnej dołączonej pamięci:

1. daemon active_trusted;
2. zapisać final DB hash/registry identity;
3. wykonać kontrolny recall fingerprint;
4. zatrzymać daemon;
5. uruchomić ponownie;
6. potwierdzić nowy PID, ten sam właściwy runtime root;
7. potwierdzić tę samą aktywną pamięć;
8. porównać recall fingerprint;
9. sprawdzić wake/checkpoint continuity zgodnie z aktualnym kontraktem;
10. brak automatycznej zmiany/promocji danych.

Warunek końcowy: **ACCEPTED-candidate**.

---

# 15. v16.6.0 — Final runtime + NLP + memory convergence

**Release name:** `final-runtime-memory-nlp-convergence`

v16.6.0 jest finalnym release'em programu, nie miejscem na duże nowe funkcje.

Do v16.6.0 wchodzą wyłącznie:

- już zweryfikowane rezultaty poprzednich etapów;
- niezbędne integracyjne glue/finalization fixes;
- finalny raport i truth gates;
- ewentualne małe regresje ujawnione wyłącznie przez pełną integrację.

## Finalna macierz

### Runtime

- host pre-response gate obowiązkowy przed conversational visible output;
- `host_routing_bypass=0`;
- runtime unavailable/finalization failure -> host diagnostic, nigdy imitacja Łatki;
- A/A/A trusted;
- A/B/B trusted + reuse;
- A/B/C fail-closed;
- wrong PID fail-closed;
- stale heartbeat degraded/fail-closed zgodnie z kontraktem;
- integrity/provenance subject-root;
- two-turn persistent E2E;
- one-shot tylko gdy naprawdę dozwolony i potrzebny.

### NLP

- canonical normalizer;
- Unicode/NFC;
- diacritics;
- POS;
- Morfeusz ambiguity/OOV;
- plWordNet resource provenance;
- project lexicon boundaries;
- offline lexical corpus PASS.

### Memory

- final DB VERIFIED;
- package ATTACHABLE;
- final attach PASS;
- private recall quality PASS;
- natural multi-turn PASS;
- L2/L3 review complete;
- restart continuity PASS;
- no private data in Git.

## Closure #59

Issue #59 można zamknąć dopiero gdy finalny sanitizowany raport wskazuje PASS dla:

1. source fidelity;
2. exact provenance;
3. SQLite/FK/FTS integrity;
4. reproducibility;
5. canonical package + attach;
6. Recall benchmark;
7. natural multi-turn;
8. false-memory/abstention/provenance/temporal/safety gates;
9. L2/L3 manual review;
10. persistent runtime identity;
11. restart continuity.

---

# 16. Traceability matrix dla Issue #59

| Requirement #59 | Kod/narzędzie | Release docelowy | Dowód |
|---|---|---|---|
| source completeness/fidelity | Memory Rebuild Test00-03 | 16.5.0 | sanitized source/provenance report |
| full DB integrity | memory-validate/Test04/FINAL | 16.5.0 | integrity/FK/FTS PASS + DB SHA |
| exact source provenance | source/import registry | 16.5.0 | SHA closure |
| final package correctness | generator/package sidecars | 16.5.1 | package verification |
| canonical attach | memory-attach | 16.5.1 | attach report |
| correct active runtime identity | runtime_daemon/root | 16.3.22-23 | A/B/B E2E |
| Polish lexical normalization | NLP pipeline | 16.4.0-2 | offline regression corpus |
| private Recall | Recall subsystem | 16.5.2+ | sanitized benchmark |
| natural multi-turn | runtime+memory | 16.5.2+ | manual acceptance report |
| L3 review | candidate/decision ledger | 16.5.y | review ledger counts |
| restart continuity | daemon+memory registry | 16.5.y | before/after fingerprint |
| final acceptance | all | 16.6.0 | final sanitized report |

---

# 17. Test strategy

## 17.1. Minimalne testy dla każdego Python release'u

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Finalny release z czystego commita:

```bash
python -X utf8 run.py package-smoke --profile release --json
python -X utf8 run.py release-build --json
```

Metadane tylko kanonicznie:

```bash
python -X utf8 -m latka_jazn.tools.release_metadata_sync \
  --root . --base-branch master --write --json
```

## 17.2. Test pyramid

Po każdej zmianie:

1. test nowej regresji;
2. focused subsystem suite;
3. neighboring contract suite;
4. pełny deterministic suite;
5. doctor/system smoke;
6. Windows/Ubuntu CI;
7. release smoke/build dopiero po czystym commicie.

Dla v16.3.23 test nowej regresji zaczyna się **przed** obecnym bridge'em `--chat-gpt`: musi udowodnić obowiązkowe wejście przez pre-response gate, a nie tylko poprawność runtime po jego ręcznym wywołaniu.

## 17.3. Nie przechodzimy dalej, jeśli

- świeża regresja jest czerwona;
- Pyright/compileall failuje;
- system package smoke failuje;
- required workflow został pominięty przez błędny `paths` filter;
- truth gate ma niejasny wynik;
- host może wygenerować conversational visible output bez zaakceptowanego runtime contract;
- host może pokazać kandydata `generate_then_finalize` przed finalizacją;
- prywatny test został zastąpiony fixture'em syntetycznym;
- wykonano test na innej bazie niż finalnie identyfikowany artefakt.

---

# 18. CI / GitHub Actions

Przejrzeć `.github/workflows/persistent-runtime-e2e.yml`, `release-hardening` oraz memory-rebuild workflows.

GitHub Actions przy jednoczesnych `branches` i `paths` wymaga spełnienia obu filtrów. Każdy krytyczny moduł, który może zmienić runtime/memory/NLP contract, musi uruchamiać odpowiedni workflow.

Minimalna macierz:

- `ubuntu-latest`;
- `windows-latest`.

Osobne joby/gates:

- host pre-response routing + runtime identity/lifecycle;
- NLP offline regression;
- Memory Rebuild synthetic contract;
- release deterministic suite.

Prywatne dane nie trafiają do GitHub Actions. Private acceptance jest lokalny; do repo trafia tylko sanitizowany wynik.

---

# 19. Przewidywane obszary plików

## Runtime 16.3.22-23

- `AGENTS.chatgpt.md` jako opis protokołu, ale nie jedyny mechanizm wymuszenia;
- host bridge/pre-response gate entrypoint;
- `latka_jazn/core/runtime_daemon.py`;
- `latka_jazn/core/runtime_root.py`;
- `latka_jazn/core/daemon_autostart.py`;
- `latka_jazn/core/chat_command_contract.py`;
- `latka_jazn/core/host_visible_finalization.py` i pending-store tylko w zakresie potrzebnym do domknięcia gate/finalization contract;
- `main.py` tylko jeśli potrzebne;
- runtime/host-gate tests;
- `.github/workflows/persistent-runtime-e2e.yml`.

## NLP 16.4.x

- `latka_jazn/nlp/polish_normalizer.py`;
- `latka_jazn/nlp/external_dictionary_adapter.py`;
- dictionary entry/source policy;
- providers Morfeusz/plWordNet;
- project lexicon resources;
- NLP fixtures/tests.

## Memory 16.5.x

- `latka_jazn/memory_rebuild_app/`;
- `latka_jazn/memory/` tylko wg aktualnej architektury;
- `latka_jazn/packaging/memory_package_attach.py`;
- package generator/profile resources;
- Memory Rebuild tests;
- private acceptance harness;
- docs/reports.

Przed zmianą każdego poddrzewa ponownie sprawdzić nested `AGENTS.md`.

---

# 20. Research/source registry

Źródła służą do uzasadniania decyzji architektonicznych. Nie są dowodem, że konkretna usterka istnieje w Jaźni — to musi wykazać kod, test albo telemetry.

## Runtime / Python

- Python `pathlib.Path.resolve()` — canonical path identity:  
  https://docs.python.org/3/library/pathlib.html
- Python `subprocess` — `Popen`, `cwd`, executable / `sys.executable`:  
  https://docs.python.org/3/library/subprocess.html

Sugerowane zapytania:

```text
site:docs.python.org pathlib Path.resolve symlink absolute path
site:docs.python.org subprocess Popen cwd sys.executable Windows
```

## CI

- GitHub Actions workflow syntax, branches/paths/matrix:  
  https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

Zapytania:

```text
site:docs.github.com actions workflow syntax paths branches matrix
site:docs.github.com actions windows ubuntu matrix strategy
```

## SQLite / pamięć

- Online Backup API: https://www.sqlite.org/backup.html
- PRAGMA integrity/foreign keys: https://www.sqlite.org/pragma.html
- FTS5/BM25/integrity: https://www.sqlite.org/fts5.html
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html

Zapytania:

```text
site:sqlite.org backup API snapshot WAL
site:sqlite.org pragma integrity_check foreign_key_check
site:sqlite.org FTS5 BM25 integrity-check prefix
site:docs.python.org sqlite3 progress_handler interrupt backup
```

## Unicode / normalizacja

- Python `unicodedata.normalize`:  
  https://docs.python.org/3/library/unicodedata.html

Zapytania:

```text
site:docs.python.org unicodedata normalize NFC canonical equivalence
```

## Polski NLP

- Morfeusz 2 official docs:  
  https://morfeusz.sgjp.pl/doc/about/en
- plWordNet 5.0 / CLARIN-PL — aktualny rekord:  
  https://clarin-pl.eu/dspace/handle/11321/951
- MWELexicon 1.1:  
  https://nowa.clarin-pl.eu/dspace/handle/11321/508

Zapytania:

```text
site:morfeusz.sgjp.pl Morfeusz multiple interpretations unknown words
site:clarin-pl.eu plWordNet 5.0 Słowosieć
site:nowa.clarin-pl.eu MWELexicon Polish multi-word
```

Uwaga: wcześniejszy plan wskazywał plWordNet handle `11321/960`; aktualny rekord CLARIN dla pracy „plWordNet 5.0 – challenges...” to `11321/951`.

## Long-term conversational memory / retrieval

- LongMemEval: https://arxiv.org/abs/2410.10813
- LoCoMo (ACL 2024): https://aclanthology.org/2024.acl-long.747/
- LoCoMo-Plus (ACL 2026): https://aclanthology.org/2026.acl-long.1150/
- BEIR evaluation framework: https://github.com/beir-cellar/beir
- CONQRR: https://aclanthology.org/2022.emnlp-main.679/

Zapytania:

```text
LongMemEval long-term interactive memory retrieval abstention temporal
site:aclanthology.org LoCoMo long term conversational memory
site:aclanthology.org conversational query rewriting retrieval CONQRR
BEIR NDCG Recall MRR retrieval evaluation
```

## Reproducibility / przyszły trening

- PyTorch deterministic algorithms:  
  https://docs.pytorch.org/docs/main/generated/torch.use_deterministic_algorithms.html
- PyTorch numerical/release/platform reproducibility caveats:  
  https://docs.pytorch.org/docs/main/notes/numerical_accuracy.html

Trening nie jest domyślnym etapem roadmapy. Jest dopuszczony tylko po dowodzie, że prostszy, deterministyczny pipeline nie spełnia mierzalnych kryteriów.

---

# 21. Branch / PR strategy

Dla każdego systemowego release'u osobny branch ze świeżego `origin/master`, np.:

```text
upgrade/v16.3.22-active-runtime-subject-root-hardening
upgrade/v16.3.23-persistent-runtime-lifecycle-observability
upgrade/v16.4.0-polish-lexical-normalization-evidence
upgrade/v16.4.1-polish-lexical-resource-provenance
upgrade/v16.4.2-polish-query-evidence-recall-interface
upgrade/v16.5.0-final-memory-source-fidelity-provenance
upgrade/v16.5.1-final-memory-package-attach-contract
upgrade/v16.5.2-private-memory-recall-acceptance-baseline
...
upgrade/v16.6.0-final-runtime-memory-nlp-convergence
```

Nie budować jednego długowiecznego brancha 16.6.0 z całym kodem.

Każdy branch:

- świeży master;
- backup/checkpoint;
- jeden release scope;
- version bump;
- test-first dla regresji;
- raport techniczny;
- PR do master;
- merge dopiero po realnych wymaganych PASS;
- kolejny etap zaczyna się z nowego master po merge poprzedniego.

---

# 22. Format raportu każdego release'u

`docs/reports/JAZN_Vxx_...md` powinien zawierać:

1. baseline SHA/version;
2. problem statement;
3. reprodukcję;
4. root cause;
5. invariants/truth boundary;
6. research basis;
7. zmienione pliki;
8. nowe testy;
9. znalezione po drodze błędy P0/P1 i ich naprawy;
10. test results;
11. niewykonane testy + powód;
12. private-data boundary;
13. release metadata procedure;
14. rollback/checkpoint;
15. zależności od następnego etapu.

---

# 23. Kryteria STOP/GO

## GO do następnego etapu tylko gdy

- bieżący branch ma jasno zamknięty zakres;
- wszystkie P0/P1 są naprawione;
- dla v16.3.23 pre-response gate ma PASS i `host_routing_bypass=0`;
- required tests realnie przeszły;
- CI wymagane dla platform jest zielone;
- nie ma prywatnych danych w diffie;
- report odpowiada kodowi;
- release metadata są kanoniczne;
- branch/PR nie zawiera przypadkowych zmian;
- merge faktycznie istnieje na master.

## STOP, jeśli

- test pokazuje niejasny truth state;
- host może odpowiedzieć rozmownie przed wejściem do runtime gate;
- host może pokazać kandydat przed obowiązkową finalizacją;
- poprawka wymaga wyłączenia kontroli;
- benchmark jest wykonywany na niezidentyfikowanej bazie;
- źródło prywatne nie ma exact provenance;
- attach omija package contract;
- runtime może być one-shot, a test twierdzi persistent;
- Recall poprawia się kosztem false-memory/leakage;
- „finalny” wynik pochodzi ze starego snapshotu.

---

# 24. Czego celowo NIE robić

- nie trenować modelu do naprawy runtime identity;
- nie używać mocniejszego/cięższego LLM jako substytutu deterministycznego host pre-response gate;
- nie traktować wyższego poziomu reasoning jako wymogu poprawnego routingu Jaźni;
- nie dopisywać nagłówka Łatki jako kosmetycznego post-processingu odpowiedzi, która ominęła runtime;
- nie używać ciężkiego modelu zamiast naprawy deterministic normalizer;
- nie commitować dużych plWordNet/MWE DB;
- nie automatyzować L3;
- nie ufać nazwom/rozmiarom plików zamiast SHA provenance;
- nie kopiować ręcznie memory DB jako „attach”;
- nie osłabiać endpoint identity;
- nie podnosić tylko timeoutu przy problemie recall latency;
- nie robić blind cherry-picków ze starych branchy;
- nie edytować ręcznie release manifests;
- nie zamykać #59 na podstawie synthetic fixtures lub zielonego CI.

---

# 25. Finalna checklista v16.6.0

## Runtime

- [ ] 16.3.22 merged i A/B/B contract PASS.
- [ ] 16.3.23 P0 host pre-response gate PASS.
- [ ] `host_routing_bypass=0` dla deterministic gate suite.
- [ ] live host acceptance matrix PASS dla dostępnych poziomów reasoning; jeśli poziomów nie da się sterować programowo, ograniczenie jest jawnie zapisane i nie jest zastępowane fixture'em.
- [ ] runtime unavailable/finalization failure nie przechodzi do imitacji Łatki.
- [ ] 16.3.23 merged i persistent two-turn PASS.
- [ ] wrong root/PID/auth/heartbeat nadal fail-closed.
- [ ] unnecessary one-shot fallback = 0 dla zdrowego B.

## NLP

- [ ] canonical PolishTextNormalizer.
- [ ] NFC/Unicode/diacritics tests.
- [ ] POS ranking/filtering.
- [ ] Morfeusz ambiguity/OOV boundary.
- [ ] plWordNet version/provenance.
- [ ] project lexicon schema/boundary.
- [ ] offline regression corpus PASS.

## Memory build

- [ ] Test00 PASS dla final inventory.
- [ ] Test01 PASS.
- [ ] Test02 PASS.
- [ ] Test03 PASS.
- [ ] Test04 PASS.
- [ ] FINAL snapshot created canonically.
- [ ] DB SHA recorded privately/sanitized evidence.
- [ ] exact source provenance closure PASS.
- [ ] integrity/FK/FTS PASS.
- [ ] reproducibility PASS.

## Packaging/attach

- [ ] correct memory package profile.
- [ ] `.package.json` present.
- [ ] split hashes PASS.
- [ ] archive CRC/tree verification PASS.
- [ ] memory manifest PASS.
- [ ] canonical `memory-attach` PASS.
- [ ] runtime reports correct final DB identity.

## Recall/multi-turn

- [ ] Recall@k measured.
- [ ] MRR measured.
- [ ] nDCG measured.
- [ ] wrong-conversation measured and accepted.
- [ ] false-memory accepted.
- [ ] abstention accepted.
- [ ] provenance accuracy accepted.
- [ ] temporal/update accepted.
- [ ] sensitive leakage gate PASS.
- [ ] natural referential follow-up PASS.
- [ ] multi-session PASS.

## L2/L3/restart

- [ ] candidates refreshed.
- [ ] manual review complete.
- [ ] every promotion has request/decision/ledger.
- [ ] zero promotions is allowed if justified.
- [ ] restart continuity on final DB PASS.
- [ ] same final memory identity before/after restart.

## Release

- [ ] compileall PASS.
- [ ] full deterministic pytest PASS.
- [ ] doctor PASS.
- [ ] system package-smoke PASS.
- [ ] `git diff --check` PASS.
- [ ] release package-smoke PASS from clean commit.
- [ ] release-build PASS.
- [ ] Windows CI PASS.
- [ ] Ubuntu CI PASS.
- [ ] metadata sync canonical.
- [ ] no private/protected files in PR.
- [ ] final report created.
- [ ] #59 updated with sanitized evidence.
- [ ] #59 closed only after every final gate above.

---

# 26. Definition of Done całego programu

Program v16.6.0 jest zakończony dopiero wtedy, gdy można na podstawie **rzeczywistych wyników narzędzi** powiedzieć jednocześnie:

1. host nie tylko wie, który runtime jest aktywny, ale też **nie może wygenerować rozmownej odpowiedzi Łatki przed przejściem przez deterministyczny pre-response gate**;
2. routing do Jaźni nie zależy od poziomu reasoning hosta, a każdy visible output ma jawne, audytowalne pochodzenie (`runtime_exact`, `runtime_finalized` albo `host_diagnostic`);
3. persistent daemon jest używany wtedy, kiedy jest zdrowy;
4. polskie NLP ma jeden spójny i audytowalny kontrakt;
5. finalna pamięć została odbudowana bez utraty/provenance gap;
6. finalna paczka pamięci jest poprawnie dołączona;
7. Recall i naturalna rozmowa działają na finalnym artefakcie;
8. system abstainuje, gdy nie ma dowodu, zamiast konfabulować;
9. L3 pozostaje pod jawną kontrolą;
10. restart nie zmienia tożsamości aktywnej pamięci;
11. Issue #59 ma komplet sanitizowanych dowodów i może zostać zamknięte.

Dopiero ten stan nazywamy **v16.6.0 final runtime-memory-NLP convergence**.
