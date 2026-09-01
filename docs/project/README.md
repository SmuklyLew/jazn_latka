# Project-wide documents

Ten katalog zawiera dokumenty przekrojowe obowiązujące w całym projekcie albo wspólne audyty/reference dla wielu release'ów.

## Bieżące źródła

- [`CURRENT_STATE.md`](CURRENT_STATE.md) — bieżący snapshot mastera, aktywnych branchy i kolejności release trainu;
- [`PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`](PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md) — kanoniczny kontrakt pojęć, source hierarchy i granic naukowych;
- [`REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md`](REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md) — aktualny audyt branch/docs convergence;
- [`RELEASE_TIMELINE.md`](RELEASE_TIMELINE.md) — indeks historii wydań i dowodów;
- [`PLAN_COHERENCE_AUDIT_2026-08-30.md`](PLAN_COHERENCE_AUDIT_2026-08-30.md) — datowany snapshot audytu planów z 2026-08-30;
- [`system-evaluation/`](system-evaluation/) — ocena architektury v16.6→v17+ oraz późniejsze datowane uzupełnienia research.

## Zasada aktualności

`CURRENT_STATE.md` może być aktualizowany wraz z masterem. Datowane audyty i system-evaluation zachowują kontekst swojej epoki; jeśli zmienił się stan repo, model capabilities albo research, dopisz nowy datowany audit/addendum zamiast przepisywać provenance starego dokumentu.

Historyczne identyfikatory paczek, SHA, branchy i wersji w datowanym audycie nie są deklaracją bieżącego runtime.

## Relacja do planów

Przekrojowe dokumenty opisują **założenia i evidence**, natomiast kolejność wykonania należy do:

- [`../plans/16.6.0-final-convergence/ROADMAP.md`](../plans/16.6.0-final-convergence/ROADMAP.md) — program v16;
- [`../plans/17.0.0-measured-architecture-consolidation/PLAN.md`](../plans/17.0.0-measured-architecture-consolidation/PLAN.md) — warunkowy program v17.

Dokumenty projektowe nie certyfikują własnego PASS i nie są dowodem aktywnego runtime.
