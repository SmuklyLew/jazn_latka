# Jaźń v16.3.25.5.54 — ChatGPT sandbox bootstrap hardening

## Cel

Ta aktualizacja domyka ścieżkę: **załącznik systemowy ZIP → lokalny executor ChatGPT → bezpieczna materializacja → `AGENTS.md` → kanoniczny operator `run.py`**.

Nie próbuje zastępować ani emulować executora platformy OpenAI. Naprawia natomiast kontrakt systemu Jaźni tak, aby:

- nie mylić awarii hostowego transportu/executora z uszkodzonym ZIP-em;
- móc rozpocząć recovery z pojedynczego kompletnego systemowego ZIP-a, gdy zaufany SHA-256 jest już znany;
- wymagać stabilnego fizycznego pliku przed ekstrakcją;
- nie używać `extractall()` jako granicy bezpieczeństwa;
- materializować operator fail-closed do świeżego katalogu;
- po materializacji natychmiast wrócić do kanonicznego lifecycle `run.py`.

## Ustalenia z badań

### Potwierdzone przez źródła

1. OpenAI udostępnia narzędzie Shell w dwóch zasadniczych wariantach: hostowanym kontenerze zarządzanym przez OpenAI oraz lokalnym runtime utrzymywanym przez dewelopera. Warstwa wykonawcza jest odrębna od samego modelu i jej dostępność jest warunkiem uruchomienia poleceń.
   - https://developers.openai.com/api/docs/guides/tools-shell

2. Dokumentacja Sandbox Agents rozdziela zaufany harness/control plane od sandbox compute. Oznacza to, że błąd komunikacji lub niedostępność executora jest inną klasą awarii niż błąd procesu działającego już wewnątrz sandboxa.
   - https://developers.openai.com/api/docs/guides/agents/sandboxes

3. ChatGPT może pracować na plikach w środowisku wykonawczym dla zadań analitycznych, ale użytkownik nie konfiguruje wewnętrznego executora ChatGPT jak własnego Dockera i nie może z poziomu paczki Jaźni wymusić utworzenia procesu przez niedostępny host.
   - https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt

4. Python ostrzega przed bezwarunkową ekstrakcją archiwów z niezaufanych źródeł bez wcześniejszej inspekcji. Bezpieczny bootstrap powinien sam kontrolować ścieżki, typy wpisów i limity.
   - https://docs.python.org/3/library/zipfile.html

### Wniosek inżynierski

Nie znaleziono publicznej, stabilnej specyfikacji OpenAI dla dokładnego wyjątku `TransportTimeoutError`, która pozwalałaby z samej nazwy wyjątku ustalić jego wewnętrzną przyczynę. Dlatego v54 stosuje zasadę opartą na obserwowalnym fakcie:

- **brak dowodu utworzenia procesu + hostowy `TransportTimeoutError` → `host_executor_unavailable`; filesystem i paczka pozostają `unknown`, runtime `unverified`;**
- **proces faktycznie wystartował, a potem timeout/stderr/non-zero → diagnoza procesu, nie awaria hostowego executora.**

To rozróżnienie zapobiega fałszywemu wnioskowi „ZIP jest uszkodzony”, gdy polecenie `stat`, `sha256`, Python albo unzip nigdy nie zostało uruchomione.

## Zmiany v16.3.25.5.54

### `CHATGPT_BOOTSTRAP.py`

Standalone bootstrap nadal używa wyłącznie biblioteki standardowej i nie importuje `latka_jazn`.

Dodano:

- stabilne kody diagnostyczne `BootstrapError.code`;
- `sha256_stable_file()` z kontrolą tożsamości pliku przed, podczas i po hashowaniu;
- opcjonalne `--expected-size-bytes`;
- możliwość użycia `--expected-sha256` zamiast lokalnego sidecara;
- odrzucanie zaszyfrowanych wpisów ZIP;
- odrzucanie symlinków, specjalnych typów filesystemu i niespójności type/name;
- ręczną strumieniową ekstrakcję po walidacji;
- sprawdzanie containment przez `commonpath`;
- tryb tworzenia plików `xb`, aby nie nadpisywać istniejących ścieżek;
- kontrolę rzeczywiście zapisanych bajtów per member i łącznie;
- wynik `operator_entrypoint = "run.py"`, `source_size_bytes` i `stable_during_hash`.

Usunięto `ZipFile.extractall()` z właściwej ścieżki materializacji.

### `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`

Loader został doprecyzowany tak, aby:

- wymieniać `TransportTimeoutError` jako możliwy błąd hostowy tylko przy braku dowodu uruchomienia procesu;
- ograniczać probing do jednej próby podstawowej i jednej niezależnej alternatywy;
- zabraniać retry-loopów i własnego backoffu;
- wymagać stabilnego pliku, rozmiaru — gdy jest znany — oraz SHA-256;
- umożliwiać pojedynczy ZIP + zaufany SHA-256 bez lokalnego sidecara;
- wydobywać tylko `CHATGPT_BOOTSTRAP.py` przez `ZipFile.read()` do świeżego pliku tymczasowego;
- po `materialized_operator_ready` przechodzić do `run.py --version`, `host-preflight`, `doctor`, `start`, `status`.

### `AGENTS.chatgpt.md`

Runbook hosta otrzymał jawne rozdzielenie:

1. **host/control plane** — czy proces w ogóle może zostać utworzony;
2. **attachment materialization** — czy fizyczny ZIP jest kompletny i stabilny;
3. **package verification** — size/SHA/CRC/structure/limits;
4. **operator materialization** — bezpieczna ekstrakcja;
5. **runtime lifecycle** — wyłącznie przez `run.py`.

Dodano również jednoznaczne stwierdzenie, że kod Jaźni nie może naprawić niedostępnego executora platformy, ponieważ nie jest jeszcze wykonywany na etapie awarii przed utworzeniem procesu.

### Testy

Dodano `tests/test_chatgpt_sandbox_bootstrap_hardening.py`, obejmujący:

- pojedynczy ZIP z explicit SHA bez lokalnego sidecara;
- poprawny top-level wrapper paczki;
- kontrolę oczekiwanego rozmiaru;
- traversal `../`;
- symlink Unix;
- duplicate member;
- zakaz `extractall()`;
- obecność nowych wymagań w loaderze i runbooku.

## Kanoniczna ścieżka recovery po v54

```text
1. minimalny probe executora
   |
   +-- proces nie powstał -> host_executor_unavailable
   |                       filesystem/package = unknown
   |                       runtime = unverified
   |
   +-- proces powstał
       |
       v
2. znajdź lokalny system ZIP / active_root
       |
       v
3. zweryfikuj stabilność pliku + expected size (jeżeli znany) + SHA-256
       |
       v
4. bez run.py: przeczytaj tylko CHATGPT_BOOTSTRAP.py z ZIP przez ZipFile.read()
       |
       v
5. uruchom standalone bootstrap z:
   --zip
   --destination
   --json
   oraz jednym z:
   --sha256-file | --expected-sha256
   opcjonalnie --expected-size-bytes
       |
       v
6. walidacja ZIP + strumieniowa materializacja do świeżego stagingu
       |
       v
7. materialized_operator_ready
       |
       v
8. odczytaj pełny AGENTS.md
       |
       v
9. run.py --version
   run.py host-preflight --json
   run.py doctor --json
   run.py start
   run.py status --json
       |
       v
10. dopiero pozytywny live status pozwala deklarować aktywny runtime
```

## Dlaczego nie dodano Dockera/Firecrackera do Jaźni

Badania potwierdziły, że rootless Docker/Podman, gVisor, Kata i Firecracker są sensownymi technologiami dla executora kontrolowanego przez właściciela infrastruktury. Nie są jednak naprawą dla bieżącego przypadku ChatGPT, w którym błąd następuje przed utworzeniem procesu przez hosta OpenAI.

Dodanie Dockera do paczki systemowej Jaźni nie pomogłoby, jeśli ChatGPT nie może uruchomić nawet pierwszego procesu potrzebnego do wywołania Dockera/Pythona. Z tego powodu v54 naprawia warstwę, którą projekt faktycznie kontroluje: poprawne rozpoznanie granicy hosta oraz bezpieczny bootstrap, gdy executor jest dostępny.

## Granice aktualizacji

v54 **nie gwarantuje**, że wewnętrzny executor ChatGPT będzie zawsze dostępny. Nie istnieje mechanizm w kodzie ZIP-a, który może utworzyć niedostępny proces platformowy przed uruchomieniem samego kodu ZIP-a.

v54 gwarantuje natomiast na poziomie kontraktu i implementacji projektu, że po odzyskaniu lokalnej zdolności wykonawczej host ma jednoznaczną, ograniczoną i fail-closed drogę z kompletnego ZIP-a do kanonicznego `run.py`, bez potrzeby traktowania paczki `memory` jako systemu ani pobierania repozytorium jako zastępczego runtime.

## Walidacja wydaniowa

W tej sesji lokalny executor ChatGPT wcześniej zwracał `TransportTimeoutError` przed dowodem utworzenia procesu. Z tego powodu lokalne `compileall`, `pytest`, `run.py doctor` i `package-smoke` nie mogą być przedstawione jako wykonane.

Walidacja brancha musi obejmować co najmniej:

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py CHATGPT_BOOTSTRAP.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
git diff --check
```

Metadane `PACKAGE_INTEGRITY_MANIFEST.json` oraz `SOURCE_PROVENANCE.json` nie są edytowane ręcznie. Powinny zostać zsynchronizowane wyłącznie kanonicznym `release_metadata_sync` / workflow `manifest_sync` zgodnie z `AGENTS.codex.md`.
