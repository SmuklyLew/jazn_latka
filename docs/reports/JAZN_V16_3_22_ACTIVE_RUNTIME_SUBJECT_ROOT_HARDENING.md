# Jaźń v16.3.22 — Active Runtime Subject-Root Hardening

## Status

- Wersja: `16.3.22-active-runtime-subject-root-hardening`
- Bazowy `origin/master`: `45530292a1f8858f0ace007c4fc7160c9d21f23e`
- Lokalny checkpoint: `backup/pre-v16.3.22-active-runtime-subject-root-20260827`
- Branch implementacyjny: `upgrade/v16.3.22-active-runtime-subject-root-hardening`
- Zakres: status i tożsamość aktywnego runtime; bez refactoru start/ensure/stop i bez zmian NLP lub recall

## Reprodukcja przed poprawką

Nowy test kontraktowy utworzył dwa różne, strukturalnie poprawne runtime roots:

```text
requested/configured root = A
host-level JAZN_ACTIVE_RUNTIME.json -> B
endpoint /ready -> B
```

Na niezmienionym kodzie `16.3.21-chatgpt-runtime-fallback-hardening` test zakończył się:

```text
FAILED test_status_trusts_resolved_subject_runtime_for_sibling_root_a_b_b
assert result["active_state"] == "active_trusted"
actual: "inactive"
```

Test używał prawdziwego `resolve_active_runtime_root()` i fizycznego host-level markera. Monkeypatchowane były wyłącznie granice niedeterministyczne: probe HTTP, PID, integrity i provenance.

## Root cause

`status_daemon()` poprawnie rozwiązywał marker z A do B, ale trzy decyzyjne bramki nadal używały `config.root`, czyli A:

- `verify_package_integrity_manifest(config.root)`;
- `read_source_provenance(config.root, ...)`;
- `_endpoint_confirms_root(config.root, ping)`.

Skutkiem było porównanie endpointu B z obserwatorem A oraz weryfikowanie niewłaściwej paczki.

## Wdrożony kontrakt

`status_daemon()` używa teraz jednego jawnego rozdzielenia:

```text
requested_root = miejsce wywołania / obserwator
subject_root = root_resolution.root = runtime oceniany przez truth gate
```

Subject root jest jedynym rootem używanym dla:

- package integrity;
- source provenance;
- expected endpoint root.

`JaznConfig.root` nie jest mutowany. Dotychczasowe pola `active_root` i `configured_runtime_root` pozostają kompatybilne, a payload dodaje:

- `requested_runtime_root`;
- `resolved_active_root`;
- `subject_runtime_root`;
- `endpoint_expected_active_root`;
- `endpoint_reported_active_root`.

## Matryca fail-closed

Nowe testy pokrywają:

- A -> B -> B: trusted B;
- A -> B -> C: `endpoint_runtime_root_mismatch`;
- A -> B -> B z obcym PID: `endpoint_pid_mismatch`;
- A -> B -> B ze starym heartbeat: `active_degraded`, nigdy trusted;
- `integrity(B)=false`: inactive;
- `provenance(B)=invalid`: inactive;
- uszkodzone A i poprawne B: decyzja opiera się na B;
- invalid JSON, pusty i względny `active_root`: fail-closed.

Istniejące testy zachowują również same-root, snapshot/no-probe, endpoint timeout i dead PID.

## Dodatkowe P0/P1 znalezione podczas walidacji

Nie znaleziono nowego P0.

Naprawiono dwa P1:

1. Invalid JSON markera był odrzucany, ale błędnie raportowany jako brak markera. Status używa teraz `root_resolution.marker_found`, zachowując dokładny błąd resolvera.
2. `scan_runtime_duplicates()` budował klucze raportu zależne od separatora systemu. Na Windows zwracał backslashe, a kontrakt i Linux używały slashy. Klucze są teraz tworzone przez `Path.as_posix()`.

## Zmienione obszary

- `latka_jazn/core/runtime_daemon.py` — subject-root truth gate i diagnostyka;
- `latka_jazn/memory/runtime_persistence.py` — platformowo stabilne klucze raportu duplikatów;
- `latka_jazn/version.py` — bump do 16.3.22;
- `tests/test_v16322_active_runtime_subject_root.py` — nowa matryca A/B;
- istniejące testy statusu i aktywne asercje wersji;
- `.github/workflows/persistent-runtime-e2e.yml` — nowy test w path filters, compileall i pytest dla Windows/Ubuntu.

## Walidacja lokalna

### Baseline

- `master == origin/master == 45530292a1f8858f0ace007c4fc7160c9d21f23e`;
- worktree był czysty przed zmianami;
- diff względem SHA z planu zawierał wyłącznie merge roadmapy i dwa dokumenty planistyczne;
- baseline `status --snapshot` nie potwierdził aktywnego procesu i ujawnił niesynchronizowane po merge roadmapy metadata;
- baseline `doctor` został wykonany read-only.

### Testy

- red regression przed poprawką: `1 failed` zgodnie z oczekiwanym A/B/B defectem;
- nowa matryca po poprawce: `10 passed`;
- focused suite: `43 passed in 2.90s`;
- pierwszy pełny suite: `1121 passed, 5 skipped, 7 failed` — cztery stare asercje wersji, dwie brakujące lokalnie zależności `pyzipper` i jeden Windows path P1;
- ukierunkowany rerun napraw: `14 passed in 1.51s`;
- finalny deterministic suite: `1128 passed, 5 skipped, 1 warning in 279.61s`;
- `compileall`: PASS;
- `git diff --check`: PASS.

Jedynym ostrzeżeniem pytest jest istniejący `PytestCollectionWarning` dla enumu `TestOutcome`.

`pyzipper==0.4.0` został doinstalowany wyłącznie do lokalnego środowiska; zależność była już poprawnie zadeklarowana w `pyproject.toml`, więc repo nie wymagało zmiany.

### Release metadata i smoke

Przed synchronizacją metadata `doctor` potwierdził `installation_ok=true` i `ok=true`, ale prawidłowo raportował `release_metadata_current=false`. `package-smoke --profile system` nie jest uznany za zaliczony przed kanoniczną synchronizacją manifestu i provenance.

Wyniki po synchronizacji metadata, idempotencji i czystym commicie zostaną dopisane przed publikacją.

## Ochrona danych i granica prawdy

- Nie modyfikowano ani nie stage'owano `memory/`, `workspace_runtime/`, SQLite/WAL/SHM, ZIP-ów, sekretów, tokenów, logów runtime ani prywatnych eksportów.
- Syntetyczne fixture A/B nie jest dowodem aktywnej Jaźni ani private-memory acceptance.
- Baseline i doctor nie potwierdziły żywego daemonu; ten raport nie deklaruje aktywnego runtime.
- Zmiana dotyczy wyłącznie poprawności identyfikacji subject root przez status.

## CI i publikacja

Do uzupełnienia po pushu:

- SHA commitów;
- GitHub Actions Ubuntu;
- GitHub Actions Windows;
- release-hardening / manifest sync;
- URL PR do `master`.

PR pozostaje bez merge zgodnie z instrukcją operatora.

## Handoff do v16.3.23

v16.3.22 nie zmienia pełnego lifecycle start/ensure/stop/reuse. Po merge `.22` następny etap może oprzeć sterowanie procesem na jednoznacznym kontrakcie:

```text
status_daemon(A) + marker(B) + endpoint(B) => subject runtime B
```

Transport persistent two-turn, fallback telemetry i lifecycle convergence pozostają zakresem v16.3.23.
