# Łatka / Jaźń — roadmapa do v16.6.0

## Runtime, host ingress, polski NLP, finalna pamięć i zamknięcie Issue #59

**Repozytorium:** `SmuklyLew/jazn_latka`  
**Bieżąca baza planu:** `master @ f56ea911d981295e37b8cf62e63cf806137dbfe0`  
**Wersja bazowa:** `16.3.25-memory-rebuild-source-union-hardening`  
**Cel końcowy programu:** `16.6.0-final-runtime-memory-nlp-convergence`  
**Issue odbiorcze pamięci:** `#59`  
**Aktualizacja roadmapy:** 2026-08-29

> Ta wersja roadmapy aktualizuje plan po wejściu linii `16.3.22`–`16.3.25` do historii `master`. Szczegółowy snapshot planu z 2026-08-27 zostaje zachowany jako dokument historyczny w `docs/archive/roadmaps/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP_2026-08-27.md`. Historyczne raporty release'ów pozostają dowodem stanu z chwili ich wykonania i nie są przepisywane retroaktywnie.

---

# 0. Fundament architektoniczny v16.0.0

Release **v16.0.0 / single-canonical-runtime-workspace** ustanowił invariant obowiązujący całą linię v16+:

1. istnieje jeden host-level `workspace_runtime`;
2. istnieje jeden kanoniczny `workspace_runtime/JAZN_ACTIVE_RUNTIME.json`;
3. mutable host/process state nie należy do wersjonowanego `active_root`;
4. historyczny `<active_root>/workspace_runtime` jest wyłącznie źródłem migracji/zgodności, nie równoległym źródłem prawdy;
5. `workspace_runtime` nie jest częścią paczki `system` ani `memory`;
6. sam marker nie dowodzi aktywnego procesu — trust nadal wymaga zgodnego rootu, integralności/provenance, PID/endpointu i świeżego heartbeat;
7. nowe namespace'y hosta mogą rozszerzać kanoniczny workspace, ale nie mogą tworzyć per-release mutable state.

Bieżący opis tego invariantu znajduje się w:

- `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`.

Plan `16.3.25.A.01+ -> 16.3.26` dla załączników i multimodalności **dziedziczy** ten kontrakt. Jeżeli potrzebna jest materializacja pliku, staging/cache ma należeć do host-level `workspace_runtime`, a nie do wersjonowanego kodu. Samo odebranie pliku nie oznacza zapisania go do pamięci.

---

# 1. Granice prawdy i źródła kanoniczne

Obowiązują aktualne `AGENTS.md`, `AGENTS.chatgpt.md`, `AGENTS.codex.md` oraz nested `AGENTS.md` dla zmienianych ścieżek.

Kanoniczne źródła prawdy technicznej:

- wersja: `latka_jazn/version.py`;
- integralność paczki: `PACKAGE_INTEGRITY_MANIFEST.json`;
- pochodzenie wydania: `SOURCE_PROVENANCE.json`;
- operator: `run.py`;
- techniczny punkt zgodności: `main.py`;
- aktywny runtime: zweryfikowany host-level `workspace_runtime/JAZN_ACTIVE_RUNTIME.json` + wskazany `active_root` + live truth gate;
- aktywna pamięć: `JAZN_MEMORY_ROOT` albo kanoniczny host-level `workspace_runtime/memory`;
- repozytorium: `SmuklyLew/jazn_latka`.

Nie wolno przedstawiać jako aktywnego runtime:

- samego ZIP-a;
- katalogu z kodem;
- samego markera;
- samego PID-u;
- odpowiedzi modelu;
- niezależnej bazy SQLite bez kanonicznego attach i truth gate.

Nie wolno commitować bez osobnego jawnego wyjątku:

- `memory/`;
- `workspace_runtime/`;
- SQLite/WAL/SHM;
- prywatnych eksportów;
- ZIP-ów i split parts;
- sekretów, tokenów i logów runtime.

---

# 2. Uniwersalny protokół pracy

Każdy **systemowy** patch/update/upgrade:

1. zaczyna się od świeżego `master` i odczytu obowiązujących AGENTS;
2. zapisuje baseline oraz bezpieczny checkpoint przed kodem;
3. dla P0/P1, jeśli technicznie możliwe, najpierw reprodukuje problem i dodaje regresję;
4. nie osłabia truth/integrity/safety tylko po to, żeby test był zielony;
5. podnosi `latka_jazn/version.py` w tej samej zmianie;
6. nie edytuje ręcznie `PACKAGE_INTEGRITY_MANIFEST.json` ani `SOURCE_PROVENANCE.json`;
7. kończy się skupionymi testami, pełną deterministyczną walidacją i właściwym E2E dla zmienianej platformy.

Dokumentacja planistyczna sama w sobie nie jest patchem systemowym i nie wymaga podbicia wersji runtime.

Jeżeli problem zostaje znaleziony **przed merge** bieżącego release branchu i nie zmienia zasadniczo zakresu, jest naprawiany w tym samym release. Problem znaleziony po merge wymaga kolejnego numeru.

---

# 3. Model stanu finalnej pamięci

Finalna pamięć przechodzi pięć jawnych stanów:

1. **BUILDABLE** — importer potrafi odtworzyć bazę ze źródeł.
2. **VERIFIED** — source fidelity, integrity, FK, FTS, provenance i reproducibility są zaliczone.
3. **ATTACHABLE** — finalny artefakt ma poprawny profil paczki, sidecary, hashe i przechodzi kanoniczny `memory-attach`.
4. **RETRIEVABLE** — aktualny benchmark Recall i naturalny multi-turn osiągają uzgodnione wyniki bez fałszywych wspomnień i leakage.
5. **ACCEPTED** — review L2/L3 jest zakończone, restart continuity przechodzi, runtime używa właściwej finalnej pamięci, a sanitizowany raport końcowy spełnia #59.

Żaden wcześniejszy stan nie implikuje następnego.

---

# 4. Release train do v16.6.0

| Linia | Status / cel | Kluczowy dowód PASS |
|---|---|---|
| `16.0.0` | **historyczny fundament:** single canonical runtime workspace | jeden host-level workspace/marker; brak per-release mutable truth state |
| `16.3.22` | **zrealizowane:** active runtime subject-root identity | `A -> B -> B` trusted, `A -> B -> C` fail-closed |
| `16.3.23` | **zrealizowane:** persistent daemon lifecycle + transport observability | subject-root B, lifecycle/reuse i transport widoczne diagnostycznie |
| `16.3.24` | **zrealizowane:** package provenance/bootstrap hardening | bootstrap i provenance paczki domknięte bez zgadywania źródła |
| `16.3.25` | **bieżąca baza:** Memory Rebuild source-union hardening | lossless source-union bez uznawania rozmiaru/nazwy/order za truth |
| `16.3.25.A.01+` | **train planistyczny, nie `PACKAGE_VERSION`:** host attachment/multimodal ingress | kolejne checkpointy jednego branchu prowadzącego do `16.3.26` |
| `16.3.26` | Host attachment + multimodal ingress convergence | attachment-only/text+multi-file/provenance/secure staging/vision capability PASS; brak auto-memory promotion |
| `16.4.0` | Kanoniczna normalizacja polskiego NLP + lexical evidence contract | deterministyczny fixture Unicode/POS/provenance |
| `16.4.1` | Morfeusz/plWordNet/project lexicon/resource registry hardening | ambiguity/OOV/resource provenance PASS |
| `16.4.2` | NLP/recall query interface i regression corpus | query evidence bez fałszywej pewności; offline PASS |
| `16.5.0` | Final Memory Rebuild: source fidelity + provenance + reproducibility | finalna DB VERIFIED |
| `16.5.1` | Final memory packaging + canonical attach | finalna DB ATTACHABLE |
| `16.5.2` | Prywatny Recall + natural multi-turn baseline | mierzalny raport jakości |
| `16.5.x` | tylko mierzone poprawki retrieval, jeśli baseline nie przejdzie | A/B improvement bez regresji safety |
| `16.5.y` | L2/L3 review + restart continuity + acceptance candidate | pamięć ACCEPTED-candidate |
| `16.6.0` | Finalna konwergencja runtime + host ingress + NLP + memory; closure #59 | wszystkie truth gates PASS |

Numery `16.5.x/y` pozostają rezerwą. Nie wymuszamy z góry liczby iteracji.

---

# 5. Historia zamkniętych etapów 16.3.22–16.3.25

## 5.1. v16.3.22 — Active runtime subject-root identity

Kontrakt rozdziela requested/observer root od subject root. Dla topologii:

```text
requested/staging root = A
host marker active_root = B
daemon endpoint root = B
```

integrity/provenance/version/endpoint aktywnego procesu są oceniane względem **B**, a A pozostaje informacją diagnostyczną. A/B/C i inne rozbieżności pozostają fail-closed.

## 5.2. v16.3.23 — Persistent runtime lifecycle observability

Lifecycle i transport rozszerzają poprawny subject-root contract. Persistent daemon może być reuse'owany pomiędzy turami, ale tylko po potwierdzeniu aktualnego rootu, procesu, endpointu i truth state. Stan procesu i session/checkpoint state nadal należą do host-level workspace z v16.0.0.

## 5.3. v16.3.24 — Package provenance/bootstrap hardening

Bootstrap paczki i provenance zostały rozdzielone od samej obecności kodu/ZIP-a. Package/root/source identity ma być jawna i weryfikowalna; nie wolno traktować nazwy pliku albo samego archiwum jako dowodu aktywności.

## 5.4. v16.3.25 — Memory Rebuild source-union hardening

Bieżąca baza domyka source-set closure dla Memory Rebuild: wszystkie lossless snapshoty ChatGPT są unionowane bez używania rozmiaru, kolejności lub nazwy pliku jako arbitra prawdy, a zachowana rozbieżność branchy jest oddzielona od nierozstrzygniętych edycji.

Szczegółowe raporty historyczne pozostają w `docs/reports/` i nie są przepisywane przez tę roadmapę.

---

# 6. v16.3.25.A.01+ — Attachment ingress implementation train

**Status:** numery A.xx są checkpointami planistycznymi jednego niezmargowanego trainu, nie kanonicznymi wersjami runtime.

**Plan szczegółowy:** `docs/plans/JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md`.

| Checkpoint | Zakres |
|---|---|
| `A.01` | audyt host→runtime, reprodukcja attachment-only, projekt kontraktu wejścia |
| `A.02` | text-only / attachment-only / text+attachments / multi-attachment |
| `A.03` | bounded secure staging w host-level `workspace_runtime` |
| `A.04` | text/document extraction, MIME/type policy, provenance |
| `A.05` | image ingress i capability negotiation |
| `A.06` | Ollama multimodal; text-only fail-closed |
| `A.07` | ChatGPT/MCP/runtime/model-context integration |
| `A.08` | memory boundary — plik nie jest automatycznie pamięcią |
| `A.09` | regression/security/E2E closure |
| `A.10+` | defect loop P0/P1 przed finalnym release closure |

Nie wykonujemy częściowych merge'y A.xx do `master`. Train ma prowadzić do jednego release'u systemowego `16.3.26`.

---

# 7. v16.3.26 — Host attachment + multimodal ingress

**Proponowany release name:** `host-attachment-multimodal-ingress-hardening`

## 7.1. Problem

Host/runtime contract jest nadal głównie tekstowy. Tura zawierająca sam plik może zostać zredukowana do pustego tekstu zamiast wejść do kanonicznego routingu. Obraz może być użyteczny tylko wtedy, gdy wybrany backend ma jawnie potwierdzone capability vision.

## 7.2. Invariants

- legalne są `text-only`, `attachment-only`, `text+attachments` i wiele załączników;
- nie używamy sztucznego placeholdera tekstowego do obejścia pustego `body`;
- oryginalny tekst użytkownika pozostaje zachowany lossless;
- attachment ma identity/type/size/source/ref oraz provenance;
- nazwa/ścieżka/MIME są nieufne i przechodzą policy gate;
- materializacja jest bounded i należy do host-level workspace zgodnego z v16.0.0;
- transient staging można usunąć bez utraty trwałej pamięci;
- plik/fakt z pliku nie staje się automatycznie L2/L3;
- model text-only nie może twierdzić, że widział obraz;
- unsupported typ/capability kończy się jawnie i fail-closed;
- prywatne bajty/treść plików nie trafiają do repo ani sanitizowanych raportów.

## 7.3. Zakres implementacyjny

Przed dodaniem nowej klasy sprawdzić odpowiedzialności istniejących:

- `latka_jazn/core/message_envelope.py`;
- istniejące turn/cognitive envelopes;
- `latka_jazn/core/chat_command_contract.py`;
- adapter ChatGPT / host bridge;
- MCP tools;
- model context compiler;
- model route/capability resolver;
- backend Ollama;
- memory use/promotion/truth gates.

Preferowany kierunek to jawny kontrakt **wejścia tury** z `text` i `attachments[]`, zamiast wtłaczania załączników do envelope finalnej widocznej odpowiedzi Łatki.

## 7.4. Acceptance

Release jest gotowy dopiero, gdy:

1. attachment-only dochodzi do kanonicznego runtime bez zawieszenia/pustej tury;
2. text+attachments i multi-attachment zachowują identity/order/provenance;
3. pliki tekstowe/dokumenty przechodzą jawne extract/policy gates;
4. obrazy trafiają tylko do backendu z potwierdzonym vision capability;
5. text-only/unsupported path jest fail-closed;
6. staging pozostaje w jednym host-level workspace;
7. zero automatycznej promocji plików/faktów do trwałej pamięci;
8. prywatna zawartość nie wycieka do repo/telemetrii;
9. regresje host/runtime, security i E2E przechodzą;
10. finalny systemowy branch ma kanoniczny `PACKAGE_VERSION = "16.3.26"`.

---

# 8. v16.4.0 — Kanoniczna normalizacja polskiego NLP

Prace NLP zaczynają się dopiero po zamknięciu kontraktu wejścia hosta z `16.3.26`, żeby późniejsza analiza językowa nie musiała równolegle rozwiązywać niejasności transportu załączników.

Zakres:

- jedna kanoniczna normalizacja Unicode/case/diakrytyki;
- lexical evidence z provenance;
- deterministyczne token/POS/resource fixtures;
- brak cichego uznawania heurystyki za fakt;
- zachowanie zgodności z memory query i routingiem.

**PASS:** deterministyczny corpus offline oraz jawny provenance każdej zewnętrznej warstwy leksykalnej.

---

# 9. v16.4.1 — Morfeusz/plWordNet/project lexicon/resource registry

Zakres:

- jawny rejestr zasobów i wersji;
- obsługa ambiguity/OOV;
- project lexicon bez maskowania niepewności;
- resource provenance i degrade/fail state;
- brak wymagania sieciowego dla krytycznej ścieżki rozmowy.

**PASS:** ambiguity/OOV/resource provenance suite bez fałszywej pewności.

---

# 10. v16.4.2 — NLP/recall query interface

Zakres:

- query evidence contract pomiędzy NLP a recall;
- regression corpus naturalnych polskich pytań;
- rozdzielenie sygnału leksykalnego od memory truth;
- brak automatycznej promocji wyniku heurystycznego do faktu.

**PASS:** mierzalne query/recall fixtures offline, bez leakage i fałszywej pewności.

---

# 11. v16.5.0 — Final Memory Rebuild

Cel: finalny artefakt pamięci osiąga stan **VERIFIED**.

Wymagane:

- pełna source fidelity;
- provenance każdego importu;
- reproducibility;
- integrity/FK/FTS;
- jawna deduplikacja bez utraty wariantów źródeł;
- brak prywatnych danych w repo/CI.

**PASS:** finalna DB VERIFIED z sanitizowanym raportem.

---

# 12. v16.5.1 — Packaging + canonical memory attach

Cel: finalna DB osiąga **ATTACHABLE**.

- poprawny profil paczki memory;
- sidecary/hashes;
- lokalny attach i opcjonalny cloud materialization przez ten sam canonical attach contract;
- brak traktowania chmury jako `active_root`;
- workspace/pamięć pozostają rozdzielone zgodnie z v16.0.0.

**PASS:** finalna DB ATTACHABLE po kanonicznym attach.

---

# 13. v16.5.2 / v16.5.x / v16.5.y — Recall i akceptacja

## 13.1. v16.5.2

Prywatny Recall + natural multi-turn baseline. Raport ma mierzyć trafność, fałszywe wspomnienia, abstention i continuity po restarcie.

## 13.2. v16.5.x

Tylko mierzone poprawki retrieval, jeśli baseline nie spełni kryteriów. Każda zmiana wymaga A/B i braku regresji safety/truth.

## 13.3. v16.5.y

Review L2/L3 + restart continuity + acceptance candidate. Jeśli kryteria przechodzą, pamięć może zostać oznaczona jako ACCEPTED-candidate.

---

# 14. v16.6.0 — Final convergence

v16.6.0 jest końcowym etapem programu, a nie miejscem na ukrywanie niezakończonych prac z wcześniejszych linii.

Wymagane jednocześnie:

- single canonical runtime workspace invariant z v16.0.0 zachowany;
- active runtime subject-root/truth gate poprawny;
- persistent host/runtime transport i finalization bez bypassu;
- host attachment/multimodal ingress z `16.3.26` zaakceptowany;
- polski NLP/resource provenance zaakceptowany;
- finalna pamięć ACCEPTED;
- restart continuity;
- prywatny recall/multi-turn spełnia ustalone bramki;
- packaging/provenance/integrity spójne;
- Issue #59 może zostać zamknięte na podstawie dowodów, nie deklaracji.

**PASS:** wszystkie wcześniejsze bramki są zielone i brak otwartego P0/P1 w zakresie finalnej konwergencji.

---

# 15. Branch strategy

Każdy release pracuje na osobnym branchu ze świeżego `master`.

Dla nowego trainu:

```text
upgrade/v16.3.26-host-attachment-multimodal-ingress-hardening
```

Checkpointy `16.3.25.A.xx` pozostają commitami/checkpointami tego jednego branchu, bez częściowych merge'y do `master`.

Dalsze przykładowe branche:

```text
upgrade/v16.4.0-polish-nlp-normalization
upgrade/v16.4.1-polish-lexical-resources
upgrade/v16.4.2-nlp-recall-query-interface
upgrade/v16.5.0-final-memory-rebuild
upgrade/v16.5.1-final-memory-packaging-attach
upgrade/v16.5.2-private-recall-baseline
upgrade/v16.6.0-final-convergence
```

Nie cherry-pickować szerokich, starych branchy „w ciemno”. Najpierw semantycznie porównać kod, raporty i aktualny `master`.

---

# 16. Defect loop i priorytety

- **P0** — truth/safety/integrity, ryzyko obcego runtime, utraty pamięci/danych lub fałszywego sukcesu: blokuje release.
- **P1** — kryterium bieżącego release'u nie działa: blokuje release.
- **P2** — realny błąd poza krytycznym zakresem: tylko mała i bezpieczna poprawka teraz, inaczej backlog.
- **P3** — kosmetyka/refactor: nie rozszerzać release'u bez potrzeby.

Dla P0/P1:

```text
finding -> root cause -> źródło -> regression test -> fix -> focused test -> full suite -> raport
```

Nie wolno maskować świeżej regresji przez `xfail`, szeroki `except`, zwiększenie timeoutu bez diagnozy ani fallback udający naprawę przyczyny.

---

# 17. Research registry

Przy każdym release używać przede wszystkim źródeł pierwotnych/oficjalnych.

Dla `16.3.26` obowiązkowo zweryfikować aktualne:

- dokumentację OpenAI/ChatGPT dotyczącą file/image inputs i host capabilities;
- dokumentację OpenAI API dla używanych input contracts, jeśli runtime korzysta z API;
- dokumentację Ollama dotyczącą vision/multimodal input i capability modelu;
- Python/OS semantics dla bezpiecznej materializacji, atomic operations, temporary files i path handling;
- własne kontrakty repozytorium jako źródło prawdy o tym, co już istnieje.

Blogi, posty forum i wynik wyszukiwarki są materiałem pomocniczym, nie podstawą projektu, jeśli istnieje źródło oficjalne.

---

# 18. Dokumenty powiązane

- `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md` — bieżący invariant wywiedziony z v16.0.0;
- `docs/plans/JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` — szczegółowy train A.xx → 16.3.26;
- `docs/plans/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md` — historyczny plan subject-root;
- `docs/plans/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md` — historyczny plan lifecycle;
- `docs/reports/JAZN_V16_3_24_PACKAGE_PROVENANCE_BOOTSTRAP_HARDENING.md` — raport 16.3.24;
- `docs/reports/JAZN_V16_3_25_MEMORY_REBUILD_SOURCE_UNION_HARDENING.md` — raport 16.3.25;
- `docs/archive/roadmaps/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP_2026-08-27.md` — zachowany szczegółowy snapshot poprzedniej roadmapy.

Historyczne raporty nie są aktualizowane retroaktywnie: mają pozostać dowodem tego, co zostało wykonane i zweryfikowane w danym release.

---

# 19. Zasada końcowa

Roadmapa jest planem, nie dowodem aktywności ani poprawności runtime. Każdy przyszły systemowy release musi osobno udowodnić swoje kryteria na aktualnym kodzie i właściwej platformie.

Dla najbliższej kontynuacji kolejność jest jawna:

```text
master 16.3.25
  -> 16.3.25.A.01+
  -> 16.3.26 host attachment + multimodal ingress
  -> 16.4.x polski NLP
  -> 16.5.x final memory acceptance
  -> 16.6.0 final convergence
```
