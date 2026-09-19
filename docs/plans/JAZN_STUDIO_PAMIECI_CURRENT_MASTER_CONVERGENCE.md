# Studio Pamięci — konwergencja z aktualnym masterem

Data: 2026-09-14. Branch: `fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence-next-step`.

## Zweryfikowana baza

Aktualny master w tym checkpointcie: `9d38a294c0479078e75b6385c8d46561c5d055c7`.
Wejściowy commit Studia: `d8a55af7204bcf89f188fbf1318cca422a9a372d`.
Przed konwergencją: 7 commitów własnych / 65 commitów mastera, wspólna baza
`5c4db661268f4361f6792ac57e9c1884a126c08c`. Dane te opisują wykonany audyt;
przed dalszą pracą trzeba ponownie pobrać i sprawdzić stan Git.

Master zawiera już historyczną linię `.74.1.001-host-handoff-outcome-convergence`.
Została przejęta przez merge mastera, bez ponownego cherry-pickowania tej gałęzi.
Nazwa wydania .75 pozostaje historyczną tożsamością; nie oznacza już, że kod
bazuje wyłącznie na .73. Poprzednie dokumenty MASTER73 opisują wcześniejszy etap.

## Zakres

Zachowano nowe pliki host preflight, capability snapshot, executor policy,
handoff outcomes, pending/accepted/declined, pre-response gate, ingress oraz
MCP visible reply z mastera. Funkcjonalne moduły i testy Studia pozostają.
Konflikty obejmowały tylko wersję, katalog testów i metadane wydania.
Katalog powstaje przez aktualny sync_contract_catalog.py; końcowe metadane
muszą zostać wygenerowane release_metadata_sync na zatwierdzonym drzewie.
Przejściowa wersja metadanych z mastera w commicie konwergencji nie stanowi
metadanych finalnego checkpointu; następny commit zawiera wynik generatora.

## Dalsza akceptacja

To checkpoint konwergencji, nie naprawa Test03 ani release candidate.
Historyczny Test03 pozostaje FAIL. Należy potwierdzić syntetyczny RED,
rozdzielić deterministyczny batch przygotowany przed zapisem od jawnego
incremental update, a następnie naprawić konfigurowalny ref Test04.
Nie wolno osłabiać porównania snapshotów ani benchmarku.

Po zmianie silnika wymagany jest nowy chain Test00–Test03, zamrożony benchmark
13 przypadków, Test04 i Final. Stare prywatne PASS/FAIL pozostają niezmienione.
Brak prywatnej akceptacji ma status NOT RUN, nigdy domyślny PASS.
Nowa wolna wersja zostanie wybrana dopiero dla rzeczywistej zmiany silnika.
Publiczne testy, Pyright, compileall i release gates muszą być raportowane
oddzielnie dla odpowiedniego commita. Prywatne dane pozostają poza Git.
