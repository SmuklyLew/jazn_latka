# Jaźń v16.3.25.5.102 — fast bootstrap & persistent runtime convergence

## Cel

Aktualizacja skraca ścieżkę od SYSTEM ZIP do gotowej rozmowy oraz usuwa
niepotrzebne ponowne koszty przy już działającym persistent runtime. Nie tworzy
drugiego control plane: `run.py` pozostaje cienkim starterem, `main.py`
właścicielem lifecycle, a istniejący daemon i supervisor pozostają kanonicznymi
mechanizmami procesu.

## Zakres

- Standalone `CHATGPT_BOOTSTRAP.py` zapisuje atomowy materialization stamp po
  poprawnym cold extract.
- `--reuse-existing-verified` omija ponowne CRC i dekompresję ZIP-a wyłącznie
  po zgodnym stampie oraz kryptograficznej weryfikacji wszystkich statycznych
  plików z `PACKAGE_INTEGRITY_MANIFEST.json`.
- `start_daemon()` ma prawdziwy warm path: poprawna live identity/root/version/
  heartbeat pozwala kontynuować już zweryfikowany daemon bez pełnego rehashu.
- Każdy rzeczywisty spawn/restart nadal przechodzi pełne package-integrity i
  source-provenance gates.
- Supervisor wymaga process identity oraz świeżego heartbeat lease; sam żywy PID
  nie jest wystarczającym dowodem.
- Intent creative/preservation wynika z `control_text`; dowolny fenced kod lub
  cytat nie może sam wymusić creative route. Strukturalne lyrics nadal mogą
  dostarczyć creative-material evidence.
- `AGENTS.chatgpt.md` definiuje warm/resume/cold oraz utrzymuje optional MEMORY
  poza krytyczną ścieżką core wake.

## Granica bezpieczeństwa

Warm path jest kontynuacją już działającego persistent runtime, a nie nową
aktywacją. Pełna walidacja statycznej paczki pozostaje obowiązkowa przy każdym
spawn/restart. Reuse materializacji nie ufa samemu stampowi: przed wykonaniem
operatora wszystkie statyczne pliki manifestu są sprawdzane rozmiarem i SHA-256.

## Regresje objęte testami

- cold extract -> verified reuse bez ponownej dekompresji;
- fail-closed po modyfikacji statycznego pliku;
- warm daemon bez ponownego cold integrity gate;
- stale supervisor heartbeat przy poprawnym PID identity;
- długi loader w fenced blocku ze słowami „zachowaj/generator/format” nie jest
  klasyfikowany jako creative;
- jawne „Przerób ... i zachowaj format” nadal trafia do creative formatting;
- strukturalny tekst piosenki nadal trafia do creative analysis.
