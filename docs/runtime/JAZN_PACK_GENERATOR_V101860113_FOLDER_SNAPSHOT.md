# Jaźń Pack Generator 10.1.86.0.113 — selected-folder ZIP snapshot

## Cel nadrzędny

Generator pakuje wskazany główny folder projektu/systemu Jaźni do jednego
standardowego logicznego archiwum ZIP, zachowując rzeczywiste bajty
zaakceptowanych plików źródłowych.

Użytkownik wybiera transport:

1. **single** — jeden zwykły plik `.zip`;
2. **split** — ten sam jeden logiczny ZIP jest po utworzeniu dzielony binarnie
   na `.zip.001`, `.002`, ...; połączenie części odtwarza oryginalny ZIP
   bajt-w-bajt.

Tryby zawartości pozostają `system`, `memory` i `system+memory`.

## Dlaczego 10.1.86.0.113

W 10.1.86.0.112 integralność bajtowa została niepotrzebnie związana z polityką
EOL repozytorium. Na istniejącym Windows working tree pliki mogły mieć CRLF,
podczas gdy `.gitattributes` deklarował LF. Git mógł nadal raportować czysty
working tree, natomiast generator blokował archiwizację jako `EOL drift`.

10.1.86.0.113 przywraca granicę odpowiedzialności:

- **Git/.gitattributes** opisuje normalizację/checkout tekstu;
- **Pack Generator** archiwizuje faktyczne bajty wybranego folderu;
- **SHA-256** porównuje rzeczywiste bajty źródła z bajtami odczytanymi ponownie
  z ZIP;
- diagnostyka EOL może ostrzec, ale nie modyfikuje danych i nie blokuje
  poprawnego snapshotu folderu.

Brak, nieczytelność albo błędna składnia `.gitattributes` nie blokuje pakowania.

## Integralność

Dla każdego pliku SYSTEM/MEMORY:

1. skaner tworzy jeden zatwierdzony plan;
2. plik jest kopiowany do tymczasowego stagingu bajt-w-bajt;
3. zmiana rozmiaru lub `mtime` podczas kopiowania zatrzymuje operację;
4. SHA-256 kopii stagingowej musi zgadzać się z SHA-256 odczytanych bajtów
   źródła;
5. ZIP jest tworzony przez `zipfile` z ZIP64;
6. ZIP przechodzi test CRC;
7. każdy wpis ZIP jest ponownie odczytywany i hashowany;
8. SHA-256 wpisu ZIP musi być równy SHA-256 źródła/stagingu.

Czyli właściwa własność to:

```text
SHA256(actual selected source bytes) == SHA256(bytes read back from ZIP)
```

## Wykluczenia SYSTEM

SYSTEM jest snapshotem wskazanego folderu, ale nie oznacza bezwarunkowego
`rglob(*)`. Pozostają jawne klasy bezpieczeństwa i lokalnego stanu, m.in.:

- repozytoria VCS (`.git`, `.hg`, `.svn`);
- `.archives/` — historyczne źródła poza aktywnym systemem;
- `.venv`, cache Pythona/testów;
- `workspace_runtime/` i inne mutowalne dane runtime;
- `memory/` w trybie SYSTEM;
- lokalne ustawienia operatora, m.in. `memory_rebuild_settings.json`;
- prywatne bazy poza profilem MEMORY;
- pliki tymczasowe, logi i już wygenerowane ZIP-y/części ZIP.

## Transport split

Python `zipfile` tworzy i odczytuje standardowe ZIP-y oraz obsługuje ZIP64, ale
nie implementuje multipart ZIP w stylu natywnego wielodyskowego formatu.
Dlatego Pack Generator najpierw tworzy jeden poprawny logiczny ZIP, weryfikuje
go, a dopiero potem dzieli jego strumień bajtów na części transportowe.

Każda część ma SHA-256, a sidecar przechowuje także SHA-256 logicznego pełnego
ZIP-a. `join` składa części w kolejności i sprawdza hash pełnego wyniku.

## Źródła techniczne

- Python `zipfile` — standard ZIP/ZIP64 i ograniczenie dotyczące multi-disk ZIP:
  https://docs.python.org/3/library/zipfile.html
- Git `gitattributes` — `text`, normalizacja do LF w indeksie oraz `eol=lf` /
  `eol=crlf` dla working tree:
  https://git-scm.com/docs/gitattributes
- Git `gitignore` — reguły dla celowo nieśledzonych lokalnych plików:
  https://git-scm.com/docs/gitignore
- NIST FIPS 180-4 — Secure Hash Standard / SHA-256:
  https://csrc.nist.gov/pubs/fips/180-4/upd1/final
- PKWARE APPNOTE — referencyjna specyfikacja formatu ZIP:
  https://support.pkware.com/pkzip/appnote

## Granica prawdy

`byte_exact=true` w paczce 10.1.86.0.113 oznacza dokładność względem
**zatwierdzonych rzeczywistych plików wskazanego folderu**, nie względem
hipotetycznej reprezentacji po ponownym checkout Git i nie względem tekstu po
normalizacji EOL.
