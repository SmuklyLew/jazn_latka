# Jaźń 16.3.25.5.115.3 — ChatGPT loader permission boundary

## Cel

Doprecyzować, że Project loader jest mechanizmem least-privilege do discovery, ustanowienia trasy i minimalnego bootstrapu, a nie ogólnym administratorem hosta.

## Granice

Loader może samodzielnie wykonywać wyłącznie read-only discovery/status, bounded executor probe, weryfikację wskazanych paczek, tymczasowy staging oraz kanoniczne operacje bootstrap/start/status/chat-gpt.

Tool availability nie jest zgodą na zapis. Loader nie może sam rozszerzać permissions/auth ani bez osobnej podstawy wykonywać skutków zewnętrznych, zmian konta/Projektu, instalacji pluginów, płatnego API, repo mutation, force-push, mutacji MEMORY/SQLite, usuwania/nadpisywania danych użytkownika lub instalacji oprogramowania.

operator_recovery nie rozszerza uprawnień; zmienia wyłącznie dopuszczalną trasę serwisową. Jawne polecenie użytkownika autoryzuje konkretną operację, nie blanket consent na przyszłe tury.

## Wersja

16.3.25.5.115.3-unified-conversation-runtime-authority-hotfix
