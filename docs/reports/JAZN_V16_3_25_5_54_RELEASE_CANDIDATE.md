# Jaźń v16.3.25.5.54 — final release candidate gate

## Status

Ten dokument oznacza branch `fix/v16.3.25.5.54-chatgpt-sandbox-bootstrap-hardening` jako kandydata do finalnej walidacji release candidate.

Finalny status RC wolno nadać wyłącznie po zielonym wyniku wymaganych kontroli CI dla bieżącego headu brancha / PR do `master`.

## Zakres RC

Release candidate obejmuje wyłącznie zmiany v16.3.25.5.54 dotyczące:

- rozdzielenia awarii hosta/executora od błędów lokalnego procesu i błędów ZIP;
- bezpiecznej materializacji pojedynczego systemowego ZIP-a do operatora `run.py`;
- stabilnej weryfikacji pliku, expected size i SHA-256;
- fail-closed walidacji struktury ZIP oraz ręcznej ekstrakcji bez `extractall()`;
- zaktualizowanego `AGENTS.chatgpt.md` i loadera projektu;
- testów regresji v54;
- kanonicznej synchronizacji `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json`.

## Obowiązkowy gate

Wymagane kontrole pozostają zgodne z `AGENTS.codex.md`:

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py CHATGPT_BOOTSTRAP.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Dodatkowo workflow musi potwierdzić synchronizację metadanych wydania i wszystkie obowiązkowe checki repozytorium dla PR do `master`.

## Kryterium finalizacji

Branch jest **final release candidate** dopiero gdy:

1. PR do `master` wskazuje bieżący head tego brancha;
2. branch jest `behind_by = 0` względem `master` albo został poprawnie zaktualizowany;
3. wszystkie wymagane workflow/checki dla PR są zakończone sukcesem;
4. nie ma nierozwiązanych błędów walidacji, testów ani manifestów;
5. nie wykonano merge do `master` w ramach samej walidacji RC.

Ten commit celowo nie zawiera `[skip ci]`, aby wymusić rzeczywistą walidację aktualnego headu.
