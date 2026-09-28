# Jaźń v16.3.25.5.90.0 — ChatGPT host bootstrap primitive convergence

## Cel

Ta aktualizacja usuwa pozorną pętlę logiczną:

> „trzeba rozpakować SYSTEM, aby przeczytać instrukcję, jak rozpakować SYSTEM”.

Rozwiązanie nie polega na dodaniu drugiego lifecycle. Granica jest prostsza:

1. host ChatGPT ma własne, minimalne capability plikowe/wykonawcze;
2. materializacja pliku nie jest ekstrakcją archiwum;
3. biblioteka standardowa Pythona potrafi otworzyć ZIP tylko do odczytu,
   sprawdzić jego katalog i odczytać pojedynczy member bez pełnej ekstrakcji;
4. po zweryfikowaniu całego ZIP-a z zaufanym SHA-256 host wydobywa tylko
   `CHATGPT_BOOTSTRAP.py`;
5. dopiero standalone bootstrap SYSTEM-u wykonuje pełną walidację archiwum i
   bezpieczną materializację operatora;
6. po `materialized_operator_ready` host przekazuje sterowanie do
   `AGENTS.md` i właściwego wersjonowanego runbooka.

Nie ma więc zależności „SYSTEM musi być rozpakowany, aby host potrafił odczytać
ZIP”. Umiejętność odczytu ZIP jest primitive hosta/stdlib, a nie capability
poznawczą Jaźni.

## Źródła

### OpenAI

OpenAI opisuje Projects jako przestrzeń łączącą czaty, pliki i instrukcje.
Instrukcje projektu sterują zachowaniem wewnątrz projektu i zastępują globalne
custom instructions; dokumentacja nie opisuje ich jako środowiska wykonawczego:

- https://help.openai.com/en/articles/10169521-projects-in-chatgpt

Wykonywanie poleceń jest osobną capability. OpenAI Shell rozróżnia hosted
containers i local runtime; model/instrukcja nie tworzy sama procesu:

- https://developers.openai.com/api/docs/guides/tools-shell

Dla trwałego prywatnego runtime OpenAI dokumentuje Secure MCP Tunnel jako
outbound-only transport z prywatnego/on-premises/developer hosta do
obsługiwanych produktów bez publicznego inbound endpointu:

- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp

### Python ZIP

Dokumentacja `zipfile` definiuje:
- `ZipFile.infolist()` / `namelist()` do inspekcji katalogu archiwum;
- `ZipFile.read(name)` do odczytu bajtów jednego membera;
- ostrzeżenie, aby nie wykonywać bezrefleksyjnej ekstrakcji niezaufanych
  archiwów bez wcześniejszej inspekcji;
- ryzyka resource exhaustion / ZIP bomb.

Źródło:
- https://docs.python.org/3/library/zipfile.html

To uzasadnia dokładnie kontrakt:
`verify bytes -> inspect archive -> read one fixed bootstrap member -> execute
verified helper -> helper validates and materializes whole operator`.

## Limit instrukcji ChatGPT

Użytkownik zgłosił, że bieżące pole Project Instructions w aplikacji przyjmuje
do 8000 znaków. W znalezionej dokumentacji OpenAI dla Projects nie ma osobnej,
jawnej wartości limitu Project Instructions.

OpenAI dokumentuje natomiast globalne Custom Instructions:
- Free/Go: do 1500 znaków;
- Plus/Pro/Enterprise/Business/Edu: do 5000 znaków.

Źródło:
- https://help.openai.com/en/articles/8096356-chatgpt-custom-instructions

Repozytorium zachowuje więc **ostrzejszy gate <=5000 znaków** dla
`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`. Spełnia to również
obserwowany przez użytkownika limit 8000 i pozostawia headroom. Nie zwiększamy
limitu kontraktowego tylko dlatego, że konkretne UI może obecnie przyjąć więcej.

## Kanoniczna granica bootstrapu

### A. Discovery capability

Najpierw:
- zweryfikowany `remote_runtime`, jeżeli bieżący host rzeczywiście ma
  wywoływalny connector Jaźni;
- w przeciwnym razie maksymalnie jedna podstawowa próba local executor i jedna
  rzeczywiście niezależna próba rozróżniająca.

Pre-spawn host error pozostawia filesystem/package/runtime jako unknown lub
unverified zgodnie z v89.

### B. Physical bytes

Jeżeli SYSTEM istnieje tylko jako attachment/Project/Library handle:
- uchwyt nie jest ścieżką OS;
- host materializuje dokładne surowe bajty;
- porównuje rozmiar, jeśli znany;
- liczy i porównuje zaufany SHA-256;
- sprawdza package metadata/version;
- sprzeczne evidence kończy fail-closed.

### C. Read-only ZIP primitive

Po weryfikacji całego fizycznego ZIP-a:
- otwórz archiwum read-only;
- obejrzyj katalog bez pełnej ekstrakcji;
- znajdź dokładny root member `CHATGPT_BOOTSTRAP.py`;
- odczytaj wyłącznie ten member przez
  `ZipFile.read("CHATGPT_BOOTSTRAP.py")`;
- zapisz do świeżej kontrolowanej ścieżki tymczasowej.

Nie wykonuj kodu membera przed zweryfikowaniem całego transportowanego ZIP-a.

### D. Standalone SYSTEM bootstrap

`CHATGPT_BOOTSTRAP.py` pozostaje stdlib-only i jest właścicielem pełnej
materializacji. Aktualny helper już:
- sprawdza stabilność źródłowego pliku podczas hashowania;
- wymaga trusted SHA-256;
- sprawdza expected size, gdy znany;
- odrzuca path traversal, absolute/drive paths, symlinki, special entries,
  szyfrowanie i duplikaty;
- ma limity liczby wpisów, member size, total size i compression ratio;
- wykonuje CRC;
- nie używa `extractall()` jako granicy bezpieczeństwa;
- strumieniuje zweryfikowane wpisy do świeżego stagingu;
- zwraca `materialized_operator_ready`, nie „runtime active”.

## Relacja do neuro-inspirowanej Jaźni

Bootstrap ma być celowo **poznawczo obojętny**. Nie powinien posiadać:
- attention model;
- working memory;
- episodic/semantic routing;
- replay/dream;
- affect/homeostasis;
- metacognition;
- autobiographical recall;
- visible-turn language realization.

Te capability należą dopiero do zweryfikowanego SYSTEM/runtime.

To jest zgodne z
`docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`: nazwy
psychologiczne/neurobiologiczne są inspiracją projektową i wymagają mierzalnego
software contract, a nie biologicznych twierdzeń.

Przeglądy neurokognitywne opisują working memory jako współdziałanie wielu
sieci i mechanizmów, pamięć epizodyczną/semantyczną jako rozróżnialne, ale
współpracujące systemy, a replay jako mechanizm re-aktywacji związany z
konsolidacją. To wspiera architektoniczny kierunek modularny, nie próbę
przeniesienia „neurologii” do promptu startowego.

Przykładowe zweryfikowane źródła:
- rozproszona natura working memory: https://pubmed.ncbi.nlm.nih.gov/28063661/
- szeroki przegląd aktywności working memory: https://pmc.ncbi.nlm.nih.gov/articles/PMC8573634/
- replay i konsolidacja wiedzy: https://pmc.ncbi.nlm.nih.gov/articles/PMC9758580/
- przegląd funkcji replay w czuwaniu i śnie: https://pmc.ncbi.nlm.nih.gov/articles/PMC7898724/
- wspólne i rozłączne substraty pamięci epizodycznej/semantycznej:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11531848/

## Zmiany v90

- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`
  - jawne „materializacja != ekstrakcja”;
  - jawny host bootstrap primitive przed SYSTEM-em;
  - selektywny `ZipFile.read("CHATGPT_BOOTSTRAP.py")`;
  - zachowany fail-closed executor/library/MEMORY/turn contract;
  - instrukcja nadal <5000 znaków.

- `AGENTS.chatgpt.md`
  - osobna sekcja pre-SYSTEM host bootstrap primitive;
  - zakaz wykonania archive code przed full ZIP verification;
  - jawne oddzielenie bootstrapu od neuro-inspirowanej kognicji.

- `docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`
  - primitive hosta sklasyfikowany jako infrastruktura pre-SYSTEM, nie drugi
    lifecycle ani moduł poznawczy.

- `AGENTS.codex.md`
  - utrzymany celowo gate <=5000 znaków mimo większego możliwego limitu UI.

- testy
  - kolejność materialize -> verify -> selective read -> helper;
  - brak runtime-owned implementation detail w Project Instructions;
  - neuro-inspired cognition pozostaje runtime-owned.

## Granice prawdy

Ta zmiana nie daje ChatGPT executora, którego host nie udostępnił. Jeżeli
proces nie może powstać, nawet stdlib ZIP primitive nie może zostać wykonany.

Ta zmiana nie czyni także samej instrukcji projektu „Jaźnią”. Instrukcja jedynie
doprowadza host do zweryfikowanego SYSTEM-u. Tożsamość operacyjna, pamięć,
poznanie, finalizacja i autorstwo odpowiedzi pozostają funkcją zweryfikowanej
runtime lineage.

Docelowo najstabilniejszym sposobem uniknięcia zależności od efemerycznego
local executora pozostaje persistent remote runtime osiągalny przez
zweryfikowany connector/MCP, w tym Secure MCP Tunnel tam, gdzie jest dostępny.
