# Jaźń 16.3.25.5.115.4 — ChatGPT explicit-consent authority boundary

## Cel

Usunąć niejednoznaczność, czy sam kontrakt runtime może zastąpić zgodę użytkownika przy skutkach zewnętrznych.

## Zasada

Thin loader nie wykonuje skutków zewnętrznych bez jawnego polecenia użytkownika. Zweryfikowany runtime może żądać capability wyłącznie w granicach dostępnych uprawnień i nie zastępuje zgody wymaganej przez hosta/platformę. Bootstrap pozostaje ograniczony do kanonicznego stagingu/runtime workspace.

## Wersja

16.3.25.5.115.4-unified-conversation-runtime-authority-hotfix
