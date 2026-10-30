# PR #436 — CI i kolejka pełnego odbioru TPA (2026-10-30)

> **DRAFT / NIE JEST ODBIOREM PRODUKCYJNYM.** Ten raport dokumentuje odczyt GitHub Actions i brak zweryfikowanych dowodów lokalnych. Nie zapisuje wyników do lokalnego TPA, nie uruchamia testów na komputerze operatora i nie zamienia CI PASS w `full_gate=PASS`.

## Zakres i źródło prawdy

- Repo: `SmuklyLew/jazn_latka`; gałąź `integration/tpa-heart-studio-20261029`; [Draft PR #436](https://github.com/SmuklyLew/jazn_latka/pull/436) do `master`.
- **Źródłowy HEAD objęty potwierdzonym CI:** `fe9ea2c8565103a8541713e93b39116ee2e34ad5`. To SHA sprzed niniejszego commita dokumentacyjnego; kolejny HEAD musi mieć osobną kontrolę CI. Nie przenosić automatycznie zielonego statusu na nowy commit.
- Odczyt GitHub API: **2026-10-30 (Europe/Warsaw, CET)**. `in_progress=0`, `queued=0` w repozytorium; 13/13 workflow dla źródłowego HEAD zakończone `success`. Ostatni `powershell-terminal-regressions` zakończył się 2026-10-29 23:24:18 UTC.
- 55 jobs: **53 success, 2 skipped, 0 failure, 0 cancelled, 0 timed_out**. Wszystkie 13 workflow mają końcowe `conclusion=success`.
- `release-hardening/manifest_sync=success`, Windows i Ubuntu verify = success. `release finalization=skipped` **zgodnie z** `if: github.event_name != 'pull_request'` w `.github/workflows/release-hardening.yml`.
- `package-distribution-cleanroom/persist canonical dependency locks and release metadata=skipped` **zgodnie z** warunkiem `push` na określone gałęzie w `.github/workflows/package-distribution-cleanroom.yml`. Pominięcia są warunkowe, nie dowodzą wydania.
- PR: `mergeable=true`, `mergeable_state=clean`, **draft=true**. Stan technicznej możliwości merge nie jest zgodą na merge ani potwierdzeniem lokalnego odbioru.
- Brak nieudanych jobów, więc nie było logów błędów do diagnozowania; dla pominiętych sprawdzono warunki w workflow. Nie pobrano prywatnych danych operatora.

## Wynik wszystkich 13 workflow na wskazanym SHA

| Workflow | Run | Jobs |
| --- | --- | --- |
| jazn-run-studio | [40969824308](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824308) | 7 PASS |
| dependency-review | [40969824536](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824536) | 1 PASS |
| javascript-node24-contract | [40969824298](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824298) | 2 PASS |
| Stable test contracts | [40969824271](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824271) | 1 PASS |
| pyright-active-tree-audit | [40969824310](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824310) | 1 PASS |
| MCP container build and Compose deployment smoke | [40969824352](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824352) | 1 PASS |
| memory-cloud optional capability release gate | [40969824281](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824281) | 4 PASS |
| persistent-runtime-e2e | [40969824451](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824451) | 2 PASS |
| host-spawn-memory-convergence | [40969824234](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824234) | 4 PASS |
| MCP 2026-07-28 conformance release gate | [40969824242](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824242) | 2 PASS |
| release-hardening | [40969824235](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824235) | 9 PASS / 1 SKIPPED (release finalization) |
| package-distribution-cleanroom | [40969824455](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824455) | 18 PASS / 1 SKIPPED (persist canonical locks/metadata) |
| powershell-terminal-regressions | [40969824492](https://github.com/SmuklyLew/jazn_latka/actions/runs/40969824492) | 1 PASS |

## Kolejka pełnego odbioru: 22/22 scenariusze TPA

**Dwie niezależne osie:** `regression_subset` jest uruchamiany automatycznie w TPA i wymaga własnego JUnit/logów. Zielony zbiorczy GitHub CI **nie dowodzi**, że każdy z 22 podtestów miał indywidualny `PASS`. W tym raporcie status indywidualnego podtestu TPA pozostaje **NIEZWERYFIKOWANY**. `full_gate` poniżej opisuje **brak dowodu pełnego odbioru na aktualnym źródłowym SHA**. `NOT_RUN` nie twierdzi, że operator nigdy wcześniej nie testował starszej wersji; `BLOCKED` wskazuje udokumentowaną lukę, a nie zaobserwowany w tym przebiegu FAIL.

| ID scenariusza | `full_gate` (dowody tego SHA) | Do wykonania / przyczyna |
| --- | --- | --- |
| `gui-daemon` | **NOT_RUN** | TPA: izolowany start/status, root/PID/instance/heartbeat i kontrolowany stop |
| `ollama-two-turns` | **NOT_RUN** | TPA P4: dwie rzeczywiste tury lokalnej Ollamy, jedna sesja, kod, display/ACK |
| `chat-reconnect` | **NOT_RUN** | TPA P4: rozłączenie własnego transportu, zachowana sesja i kod |
| `chat-resume` | **NOT_RUN** | TPA P4: resume tego samego request_id bez replay, jedna finalizacja/ACK |
| `daemon-restart` | **NOT_RUN** | TPA P4: restart wyłącznie izolowanego daemona, nowa instancja i ciągłość sesji |
| `smoke-isolation` | **NOT_RUN** | TPA: sentinele syntetyczne, porównanie markerów przed/po |
| `config-persistence` | **NOT_RUN** | TPA: izolowany profil ROOT, reload, previous-profile, CAS/conflict |
| `studios-parity` | **BLOCKED** | Pełna parzystość 12 natywnych Qt nieukończona; wymagane 12 odrębnych odbiorów i usunięcie luk w STUDIO_MIGRATION.md |
| `offline-exe` | **NOT_RUN** | TPA P5: final-source Windows onedir/VM offline, SHA/BUILD_INFO/manifest; osobny AV security HOLD do rozstrzygnięcia przed wykonaniem |
| `ui-accessibility` | **NOT_RUN** | TPA P5: realne Windows Qt, klawiatura, 860×580, motywy, DPI 100/150/200% |
| `studio-system` | **NOT_RUN** | TPA: aktualizacje/audyty/ustawienia i odmowy; macierz Qt nadal częściowa |
| `studio-start` | **NOT_RUN** | TPA: katalog usług, ownership, gotowość, logi; macierz Qt nadal częściowa |
| `studio-configuration` | **NOT_RUN** | TPA: Qt preview/save/restore, migracja ROOT, konflikt CAS, dirty-state |
| `studio-memory` | **NOT_RUN** | TPA: syntetyczne źródła/role, kandydaci, afekt, protokół; macierz Qt nadal częściowa |
| `studio-memory-rebuild` | **NOT_RUN** | TPA: plan, walidacja, anulowanie, eksport w izolowanym projekcie |
| `studio-test-studio` | **BLOCKED** | Brak potwierdzonego pełnego natywnego Qt review editor/history; uzupełnić przepływy i wykonać odbiór TPA |
| `studio-generator` | **NOT_RUN** | TPA: plan/pack/verify/split/join, anulowanie i ustawienia w sandboxie |
| `studio-dependencies` | **NOT_RUN** | TPA: inspect/verify lock/wheelhouse, instalacja tylko do testowego venv po potwierdzeniu |
| `studio-python-runtime` | **NOT_RUN** | TPA: detect-host, inwentarz, błędny interpreter/pakiet |
| `studio-version-rebuild` | **BLOCKED** | Natywny Qt tylko częściowy (read-only); brakuje pełnego edit/diff/backup/sync/rollback, wymagany TPA |
| `studio-chat-import` | **BLOCKED** | Brak kompletnego dedykowanego natywnego Qt import/verify/queue/search; nie zastępować klasycznym oknem |
| `studio-memory-restore` | **BLOCKED** | Brak kompletnego natywnego Qt scan/plan/backup/restore/compare; nie wykonywać na prywatnej MEMORY |

**Bilans:** 17 × `NOT_RUN` / DO WYKONANIA (TPA); 5 × `BLOCKED` (udokumentowane luki pełnej parzystości). Żaden `full_gate` nie jest `PASS` na podstawie samego CI. Dla `BLOCKED` należy najpierw domknąć brakujący natywny workflow, potem wykonać TPA i zebrać dowód.

## Kolejność lokalnego odbioru i ograniczenia

1. Uruchomić TPA na **oddzielnym, zweryfikowanym stagingu** dokładnie odpowiadającym SHA i wersji. `Sprawdź gotowość` → `Uruchom dostępne automatyczne` / wybór podtestów; sprawdzić JUnit, logi, `status`, `full_gate`. Brak modelu, PySide6, wheelhouse lub Windows VM = jawne `BLOCKED`/`NOT_RUN`, nie `PASS`.
2. P4: istniejąca lokalna Ollama; izolowany daemon; dwie realne tury, reconnect, resume **tego samego** request_id, restart tylko własnej instancji, sprawdzenie session/request/turn/trace, lineage i `display_exact`/ACK. Nie utożsamiać syntetycznego testu z zaakceptowaną wypowiedzią modelu.
3. P5: niezależna weryfikacja final-source `onedir` Windows (EXE + `_internal` + `BUILD_INFO.json` + manifest), hashe całego pakietu i licencje. Historyczne Avast `IDP.Generic` pozostaje **security HOLD**: brak niezależnego rozstrzygnięcia, nie przywracać pliku z kwarantanny ani nie wyłączać AV. Po pozytywnym rozstrzygnięciu — odizolowana VM bez sieci i raport człowieka.
4. GUI: prawdziwe okno Windows, klawiatura i 860×580, motywy, DPI 100/150/200%, odrębny raport i identyfikacja zrzutów; offscreen nie zastępuje odbioru.
5. P3: 12 odrębnych odbiorów `studio-*` na tej samej wersji/SHA; porównanie funkcji natywnych Qt ze starszymi narzędziami, sukcesy/błędy, ustawienia i backup. Nie uznawać launchera starego okna za parzystość Qt. Po usunięciu luk `BLOCKED` powtórzyć ich odbiór.
6. Wyniki operatora i dowody pozostają poza repo, w TPA (`~/.jazn/tools/jazn_studio_manual_acceptance/manual_results.json` lub kanoniczna lokalizacja operatora). Nie commitować prywatnych logów, MEMORY, tokenów, baz, markerów ani zrzutów z sekretami.

## Decyzja

- **CI źródłowego SHA: PASS (z dwoma warunkowymi SKIPPED).**
- **P3/P4/P5 i `full_gate` TPA: OPEN / NOT ACCEPTED**. Release i merge: **HOLD**; PR pozostaje Draft.
- Ten commit to **wyłącznie raport dokumentacyjny**. Nie zmienia kodu, wersji, manifestu, provenance, lokalnych wyników TPA ani runtime. Jego nowy HEAD wymaga świeżego sprawdzenia CI przed jakąkolwiek finalną deklaracją.

## Materiały źródłowe

- `AGENTS.md`, `AGENTS.codex.md` — instrukcje repozytorium.
- `tools/jazn_run_studio/TPA_WORKBENCH.md`, `tools/jazn_run_studio/tpa_catalog.py`, `tools/jazn_run_studio/local_acceptance.py` — 22 scenariusze i oddzielenie regresji od `full_gate`.
- `tools/jazn_run_studio/STUDIO_MIGRATION.md` — częściowa parzystość Qt; `docs/reports/JAZN_STUDIO_P4_P5_ACCEPTANCE_EVIDENCE_20261024.md` — historyczne P4/P5 i Avast HOLD.
- [GitHub Actions dla repozytorium](https://github.com/SmuklyLew/jazn_latka/actions) oraz powiązane runy powyżej.

---

## Kolejna kontrola CI — ff6d5927 (2026-10-30, ok. 04:24 CET)

**Zakres nowego odczytu GitHub API:** Draft PR #436, źródłowy HEAD `ff6d5927f24325fa06a424915b189f6b133c00ae`, gałąź `integration/tpa-heart-studio-20261029`. To osobny, nowszy odczyt niż historyczna tabela `fe9ea2c` powyżej; historycznych dowodów nie nadpisano.

- **Wszystkie 13/13 workflow przypisane do `ff6d5927f24325fa06a424915b189f6b133c00ae` zakończone `completed/success`**. Wynik 55 jobs: **53 success, 2 skipped, 0 failure, 0 cancelled, 0 timed_out, 0 in_progress, 0 queued**. Ostatni workflow `powershell-terminal-regressions` zakończył się 2026-10-30 02:25:01 UTC.
- `release-hardening/manifest_sync=success`; `verify (ubuntu-latest)=success`, `verify (windows-latest targeted)=success`; 6 macierzy dependency contract = success. Weryfikacja idempotencji metadanych jest częścią ukończonego workflow.
- Dwa `skipped` są **warunkowe**: `release finalization` (wyłączony dla `pull_request` w `.github/workflows/release-hardening.yml`) i `persist canonical dependency locks and release metadata` (tylko `push` do wskazanych gałęzi w `.github/workflows/package-distribution-cleanroom.yml`). Nie są dowodem zakończenia wydania.
- PR w chwili odczytu: `draft=true`, `mergeable=true`, `mergeable_state=clean`. Techniczna możliwość merge nie oznacza zgody na merge.
- **Globalny widok repozytorium:** `queued=0`, ale jeden `in_progress` dotyczył **innej gałęzi** `upgrade/heart-unified-operator-ui-20261030`, run [40996915081](https://github.com/SmuklyLew/jazn_latka/actions/runs/40996915081), SHA `288ffea605567af725ace25f97a6455a99b2d606`. Nie należy mylić go z brakującym jobem PR #436.
- Na aktualnym źródłowym HEAD nie ma nieudanych jobów ani logów błędów do naprawy. Dla poprzedniego SHA `4df4cda2` odczytano log [powershell-terminal-regressions 40987159933](https://github.com/SmuklyLew/jazn_latka/actions/runs/40987159933): test `test_isolated_health_check_is_fast_valid_and_has_no_semantic_write` przekroczył rygorystyczne 5 s (`5.0213192 < 5.0` było fałszywe). To **rzeczywisty FAIL testu CI na Windows**, nie niewykonany odbiór TPA. Na `ff6d5927f24325fa06a424915b189f6b133c00ae` ten sam workflow jest `success`; pojedynczy zielony przebieg nie dowodzi trwałego wyeliminowania niestabilności czasu.

| Workflow na `ff6d592` | Run | Wynik jobs |
| --- | --- | --- |
| dependency-review | [40989887284](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887284) | 1 PASS |
| powershell-terminal-regressions | [40989887334](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887334) | 1 PASS |
| jazn-run-studio | [40989887414](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887414) | 7 PASS |
| package-distribution-cleanroom | [40989887320](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887320) | 18 PASS / 1 SKIPPED |
| Stable test contracts | [40989887434](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887434) | 1 PASS |
| pyright-active-tree-audit | [40989887275](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887275) | 1 PASS |
| host-spawn-memory-convergence | [40989887324](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887324) | 4 PASS |
| MCP container build and Compose deployment smoke | [40989887439](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887439) | 1 PASS |
| memory-cloud optional capability release gate | [40989887321](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887321) | 4 PASS |
| javascript-node24-contract | [40989887328](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887328) | 2 PASS |
| MCP 2026-07-28 conformance release gate | [40989887309](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887309) | 2 PASS |
| persistent-runtime-e2e | [40989887347](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887347) | 2 PASS |
| release-hardening | [40989887352](https://github.com/SmuklyLew/jazn_latka/actions/runs/40989887352) | 9 PASS / 1 SKIPPED |

### TPA — stan pozostaje otwarty

Zachowano **22/22 scenariusze** opisane w tabeli powyżej i w `tools/jazn_run_studio/tpa_catalog.py`. Nie otrzymano nowego dowodu operatora dla `ff6d5927f24325fa06a424915b189f6b133c00ae`, więc **17 × DO WYKONANIA (TPA) / NOT_RUN, 5 × BLOCKED** pozostaje bez zmian. Zbiorcze CI `success` **nie** nadaje żadnemu scenariuszowi `full_gate=PASS`; automatyczny `regression_subset` TPA nadal wymaga indywidualnych JUnit/logów.

Otwarte: P4 rzeczywiste dwie tury lokalnej Ollamy, reconnect/resume tego samego `request_id`, izolowany restart i ACK; P5 Windows `onedir` EXE z SHA/BUILD_INFO/manifestem, niezależna kontrola AV (`IDP.Generic` — **security HOLD**), offline VM, rzeczywiste Qt i DPI 100/150/200%; 12 odrębnych studiów Qt, w tym pięć opisanych luk `BLOCKED`. Wymagane są dowody z izolowanego stagingu **tego samego SHA i wersji**. Release/merge nadal **HOLD**.

**Granica nowego commita:** aktualizacja niniejszego raportu jest wyłącznie dokumentacyjna i sama przesuwa HEAD PR. Sukces `ff6d5927f24325fa06a424915b189f6b133c00ae` nie może być przypisany nowemu commitowi dokumentacyjnemu; po zapisie trzeba osobno zweryfikować jego GitHub Actions. Nie zmieniano `master`, runtime, prywatnej MEMORY, sekretów ani manifestu ręcznie.
