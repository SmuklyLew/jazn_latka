# JSS — system projektowy UI/UX (trzy style)

Status: implementacja bazowej warstwy profili na gałęzi rozwojowej. Nie jest to certyfikat działania realnego runtime ani odbiór wizualny Windows. Zakres ekranów i brakujące czynności operatorskie wyszczególnia [JSS_SCREEN_CONTRACTS.md](JSS_SCREEN_CONTRACTS.md).

## 1. Cel i inspiracje

JSS / „Jaźń — Serce Systemu” pozostaje **jednym** interfejsem operatorskim. Nie jest nowym runtime ani klonem IDE. Punktem wejścia jest `run_studio.py`, istniejące `Controller`, `main.py` i `run.py` nie zmieniają właściciela operacji.

Sześć zrzutów operatora określa kierunek:
1. VS Code — kategorie ustawień, wyszukiwanie, bezpieczeństwo, zachowanie podziału User/Workspace.
2. XAMPP Services — czytelna tabela usług i celowane sterowanie procesami; **bez** niebezpiecznego Start All/Stop All.
3. VS Code Debug Console/Output — zdarzenia, błędy, filtry i techniczne logi.
4. VS Code strona startowa — identyfikacja JSS, statusy i najczęstsze czynności.
5. VS Code Testing — katalog testów, TPA, wyniki i historia.
6. VS Code Remote Explorer — lokalne połączenia i odrębne warunki zdalnego MCP/Cloudflare.

## 2. Jeden szkielet, wymienne profile

```text
┌────────────────────────── JSS / menu / polecenia / wybór stylu ─────────────────────────────┐
│ AKTYWNOŚĆ │ EKSPLORATOR │ OTWARTE ZAKŁADKI                  │ MONITOR / kontekst (dock) │
│           │            ├───────────────────────────────────┤                           │
│  Pulpit   │ Sekcje     │ Aktualna strona: formularze,      │ Dowody, zadania, procesy  │
│  Usługi   │ Drzewo     │ tabele, testy, połączenia         │ i jawne stany             │
│  Testy    │ Filtrowanie│                                   │                           │
│  Pamięć   │            ├───────────────────────────────────┴───────────────────────────┤
│  Ustaw.   │            │ OUTPUT / Problemy / Konsole / TPA / PTY (dock)                  │
├───────────┴────────────┴────────────────────────────────────────────────────────────────────┤
│ STATUS: SYSTEM | host | daemon | MEMORY | adapter — każda zdolność osobno                │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Aktualne JSS już dysponuje paskiem aktywności, nawigacją, zakładkami, panelem dock, katalogiem testów i ekranami usług. Nowe profile nie tworzą równoległego shell ani nie usuwają legacy. Boczne i dolne obszary można ukrywać i zmieniać ich szerokość/wysokość. Stan układu to walidowany lokalny JSON `jazn_heart_layout/v3`, a nie zaufanie do obcego binarnego blobu Qt.

## 3. Trzy kompletne kierunki wyglądu

| Token / zastosowanie | Technical Workbench (DOMYŚLNY) | Operations Studio | Fluent Studio |
|---|---|---|---|
| Klucz ustawień | `technical-workbench` | `operations-studio` | `fluent-studio` |
| Tło | `#141A23` | `#111C21` | `#171E2B` |
| Lewy panel | `#1B2430` | `#172931` | `#1F2938` |
| Obszar treści | `#202A36` | `#1C3038` | `#253347` |
| Karta/powierzchnia | `#263342` | `#25414B` | `#2D3F55` |
| Ramki | `#465568` | `#47636B` | `#50657B` |
| Tekst | `#F5F8FC` | `#F2FAFC` | `#F6F9FC` |
| Tekst pomocniczy | `#BFCDD9` | `#BBD0D7` | `#C1CFDE` |
| Akcent | `#5BA5F5` | `#5CD4C2` | `#86B6FF` |
| Gęstość odstępów | 5 | 8 | 10 |
| Wysokość bazowej kontrolki | 24 | 30 | 34 |
| Promień narożnika | 3 | 6 | 9 |
| Podstawowy tekst (pt) | 9 | 10 | 10 |

**Technical Workbench:** minimalne odstępy, mało dekoracji, gęste tabele, treść przed ornamentem. Podstawowy tryb operatora dla diagnostyki, kodu i testów.

**Operations Studio:** więcej przestrzeni wokół kart usług, nacisk na obserwację, czytelność statusów i pojedynczych akcji. Nie zmienia polityki kontroli procesów.

**Fluent Studio:** łagodniejsze powierzchnie, większe odstępy i czytelne formularze. To wariant inspirowany zasadami Fluent, **bez** zależności od Windows-only efektów czy Mica.

Profile są zdefiniowane jako niezmienne tokeny `ThemeProfile` + `WorkbenchMetrics`, zaś bazowa paleta jest zwracana przez `workbench_colors()`. Pozwala to później ułożyć **jeden personalizowany styl** z wybranych parametrów bez pisania osobnego okna. Motywy zgodności `violet-night`, `system`, `light`, `dark`, `purple` i `custom` nadal są wspierane i nie migrują się automatycznie.

## 4. Dostępność i zachowanie

- Tekst podstawowy i pomocniczy wobec paneli: kontrast co najmniej 4.5:1.
- Widoczny fokus klawiatury: co najmniej 3:1 wobec tła. Sam kolor nie jest jedynym sygnałem statusu.
- Pasek wyboru wyglądu dostępny z klawiatury, z nazwą dla technologii asystujących.
- Zmiana stylu zapisuje istniejącym mechanizmem bez uruchamiania usług; gdy formularz ma niezapisane zmiany, operacja jest odrzucana bez kasowania danych.
- Profile stosują się do tej samej hierarchii kontrolek Qt, nie modyfikują globalnego stylu innych okien narzędzi.
- Dla małych ekranów widoki przewijają się pionowo i zachowują kluczowe przyciski; odbiór wymagany przy 860×580, 1240×840, 1920×1080 oraz zwiększonej skali DPI.
- Teksty i etykiety pozostają po polsku, techniczne nazwy kontraktów nie są tłumaczone.

## 5. Stan prawdziwy, nie atrapowy

Stany usług są wyświetlane wyłącznie na podstawie odczytów z `Controller`, `service_visual_state` i publicznych komend. PID ≠ gotowość; HTTPS ≠ uwierzytelnione MCP; pamięć technicznie dostępna ≠ potwierdzony autobiograficzny recall; odpowiedź modelu ≠ accepted finalization. Gdy brakuje danych, interfejs pokazuje „niezweryfikowano”, nie zielony wskaźnik. Zmiany nie dotykają `memory/` ani `workspace_runtime/` w Git.

## 6. Referencje weryfikacyjne

- VS Code: [User Interface](https://code.visualstudio.com/docs/editing/getting-started/userinterface), [Custom Layout](https://code.visualstudio.com/docs/configure/custom-layout).
- Qt for Python: [QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html), [QDockWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QDockWidget.html).
- W3C: [WCAG 2.2](https://www.w3.org/TR/WCAG22/) — kontrast, fokus, sterowanie z klawiatury.
- Wewnętrzne kontrakty: `docs/tools/JAZN_HEART_SYSTEM.md`, `docs/project/REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`, `tools/jazn_run_studio/STUDIO_MIGRATION.md`.

## 7. Kryteria odbioru i rollback

Testy jednostkowe w `tests/test_jss_uiux_profiles.py` chronią rejestr, stare ustawienia, kontrast i walidację. Testy Qt w `tests/test_jss_uiux_profiles_qt.py` chronią selektor, zapis, niezapisany formularz, nawigację i brak zadań runtime po zmianie stylu. Uzupełnieniem muszą być realne testy manualne na Windows i CI; samo przejście testów syntetycznych nie poświadcza działania usługi ani kompletnego odbioru UX.

Rollback: wybrać poprzedni motyw z listy; kod zmian jest izolowany do warstwy JSS i można go wycofać bez migracji MEMORY i zmian lifecycle.
