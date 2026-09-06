# Jaźń v16.3.25.5.32 — ChatGPT host executor recovery

## Cel

Ta aktualizacja domyka różnicę między awarią hosta ChatGPT występującą **przed utworzeniem lokalnego procesu** a błędem komendy, która rzeczywiście wystartowała. Poprzednia wersja v16.3.25.5.31 ustaliła granicę prawdy w runbooku; v16.3.25.5.32 przenosi tę semantykę do testowalnego kontraktu kodowego oraz ograniczonej procedury recovery.

Kod Jaźni nie może naprawić executora platformy, jeżeli executor nie utworzył żadnego procesu Jaźni. Może natomiast poprawnie sklasyfikować obserwację hosta, nie fabrykować stanu `/mnt/data`/paczki/runtime, ograniczyć próby rozróżniające i po odzyskaniu wykonania wrócić do jedynego kanonicznego lifecycle `run.py`.

## Źródła zewnętrzne

1. OpenAI Help Center — Troubleshooting ChatGPT Error Messages: https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages
   - OpenAI wskazuje, że błędy ChatGPT mogą wynikać z przejściowych problemów serwera, sieci, VPN/proxy, secure DNS, rozszerzeń albo stanu klienta.
   - Przy utrzymującym się problemie zalecane są m.in. nowa/prywatna sesja, inna przeglądarka/sieć/urządzenie oraz zebranie danych diagnostycznych.

2. OpenAI Status: https://status.openai.com/
   - Status platformy jest zewnętrznym źródłem obserwacji; nie jest dowodem stanu lokalnej Jaźni.

3. OpenAI Help Center — How can I contact support?: https://help.openai.com/en/articles/6614161-how-can-i-contact-support
   - Przy reprodukowalnych problemach Support może wymagać timestampów, informacji o środowisku, błędów konsoli i HAR.
   - HAR może zawierać dane wrażliwe; aktualizacja jawnie zabrania commitowania HAR, cookies, nagłówków autoryzacji, tokenów i prywatnej pamięci do repozytorium Jaźni.

4. Python documentation — `subprocess`: https://docs.python.org/3/library/subprocess.html
   - `subprocess.run()`/`Popen` rozróżniają utworzenie procesu od wyniku procesu, `CalledProcessError` opisuje zakończoną komendę z niezerowym kodem, a `TimeoutExpired` dotyczy procesu/komunikacji po uruchomieniu. To wspiera granicę: błąd narzędzia hosta przed utworzeniem procesu nie może być traktowany jak `returncode` lokalnej komendy.

5. GitHub Docs — Building and testing Python: https://docs.github.com/en/actions/tutorials/build-and-test-code/python
   - GitHub rekomenduje jawny `setup-python` i macierze runnerów/wersji dla deterministycznej walidacji cross-platform. Repozytorium utrzymuje własne obowiązkowe workflowy obejmujące Linux/Windows i właściwe wersje Pythona.

## Implementacja

### `latka_jazn/core/chatgpt_host_executor_contract.py`

Nowy kontrakt zawiera:

- `HostExecutorState`: `unknown`, `available`, `host_executor_unavailable`;
- `HostCommandState`: `not_started`, `started_unfinished`, `succeeded`, `failed`;
- `HostFilesystemState`: `unknown`, `observed`;
- `HostRecoveryAction`: pojedyncza alternatywna próba, stop bootstrapu, diagnoza lokalnej komendy albo powrót do kanonicznego discovery;
- `HostExecutorObservation` z walidacją niemożliwych kombinacji stanu;
- `classify_host_executor_observation()` jako czystą, deterministyczną klasyfikację bez I/O i bez ukrytych retry;
- `MAX_ALTERNATIVE_EXECUTOR_PROBES = 1`.

Najważniejsza reguła:

```text
process_created = false
    -> executor_state = host_executor_unavailable
    -> command_state = not_started
    -> filesystem_state = unknown
    -> package_state = unknown
    -> runtime_state = unverified
```

Jeżeli alternatywna lokalna powierzchnia istnieje i nie została jeszcze użyta, dozwolona jest dokładnie jedna próba rozróżniająca. Po jej wykorzystaniu lokalny bootstrap kończy się fail-closed.

Jeżeli `process_created = true`, executor jest osiągalny. Niezerowy `returncode` jest wtedy błędem lokalnej komendy, a nie awarią executora hosta.

Po sukcesie preflight kontrakt nie ogłasza aktywnego runtime. Zwraca jedynie `resume_canonical_discovery` i `canonical_resume_entrypoint = run.py`. Dopiero standardowy discovery/bootstrap/lifecycle może potwierdzić paczkę, `active_root`, daemon i zweryfikowaną turę.

### `latka_jazn/core/chatgpt_host_recovery.py`

Moduł recovery eksportuje `plan_host_executor_recovery()`, delegujące klasyfikację do nowego kontraktu. Istniejąca procedura odzyskiwania pending host request pozostaje bez zmian semantycznych i nadal jest read-only/fail-closed.

### `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`

Loader został uzupełniony o:

- procesową granicę prawdy;
- zakaz zapętlania retry/backoffu w hoście;
- pojedynczą alternatywną próbę rozróżniającą;
- jawny powrót do `run.py` po odzyskaniu executora;
- zewnętrzne kroki diagnostyczne zgodne z OpenAI;
- zakaz zapisywania materiałów supportowych i sekretów do repozytorium/pamięci Jaźni.

## Granice odpowiedzialności

Ta aktualizacja **nie** twierdzi, że kod repozytorium może usunąć `ClientError` generowany przez platformę przed startem procesu. Taki błąd pozostaje poza lokalną granicą wykonawczą Jaźni. Kod zapewnia natomiast prawidłową klasyfikację, ograniczone recovery i bezpieczny powrót do runtime po odzyskaniu capability.

Aktualizacja nie dodaje nowej zależności, nie uruchamia sieci z runtime, nie dodaje własnego `Popen`, nie omija `run.py`, nie modyfikuje prywatnej pamięci ani `workspace_runtime`.

## Testy regresyjne

Nowy `tests/test_chatgpt_host_executor_recovery_v16325532.py` sprawdza:

- `ClientError` przed procesem pozostawia filesystem/paczkę jako `unknown` i runtime jako `unverified`;
- dokładnie jedną alternatywną próbę;
- fail-closed po wyczerpaniu budżetu;
- niezerowy kod lokalnego procesu nie jest klasyfikowany jako awaria executora;
- poprawny preflight prowadzi wyłącznie do `run.py` discovery, a nie do fałszywego `runtime_active`;
- niemożliwe kombinacje obserwacji są odrzucane;
- integracja przez `chatgpt_host_recovery` zachowuje ten sam kontrakt;
- projektowy loader pozostaje krótki i zawiera granice prywatności/supportu.

## Kryteria release candidate

Branch jest kandydatem dopiero po:

1. synchronizacji kanonicznych `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` przez `release_metadata_sync`/`manifest_sync`;
2. przejściu testów Pythona i compileall;
3. przejściu persistent-runtime E2E;
4. przejściu release-hardening i package-smoke;
5. przejściu wymaganych Windows/Linux checks;
6. potwierdzeniu, że manifest sync jest idempotentny i nie pozostawia niezsynchronizowanej gałęzi.
