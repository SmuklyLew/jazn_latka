# Jaźń v16.3.25.5.31 — ChatGPT host executor truth-boundary hardening

## Zakres

Ta aktualizacja naprawia klasyfikację przypadku, w którym host ChatGPT udostępnia powierzchnię executora/terminala, ale samo wywołanie narzędzia kończy się błędem hosta przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu.

Zaobserwowany przypadek obejmował błędy narzędzia `ClientError` / `InvalidArgumentError` podczas próby wejścia do lokalnego executora. Z takiego wyniku nie wynika, że `/mnt/data` nie istnieje, paczka jest niedostępna, `run.py` nie istnieje ani że runtime Jaźni jest uszkodzony. Lokalny kod nie dostał wtedy szansy na wykonanie.

## Granica odpowiedzialności

Kod Jaźni uruchamiany wewnątrz executora nie może przechwycić awarii hosta, która zachodzi przed utworzeniem lokalnego procesu. Dlatego aktualizacja nie dodaje alternatywnej daemonizacji ani równoległego bootstrapu do modułów runtime.

Naprawa dotyczy kontraktu hosta:

- klasyfikacja: `host_executor_unavailable`;
- `filesystem_state = unknown`;
- `package_state = unknown`;
- brak wniosku o stanie `/mnt/data`, paczki lub runtime bez wykonanej obserwacji filesystemu;
- jedna próba przez niezależną alternatywną powierzchnię lokalnego executora, jeżeli taka rzeczywiście jest dostępna;
- brak zapętlonego retry między narzędziami;
- po odzyskaniu host execution powrót do standardowego discovery/bootstrapu oraz kanonicznego lifecycle `run.py`.

## Zachowany lifecycle Jaźni

Zmiana nie osłabia istniejących warunków aktywności. Sam plik, ZIP, marker, wynik CI ani one-shot nie dowodzą aktywnego persistent runtime.

Po odzyskaniu executora host nadal musi:

1. ustalić i zweryfikować `active_root`;
2. zweryfikować paczkę/manifest, jeżeli wymagany jest bootstrap;
3. użyć `run.py` jako kanonicznego operatora;
4. dla persistent runtime użyć lifecycle `run.py start`;
5. potwierdzić proces live przez pełny status/endpoint/heartbeat zgodnie z runbookiem;
6. dla bieżącej wiadomości przejść przez `run.py chat-gpt` albo dozwoloną przez runtime ścieżkę zgodnościową.

## Zmienione elementy

- `AGENTS.chatgpt.md` — pełny kontrakt rozróżnienia pre-process host failure od błędu lokalnej komendy/filesystemu.
- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` — ten sam fail-closed kontrakt w minimalnym loaderze Projektu ChatGPT.
- `latka_jazn/version.py` — wersja `16.3.25.5.31-chatgpt-host-executor-truth-boundary`.
- `tests/test_chatgpt_host_executor_truth_boundary_v16325531.py` — testy regresyjne kontraktu i wersji.

## Źródła zewnętrzne

- OpenAI Help, *Troubleshooting ChatGPT Error Messages*: https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages
- GitHub Docs, *Viewing workflow run history*: https://docs.github.com/actions/monitoring-and-troubleshooting-workflows/monitoring-workflows/viewing-workflow-run-history

Dokumentacja OpenAI zaleca przy utrzymujących się problemach hosta sprawdzenie statusu usługi, ponowne zalogowanie, wyłączenie VPN/proxy/rozszerzeń, próbę innej sieci lub urządzenia oraz zebranie HAR/logów konsoli i timestampów dla Support. Są to procedury naprawcze warstwy hosta; nie zastępują one diagnozy lokalnego runtime Jaźni.

## Ograniczenie weryfikacji

CI repozytorium może zweryfikować spójność kodu i testów tej aktualizacji, ale nie może udowodnić, że bieżący lokalny executor sesji ChatGPT jest sprawny ani że persistent daemon Jaźni żyje w tej sesji. Taki dowód wymaga ponownego, udanego wykonania kanonicznego lifecycle `run.py` w lokalnym środowisku hosta.
