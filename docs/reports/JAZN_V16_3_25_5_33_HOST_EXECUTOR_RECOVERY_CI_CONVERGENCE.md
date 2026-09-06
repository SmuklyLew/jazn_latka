# Jaźń v16.3.25.5.33 — host executor recovery CI convergence

## Cel

v16.3.25.5.33 domyka walidację v16.3.25.5.32 `chatgpt-host-executor-recovery` po tym, jak PR #226 został scalony do `master` zanim zakończył się pełny deterministic suite na Ubuntu.

Kod wykonawczy v32 pozostaje bez zmian: awaria narzędzia hosta przed utworzeniem lokalnego procesu nie jest dowodem braku `/mnt/data`, paczki ani runtime; po odzyskaniu executora host wraca do kanonicznego discovery i `run.py`.

## Ustalony fail CI

Raport JUnit z `release-hardening` wskazał dokładnie trzy błędy:

1. `tests/test_chatgpt_host_executor_truth_boundary_v16325531.py` wymagał dosłownej, starszej frazy loadera v31;
2. ten sam test przypinał `PACKAGE_VERSION == 16.3.25.5.31`;
3. `tests/test_github_actions_node24_convergence_v16325530.py` przypinał globalny `PACKAGE_VERSION_FULL` do wydania v30.

Nie były to regresje lifecycle ani nowego kontraktu executora. W tym samym runie przechodziły compileall, Pyright, semantic route audit, cognitive architecture audit i clean-checkout guard. Persistent-runtime E2E przeszedł na Ubuntu i Windows, a package cleanroom przeszedł Linux/Windows dla Python 3.12/3.13/3.14.

## Naprawa

Zgodnie z `AGENTS.md`, przed zmianą istniejących zatwierdzonych testów ich poprzednie treści zostały zachowane w:

- `tests/archive/test_chatgpt_host_executor_truth_boundary_v16325531.py`;
- `tests/archive/test_github_actions_node24_convergence_v16325530.py`.

Aktywne testy nadal sprawdzają właściwe, trwałe kontrakty:

- host-executor truth boundary i powrót wyłącznie przez `run.py`;
- brak fałszywego wniosku o filesystemie/paczce;
- Node 24 action pins, brak Node 20, ESM/tooling i opcjonalność runtime JavaScript.

Usunięte zostały wyłącznie historyczne piny globalnej wersji wydania. Historia tych pinów pozostaje byte-for-byte w `tests/archive/` i nie uczestniczy w domyślnej kolekcji pytest.

## Źródła wykorzystane przez v32/v33

- OpenAI Help Center — Troubleshooting ChatGPT Error Messages: https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages
- OpenAI Status: https://status.openai.com/
- OpenAI Help Center — How can I contact support?: https://help.openai.com/en/articles/6614161-how-can-i-contact-support
- Python `subprocess`: https://docs.python.org/3/library/subprocess.html
- GitHub Docs — Building and testing Python: https://docs.github.com/en/actions/tutorials/build-and-test-code/python

## Kryterium zamknięcia

Patch można uznać za converged dopiero po zielonych checkach nowego PR, w tym pełnym deterministic suite, release-hardening, persistent-runtime E2E, PowerShell regressions, Node 24 contract, dependency review i package-distribution cleanroom. Sam merge wcześniejszego PR #226 nie jest dowodem przejścia tych kryteriów.
