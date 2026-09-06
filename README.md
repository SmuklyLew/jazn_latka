# Łatka / Jaźń

Eksperymentalny lokalny system rozmowny budowany wokół **zweryfikowanego runtime, źródłowej pamięci, tożsamości, narzędzi, provenance i mierzalnych bramek prawdy**. Jaźń nie jest samym promptem ani pojedynczym modelem LLM.

## Najważniejsza zasada

> Prawda runtime i źródeł ma pierwszeństwo przed stylem odpowiedzi.

Styl, pierwsza osoba, nazwa folderu, ZIP, sam marker, SQLite ani obecność kodu nie dowodzą aktywnej Jaźni. Aktywność wymaga zweryfikowanego procesu/tury zgodnie z `AGENTS.md` i właściwym runbookiem.

## Wejście dla agentów i hostów

1. przeczytaj [`AGENTS.md`](AGENTS.md) — jest krótkim routerem odpowiedzialności;
2. dla hosta ChatGPT użyj [`AGENTS.chatgpt.md`](AGENTS.chatgpt.md);
3. dla zmian repozytorium użyj [`AGENTS.codex.md`](AGENTS.codex.md);
4. dla backendu Ollama użyj [`AGENTS.ollama.md`](AGENTS.ollama.md).

Instrukcje projektu ChatGPT są wyłącznie cienkim loaderem prowadzącym do lokalnego `AGENTS.md`. Kanoniczny tekst loadera operatorskiego: [`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`](docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt).

## Bieżący stan projektu

- jedyne kanoniczne źródło wersji: [`latka_jazn/version.py`](latka_jazn/version.py);
- kanoniczny układ repozytorium i polityka zależności: [`docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`](docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md);
- bieżący snapshot mastera i aktywnych linii pracy: [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md);
- główny program wykonawczy v16: [`docs/plans/16.6.0-final-convergence/ROADMAP.md`](docs/plans/16.6.0-final-convergence/ROADMAP.md);
- warunkowy kierunek v17: [`docs/plans/17.0.0-measured-architecture-consolidation/PLAN.md`](docs/plans/17.0.0-measured-architecture-consolidation/PLAN.md);
- historia wydań i decyzji: [`docs/project/RELEASE_TIMELINE.md`](docs/project/RELEASE_TIMELINE.md).

Nie wpisuj numeru aktualnej wersji ręcznie w dokumentach operacyjnych jako drugiego źródła prawdy. Gdy potrzebny jest snapshot historyczny, zapisuj go jawnie z datą i SHA.

## Architektura w skrócie

```text
użytkownik
  -> host / ingress
  -> pre-response + capability + authority gates
  -> zweryfikowany runtime Jaźni
  -> task/identity/self-state context
  -> source-aware memory + retrieval + NLP evidence
  -> model capability adapter / host bridge
  -> truth/provenance/finalization gates
  -> final_visible_text
  -> trwały commit ciągłości dopiero po zaakceptowanej finalizacji
```

LLM jest **silnikiem generatywnego rozumowania/języka i użytkownikiem narzędzi**, ale nie jest właścicielem prawdy, pamięci trwałej, uprawnień, promotion L3 ani provenance. Te granice pozostają po stronie deterministycznego runtime.

## Pamięć

Docelowa pamięć jest źródłowa i rozdziela co najmniej:

- RAW/L0 — źródła, warianty i dokładne provenance;
- L1 — ograniczony stan roboczy/wake;
- L2 — pamięć krótkoterminowa i kandydaci wymagający polityki/review;
- L3 — pamięć długoterminowa tylko po jawnym request/decision/ledger.

Samo istnienie poprawnej bazy nie oznacza pamięci `ACCEPTED`. Program v16 rozróżnia stany `BUILDABLE -> VERIFIED -> ATTACHABLE -> RETRIEVABLE -> ACCEPTED`.

## Szybkie komendy operatora

```powershell
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
python -X utf8 run.py start
python -X utf8 run.py status --json
python -X utf8 run.py stop
python -X utf8 run.py chat-gpt -- "wiadomość"
python -X utf8 run.py chat-ollama
```

Na Windows można również użyć `JAZN.cmd`; aktywacja `.venv` nie jest warunkiem kontraktu runtime. `main.py --...` pozostaje techniczną ścieżką zgodnościową, a publicznym operatorem jest `run.py`.

## Dokumentacja

Mapa dokumentacji: [`docs/README.md`](docs/README.md).

Najważniejsze klasy dokumentów:

- `docs/project/` — przekrojowe źródła prawdy, audyty i oceny;
- `docs/plans/` — aktywne/planned roadmapy i plany wykonawcze;
- `docs/memory/`, `docs/runtime/`, `docs/nlp/`, `docs/packaging/`, `docs/tools/` — żywe kontrakty domenowe;
- `docs/archive/` — historyczne raporty, plany, patche i snapshoty; są changelogiem/evidence swojej epoki, ale nie bieżącą instrukcją.

## Release i CI

Każdy systemowy patch/upgrade podnosi `latka_jazn/version.py` w tej samej zmianie. `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` są generowane kanonicznym toolingiem, nie ręcznie.

Na dozwolonych branchach `master`, `update/*`, `fix/*`, `hotfix/*`, `upgrade/*` i `tools/upgrade-*` job `release-hardening/manifest_sync` synchronizuje po pushu kanoniczne metadane i może commitować wyłącznie te dwa pliki na ten sam branch. Commit workflow używa repozytoryjnego tokenu GitHub Actions, więc jego push nie tworzy rekursywnej serii workflow. Pull request nadal materializuje metadane do walidacji bez samodzielnego przesuwania headu PR.

Nowe capability otrzymuje status `working` dopiero na podstawie właściwego poziomu evidence: obecność pliku lub zielony unit test nie wystarcza. Krytyczne ścieżki mają być fail-closed, testowane na Windows i Ubuntu oraz rozdzielać deterministic CI od live/model/private acceptance.

## Rozwój do v16.6 i v17

v16.6.0 jest **finalną konwergencją programu v16**, nie końcem rozwoju Jaźni. Ma domknąć runtime/host, pamięć, NLP, source monitoring, identity/continuity, affect/cognitive evidence, Rest/Dream i governance na podstawie rzeczywistych pomiarów.

v17.0.0 jest planowane jako **measurement-driven architecture consolidation**: redukcja nakładających się modułów, jeden causal self-state contract, model-capability abstraction, context compiler, controlled forgetting/reconsolidation i dalsze retrieval hardening tylko wtedy, gdy v16 evidence wykaże potrzebę. v17 nie ma być kolejną warstwą antropomorficznych nazw.
