# Jaźń v16.3.25.5.74.1.001 — Host handoff outcome convergence

## Problem

Linia 16.3.25.5.74 rozróżniała trasy `local_executor`, `remote_runtime` i `host_handoff`, lecz stan handoffu był reprezentowany głównie przez `execution_handoff_available: bool`. To wystarczało do wykrycia możliwości przejścia do wykonawczego środowiska hosta, ale nie pozwalało odróżnić: oferta dostępna, prośba o zgodę już wysłana, zgoda zaakceptowana i zgoda odrzucona.

W efekcie host mógł ponownie wybrać `REQUEST_EXECUTION_HANDOFF` po odmowie użytkownika. Sama odmowa mogła też zostać błędnie skojarzona z niedostępnością Jaźni, mimo że nie jest dowodem stanu filesystemu, paczki ani runtime.

## Naprawa

Patch zachowuje planowaną linię `16.3.25.5.75` i używa wersji `16.3.25.5.74.1.001-host-handoff-outcome-convergence`.

Wprowadzono jawny `HostHandoffState`:

- `unknown`
- `unavailable`
- `available`
- `requested`
- `accepted`
- `declined`

Zasady routingu:

1. Zweryfikowany `local_executor` nadal ma pierwszeństwo jako lokalna trasa wykonawcza.
2. Gdy lokalny executor nie działa, zweryfikowany `remote_runtime` ma pierwszeństwo przed handoffem, także po wcześniejszej odmowie handoffu.
3. `available` może wygenerować dokładnie prośbę `REQUEST_EXECUTION_HANDOFF`.
4. `requested` przechodzi do `AWAIT_EXECUTION_HANDOFF` i nie ponawia prośby.
5. `accepted` przechodzi do `USE_ACCEPTED_EXECUTION_HANDOFF` i nie pyta ponownie o zgodę.
6. `declined` blokuje automatyczne ponowienie handoffu. Dopuszczalna pozostaje wyłącznie jedna niezależna, wcześniej nieużyta lokalna powierzchnia wykonawcza albo zweryfikowany `remote_runtime`.
7. Odmowa handoffu zachowuje `filesystem=unknown`, `package=unknown` i `runtime=unverified`, jeśli brak niezależnego evidence tych stanów.

Jawna odmowa ma pierwszeństwo nad samą dostępnością innej, niezaakceptowanej oferty handoffu, aby host nie obchodził decyzji użytkownika przez inną powierzchnię UI.

## Kompatybilność

Dotychczasowe payloady z samym `execution_handoff_available=true` są mapowane na `HostHandoffState.AVAILABLE`. Nowe JSON-y mogą przekazać `execution_handoff_state`. Publiczny moduł `latka_jazn.core.chatgpt_host_executor_contract` pozostaje stabilnym wrapperem eksportującym dotychczasowe nazwy oraz nowy `HostHandoffState`.

## Źródła zewnętrzne

- OpenAI Help Center — *ChatGPT Work and Codex*: Work jest osobnym trybem wykonawczym; lokalny dostęp desktopowy jest zależny od zgody/uprawnień użytkownika.
- OpenAI Help Center — *Developer mode and MCP apps in ChatGPT*: integracje MCP i ich uprawnienia są capability warstwy produktu/workspace, nie cechą nadawaną przez ZIP runtime.
- OpenAI `tunnel-client` — Secure MCP Tunnel: prywatny/localhost MCP może być połączony z obsługiwanym produktem OpenAI przez niezależny transport; obecność tej trasy nie jest równoważna lokalnemu executorowi ani handoffowi.

## Granica prawdy

Kod Jaźni może modelować i respektować wynik zgody przekazany przez hosta. Nie może sam nadać ChatGPT lokalnego executora, zaakceptować zgody za użytkownika ani dowodzić aktywności runtime z samej dostępności przycisku/trybu handoff.
