@echo off
setlocal EnableExtensions
set "JAZN_ROOT=%~dp0"

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 -X utf8 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 3)" >nul 2>nul
    if not errorlevel 1 (
        py.exe -3 -X utf8 "%JAZN_ROOT%run.py" %*
        exit /b %errorlevel%
    )
)

for %%P in (python.exe python3.exe) do (
    where %%P >nul 2>nul
    if not errorlevel 1 (
        %%P -X utf8 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 3)" >nul 2>nul
        if not errorlevel 1 (
            %%P -X utf8 "%JAZN_ROOT%run.py" %*
            exit /b %errorlevel%
        )
    )
)

echo [JAZN] Nie znaleziono dzialajacego Pythona 3.12 lub nowszego. 1>&2
echo [JAZN] Zainstaluj Pythona globalnie; srodowisko .venv nie jest wymagane. 1>&2
exit /b 9009
