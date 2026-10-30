# TPA local acceptance triage — 2026-10-30 (v .94.6.35)

UI `Odbiór lokalny` i filtr `Nowe / Do powtórzenia / Nieaktualne dowody / Odebrane` nie zmieniają canonical `status` ani `full_gate`. Informacje są **wyliczane tylko do prezentacji** z raportów `RunStore.history()` i z obserwacji bieżącego `version.py` / Git preflight.

- **Nowe**: nie ma żadnego historycznego przebiegu dla scenariusza.
- **Do powtórzenia**: istnieje odbiór dla bieżącego źródła, lecz nie zatwierdzono wszystkich bramek lub tożsamości źródła nie można zweryfikować.
- **Nieaktualne dowody**: ostatni przebieg należy do innej wersji, innego SHA lub innego hash `version.py`; historyczne wyniki pozostają nietknięte.
- **Odebrane**: tylko wtedy, gdy jest `status=PASS` i `full_gate=PASS` oraz pozytywna zgodność źródła.

Zachowano 22 scenariusze TPA. Dodatkowa karta zawiera dziewięć instrukcji lokalnego odbioru: realne PTY/ConPTY, własność usług, wszystkie 12 Studiów, EXE offline, AV, DPI i powtórzenie chat-resume oraz daemon-restart. Instrukcje nie są automatycznie wykonywalnymi testami ani dowodami.

Nie przeprowadzono lokalnego odbioru Windows. Wymagana fizyczna maszyna, lokalna Ollama, izolowany daemon i środowisko odbioru. Żadna kontrola typu `full_gate` nie jest automatycznie promowana.

Testy: `tests/test_jazn_tpa_local_triage.py`, `tests/test_jazn_tpa_local_triage_qt.py`; końcowy Pyright i regresja Windows/Linux — GitHub Actions. Manifest i provenance synchronizuje tylko canonical workflow.
