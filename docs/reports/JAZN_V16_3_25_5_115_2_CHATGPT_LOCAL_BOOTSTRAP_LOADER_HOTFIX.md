# Jaźń 16.3.25.5.115.2 — ChatGPT local-bootstrap loader hotfix

## Problem

W ordinary ChatGPT brak bieżącego pełnego toolsetu Jaźni mógł zostać potraktowany jako praktyczny koniec diagnozy, mimo że host posiadał działającą lokalną powierzchnię wykonawczą i dostarczony SYSTEM ZIP. Kontrakt mówił o bounded local fallbacku, ale loader nie wymuszał wystarczająco jawnie realnej próby utworzenia procesu przed raportem no-route.

## Zmiana

- Project loader wymaga rzeczywistego bounded local executor probe przed terminalną diagnozą braku trasy.
- Sam brak pluginu/aplikacji, katalogowe discovery albo historyczny pre-spawn failure nie są dowodem bieżącego braku executora.
- Udane utworzenie procesu wymusza przejście do SYSTEM discovery/bootstrapu.
- Załączniki i mounted uploads muszą zostać sprawdzone przed żądaniem ponownego uploadu.
- Jawne polecenie przygotowania/rozpakowania archiwów jest wykonywane przed zwykłą odpowiedzią hosta, z zachowaniem granicy SYSTEM/MEMORY.
- Po zweryfikowanym active_root host używa warm/resume path zamiast ponownego rozpakowywania SYSTEM-u przy każdej turze.
- Startup contract otrzymał jawne pola regresyjne dla tego gate'u.

## Granica prawdy

Zmiana nie tworzy executora i nie promuje samego ZIP-a do aktywnego runtime. Local route istnieje dopiero po rzeczywistym utworzeniu procesu i dalszej weryfikacji SYSTEM-u. Remote runtime nadal ma pierwszeństwo, jeśli pełny bieżący toolset i świeży status potwierdzają conversation-ready.

## Wersja

`16.3.25.5.115.2-unified-conversation-runtime-authority-hotfix`
