# Jaźń v16.3.25.5.91.1 — ChatGPT plugin runtime CI convergence

## Zakres

Patch naprawia regresje wykryte przez GitHub Actions już po scaleniu v91.0 do master.

## Naprawy

- standalone Pyright: test RFC 7662 nie wykonuje już operatora `in` na wartości typowanej jako `object`; wartość body jest jawnie zawężana do `bytes`;
- host-spawn-memory-convergence: release identity nie jest już zahardkodowane do historycznej wersji 90.2 i sprawdza bieżącą linię 91.1;
- aktywne testy wersji zostały przesunięte do 91.1, a ich zatwierdzone postacie 91.0 zachowano w `tests/archive/`;
- wersja patcha: `16.3.25.5.91.1-chatgpt-plugin-runtime-ci-convergence`.

## Stan v91.0 na master

PR #295 został scalony do master i kod plugin runtime jest obecny. Patch 91.1 nie odtwarza ani nie zastępuje funkcjonalności v91.0; domyka bramki CI/release wymagane, aby linia była poprawnym kandydatem do kolejnego scalenia.

## Granica

Metadata `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` nie są edytowane ręcznie. Po source push mają zostać zsynchronizowane przez kanoniczny workflow repozytorium.
