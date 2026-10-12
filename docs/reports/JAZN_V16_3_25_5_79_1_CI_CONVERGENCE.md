# Jaźń v16.3.25.5.79.1 — CI convergence

Follow-up domyka błędy pełnego GitHub Actions po v79.0 bez cofania kontraktu optional MEMORY ani executor-epoch recovery.

- SYSTEM-only operational SQLite pozostaje w `workspace_runtime/core_state/memory_runtime`; persistent MEMORY w `workspace_runtime/memory`.
- `memory_validation` ufa obu rozdzielonym rootom i przy `--include-all-sqlite` skanuje oba.
- cognitive audit sprawdza rzeczywistą semantykę separacji recovery/runtime-write zamiast starego wzorca tekstowego.
- testy oczekujące persistent MEMORY tworzą jawny marker paczki zamiast traktować pusty katalog jako pamięć.
- full-turn bez zweryfikowanego wake-state nie fabrykuje dodatkowego rekordu wake-hydration.
- aktywne kontrakty Pack Generatora zostają zsynchronizowane do 10.1.86.0.116 oraz host bootstrap v2 w kolejnych commitach tego samego patcha.
- zmienione aktywne testy mają byte-exact snapshot źródłowej wersji v79.0 w `tests/archive/v16.3.25.5.79.0-host-executor-epoch-recovery/`.

Źródła: Python pathlib https://docs.python.org/3.12/library/pathlib.html ; SQLite WAL https://www.sqlite.org/wal.html ; GitHub Actions re-run https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs ; Git Trees API https://docs.github.com/en/rest/git/trees .
