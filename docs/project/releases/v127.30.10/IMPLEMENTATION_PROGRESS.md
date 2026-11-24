# JAŹŃ v127.30.10 — checkpoint implementacji

- Branch: `fix/v12730-10-runtime-architecture-hardening`
- Commit bazowy: `9db1993f8734413b370c0325fb1135dfdf42aeba`
- Plan zapisany w commicie `662d58760cf8be2bc7a3d6981cb97b14fc587e17`.
- Stan lokalnego worktree: UNKNOWN (dostęp przez GitHub API, executor zwrócił ClientError).
- Budżet hosta: usage_unknown.

| Etap | Stan | Dowody / następny krok |
|---|---|---|
| 00 | PARTIAL | Plan opublikowany, ref sprawdzony; lokalny worktree niezweryfikowany. |
| 01 | ANALYZING | Odczytano router AGENTS, runbook Codex i referencję operacyjną, granice naukowe, kontrakty finalizacji, RecoveryPolicy i istniejący test regresji. Pełna mapa zależności niegotowa. |
| 02 / J-001 | IMPLEMENTED_UNVERIFIED | Projekcja VerifiedSessionQuote wydzielona bez zmiany warunku, kolejności i mutacji. Statycznie zakres resolve zmniejszono z 166 do 150 linii (pomiar tekstowy, nie test AST). Testy pytest/pyright NOT_RUN na tym etapie. |
| 03 / J-002 | NOT_STARTED | Zbadać istniejące dowody finalizacji i testy hosta, odróżnić runtime-exact/local od host phase-2; nie osłabiać bramek. |
| 04–11 | NOT_STARTED | Zgodnie z planem. |
| 12 | PARTIAL | Podniesiono PACKAGE_VERSION i zgodne kontrakty startup/MCP. Manifest/provenance i katalog JSS oczekują kanonicznego generatora w release-hardening. |
| 13–14 | NOT_RUN | Pełny CI i rzeczywisty odbiór wymagane. |

## Kontrole
- Istniejący test limitu i testy pamięci sesyjnej pozostają bez zmian.
- Nie uruchamiano lokalnego Pythona: executor ClientError. Nie deklarować PASS.
- Nie dołączono danych MEMORY ani logów prywatnych. Nie zmieniano master ani historii.
- Następny krok: odczytać faktyczny zdalny HEAD (również po auto-commitach CI), Actions i wynik testu hotspotu; kontynuować J-002 po audycie kontraktów. Weryfikacja aktualnego SHA obowiązkowa.

## Checkpoint J-002 — implementacja niezweryfikowana

- Zidentyfikowano, że host_finalization_gate_state opisuje również poprzednią turę; samo not_required nie dowodzi finalizacji.
- Wydzielono istniejący warunek renderowania do wspólnego predykatu odczytowego, bez zmiany bramki wyświetlania lokalnego.
- CLI completion dla jawnych kanałów runtime-owned sprawdza istniejące dowody: brak bieżącego host phase-2, gate, truth/author/hash, MessageEnvelope, canonical persistence, powiązanie request/session/turn/trace oraz format SHA rekordu. Dotychczasowy warunek host-visible completion pozostaje niezmieniony. Nie dodano finalizatora ani nowych wywołań modelu.
- Dodano syntetyczne testy pozytywne i negatywne w tests/test_daemon_runtime_owned_completion.py. Nie wykonują płatnych API. Testy NOT_RUN lokalnie; oczekują CI. Odbiór rzeczywisty NOT_RUN.
- Stan poprzedniego commita 5631d0c2: 5 workflow success, pozostałe w toku lub pending w momencie odczytu (nie stan nowego SHA). Release-hardening może przesunąć ref poprzez generator metadanych; weryfikować końcowy HEAD.
- Następny krok: odczyt wyników nowego commita, testy completion i hotspot, audyt continuity J-003/J-004; nie deklarować pełnego release.

## Checkpoint — korekta kierunku 2026-11-24

- Zdalny HEAD przed korektą: `efe0423e9f3375beef8ea962afba7c09e03305ec`. Wszystkie 6 workflow dla kodu `40709fcf8affbeb343e11e44ba4aac9ad2ec2115` zakończone success, w tym release-hardening 45495010823 oraz persistent-runtime-e2e 45495010985. Automatyczny commit metadanych nie jest samodzielnym dowodem odbioru na żywo. J-001/J-002: CI PASS, live odbiór v127.30.10 NOT_RUN.
- Operator przywrócił docelowy remote-only ordinary-chat przez autoryzowane MCP/Cloudflare; brak ZIP/executora/handoffu w normalnej rozmowie. J-012: ANALYZING. Istniejący `chatgpt_ingress_policy.py` nadal domyślnie wybiera hybrid_adaptive, `negotiate_chatgpt_ingress` nadal promuje proces lokalny, instrukcje projektu nakazują lokalny fallback. Zmiana planu sama nie wdraża tej funkcji.
- Kolejny krok: zbieżność policy, capability, preflight, loadera i ich kontraktów; zachować jawny operator_recovery i regresje lokalnego PC. Nie usuwać istniejących testów bez snapshotów. Dalszy odbiór live ChatGPT/MCP i PC NOT_RUN. Budżet usage_unknown.
