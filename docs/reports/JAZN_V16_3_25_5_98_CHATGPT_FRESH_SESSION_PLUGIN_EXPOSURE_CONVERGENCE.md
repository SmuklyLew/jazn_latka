# Jaźń v16.3.25.5.98 — ChatGPT fresh-session/plugin-exposure convergence

## Cel

Aktualizacja domyka lukę pomiędzy posiadaniem/instalacją aplikacji Jaźni a
faktyczną możliwością wykonania kompletnej tury w świeżej rozmowie lub
wiadomości ChatGPT. Branch powstał bezpośrednio z aktualnego `master`, a nie
z rozbieżnego PR #305.

## Ustalenia

Project instructions obowiązują w rozmowach danego Projektu, ale nie instalują,
nie wybierają i nie autoryzują aplikacji. Bieżące powierzchnie apps/plugins mogą
wiązać wybór aplikacji z konkretną wiadomością. Dlatego remote route Jaźni nie
może dziedziczyć tool-exposure z poprzedniego promptu ani promować installed,
catalog, manifestu lub @mention do poziomu callability.

Źródła sprawdzone 2026-10-02:
- https://help.openai.com/en/articles/10169521-projects-in-chatgpt
- https://developers.openai.com/plugins/quickstart
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/reference
- https://developers.openai.com/plugins/changelog
- https://developers.openai.com/plugins/plugin-guidelines
- https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Korekty względem researchu wejściowego

- `system_candidate_found=true => system_search_attempted=true` już było
  egzekwowane maszynowo; nie dodano drugiego mechanizmu.
- `jazn_resume_visible_reply` pozostaje read-only, bo polluje/wznawia istniejący
  request. Generate/finalize pozostają stateful.
- Użytkownik wybiera/@wspomina aplikację **Jaźń Runtime**, nie techniczną nazwę
  narzędzia MCP.
- Nazwa planu (np. Plus) nie jest predykatem runtime; gate jest capability-first.

## Nowy invariant

Remote dialogue jest gotowy tylko, gdy bieżąca wiadomość ma host-observed:
`jazn_status`, `jazn_generate_visible_reply`,
`jazn_resume_visible_reply`, `jazn_finalize_reply`, oraz świeży poprawny
status/binding runtime. Status-only może potwierdzić transport, ale nie pełną turę.

## Zmienione warstwy

- jeden classifier current-message toolset;
- public Streamable HTTP i Secure MCP Tunnel wymagają pełnego toolsetu;
- host-preflight przenosi `current_message_toolset_observed` i
  `callable_tool_names`;
- status/gateway publikują oczekiwany toolset;
- bootstrap, generator, startup contract i bridge discovery publikują ten sam invariant;
- `AGENTS.chatgpt.md` rozdziela installed → selected → exposed → status → full turn;
- `CHATGPT_PROJECT_INSTRUCTIONS.txt` jest jawnie tekstem do wklejenia w Project instructions;
- plugin metadata i testy opisują current-message validation.

## Naprawiony drift

`startup_contract.json` deklarował źródło wersji `latka_jazn.version.PACKAGE_VERSION`,
ale miał stare `version=v15.1.0.3.96`. v5.98 synchronizuje pole i dodaje regresję.

## Truth boundary

SYSTEM ZIP nadal nie tworzy executora ChatGPT. Project instructions nie aktywują
pluginu. MEMORY pozostaje opcjonalnym niezależnym pakietem danych. Widoczna
odpowiedź Jaźni nadal wymaga accepted `display_exact`, poprawnej lineage i
finalizacji.
