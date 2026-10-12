@echo off
setlocal EnableExtensions
set "JAZN_ROOT=%~dp0"
set "JAZN_RUNTIME_SET=%JAZN_ROOT%JAZN_PYTHON_RUNTIME_SET.json"
set "JAZN_PORTABLE_LAUNCHER=%JAZN_ROOT%tools\Start-JaznPythonRuntime.ps1"

if exist "%JAZN_RUNTIME_SET%" (
    where powershell.exe >nul 2>nul
    if errorlevel 1 (
        echo [JAZN] Znaleziono JAZN_PYTHON_RUNTIME_SET.json, ale brak powershell.exe potrzebnego do bezpiecznej selekcji i materializacji prywatnego runtime. 1>&2
        exit /b 9009
    )
    if not exist "%JAZN_PORTABLE_LAUNCHER%" (
        echo [JAZN] Brak kanonicznego launchera tools\Start-JaznPythonRuntime.ps1. 1>&2
        exit /b 9009
    )
    powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%JAZN_PORTABLE_LAUNCHER%" -Root "%JAZN_ROOT%" %*
    exit /b %errorlevel%
)

rem Thin/developer fallback: only used when no private runtime-set contract is present.
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

echo [JAZN] Nie znaleziono prywatnego runtime Jaźni ani dzialajacego Pythona 3.12 lub nowszego. 1>&2
echo [JAZN] Paczka portable powinna zawierac JAZN_PYTHON_RUNTIME_SET.json i zgodny runtime ZIP; checkout developerski moze korzystac z Pythona hosta. 1>&2
exit /b 9009
