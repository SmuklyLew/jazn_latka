# Jaźń v16.3.22 — plan wykonawczy Active Runtime Subject-Root Identity

## Status dokumentu

**Typ:** implementation plan / plan wykonawczy przed implementacją  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Stan bazowy potwierdzony podczas przygotowania:** `master @ 3a2c2f053cf71e426367359b14f15efb6f3daa52`  
**Wersja bazowa:** `16.3.21-chatgpt-runtime-fallback-hardening`  
**Wersja docelowa etapu:** `16.3.22-active-runtime-subject-root-hardening`  
**Planowany branch implementacyjny:** `upgrade/v16.3.22-active-runtime-subject-root-hardening`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Issue pamięci zależne od tego etapu:** `#59`  
**Data planu:** 2026-08-27

> Ten dokument jest pierwszym release-specific implementation planem roadmapy do v16.6.0. Nie implementuje zmian samym swoim istnieniem. Przed rozpoczęciem kodowania należy ponownie potwierdzić aktualny `origin/master`; jeżeli master przesunął się względem wskazanego SHA, wykonać diff-audyt i zaktualizować plan przed pierwszą zmianą kodu.

---

# 1. Cel wydania

Naprawić deterministyczny błąd tożsamości aktywnego runtime w sytuacji, gdy:

```text
requested/staging/observer root = A
host-level JAZN_ACTIVE_RUNTIME.json -> active_root = B
daemon endpoint -> active_root = B
```

Poprawny wynik:

```text
A -> B -> B == active_trusted / właściwy trusted state
```

Błędny wynik, którego v16.3.22 ma zabronić:

```text
A != B
-> status porównuje endpoint B do A
-> endpoint_runtime_root_mismatch
-> zdrowy daemon B jest fałszywie odrzucony
```

Wydanie ma ustanowić jeden kontrakt:

```text
requested_root = obserwator / miejsce wywołania
subject_root   = runtime, którego prawda jest oceniana
```

Jeżeli kanoniczny marker jest poprawny i wskazuje B, to **B jest subject rootem** dla identity, package integrity i source provenance.

---

# 2. Dlaczego zaczynamy właśnie tutaj

Ten etap jest fundamentem kolejnych prac roadmapy:

- v16.3.23 ma bezpiecznie reuse/start/stop persistent daemon;
- v16.4.x ma rozwijać NLP bez mieszania problemów transportowych;
- v16.5.x ma testować finalną pamięć na jednoznacznie zidentyfikowanym runtime;
- Issue #59 nie może uznać finalnego acceptance, jeżeli nie wiadomo, czy host rzeczywiście użył aktywnego persistent runtime B.

Nie wolno rozpoczynać finalnego acceptance pamięci od „naprawiania recallu”, jeżeli wcześniejsza warstwa może błędnie określać tożsamość procesu.

---

# 3. Potwierdzony stan kodu na master

## 3.1. `runtime_root.py` ma już właściwy model requested -> resolved

`latka_jazn/core/runtime_root.py` definiuje `ActiveRuntimeRootResolution` z polami:

- `requested_root`;
- `root`;
- `marker_path`;
- `marker_found`;
- `marker_valid`;
- `source`;
- `error`.

`resolve_active_runtime_root()`:

1. kanonikalizuje requested root przez `expanduser().resolve()`;
2. znajduje host-level marker;
3. odrzuca invalid JSON;
4. odrzuca pusty `active_root`;
5. odrzuca względny `active_root`;
6. rozwiązuje candidate przez `Path.resolve()`;
7. sprawdza strukturalne markery runtime;
8. dopiero wtedy zwraca `source="active_marker"` i `root=candidate`.

Wniosek: **nie trzeba budować drugiego resolvera**. v16.3.22 powinno konsumować istniejący wynik.

## 3.2. Repo ma już poprawny wzorzec w `build_active_runtime_status()`

`latka_jazn/tools/_active_extraction_cache_impl.py::build_active_runtime_status()` wykonuje poprawną sekwencję:

```text
requested_root = Path(root).resolve()
marker_output = resolve_active_runtime_marker_path(requested_root, ...)
root_resolution = resolve_active_runtime_root(requested_root, marker_path=marker_output)
root = root_resolution.root
version = read_runtime_version_from_version_py(root, ...)
package_manifest_status = package_integrity_manifest_status(root)
package_manifest_verification = verify_package_integrity_manifest(root)
source_provenance = read_source_provenance(root).to_dict()
```

To jest kanoniczny wzorzec do wyrównania `status_daemon()`, a nie miejsce do tworzenia nowej konkurencyjnej architektury.

## 3.3. `status_daemon()` rozwiązuje B, ale część truth gate nadal ocenia A

Na aktualnym master `status_daemon()` wykonuje:

```text
marker_path = resolve_active_runtime_marker_path(config.root, marker_output)
marker = read_json_file(marker_path)
root_resolution = resolve_active_runtime_root(config.root, marker_path=marker_path)
```

ale później:

```text
verify_package_integrity_manifest(config.root)
read_source_provenance(config.root, profile="system_smoke")
_endpoint_confirms_root(config.root, ping)
```

Czyli poprawnie uzyskane `root_resolution.root = B` nie staje się konsekwentnie rootem decyzyjnym.

## 3.4. Sam payload statusu już rozróżnia część tych pojęć

`status_daemon()` zwraca m.in.:

- `active_root = str(root_resolution.root)`;
- `configured_runtime_root = str(Path(config.root).resolve())`;
- `active_root_source = root_resolution.source`;
- `active_root_validation_error = root_resolution.error`.

Problem nie polega więc na braku informacji o B, lecz na tym, że część decyzji nadal jest liczona dla A.

## 3.5. `_same_runtime_path()` już używa kanonikalizacji

Helper `_same_runtime_path(left, right)` porównuje:

```python
Path(str(left)).expanduser().resolve() == Path(str(right)).expanduser().resolve()
```

Nie trzeba tworzyć nowej semantyki porównywania ścieżek. Trzeba podać helperowi **właściwy expected root**.

## 3.6. Istniejące testy nie pokrywają A -> B -> B

`tests/test_runtime_stability_daemon_status.py` ma m.in.:

- healthy same-root daemon;
- package integrity failure;
- provenance failure;
- snapshot bez HTTP;
- PID mismatch;
- endpoint runtime root mismatch;
- stale heartbeat;
- endpoint timeout;
- dead PID.

Istniejący helper testowy `_install()` ustawia resolver tak, że resolved root jest tym samym rootem używanym przez config/test. Nie ma kontraktowego przypadku:

```text
config.root = A
marker active_root = B
resolved root = B
endpoint active_root = B
```

To jest bezpośrednia luka regresyjna.

## 3.7. Workflow persistent-runtime E2E wymaga dopisania nowego testu

`.github/workflows/persistent-runtime-e2e.yml` już reaguje na zmiany m.in.:

- `runtime_root.py`;
- `runtime_daemon.py`;
- `daemon_autostart.py`;
- `version.py`.

Jednak lista testów uruchamianych przez workflow jest jawna i obecnie nie zawiera przyszłego `tests/test_v16322_active_runtime_subject_root.py`.

Nowy test musi zostać dopisany zarówno do `paths`, jak i do `compileall`/`pytest` tego workflow, jeżeli ma być częścią specjalistycznego persistent E2E gate.

---

# 4. Źródła pierwotne potwierdzające projekt

Źródła zewnętrzne służą do potwierdzenia semantyki użytych mechanizmów. Nie są dowodem istnienia konkretnego błędu w Jaźni — ten dowód pochodzi z kodu i failing regression testu.

## 4.1. Python `pathlib.Path.resolve()`

Oficjalna dokumentacja:

- https://docs.python.org/3/library/pathlib.html

Istotna semantyka:

- tworzy ścieżkę absolutną;
- rozwiązuje symlinki;
- eliminuje komponenty `..`;
- `strict=False` rozwiązuje istniejącą część ścieżki i nie wymaga istnienia całej reszty.

Wniosek dla Jaźni:

- canonical path comparison powinien bazować na `Path.resolve()`;
- aktualny `_same_runtime_path()` już realizuje ten kierunek;
- nie potrzebujemy tekstowego porównania raw pathów ani własnego parsera ścieżek.

## 4.2. Python `subprocess` — granica dla następnego etapu

Oficjalna dokumentacja:

- https://docs.python.org/3/library/subprocess.html

Dokumentacja zaleca używanie pełnej ścieżki executable i wskazuje `sys.executable` jako rekomendowany sposób ponownego uruchomienia bieżącego interpretera Pythona. Dokumentuje też różnice semantyki `cwd` między POSIX i Windows.

Znaczenie:

- źródło potwierdza kierunek v16.3.23 dla start lifecycle;
- v16.3.22 **nie powinno rozszerzać się na duży refactor Popen/start**, chyba że test subject-root ujawni bezpośredni P0/P1 zależny od tej funkcji.

## 4.3. GitHub Actions — `branches` + `paths`

Oficjalna dokumentacja:

- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

GitHub dokumentuje, że jeżeli zdefiniowane są jednocześnie filtry branch i path, workflow uruchamia się tylko wtedy, gdy **oba** filtry są spełnione.

Znaczenie:

- nowy plik testowy v16.3.22 musi zostać jawnie dodany do `paths`, jeżeli sama zmiana testu ma uruchamiać persistent-runtime E2E;
- nie wolno zakładać, że „workflow istnieje, więc zawsze się uruchomi”.

## 4.4. GitHub Actions matrix

Ta sama oficjalna dokumentacja potwierdza `strategy.matrix` jako sposób uruchamiania wariantów na wielu systemach.

Obecny workflow ma już:

```text
ubuntu-latest
windows-latest
```

Wniosek:

- nie trzeba projektować nowego workflow tylko po to, aby mieć Windows/Linux;
- należy rozszerzyć istniejący kanoniczny workflow o właściwe pliki/testy.

---

# 5. Zakres v16.3.22

## W zakresie

1. failing regression dla A -> B -> B;
2. jawny kontrakt requested root vs subject root w `status_daemon()`;
3. package integrity aktywnego procesu względem subject root;
4. source provenance aktywnego procesu względem subject root;
5. endpoint expected root względem subject root;
6. addytywna diagnostyka requested/resolved/endpoint root;
7. zachowanie wszystkich obecnych fail-closed gates;
8. testy A/B/C, PID, stale heartbeat, invalid marker, integrity/provenance;
9. synchronizacja dedykowanego CI path/test list;
10. bump wersji do 16.3.22 w tym samym systemowym patchu;
11. raport techniczny v16.3.22.

## Poza zakresem — przechodzi do v16.3.23

- pełny refactor `start_daemon()`;
- pełny refactor `ensure_daemon_for_runtime_turn()`;
- stop/refresh/init lifecycle convergence;
- transport fallback telemetry;
- two-turn ChatGPT persistent transport E2E;
- rozszerzenie one-shot policy;
- NLP;
- pamięć/retrieval.

Wyjątek: jeżeli implementacja samego subject-root status ujawni P0/P1, którego nie da się poprawnie zamknąć bez minimalnej zmiany sąsiedniego helpera, zmiana może wejść do v16.3.22 pod warunkiem:

- regression test;
- jawnego uzasadnienia w raporcie;
- braku rozszerzenia na cały lifecycle.

---

# 6. Invariants v16.3.22

Po implementacji muszą zachodzić jednocześnie:

## I1 — marker wskazuje subject root

Jeżeli marker jest prawidłowy i wskazuje B:

```text
subject_root == B
```

niezależnie od tego, że wywołanie przyszło z A.

## I2 — integrity truth dotyczy B

```text
verify_package_integrity_manifest(subject_root)
```

jest decyzyjne dla aktywnego procesu.

Integrity A może być co najwyżej diagnostyczne i nie może odrzucać poprawnego B.

## I3 — provenance truth dotyczy B

```text
read_source_provenance(subject_root, profile="system_smoke")
```

jest decyzyjne dla aktywnego procesu.

## I4 — endpoint identity dotyczy B

```text
_endpoint_confirms_root(subject_root, ping)
```

Nie:

```text
_endpoint_confirms_root(requested_root, ping)
```

## I5 — PID nadal jest obowiązkowy

Root match bez PID match nie daje trusted state.

## I6 — heartbeat nadal jest obowiązkowy

Stale heartbeat nie może stać się `active_trusted` tylko dlatego, że root naprawiono.

## I7 — invalid marker nadal fail-closed

Naprawa nie może zamieniać nieprawidłowego markera w domyślne zaufanie do endpointu.

## I8 — obcy endpoint nadal fail-closed

```text
A -> marker B -> endpoint C
```

musi pozostać odrzucone.

## I9 — API compatibility

Istniejące klucze statusu nie powinny być usuwane bez konieczności:

- `active_root`;
- `configured_runtime_root`;
- `active_root_source`;
- `active_root_validation_error`;
- `endpoint_root_matches`;
- `endpoint_pid_matches`;
- `endpoint_identity_matches`;
- `package_integrity_verified`;
- `source_provenance_verified`.

Nowe pola powinny być addytywne.

---

# 7. Proponowany kontrakt danych statusu

Zachować obecne pola i dodać jawne pola diagnostyczne:

```text
requested_runtime_root
resolved_active_root
subject_runtime_root
active_root_source
endpoint_reported_active_root
endpoint_expected_active_root
endpoint_root_matches
active_runtime_integrity
active_runtime_provenance
```

Minimalna semantyka:

```text
requested_runtime_root = A
resolved_active_root = B
subject_runtime_root = B
endpoint_expected_active_root = B
endpoint_reported_active_root = B
```

`active_root` może pozostać kompatybilnym aliasem resolved/subject B.

`configured_runtime_root` może pozostać kompatybilnym aliasem requested A.

Nie wprowadzać trzeciego niezależnego sposobu wyboru rootu.

---

# 8. Faza 0 — preflight przed utworzeniem implementacyjnego brancha

Przed kodowaniem wykonać na rzeczywistym checkout:

```bash
git fetch origin
git switch master
git pull --ff-only origin master
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/master
```

Warunki:

- worktree czysty;
- lokalny `master == origin/master`;
- jeżeli HEAD != `3a2c2f053cf71e426367359b14f15efb6f3daa52`, wykonać diff:

```bash
git log --oneline 3a2c2f053cf71e426367359b14f15efb6f3daa52..origin/master
git diff --stat 3a2c2f053cf71e426367359b14f15efb6f3daa52..origin/master
```

Następnie ponownie sprawdzić:

- `AGENTS.md`;
- `AGENTS.codex.md`;
- wszystkie nested `AGENTS.md` dla zmienianych ścieżek.

Dla runtime zapisać baseline:

```bash
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
```

Nie commitować wyników zawierających host runtime state.

---

# 9. Faza 1 — checkpoint

Utworzyć punkt przywracania z dokładnego świeżego master, np.:

```text
backup/pre-v16.3.22-active-runtime-subject-root-YYYYMMDD
```

Dopiero potem branch implementacyjny:

```text
upgrade/v16.3.22-active-runtime-subject-root-hardening
```

Sprawdzić:

```bash
git merge-base --is-ancestor origin/master HEAD
git status --short
git rev-parse HEAD
```

Branch nie może dziedziczyć przypadkowych zmian z dokumentacyjnego brancha roadmapy.

---

# 10. Faza 2 — failing regression test przed zmianą produkcyjną

## 10.1. Nowy plik

Preferowany:

```text
tests/test_v16322_active_runtime_subject_root.py
```

## 10.2. Fixture A/B

Utworzyć dwa różne katalogi:

```text
<tmp>/runtime_A
<tmp>/runtime_B
<tmp>/workspace_runtime/JAZN_ACTIVE_RUNTIME.json
```

A i B powinny być strukturalnie poprawnymi minimalnymi runtime roots dla `resolve_active_runtime_root()`:

```text
latka_jazn/
latka_jazn/version.py
run.py lub main.py
```

Marker host-level wskazuje absolutny B.

Preferencja: użyć **prawdziwego `resolve_active_runtime_root()`**, nie monkeypatchować go w głównym teście A/B/B. Dzięki temu test obejmie integrację z host-level workspace contract.

Można monkeypatchować ciężkie/niedeterministyczne granice:

- HTTP probe;
- OS PID probe;
- package verifier;
- source provenance reader.

## 10.3. Spies na root decyzyjny

Verifier integrity powinien rejestrować otrzymaną ścieżkę:

```text
integrity_calls == [B]
```

Provenance reader:

```text
provenance_calls == [B]
```

Endpoint:

```text
ping.active_root == B
ping.daemon_pid == marker.pid
ping.runtime_process_active == true
fresh heartbeat
```

## 10.4. Oczekiwanie na niezmienionym v16.3.21

Test powinien wykazać co najmniej jeden z obecnych błędów:

- `endpoint_root_matches == false`; lub
- `active_state_reason == endpoint_runtime_root_mismatch`; lub
- integrity/provenance spy został wywołany dla A zamiast B.

Nie zmieniać testu tak, by „udawał” reprodukcję. W raporcie zachować faktyczny failure.

## 10.5. Oczekiwanie po poprawce

```text
active_root == B
requested_runtime_root == A
resolved_active_root == B
subject_runtime_root == B
endpoint_expected_active_root == B
endpoint_reported_active_root == B
endpoint_root_matches == true
endpoint_pid_matches == true
endpoint_identity_matches == true
package_integrity_verified == true
source_provenance_verified == true
active_state == active_trusted
```

Dokładna nazwa trusted state ma pozostać zgodna z bieżącym kontraktem, jeżeli master zmieni ją przed implementacją.

---

# 11. Faza 3 — przeciwne testy fail-closed przed refactorem

Dodać lub rozszerzyć przypadki:

## T1 — A/B/C

```text
requested A
marker B
endpoint C
=> inactive/fail-closed
=> reason endpoint_runtime_root_mismatch
```

## T2 — A/B/B, wrong PID

```text
root matches
PID mismatch
=> fail-closed
```

## T3 — A/B/B, stale heartbeat

```text
identity matches
heartbeat stale
=> degraded, nie trusted
```

## T4 — integrity B false

A może być poprawne, ale:

```text
integrity(B) = false
=> inactive
```

Ten test jest ważny, ponieważ zapobiega odwrotnemu błędowi: zaakceptowaniu uszkodzonego B na podstawie zdrowego A.

## T5 — provenance B invalid

```text
provenance(B) = invalid
=> inactive
```

## T6 — A broken, B valid

Jeżeli marker B jest poprawny:

```text
integrity(A) = false
integrity(B) = true
provenance(B) = verified
endpoint B
=> B może być trusted
```

Requested A nie może decydować o trust state B.

## T7 — invalid marker

- invalid JSON;
- empty active_root;
- relative active_root;
- B bez wymaganych markerów runtime.

Każdy przypadek pozostaje fail-closed.

## T8 — marker missing

Nie zmieniać semantyki istniejącego same-root/no-marker contract w tym wydaniu poza tym, co wynika z obecnych testów.

---

# 12. Faza 4 — minimalny refactor `status_daemon()`

## 12.1. Jawne zmienne

Na początku części resolution w `status_daemon()` wprowadzić lokalnie:

```python
requested_root = Path(config.root).expanduser().resolve()
marker_path = resolve_active_runtime_marker_path(requested_root, marker_output)
marker = read_json_file(marker_path)
root_resolution = resolve_active_runtime_root(requested_root, marker_path=marker_path)
subject_root = root_resolution.root
```

Nie mutować `config.root`.

Powód:

- config nadal opisuje środowisko wywołania;
- status ma rozróżniać observer od subject;
- unikamy ukrytych side effects dla innych użytkowników `JaznConfig`.

## 12.2. Integrity

Zmienić decyzyjny verifier z:

```python
verify_package_integrity_manifest(config.root)
```

na:

```python
verify_package_integrity_manifest(subject_root)
```

## 12.3. Provenance

Zmienić:

```python
read_source_provenance(config.root, profile="system_smoke")
```

na:

```python
read_source_provenance(subject_root, profile="system_smoke")
```

Nie zmieniać w tej wersji polityki listy dozwolonych statusów provenance bez osobnego dowodu regresji.

## 12.4. Endpoint root

Zmienić:

```python
_endpoint_confirms_root(config.root, ping)
```

na:

```python
_endpoint_confirms_root(subject_root, ping)
```

Helper `_same_runtime_path()` już kanonikalizuje obie strony przez `Path.resolve()`.

## 12.5. Payload

Zachować:

```text
active_root
configured_runtime_root
```

oraz addytywnie dodać jawne pola requested/subject, jeżeli nie istnieją.

Nie usuwać istniejących kluczy tylko po to, aby nazewnictwo było „ładniejsze”.

## 12.6. Recommended repair

`_daemon_degraded_recommendation()` korzysta z obliczonego `endpoint_root_matches`. Po zmianie expected root powinien automatycznie przestać sugerować fałszywy mismatch A/B/B.

Nie osłabiać samej funkcji rekomendacji.

---

# 13. Faza 5 — audyt wszystkich `config.root` w `status_daemon()`

Po podstawowej poprawce wykonać review funkcji linia po linii i sklasyfikować każde użycie `config.root`:

## Klasa A — observer/requested context

Może pozostać A, np. pola diagnostyczne opisujące caller/config.

## Klasa B — active subject truth

Musi używać B:

- endpoint expected root;
- package integrity;
- source provenance;
- active version/manifest identity, jeżeli występuje w tej ścieżce.

## Klasa C — host-level mutable workspace

Nie zmieniać mechanicznie. Najpierw sprawdzić `workspace_runtime_path()` i kontrakt host-level shared workspace.

## Klasa D — lifecycle

Jeżeli użycie dotyczy start/stop/ensure zamiast samego statusu, zapisać do v16.3.23, chyba że jest bezpośrednim P0/P1 blokującym poprawność statusu.

Cel tego audytu: uniknąć błędu typu „zamieniono wszystkie `config.root` na B”, co mogłoby zepsuć informacje o observerze lub granice host workspace.

---

# 14. Faza 6 — wersja

W tym samym systemowym zestawie zmian:

```python
DISTRIBUTION_VERSION = "16.3.22"
PACKAGE_VERSION = "16.3.22"
PACKAGE_RELEASE_NAME = "active-runtime-subject-root-hardening"
```

Nie odkładać bumpu na osobny późniejszy release commit.

Zaktualizować tylko aktywne testy/resource references, które zgodnie z polityką repo muszą wskazywać bieżącą wersję.

Nie edytować historycznych `.archives`.

---

# 15. Faza 7 — CI

## 15.1. `persistent-runtime-e2e.yml`

Dodać nowy test do `paths` dla `pull_request` i `push`:

```text
tests/test_v16322_active_runtime_subject_root.py
```

Dodać go do:

- compileall list;
- persistent runtime pytest list.

## 15.2. Platformy

Zachować istniejącą matrix:

```text
ubuntu-latest
windows-latest
```

Nie tworzyć drugiego równoległego workflow bez potrzeby.

## 15.3. Path coverage audit

Sprawdzić, czy wszystkie pliki, których zmiana może zepsuć kontrakt A/B/B, są triggerami workflow:

- `runtime_root.py`;
- `runtime_daemon.py`;
- `version.py`;
- nowy test;
- workflow itself.

Jeżeli w implementacji zostanie zmieniony dodatkowy krytyczny moduł, dopisać go do paths.

---

# 16. Faza 8 — testy celowane

Minimalny zestaw po implementacji:

```bash
python -X utf8 -m pytest -q \
  tests/test_v16322_active_runtime_subject_root.py \
  tests/test_runtime_stability_daemon_status.py \
  tests/test_v16321_chatgpt_runtime_fallback_hardening.py
```

Na Windows użyć składni odpowiedniej dla PowerShell albo jednej linii.

Sprawdzić osobno:

- A/B/B trusted;
- A/B/C fail-closed;
- wrong PID;
- stale heartbeat;
- B integrity failure;
- B provenance failure;
- invalid marker;
- snapshot `probe_endpoint=False` bez fałszywego live claim.

---

# 17. Faza 9 — pełna walidacja repo

Po zielonych focused tests:

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Jeżeli repo wymaga dodatkowych audytów obecnej linii, uruchomić je zgodnie z aktualnym `AGENTS.codex.md`/workflow.

Każdy failure sklasyfikować P0/P1/P2/P3 zgodnie z roadmapą.

Nie przechodzić do „naprawy CI przez zmianę testów”, dopóki nie ustalono root cause.

---

# 18. Faza 10 — defect loop podczas implementacji

## P0

Przykłady:

- B może zostać uznane za trusted mimo integrity(B)=false;
- endpoint C może zostać uznany za B;
- PID mismatch zostaje zaakceptowany;
- invalid marker jest omijany;
- status raportuje sukces dla niezweryfikowanego procesu.

**Blokuje release i naprawiamy w v16.3.22.**

## P1

Przykłady:

- A/B/B nadal daje mismatch;
- Windows path identity zachowuje się inaczej niż Linux w testowanym kontrakcie;
- nowy test nie uruchamia się w kanonicznym CI;
- istniejący same-root daemon status regresuje.

**Blokuje release i naprawiamy w v16.3.22.**

## P2

Przykład:

- dodatkowa obserwowalność start lifecycle, która nie wpływa na correctness statusu.

Przenieść do v16.3.23, chyba że mały fix jest konieczny i jednoznaczny.

## P3

- naming cleanup;
- komentarze/refactor bez wpływu na kontrakt.

Nie rozszerzać brancha.

---

# 19. Faza 11 — review diffu przed commitem finalnym

Sprawdzić:

```bash
git status --short
git diff --stat
git diff --check
git diff -- latka_jazn/core/runtime_daemon.py
git diff -- tests/test_v16322_active_runtime_subject_root.py
git diff -- .github/workflows/persistent-runtime-e2e.yml
git diff -- latka_jazn/version.py
```

Odpowiedzieć na pytania:

1. Czy istnieje dokładnie jedno źródło subject root?
2. Czy B jest używane dla integrity/provenance/endpoint identity?
3. Czy requested A nadal jest widoczne diagnostycznie?
4. Czy A/B/C nadal fail-closed?
5. Czy PID/heartbeat/auth gates nie zostały osłabione?
6. Czy nie dotknięto start/stop szerzej niż plan?
7. Czy version bump jest w tej samej zmianie?
8. Czy nie ma private/protected files?

---

# 20. Faza 12 — commit sequence

Preferowana mała sekwencja logiczna:

1. `test: reproduce sibling-root active daemon identity regression`
2. `fix: evaluate daemon truth against resolved active subject root`
3. `test: cover subject-root integrity provenance and fail-closed matrix`
4. `ci: run v16.3.22 subject-root regressions on Windows and Ubuntu`
5. `release: bump Jaźń to v16.3.22 active-runtime-subject-root-hardening`
6. `docs: report v16.3.22 active runtime subject-root hardening`

Uwaga: zasada repo wymaga, aby systemowy patch miał version bump w tym samym zestawie zmian. Jeżeli repo/workflow wymaga, aby bump był już w pierwszym właściwym systemowym commicie, dostosować kolejność tak, by żaden publikowany systemowy commit/PR nie przedstawiał zmiany zachowania pod starą wersją.

Nie wykonywać blind cherry-picków ze starych branchy.

---

# 21. Faza 13 — raport techniczny

Utworzyć:

```text
docs/reports/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_HARDENING.md
```

Raport ma zawierać:

- baseline master SHA;
- failing reproduction A/B/B;
- root cause;
- dokładny kontrakt requested vs subject;
- zmienione pliki;
- test matrix;
- każde znalezione P0/P1;
- rzeczywiste wyniki focused/full tests;
- Windows/Ubuntu CI;
- truth boundary;
- niewykonane testy + powód;
- checkpoint/rollback;
- explicit handoff do v16.3.23.

---

# 22. Faza 14 — release metadata

Nie edytować ręcznie:

```text
PACKAGE_INTEGRITY_MANIFEST.json
SOURCE_PROVENANCE.json
```

Po czystym zatwierdzonym kodzie użyć kanonicznego mechanizmu repo:

```bash
python -X utf8 -m latka_jazn.tools.release_metadata_sync \
  --root . --base-branch master --write --json
```

albo `manifest_sync` w `release-hardening`, zgodnie z aktualnym `AGENTS.md`.

Po synchronizacji sprawdzić idempotencję zgodnie z workflow repo.

---

# 23. Faza 15 — release gates

Dopiero z czystego commita:

```bash
python -X utf8 run.py package-smoke --profile release --json
python -X utf8 run.py release-build --json
```

Wymagane:

- system smoke PASS;
- release smoke PASS;
- release-build PASS;
- pełny deterministic pytest PASS;
- Windows persistent-runtime E2E PASS;
- Ubuntu persistent-runtime E2E PASS;
- clean checkout guard PASS;
- metadata canonical;
- brak protected/private files.

---

# 24. Kryteria akceptacji v16.3.22

Wydanie można uznać za gotowe tylko gdy wszystkie są spełnione:

- [ ] fresh origin/master potwierdzony przed pracą;
- [ ] checkpoint utworzony;
- [ ] failing A/B/B regression odtworzony na bazowym kodzie;
- [ ] requested A + marker B + endpoint B => trusted B;
- [ ] integrity decyzyjne jest liczone dla B;
- [ ] provenance decyzyjne jest liczone dla B;
- [ ] endpoint expected root = B;
- [ ] requested A pozostaje diagnostycznie widoczne;
- [ ] A/B/C fail-closed;
- [ ] wrong PID fail-closed;
- [ ] stale heartbeat nie daje trusted;
- [ ] integrity(B)=false fail-closed nawet gdy A jest zdrowe;
- [ ] provenance(B)=invalid fail-closed;
- [ ] A uszkodzone nie odrzuca poprawnego B, jeśli A nie jest subject rootem;
- [ ] invalid marker fail-closed;
- [ ] same-root A/A/A nie regresuje;
- [ ] snapshot/no-probe nie zgłasza fałszywego live verification;
- [ ] nowy test znajduje się w persistent-runtime E2E workflow;
- [ ] Windows CI PASS;
- [ ] Ubuntu CI PASS;
- [ ] compileall PASS;
- [ ] pełny deterministic pytest PASS;
- [ ] doctor PASS;
- [ ] system package-smoke PASS;
- [ ] git diff --check PASS;
- [ ] release package-smoke PASS;
- [ ] release-build PASS;
- [ ] version = 16.3.22;
- [ ] raport techniczny odpowiada kodowi;
- [ ] release metadata wygenerowane kanonicznie;
- [ ] brak `memory/`, `workspace_runtime/`, SQLite/WAL/SHM, ZIP, sekretów i prywatnych danych w PR.

---

# 25. Warunek GO do v16.3.23

v16.3.23 może rozpocząć się dopiero po rzeczywistym merge v16.3.22 do `master` oraz potwierdzeniu, że:

```text
status_daemon(A)
marker -> B
endpoint -> B
=> B jest jednoznacznie rozpoznane jako subject runtime
```

Dopiero wtedy następny release może bezpiecznie odpowiadać na pytania:

- czy `ensure` reuse B;
- czy `start` nie uruchamia A;
- czy stop/refresh/init sterują właściwym B;
- dlaczego wybrano daemon vs one-shot;
- czy dwie kolejne tury idą przez ten sam persistent daemon.

Nie przenosić tych problemów z powrotem do v16.3.22 bez P0/P1 wymagającego minimalnej interwencji.

---

# 26. Gotowe zapytania research dla implementatora

Przed zmianą konkretnej części kodu używać przede wszystkim źródeł pierwotnych.

## Path identity

```text
site:docs.python.org pathlib Path.resolve symlink absolute path strict
site:docs.python.org pathlib samefile resolve Windows paths
```

## Process launch — tylko jeśli ujawni się bezpośrednia zależność

```text
site:docs.python.org subprocess Popen sys.executable cwd Windows POSIX
```

## GitHub CI

```text
site:docs.github.com actions workflow syntax paths branches both filters
site:docs.github.com actions strategy matrix windows-latest ubuntu-latest
```

## Repo

```text
runtime_daemon status_daemon endpoint_root_matches
verify_package_integrity_manifest config.root
read_source_provenance config.root
resolve_active_runtime_root requested_root
build_active_runtime_status root_resolution.root
endpoint_runtime_root_mismatch
```

Zawsze najpierw sprawdzić aktualny master. Wynik wyszukiwarki nie może zastąpić odczytu bieżącego kodu.

---

# 27. Czego nie robić w v16.3.22

- nie usuwać one-shot fallbacku v16.3.21;
- nie przepisywać całego daemon lifecycle;
- nie ufać portowi bez root + PID;
- nie osłabiać heartbeat;
- nie akceptować invalid markera;
- nie weryfikować B na podstawie integrity/provenance A;
- nie zmieniać wszystkich `config.root` mechanicznie;
- nie mutować `JaznConfig.root` jako skrótu refactoru;
- nie tworzyć drugiego active-root resolvera;
- nie edytować manualnie release manifests;
- nie dodawać prywatnej pamięci do fixture;
- nie używać synthetic fixture jako dowodu aktywnej Jaźni;
- nie podnosić timeoutów zamiast naprawy identity;
- nie mieszać NLP ani #59 Recall do tego PR;
- nie merge'ować do master przed pełnym PASS.

---

# 28. Definition of Done

v16.3.22 jest zakończone wtedy, gdy na podstawie rzeczywistych testów można powiedzieć:

> Wywołanie statusu z sąsiedniego/stagingowego runtime A poprawnie rozpoznaje zweryfikowany active runtime B wskazany przez host-level marker; integralność, provenance oraz endpoint identity są oceniane względem B, natomiast niezgodny root/PID/marker/integrity/provenance nadal kończy się fail-closed. Poprawka nie zmienia jeszcze pełnego lifecycle start/stop/reuse — to jest jawny zakres v16.3.23.

Dopiero ten stan daje **GO do v16.3.23**.
