# AGENTS.codex.md — runbook zmian kodu i repozytorium

Ten plik uzupelnia nadrzedny `AGENTS.md` dla zmian kodu,
testow, konfiguracji, dokumentacji i historii Git.
`AGENTS.codex.md` jest projektowym runbookiem, a nie
promptem modelu ani dowodem aktywnego runtime.

Pelny, niezmieniony kontrakt sprzed refaktoryzacji:
`docs/project/AGENTS_CODEX_OPERATIONAL_REFERENCE.md`.
Odczytaj odpowiednia czesc przy operacjach specjalistycznych.

## 1. Discovery i zakres

Przeczytaj nadrzedny AGENTS.md oraz wszystkie dotyczace
zmienianych plikow podrzedne AGENTS.md.
Uwzglednij AGENTS.override.md, jezeli obowiazuje.
Nie zakladaj automatycznego odkrywania plikow o nazwach
niestandardowych bez konfiguracji.

Ustal zadanie, branch, HEAD i status Git przed edycja.
Nie skanuj calego SYSTEM, historii i MEMORY bez potrzeby.
Przed ryzykowna zmiana przygotuj punkt przywracania.

## 2. Jeden control plane

`run.py` pozostaje publicznym, cienkim starterem.
`main.py` jest jedynym centralnym control plane.
`latka_jazn/cli.py` obsluguje parser i uslugi komend.

Nie tworz drugiego parsera, lifecycle ani finalizatora.
Studio pozostaje klientem kanonicznych uslug.
Edycja kodu nie aktywuje Jaźni ani jej tozsamosci operacyjnej.

## 3. Zakres danych i konfiguracji

Nie modyfikuj bez jawnej autoryzacji prywatnych:
- memory/, workspace_runtime/ i baz SQLite/WAL/SHM;
- sekretow, tokenow, markerow, aktywnych daemonow;
- niepowiazanych worktree, archiwow i kopii operatora.

.settings/ to planowana wersjonowana konfiguracja.
.settings_local/ to prywatna przestrzen lokalna ignorowana przez Git.
Ich utworzenie nie dowodzi, ze resolver jest juz zintegrowany.

## 4. Implementacja i zaleznosci

Zmieniaj najmniejszy kompletny zakres, zachowuj kontrakty
publiczne i fail-closed. Nie ukrywaj awarii falszywym PASS,
szerokim except, replayem tury ani nieautoryzowanym fallbackiem.

Zrodlem zaleznosci Pythona jest pyproject.toml.
Dependency Studio i wheelhouse zachowuja weryfikacje hashy.
JavaScript jest opcjonalną capability; brak Node nie blokuje
podstawowego runtime. CI stosuje Node.js 24 LTS.

Nowe GitHub Actions musza byc przypiete do pelnego SHA,
po sprawdzeniu upstream oraz plikow action.yml.

## 5. Testy i archiwum

Najpierw uruchom testy dotyczace zmian. Pelna regresja
obowiazuje przed odpowiednim gate integracyjnym lub release.
Nie deklaruj testow niewykonanych.

tests/archive/ jest append-only i poza domyslna kolekcja.
Przed zmiana aktywnego testu zachowaj jego zatwierdzony
oryginal bajt w bajt, z wersja i provenance.
Nie archiwizuj testu tylko z powodu starej nazwy.
Test zastępczy musi chronic co najmniej ten sam kontrakt.

Dla zmian JavaScript/Actions stosuj odpowiednie kontrole:
tools/github_actions_node24_audit.py, npm ci,
npm run check i wymagane workflow.

## 6. Wersja i wydanie

Kazdy patch SYSTEM wymaga podniesienia wersji w
latka_jazn/version.py w tej samej zmianie wydaniowej.

Nigdy nie edytuj recznie PACKAGE_INTEGRITY_MANIFEST.json
ani SOURCE_PROVENANCE.json.

Kanoniczny synchronizator metadanych:
python -X utf8 -m latka_jazn.tools.release_metadata_sync
  --root . --base-branch master --write --json

Przed release candidate wymagaj synchronizacji metadanych,
sprawdzenia jej idempotencji oraz wymaganych kontroli CI.
Nie wykonuj force-push ani merge bez osobnej zgody.

## 7. Walidacja i raport

Wykonaj git diff --check, testy celowane oraz kontrole
wymagane zakresem. Nie zmieniaj testow w celu ukrycia regresji.

Dla loadera ChatGPT obowiazuje limit <= 5000 znakow
w docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt.

Podaj zmienione pliki, wyniki testow, rzeczywiste bledy,
niewykonane kontrole i SHA commita tylko gdy faktycznie istnieje.
