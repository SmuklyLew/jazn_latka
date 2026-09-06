# Kanoniczny układ repozytorium i polityka zależności Jaźni

Ten dokument definiuje bieżący kontrakt organizacji repozytorium `SmuklyLew/jazn_latka`.
Nie jest historycznym planem migracji. Jego celem jest utrzymanie jednego
przewidywalnego układu dla Windows, Linux, rozpakowanej paczki runtime, hosta
ChatGPT oraz lokalnych backendów LLM takich jak Ollama.

## 1. Zasada nadrzędna

Struktura ma służyć działającemu runtime, a nie estetyce drzewa.

`run.py` pozostaje kanonicznym publicznym operatorem i musi działać bezpośrednio
z poprawnie rozpakowanego rootu systemu. Z tego powodu projekt świadomie
pozostaje przy flat-layout dla pakietu `latka_jazn/`: przeniesienie całego kodu
do `src/` wymagałoby instalacji pakietu albo manipulacji `sys.path`, co
osłabiałoby kontrakt portable/offline runtime.

Nie przenoś stabilnych ścieżek operatorskich tylko po to, aby upodobnić repo do
innego szablonu projektu.

## 2. Kanoniczne role katalogów

```text
/
├─ run.py                         # publiczny operator Jaźni
├─ main.py                        # compatibility/implementation entrypoint
├─ AGENTS*.md                     # routing i runbooki hostów/agentów
├─ pyproject.toml                 # kanoniczne deklaracje zależności Pythona
├─ requirements.txt               # compatibility/cache marker, nie drugie źródło deps
├─ latka_jazn/                    # importowalny kod systemu
│  ├─ bootstrap/                  # discovery/materializacja/recovery
│  ├─ core/                       # runtime, gates, routing, lifecycle i kontrakty tury
│  ├─ adapters/ + model_adapters/ # granice modeli i hostów
│  ├─ bridge/ + mcp/              # transporty host-runtime
│  ├─ memory/ + db/               # pamięć i trwałe magazyny
│  ├─ dependencies/               # dependency studio i offline bundles
│  ├─ nlp/                        # przetwarzanie języka
│  ├─ resources/                  # wersjonowane zasoby statyczne
│  └─ tools/                      # narzędzia należące do pakietu
├─ tools/                         # narzędzia repo/release/operator studio
├─ tests/                         # aktywne testy
│  └─ archive/                    # append-only snapshoty historycznych testów
├─ docs/                          # żywa dokumentacja i archiwum
└─ .github/workflows/             # CI/release evidence
```

Mutable/private state nie należy do drzewa wydania: `workspace_runtime/`,
`memory/`, SQLite/WAL/SHM, logi, PID-y, heartbeat, sekrety i staging są
oddzielone od statycznego kodu i manifestu paczki.

## 3. Publiczne entrypointy

- lifecycle i diagnostyka: `python -X utf8 run.py <command>`;
- ChatGPT: `python -X utf8 run.py chat-gpt ...`;
- Ollama: `python -X utf8 run.py chat-ollama ...`;
- `main.py --...` pozostaje kompatybilnością dla istniejących integracji, a nie
  drugim równorzędnym operatorem.

Warstwa modelu nie jest właścicielem tożsamości, pamięci, provenance,
uprawnień ani finalizacji. Te granice pozostają w runtime Jaźni.

## 4. Polityka zależności: stdlib/host-first

Nowa biblioteka zewnętrzna nie trafia do rdzenia dlatego, że jest popularna albo
ułatwia kilka linii kodu. Dodanie zależności wymaga jednocześnie:

1. konkretnej brakującej capability, której nie zapewnia bezpiecznie standardowa
   biblioteka Pythona ani host wykonawczy;
2. uzasadnienia cross-platform dla Windows i Linux;
3. testu regresyjnego/kontraktowego;
4. zgodności licencyjnej i wersji wspieranej przez używane Python ABI;
5. możliwości materializacji w zweryfikowanym offline wheelhouse z hash-lockiem;
6. fail-closed zachowania, gdy dependency bundle jest niedostępny lub niezgodny.

`pyproject.toml [project].dependencies` jest źródłem bezpośrednich zależności
rdzenia. Capability opcjonalne należą do `[project.optional-dependencies]`.
Dokładne, reprodukowalne artefakty instalacyjne należą do
`JAZN_WHEELHOUSE_REQUIREMENTS.txt` generowanego przez Dependency Studio; hashy
nie wpisuje się ręcznie.

## 5. ChatGPT

ChatGPT w Projekcie jest hostem/runtime executor channel, a nie pakietem Python
instalowanym przez Jaźń. Nie dodawaj `openai` SDK jako zależności tylko po to,
aby rozmawiać z Jaźnią w środowisku ChatGPT. Lokalna ścieżka hosta korzysta z
`run.py chat-gpt` albo zatwierdzonego transportu MCP dostępnego w danym hoście.

Instrukcje Projektu pozostają cienkim loaderem. Dostęp do terminala, plików,
sieci i innych narzędzi jest capability hosta i musi być wykrywany, a nie
zakładany.

## 6. Ollama

Lokalna Ollama pozostaje wymienną warstwą językową. Runtime korzysta z jej
lokalnego HTTP API i nie wymaga `OPENAI_API_KEY`. Nie dodawaj pakietu Python
`ollama` ani `openai` do rdzenia, dopóki natywny transport HTTP spełnia
kontrakt i nie istnieje zmierzona luka funkcjonalna.

Stan Ollamy i stan Jaźni raportuj oddzielnie: działający endpoint modelu nie
jest dowodem aktywnego runtime Jaźni.

## 7. Release i synchronizacja metadanych

Każdy systemowy patch podnosi `latka_jazn/version.py`.

Kanoniczne `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` tworzy
wyłącznie `latka_jazn.tools.release_metadata_sync`. Na dozwolonych branchach
`master`, `update/*`, `fix/*`, `hotfix/*`, `upgrade/*` i `tools/upgrade-*`
workflow `release-hardening/manifest_sync` ma po pushu synchronizować i
commitować wyłącznie te dwa pliki. Pull request nadal waliduje metadane bez
samodzielnego przesuwania headu PR.

Branch nie jest gotowy do raportu jako release candidate, dopóki synchronizacja
jest idempotentna i wymagane CI nie jest zielone.

## 8. Zmiany strukturalne

Masowe przeniesienie katalogu jest dopuszczalne tylko wtedy, gdy jednocześnie:

- istnieje zmierzony problem, który przeniesienie rozwiązuje;
- wszystkie publiczne entrypointy i package profiles mają plan migracji;
- testy Windows/Linux i clean-room package przechodzą przed usunięciem aliasów;
- manifest, provenance, dokumentacja i recovery zostały zaktualizowane;
- nie powstaje drugi kanoniczny root, pamięć ani workspace.

Bez tych dowodów preferuj reorganizację odpowiedzialności wewnątrz istniejących
modułów zamiast masowego rename/move.
