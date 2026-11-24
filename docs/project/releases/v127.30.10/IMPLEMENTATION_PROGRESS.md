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

## J-012 — etap migracji 1: executable policy

- Skorygowany plan zapisano w `a8e73cb3cb9ee98c63671d86f832e2ccb84d7178`; automatyczny commit `4857fa0e0bcd3bd1c045b0c53e683271fbdddd21` zmienia wyłącznie manifest i provenance.
- `select_chatgpt_entry_action`, normalizacja domyślnego trybu i `negotiate_chatgpt_ingress` używają teraz remote_only jako domyślnej polityki; nie promują istniejącego lokalnego procesu ani zweryfikowanego SYSTEM do zwykłej rozmowy. CLI capability gate wymaga jawnego `--ingress-mode operator_recovery` do klasyfikacji bootstrapu; niezaufany JSON nie wybiera trybu. Explicit legacy hybrid pozostaje na czas migracji, operator recovery i lokalny PC nie są usuwane.
- Historyczne trzy zmienione testy skopiowano jako identyczne bloby Git z poprzedniego SHA. Aktywne testy zachowują scenariusze recovery i dodają negatywne przypadki ordinary-chat, w tym fałszywy tryb z payloadu. Testy NOT_RUN lokalnie; CI weryfikuje. Wersja pozostaje v127.30.10 jako nieodebrana, wielocommitowa zmiana wydaniowa (podniesiona w 5631d0c2).
- J-012 pozostaje IMPLEMENTING: preflight adaptive wrapper, startup/evidence contracts, plugin prompt, AGENTS.chatgpt.md, instrukcja projektu i ich historyczne testy nadal wymagają skoordynowanej migracji. Nie używać tych instrukcji jako finalnej wersji remote-only. Nie deklarować kompletnego odbioru. Następny krok: audyt CI oraz kompletna migracja pozostających domyślnych punktów wejścia i generatorów; następnie live MCP/Cloudflare. Brak zmian produkcji, konfiguracji Cloudflare, prywatnej MEMORY; usage_unknown.

## J-012 — etap migracji 2a: ordinary preflight wrapper

- Baza zmiany: `c788128cfe76e9f0db7f5629bd575e003fac1093`. Historyczny wrapper `plan_chatgpt_adaptive_ingress_preflight` deleguje do istniejącego strict remote planner; nie tworzy drugiej polityki. Jawny legacy hybrid nadal dostępny przez generyczny planner z `HYBRID_ADAPTIVE`; operator recovery bez zmian.
- Zachowano oryginalny test jako identyczny blob Git w `tests/archive/test_chatgpt_hybrid_adaptive_ingress_convergence_v127_30_10_pre_wrapper_c788128.py`. Testy legacy jawnie wybierają tryb, a regresja ordinary sprawdza lokalny executor, alternatywny probe, handoff oraz zweryfikowaną zdalną trasę. Nie zmieniano kontraktów startup ani promptów w tej atomowej zmianie.
- Status: IMPLEMENTED_UNVERIFIED. Lokalny executor ponownie ClientError; pytest/compileall/pyright NOT_RUN; bieżące przebiegi CI niedostępne przez użyty interfejs. Wersja pozostaje w tej samej nieodebranej zmianie wydaniowej v127.30.10. JSS catalog i metadane wymagają kanonicznej synchronizacji CI. Następny krok: zweryfikować CI tego patcha, następnie zbieżność CLI preflight, kontraktów i generatorów loadera. J-012 nie jest zamknięty; live odbiór NOT_RUN. Bez zmian master, produkcji, MEMORY i auth.

## J-012 — CI correction: Pyright test typing

- For code SHA `d3b0857d0f011e09ff21d944e901107005d64d5e`, GitHub Actions REST evidence: Stable test contracts 45500224099, MCP conformance 45500224077, memory-cloud 45500223978 and release-hardening 45500224031 completed success. Pyright 45500224028 failed with 2 errors, 0 warnings, 1618 files analyzed. Persistent-runtime-e2e not observed for this SHA. Metadata/JSS synchronization moved HEAD to `eddf0df44f457d5ffbe556225b56a6116bde4f1f`; no runtime code changes in those two intervening commits.
- Fixed exactly the reported test typing defects: explicit optional-key TypedDict for local evidence kwargs and a real isinstance assertion narrowing recovery hint to str before membership check. Retained parameterized evidence and all original assertions; no production changes or suppressions. Original tests preserved as Git blobs in tests/archive with provenance.
- Status IMPLEMENTED_UNVERIFIED until new CI returns. No local tests executed; live acceptance NOT_RUN. Next: verify current SHA Pyright and other required gates, then J-012 CLI preflight and contracts migration. No change to master, auth, private MEMORY or production.

## J-012 — etapa migracji 2b: CLI preflight

- Verified GitHub CI for `b48158e898eb56fc95e28f20f20a3616364979d2`: release-hardening 45503171785, Pyright 45503171803 (1618 files, 0 errors/warnings), MCP conformance 45503171813, memory-cloud 45503171867, Stable test contracts 45503171851 all success. Persistent-runtime and monitor acceptance skipped in release-hardening, not PASS. Two subsequent commits changed only metadata and JSS catalog; base HEAD `d602091e7e262e912cc32943919ca360a16db0bd`.
- External `host-preflight --input` defaults to remote_only; JSON cannot select the mode. Explicit CLI `--ingress-mode operator_recovery` allows attachment probes. Remote-only skips attachment parsing entirely, including local paths provided by untrusted JSON. Existing no-input local operator diagnostic retained for PC/Studio/package recovery; it is not an ordinary ChatGPT entrypoint. No runtime startup or lifecycle changes.
- Original CLI regression snapshotted as identical Git blob. Existing operator tests explicitly select recovery; new negative tests cover JSON mode escalation, skipped attachment parsing and explicit remote mode; bare local diagnostic remains tested.
- IMPLEMENTED_UNVERIFIED for new SHA; no local compileall/pytest/pyright execution in this turn; CI and live acceptance pending. Next: verify CI, migrate startup/evidence contracts and loader/plugin generators; audit remaining legacy policy references. No changes to master, private MEMORY, auth or production. usage_unknown.
