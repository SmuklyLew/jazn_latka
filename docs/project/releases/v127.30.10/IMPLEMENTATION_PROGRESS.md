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

## J-012 — etap migracji 3: startup/evidence contracts

- Base `013b8c2fd34b6bf25cc6997e07db70b37f0bca66` includes metadata/catalog synchronization after CLI patch. The last observed CLI CI had Stable test contracts and Pyright success, other gates in progress; do not infer full PASS.
- Startup ordinary policy is remote_only with no local probe budget, fallback, discovery/materialization, daemon start or handoff; no ready route gives host_diagnostic. Existing local bridge fields explicitly scoped to PC/operator recovery, with separate operator budgets, integrity and write scope. No new transport or lifecycle implementation. Startup evidence separates remote readiness sequence from explicit recovery sequence and scopes existing file/ZIP capabilities to recovery.
- Three test snapshots preserved as original Git blobs. Updated active assertions verify both scopes, zero ordinary probe budget and retained operator integrity/finalization safeguards. Existing loader/plugin assertions deliberately unchanged until the coordinated next patch. No production/deployment config or MEMORY changes.
- Status IMPLEMENTED_UNVERIFIED; no local Python/pytest/pyright run. Verify CLI and this SHA CI; next J-012/4 loader, plugin generator, operator references and corresponding tests. Full acceptance NOT_RUN. Version remains same unreleased v127.30.10. usage_unknown.

## J-012 — etap migracji 4a: portable plugin prompt

- Base `aab254908c65c66a4b53aa4851bbbb252f6811af`. Latest observed stage 3 CI: Pyright, Stable test contracts and memory-cloud success; MCP conformance in progress, release-hardening pending. Stage 2b release-hardening still in progress at initial check. No claim of full CI PASS.
- Shared `_openai_extension` now directs ordinary ChatGPT to verified remote-only MCP for both endpoint and registered-app packages, fail-closed on unavailable/stale/unverified status, with no automatic executor/ZIP/MEMORY/bootstrap/start/handoff. Explicit separately authorized operator recovery retains canonical file identity and materialization safeguards; no new runtime or finalizer. Request lineage and accepted display_exact, MessageEnvelope and persistence remain required.
- Three original test blobs preserved in tests/archive with provenance. Active tests cover both package shapes and recovery-only file integrity guidance. Loader/runbook assertions unrelated to the plugin deliberately unchanged until coordinated stage 4b. No change to deployment/auth, plugin installation, private MEMORY or master.
- IMPLEMENTED_UNVERIFIED; no local Python/pytest/pyright execution. Next: verify CI for this SHA and prior stage, migrate AGENTS.chatgpt.md, CHATGPT_PROJECT_INSTRUCTIONS.txt, remaining references and tests in a coordinated patch. Live acceptance NOT_RUN. Version remains same unreleased v127.30.10; usage_unknown.

## J-012 — etap migracji 4b1: active runbook and project loader

- Base `dcf4ce1edc8a289e22922a3cb8e802de6ae739d1`, code SHA `21ace34e10e3c8ea23a9b4b6a32689c9b7909670` had 6/7 workflow success; release-hardening 45506779928 still running at preparation (Windows targeted success, Ubuntu full deterministic suite running).
- Active AGENTS.chatgpt.md and short project loader distinguish ordinary remote-only from explicit local recovery. Ordinary no-route gives host_diagnostic without process probe, ZIP/MEMORY discovery, materialization, daemon start or handoff. Recovery keeps bounded probes, exact file identity/integrity, canonical lifecycle and same-request finalization. Loader length 4972 characters, checked statically. No runtime, private MEMORY, production or master changes.
- Three affected regression tests updated and original blobs archived. Remaining historical/operational reference, packaging generator and cross-document convergence audit pending (4b2); live acceptance NOT_RUN. No local Python/pytest/pyright execution. Current patch must pass CI. usage_unknown.

## J-012 — etap migracji 4b2a: distribution scope and ingress references

- Code SHA `e48db044f2972dd550803ede67a49994136f33e3` completed 7/7 observed workflows success, including release-hardening 45508703766 and persistent-runtime-e2e 45508703508. Release-hardening acceptance_monitor and acceptance_persistent_runtime jobs skipped; live ChatGPT not tested. Base `542bdc3baff2e10c9862a37d2cd6046466ebe558` differs only in canonical metadata and JSS catalog.
- Package generator now exports explicit ordinary remote-only route and negative capability flags; all-mode supported_execution_routes retained for compatibility and scoped as inventory, not ordinary authorization. Local bootstrap only explicit operator recovery/local PC; package still cannot prove remote readiness. Regression assertions added without removing prior ones; original test blob archived.
- Current remote-only reference restored, historical hybrid reference explicitly marked, persistent remote architecture section corrected. No changes to deployed gateway, auth, MEMORY, lifecycle or master. Remaining audit: standalone CHATGPT_BOOTSTRAP.py contract, other active reference/index documents and tests, branch-specific legacy callers, then stage 5 gates. Status IMPLEMENTED_UNVERIFIED; no local Python tests or package build; new SHA CI pending. usage_unknown.

## J-012 — etap migracji 4b2b: standalone activation scope and operational references

- Previous code SHA `a721e0aa9cf140f6a8df840c87014122ce9911cc`: all six observed workflows success, release-hardening 45510517272 and persistent-runtime-e2e 45510517182 included. Base HEAD `439975f6321ac13f0e0cd1f729b71dc6efe17ab3`.
- Standalone stdlib bootstrap activation and local bridge contracts now explicitly scope local commands to authorized operator recovery/local PC; ordinary policy mirrors package generator flags, no execution behavior changes. Cross-contract regression appended; original test archived byte-exact. Updated operational reference, index, historical state overlay, plan pointer and optional SIWC model channel documentation. No deployment/authorization/production/MEMORY changes.
- Inspected current SHA ingress policy, generic preflight planner, route resolver and prior CLI gate: ordinary wrapper is remote-only; generic low-level planner and resolver retain operator defaults for existing local diagnostics, explicit legacy hybrid still accepted internally. Repository search candidates are not exhaustive branch-wide proof (search may index default branch); need remaining callsite audit, stale/unverified status regression and live acceptance before J-012 closure. No local execution/package build; current SHA CI pending. Next stage 5 then J-003/004/007. usage_unknown.

## Etap 04 — J-003/J-004, pierwsza implementacja; J-007 regression candidate

- Current base `1dc90d7cc1b21197a55b99bad51af716bc29b8ae`. J-012 prior code SHA `b959b58cee7059f712e4f37ab26924df07ca16b1`: 5/5 observed workflows completed success, including release-hardening 45513958434, Pyright 45513958518, stable contracts 45513958562, MCP 45513958442 and memory-cloud 45513958437. J-012 remains open for branch-wide and live acceptance evidence.
- Root cause: ConversationRunner previously reused initialization-only last_load_metadata after processing every turn. Added pre-turn provenance projection over canonical accepted history, independently of process_reused, engine lifecycle and current save. Distinguish new/in_process/verified disk checkpoint/history-only/disabled/unverified; keep initialization source separately. Credit checkpoint reuse only when verified checkpoint and prior accepted record agree on both previous user and visible text. Record prior accepted turn/trace and input checkpoint SHA separately from output checkpoint. Local worker reuse requires most recent verified record to match a locally accepted, canonically persisted turn. Legacy unverifiable checkpoints no longer claim session_reused. No changes to finalization authority, admission/routing, or checkpoint save algorithm.
- New real ConversationRunner regression and negative evidence tests; appended cross-OS-process test using the actual JaznDaemonServer job loop and real deterministic turns, isolated synthetic workspace, memory/model/network off, graceful worker close, same-request duplicate in-process, exact recall after restart, distinct daemon instances, same session and verified input SHA. Original persistent E2E test retained as identical Git blob. The process test is not the full public HTTP/CLI or hard-isolated worker acceptance. Further work: phase-2 stale worker checkpoint reconciliation, rejection/timeout, cross-restart idempotency, model switch, wake mismatch and concurrent isolation acceptance, verify all gates before marking J-003/004/007 PASS.
- Status IMPLEMENTED_UNVERIFIED for J-003/004; J-007 regression candidate NOT_RUN. Local executor exists (git and Python observed), but git ls-remote failed DNS resolution; no local checkout of this SHA, no local compileall/pytest/Pyright or pre-fix reproduction run. Existing tests not weakened; new tests require CI. Worktree status unknown, usage_unknown. Same unreleased version v127.30.10, no private MEMORY/production/master changes. References: https://docs.pytest.org/en/stable/how-to/tmp_path.html and https://docs.python.org/3/library/subprocess.html.
- Pre-publication review strengthened source binding: disk checkpoint may be credited only while the worker's original state has not been locally advanced and its positive turn count agrees with the verified accepted history. In-process credit additionally requires matching current state text. Added three parameterized regression cases for stale/checkpoint-count ambiguity; no claim that two independent hashes provide a cryptographic turn-ID binding. These tests are also NOT_RUN.

## Etap 04 — J-007: completed request tombstone / restart no-replay

- Base `c5e12f03151188f3cc76839115aeac30981efbe3`. All six GitHub workflows for code SHA `93553de649ab0284420cb210fe621122063bea94` completed success, including Pyright, stable contracts, MCP and persistent-runtime-e2e on Windows/Linux. The subsequent HEAD differs only by metadata/JSS catalog sync.
- Found concrete post-restart idempotency gap: `_persist_chat_jobs_locked_unsafe` previously dropped terminal successes, allowing a repeated completed `request_id` to become executable after daemon restart. Added metadata-only durable tombstone for completed request fingerprints; no user input or response persisted. On restart/TTL expiry, same fingerprint returns terminal `recovered_after_restart` with `completed_request_result_unavailable` (not a falsely successful final); different fingerprint is rejected `request_id_conflict`. No replay. Existing pending-finalization and terminal rejection recovery preserved.
- Expanded real two-OS-process daemon regression: check original completed request ID in second process before next turn, reject mismatched text, ensure no duplicated history; original test archived verbatim. Added synthetic repeated-restart/TTL tombstone test with explicit absence of canary prompt/answer from ledger.
- STATUS IMPLEMENTED_UNVERIFIED for this patch. No local pytest/compileall/Pyright due to host executor ClientError; CI on new SHA pending. Full HTTP/MCP live, model-switch and external finalization acceptance remain NOT_RUN. Persistent tombstones have growth/retention considerations for future bounded compaction; do not prune without durable replay-policy evidence. No changes to master, MEMORY, auth, deployment or production. usage_unknown.

## Etap 04 — J-007 CI regression correction: typed tombstone and telemetry

- Code SHA `1db2ed429a78e970f472aa0ad539fade6bee6dde`: Stable contracts SUCCESS; Pyright FAIL due to untyped mixed-value test kwargs; Persistent Runtime E2E Ubuntu FAIL because completed-request tombstone was counted as recovered *failure* in `terminal_failure_total` (1 versus expected 0). Failures reproduced from GitHub Actions logs, no test assertions weakened.
- Typed the test kwargs as `TypedDict` and preserved all duplicate/conflict/privacy assertions. On startup, a completed replay-prevention tombstone remains terminal and unavailable, but does not increment recovered_failure counters. Added explicit `completed_request_tombstones_current` observability and regression assertions, preserving existing zero-failure contract. Original test snapshot retained byte-for-byte before this update.
- Status IMPLEMENTED_UNVERIFIED for this correction: local executor ClientError, CI on new SHA pending. No real ChatGPT/MCP production, private MEMORY or master changes. J-003/J-004/J-007 remain open pending full required evidence; usage_unknown.

## Etap 04 — rozszerzenie macierzy: finalizacja, utrata transportu, zmiana kanału modelu

- Baza `ee1041686baaef864ccbdd619ea68da49e7f720e`; poprzedni kod `e65db257a916138187f44c519b8f4971299ed539` przeszedł 6/6 workflow CI (Pyright, Persistent Runtime E2E, Release Hardening, Stable Contracts, MCP, Memory-cloud). Następujące commity synchronizowały wyłącznie metadane/JSS. J-012 pozostaje open do rzeczywistego live MCP/Cloudflare.
- Rozszerzony test Persistent Runtime E2E o przerwanie phase-2 przed poprawnym ACK, odrzucenie niezgodnego host hash, restart właściciela daemona, readback tej samej pending lineage, zakaz replay i poprawne powiadomienie accepted. Brak zapisu do historii z samego ACK jest testowany oddzielnie od poprawnej finalizacji treści.
- Nowy test rzeczywistego loopback HTTP: po pełnym POST klient zamyka połączenie bez odczytu odpowiedzi, nowy klient odczytuje rezultat przez GET z tym samym request_id, ponowny POST jest idempotentny, zmiana modelu pod tym samym ID oznacza konflikt, nowy ID z innym turn-scoped channel zachowuje session_id i workera. Drugi nowy test uruchamia rzeczywisty ConversationRunner w izolacji z adapterem null i dwoma turn-scoped wyborami modelu, sprawdzając accepted history i provenance. Nie jest to dowód aktywnej zmiany Ollama/ChatGPT ani publicznego MCP.
- Wprowadzono tylko testy i checkpoint; istniejący test Persistent E2E zarchiwizowano jako identyczny Git blob, bez zmiany runtime, prywatnej MEMORY, master lub deploy. STATUS IMPLEMENTED_UNVERIFIED dla nowej macierzy: lokalnie testy nie mogły być uruchomione bez checkoutu (DNS Github), CI nowego SHA oczekuje. J-003/004/007 nadal open, live acceptance NOT_RUN, usage_unknown.

## Etap 05 — pierwsza implementacja: proof-aware LLM route

- Baza `8eb1e97186d3536c6192078cb50c026ca0903cea`. J-003/004/007 SHA `d4becec0005eab85934d3a139fad55ba341a9496`: 6/6 observed GitHub workflows success, including Pyright, persistent-runtime-e2e, Release Hardening, MCP, Memory-cloud and Stable Contracts. Current base differs only by canonical release metadata sync; live ChatGPT/MCP acceptance remains open.
- Static audit found no-probe Ollama path marked configured model as available despite no endpoint evidence; ordinary auto-route also allowed implicit paid API fallback whenever a key and allow flag existed. Host bridge marker alone claimed presence without fresh generator verification. Patch splits host declaration and verified host generation and preserves truthful null core when no generator is proven, while forced paid route still requires both explicit mode and permission. No runtime/daemon lifecycle changes, no model API requests.
- Added independent route-evidence tests: no probe, host declared but not verified, explicit verified bridge, local-only, both-priority, neither, paid API guard. Test file is new (no history replacement); original speech tests remain unchanged. Potential compatibility risk: existing CLI host callers must explicitly convey host-generation verification rather than relying on host marker alone; pending caller and integration audit. STATUS IMPLEMENTED_UNVERIFIED; no local pytest/compileall/Pyright evidence; new CI required. usage_unknown.

## Etap 05 — CI regression correction, remote-only/host distinction

- Previous code SHA `3cefaee4e398c77de6aa6954ed386f7d10c4d27f`: Stable Contracts, Pyright, MCP, memory-cloud SUCCESS; release-hardening `45545254759` FAILURE. Windows job `138973803632` failed `test_universal_chat_prefers_confirmed_chatgpt_host`, Ubuntu job `138973803696` failed this plus `test_auto_route_behavior_matches_declared_priority`. Observed directly in GitHub job logs; cannot mark prior gate PASS.
- Restored explicit host-visible bridge selection as a request for external phase-2, never as live MCP readiness. Environment marker `JAZN_CHATGPT_HOST_GENERATION_VERIFIED` is ignored as evidence and `generation_verified` stays false in this config-only resolver. Ordinary ChatGPT remote-only still checks actual toolset, live readiness, lineage and accepted finalization separately. No-probe Ollama remains unverified; paid API never silently selected in auto.
- Updated existing test assertions to verify accurate meaning (host choice, not readiness; no-probe/no-paid-auto negatives), preserving originals as byte-identical Git blob archives before edit. Updated repository layout policy to agree with remote-only while retaining CLI/JSONL only in authorized PC/recovery scope.
- STATUS IMPLEMENTED_UNVERIFIED for new SHA; CI not yet executed at commit time, live ChatGPT/MCP NOT_RUN. Stage 05 and J-008/J-012 remain OPEN. No master, production, private MEMORY, gateway or auth changes; usage_unknown.

## Etap 05 — korekta dokumentacyjna po release-hardening Ubuntu

- Commit `34c36dd32e5412f49322eccb4c7d145341c58359`: 4/5 workflows success; release-hardening run `45546901268` failed only Ubuntu deterministic suite job `138979203804` in `tests/test_repository_layout_dependency_operator.py::test_repository_policy_documents_host_and_model_boundaries`. Windows targeted success; expected exact compatibility CLI string absent from policy, with no daemon behavior failure in this run.
- Restore exact legacy operator command `python -X utf8 run.py chat-gpt --session-id <id>` in repository policy with explicit PC/operator_recovery-only scope and without reverting ordinary ChatGPT remote-only/MCP. No test weakening, runtime change, private MEMORY, or master changes. CI for new SHA pending; stage 05 and live ChatGPT/MCP remain OPEN, usage_unknown.
