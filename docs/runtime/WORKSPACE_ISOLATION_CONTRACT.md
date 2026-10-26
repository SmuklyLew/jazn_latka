# Jaźń — izolacja SYSTEM, MEMORY, runtime i odbioru TPA (.94.6)

Kontrakt zachowuje **kanoniczny $ROOTDIR**: importowalny kod w
\`$ROOTDIR/latka_jazn\`, narzędzia w \`$ROOTDIR/tools\`, prywatna MEMORY
w \`$ROOTDIR/memory\` oraz stan uruchomionego systemu w
\`$ROOTDIR/workspace_runtime\` dla kanonicznego checkoutu
\`jazn_latka_master\`. \`run.py -> main.py\` pozostaje jedynym
sterowaniem runtime. \`docs/\` i \`tests/archive/\` pozostają dokumentacją
i historycznymi testami, nie kodem staging w workspace.

## Wybór workspace

1. Jawne \`JAZN_RUNTIME_WORKSPACE_DIR\` ma pierwszeństwo. Operator musi
   sprawdzić jego tożsamość i nie kierować worktree na działający daemon.
2. Kanoniczny \`jazn_latka_master\` bez override nadal korzysta
   z \`$ROOTDIR/workspace_runtime\`. Zmiana nie migruje jego danych.
3. Git **linked worktree** (\`.git\` jest plikiem) bez override
   domyślnie otrzymuje własny \`$ROOTDIR/workspace_runtime\`.
   Nigdy nie adopuje automatycznie PID, MEMORY, sesji ani heartbeat
   zapisanych wcześniej w wspólnym katalogu rodzeństwa.
4. Pozostałe historyczne/host-managed ROOT zachowują swoje dotychczasowe
   reguły kompatybilności. Zmiana domyślnej ścieżki nie przenosi
   istniejących plików i nie oznacza gotowości daemona.

## Izolowany odbiór operatorski

Uruchamiaj z **zweryfikowanego oddzielnego worktree**, bez aktualizowania
aktywnych plików master:

\`\`\`powershell
& 'D:\.AI\codex_tasks\jazn-run-studio-env\Scripts\python.exe' -X utf8 run_studio.py --isolated-acceptance --gui-smoke
& 'D:\.AI\codex_tasks\jazn-run-studio-env\Scripts\python.exe' -X utf8 run_studio.py --isolated-acceptance
\`\`\`

Przełącznik jawnie ustawia na czas życia procesu:

- \`JAZN_RUNTIME_WORKSPACE_DIR\` → \`~/.jazn/acceptance/<hash-root>/runtime\`
- \`JAZN_OPERATOR_STATE_ROOT\` → \`~/.jazn/acceptance/<hash-root>/operator\`
- \`JAZN_MEMORY_ROOT\` → \`<acceptance-runtime>/memory\`
- \`JAZN_MEMORY_MODE=off\`

\`<hash-root>\` zależy od kanonicznej ścieżki konkretnego checkoutu.
Ustawienia i raporty nie trafiają do repo. Stan z poprzedniej sesji
odbiorowej w tym samym katalogu jest zachowywany do celowej kontroli;
w razie potrzeby operator ręcznie używa nowego profilu/katalogu.
Wpisy ENV są przywracane po zamknięciu procesu (także po błędzie).
Resolver sprawdza symlinki/junctions i odrzuca nakładanie się z SYSTEM,
produkcyjną MEMORY, aktywnym lub historycznym workspace.

**Nie myl izolacji ścieżek z automatycznym sandboxem procesów.**
Studio nie startuje usług automatycznie. Ręczne Start/Restart/Stop,
połączenia z Ollamą, MCP i Cloudflare wymagają osobnych testów ownership,
portów, tożsamości i jawnej decyzji operatora. Sam GUI smoke albo
TPA podtest nie stanowi accepted turn ani produkcyjnej gotowości.

## TPA i wyniki testów

\`SafeTPARunner\` uruchamia trzy dozwolone podtesty pytest w jednorazowym
katalogu tymczasowym, z odizolowanym runtime/operatorem/MEMORY i z
\`JAZN_MEMORY_MODE=off\`. \`--basetemp\` wskazuje wyłącznie katalog
utworzony przez TPA — pytest może go wyczyścić. Żaden PASS podtestu
nie zatwierdza automatycznie 22 manualnych bramek. Ręczne wyniki i
dowody operatora są rozdzielone od stanu produkcyjnego.

Nie zmieniaj ani nie przenoś w ramach testu:
\`memory/\`, \`workspace_runtime/\` aktywnego master,
SQLite/WAL/SHM, markerów, PID, ustawień produkcji i sekretów.

## Walidacja

\`\`\`text
python -X utf8 -m pytest -q tests/test_jazn_workspace_layout_isolation.py tests/test_jazn_tpa_safe_executor.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 -m compileall -q -x 'tests[\\/]archive[\\/]' latka_jazn tests main.py run.py
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
\`\`\`

Nie uznawaj kontrolki CI za zaliczoną bez zakończonego workflow
dla właściwego commit SHA. Brak lokalnego Windows GUI/EXE i prawdziwego
MCP/ChatGPT E2E pozostaje odrębną bramką odbioru.

Źródła zasad implementacji:
- Git worktree: https://git-scm.com/docs/git-worktree
- Python pathlib.resolve: https://docs.python.org/3/library/pathlib.html
- pytest temp files: https://docs.pytest.org/en/stable/how-to/tmp_path.html
