# AGENTS.chatgpt.md — kontrakt hosta ChatGPT

Ten runbook obowiązuje wyłącznie dla transportu i operacji hosta ChatGPT.
Nie jest personą ani zastępczym runtime Jaźni.
Kanoniczny SYSTEM pozostaje właścicielem routingu, MEMORY,
tożsamości operacyjnej i finalizacji.

Pełna referencja sprzed refaktoryzacji:
`docs/runtime/CHATGPT_HOST_OPERATIONAL_REFERENCE.md`.
Czytaj odpowiednie procedury tylko przy diagnostyce, cold bootstrapie
lub operacjach serwisowych wymagających szczegółowego kontraktu.

## 1. Runtime-first, identity-by-lineage

Zasada: runtime-first, identity-by-lineage.
`run.py` jest cienkim starterem.
`main.py` jest jedynym centralnym control plane.
Parser/usługi należą do `latka_jazn/cli.py`.

Nie rekonstruuj logiki SYSTEM w hoście.
Obecność ZIP, MCP, modelu, folderu, PID ani gotowego tekstu
nie dowodzi aktywnego runtime ani autorstwa Jaźni.

## 2. Hybrid/adaptive ingress

Zachowaj kolejność:
1. zweryfikowany remote runtime;
2. zweryfikowany lokalny active_root i daemon;
3. bounded local executor/bootstrap;
4. fail-closed przy braku gotowej trasy.

### Fresh-message app exposure gate

Sprawdź w bieżącej wiadomości faktycznie callable:
- `jazn_status`
- `jazn_generate_visible_reply`
- `jazn_resume_visible_reply`
- `jazn_finalize_reply`

Wymagaj `current_message_toolset_observed=true`,
autoryzacji, zgodnej wersji i instancji, kompletnego kontraktu,
readiness oraz świeżego heartbeat.

Nie koduj polityki jako `plan == Plus/Pro/Business/...`.
Nazwa lub instalacja aplikacji Jaźń Runtime nie jest dowodem
bieżącej ekspozycji narzędzi.

### Preferowany probe przez rzeczywistą akcję Jaźni

Wykonaj jedno read-only wywołanie `jazn_status`, gdy narzędzie
jest faktycznie dostępne. Zweryfikuj lineage oraz wynik statusu.
`host_connector_invocation_observed=true` wymaga rzeczywistego
wywołania konektora. Wklejony JSON nie jest takim dowodem.

Status connector-observed i samodzielny HTTP probe to inne
rodzaje dowodów; nie wolno ich mieszać.
`classify_public_connector_status_failover()` wymaga
danych zgodnych z kontraktem.

## 3. Warm, resume i cold

Warm: reuse tylko po sprawdzeniu root, wersji, daemon_instance_id,
endpointu i heartbeat. Nie uruchamiaj drugiego daemona.

Resume: gdy root jest zweryfikowany, ale daemon niegotowy,
korzystaj wyłącznie z kanonicznego lifecycle `run.py`;
nie twórz równoległej ścieżki uruchamiania.

Cold: dopiero przy braku zaufanego active_root sprawdzaj SYSTEM ZIP.
Weryfikuj wydanie, SHA-256, wszystkie części archiwum, CRC,
bezpieczne ścieżki, komplet manifestu oraz provenance.

Przed analizą kodu wymagaj pełnej bezpiecznej ekstrakcji SYSTEM
do odrębnego katalogu, bez surowego extractall().
Po weryfikacji wczytaj `AGENTS.md` i właściwy runbook.

## 4. Granica executora i plików

Sprawdzaj rzeczywiście dostępne pliki i executor/terminal.
Jeżeli istnieje `/mnt/data`, jest pierwszym kandydatem do
lokalnego discovery, a nie automatycznie gotowym SYSTEM.

Jeżeli marker nie istnieje albo jest nieważny, sprawdź
kompletna paczka systemowa ZIP i jej pochodzenie.

Błąd ClientError, InvalidArgumentError lub TransportTimeoutError
przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu
oznacza `host_executor_unavailable`.

Utrzymuj `filesystem_state = unknown` i `package_state = unknown`.
W szczególności nie twierdź, że `/mnt/data` nie istnieje.

Wykonaj najwyżej jedną próbę na podstawowym executorze i
dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza
może zostać sprawdzona raz, jeśli jest faktycznie dostępna.
Nie zapętlaj retry między narzędziami.

Po odzyskaniu executora wróć do zwykłego discovery/bootstrapu.
One-shot dowodzi wyłącznie wykonania danej tury.

## 5. Biblioteka i MEMORY

Brak paczki w `/mnt/data` nie dowodzi jej braku w Bibliotece ChatGPT.
Logiczna ścieżka Biblioteki, `file_id` ani inny uchwyt hosta
nie są ścieżką systemu plików.

Dostępny SYSTEM zmaterializuj jako dokładne surowe bajty.
Dopiero zweryfikowana lokalna kopia może wejść do
istniejącego bootstrapu.

Przy sprzeczny rozmiar, SHA-256 albo metadane zakończ fail-closed.
`library_surface_unavailable` nie jest dowodem, że paczki
w Bibliotece nie ma.

Materializacja SYSTEM nie materializuje automatycznie MEMORY.
Profil `memory` nadal nie może stać się `active_root`.
Nie deklaruj autobiograficznej ciągłości bez jej dowodów.

## 6. Preflight i persistent runtime

Przy pierwszym kanonicznym starcie lokalnym:
- `python -X utf8 run.py host-preflight --json`
- `python -X utf8 run.py start`
- `python -X utf8 run.py status --json`

Rozmowa lokalna:
`python -X utf8 run.py chat-gpt --session-id <session-id>`

Uruchomienie persistent bridge wykonuj raz na sesję wykonawczą.
Jeżeli utrzymujesz stdin/stdout, wykorzystaj ten sam otwarty kanał;
nie uruchamiaj nowej komendy CLI dla każdej wiadomości.

Utrzymuj stabilny session_id, unikalny request_id oraz zgodne
turn_id, trace_id, kontrakt i instance lineage.
Przy timeout poll/resume tego samego requestu bez replayu.

## 7. Jedna wiadomość, zaakceptowana finalizacja

Każdą bieżącą wiadomość przekaż w dokładnym brzmieniu.
Nie parafrazuj wiadomości przed przekazaniem.
Nie wyprowadzaj akcji samodzielnie.

Rozpoznawaj wyłącznie kanoniczne akcje:
- action=poll_runtime
- action=generate_then_finalize
- action=host_diagnostic
- action=display_exact

Generowanie według runtime contract wymaga phase-2 finalization.
Widoczna odpowiedź Jaźni wymaga accepted finalization,
zgodnego MessageEnvelope, lineage i persistence.
`final_visible_text` wyświetlaj znak w znak.
Nie dopisuj własnych nagłówków ani stylizacji.

Stosuj pola `must_not_claim_runtime_voice`
oraz `must_preserve_runtime_voice`.
Narzędzia hosta są capability, nie dowodem autorstwa runtime.

## 8. Uprawnienia i diagnostyka

ROZMOWA: szybka gotowa trasa, jedna tura, finalizacja.
DIAGNOSTYKA: szczegółowe dowody i techniczne runbooki na żądanie.
PROGRAMOWANIE: `AGENTS.codex.md` i właściwe instrukcje poddrzew.
operator_recovery: osobny jawny tryb serwisowy.

Dostęp do narzędzia nie jest zgodą na zapis, publikację,
instalację, zmianę auth, płatne API ani edycję prywatnej pamięci.
`chat-gpt` nie wykonuje płatnych wywołań OpenAI API.

Nie zatrzymuj daemona po każdej turze ani zamknięciu czatu.
Stop wymaga zgody, kanonicznego lifecycle i potwierdzenia statusu.
Przy blokadzie mów jako host, bez imitacji Jaźni.

## 9. Konfiguracja i repozytorium

`.settings/` jest planowaną wersjonowaną konfiguracją.
`.settings_local/` jest prywatne i ignorowane przez Git.
Nie deklaruj pełnej integracji przed odbiorem resolverów.

Nie zmieniaj master, MEMORY, manifestów ani źródeł
bez odrębnej podstawy i wymaganej weryfikacji.
Szczegółowe procedury oraz kontrakty pozostają w dokumentacji
referencyjnej i w kanonicznym runtime.

## 10. Uzupełniające kontrakty operacyjne

Te procedury stosuj tylko w kontekście odpowiedniej operacji.
Nie są listą czynności do wykonania przy każdej wiadomości.
Warm oznacza użycie zweryfikowanego żywego daemona;
resume nie może tworzyć duplikatu procesu ani nowej tury.
One-shot CLI jest dopuszczalny jako transport istniejącego,
trwałego requestu, gdy host nie utrzymuje interaktywnego bridge.
Maintenance MEMORY, stop/restart i operacje zapisu wymagają
oddzielnej autoryzacji operatora i kanonicznego lifecycle.
W zwykłej ROZMOWIE obowiązuje szybka trasa i brak działań
serwisowych. Przy konflikcie stosuj fail-closed i odpowiedni
kanoniczny kontrakt runtime, nie improwizowany fallback.

Zachowane szczegółowe wymagania operacyjne tego rozdziału są już zawarte dosłownie w `docs/runtime/CHATGPT_HOST_OPERATIONAL_REFERENCE.md`. Odwołuj się do tego dokumentu tylko przy zadaniu wymagającym szczegółowego recovery, bootstrapu, transportu lub finalizacji. Nie kopiuj tych procedur ponownie tutaj i nie wczytuj referencji przy każdej zwykłej wiadomości.

W referencji znajdują się między innymi:
- OAuth i publiczne MCP: challenge, scope, audience, readiness, status zredagowany i aktualna ekspozycja narzędzi;
- warm/resume/cold, weryfikacja `active_root`, supervisora, package integrity, SYSTEM ZIP oraz bezpieczna materializacja z Biblioteki;
- dołączanie MEMORY, kontrakty provenance, `memory-converge` i jedno okno maintenance;
- granice lokalnego executora, sześć pól tri-state, błędy przed utworzeniem procesu i bounded recovery;
- trwałe `session_id`/`request_id`, jednokrotny submit, poll/resume bez replayu, phase-2 i accepted finalization.

Właściwe procedury MCP i finalizacji są dodatkowo indeksowane przez `docs/runtime/CHATGPT_MCP_CONNECTION_RECOVERY.md` oraz `docs/runtime/TURN_FINALIZATION_CONTRACTS.md`. Te dokumenty nie tworzą alternatywnego lifecycle, routingu, pamięci ani finalizatora. W przypadku rozbieżności z aktualną implementacją weryfikuj kontrakt kodu i testy; nie usuwaj warunków bezpieczeństwa tylko na podstawie redakcyjnego skrótu.
