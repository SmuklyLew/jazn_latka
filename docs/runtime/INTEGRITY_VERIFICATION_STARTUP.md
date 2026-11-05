# Weryfikacja integralności na ścieżce startu

Start eksportowanego SYSTEM i zapis markera aktywności wymagają weryfikacji
manifestu. Marker, PID i obecność plików nie zastępują poprawnych hashy ani
identity/readiness daemona. Limit startu pozostaje własnością kanonicznego
lifecycle; tej zmiany nie uzyskano przez jego wydłużenie.

`verify_package_integrity_manifest` używa jednego `SafePathRoot` na przebieg.
Resolver przypina kanoniczny ROOT raz. Każdy wpis nadal przechodzi sprawdzenie
względnej składni, rozwiązanie aktualnego celu, kontrolę containment oraz odczyt
symlinków/reparse points. Metadane elementów, cele dowiązań, treść i hashe plików
nie są buforowane pomiędzy wpisami ani przebiegami. Zmiana ROOT w dowiązanie do
obcego katalogu nie powoduje przyjęcia nowego celu jako zaufanej bazy.

Polityka wykluczeń może korzystać z już zweryfikowanej kanonicznej nazwy zamiast
ponownie normalizować ten sam tekst. Publiczne `path_is_forbidden` zachowuje
pełną walidację wejścia. Weryfikator nadal sprawdza wszystkie wymagane hashe,
rozmiary, liczbę wpisów, pełny inwentarz statycznych plików i wersję. Czysty Git
zachowuje dotychczasowy kontrakt kanonicznych blobów; eksport używa bajtów plików.

Testy `test_integrity_pinned_root.py` obejmują odmowę obcego wpisu po wcześniejszym
poprawnym wpisie, zmianę katalogu/ROOT w dowiązanie po pierwszym odczycie oraz
wykrycie późniejszej zmiany treści i dodanego statycznego pliku. Testy dowiązań
wymagają odpowiedniej capability hosta i nie stają się PASS wskutek jej braku.

Odczytowy profil zatrzymanego Windows stagingu z 3663 wpisami wykazał w trzech
naprzemiennych pomiarach 5,41–5,60 s dla bazy i 4,48–4,53 s po zmianie, przy
zgodnym manifeście/provenance. To dowód kosztu tej operacji, nie pełny odbiór
zimnego startu, recovery ani rozmowy. Te scenariusze wymagają osobnych dowodów
istniejącego TPA, powiązanych z dokładnym źródłem i potwierdzonym cleanup.
