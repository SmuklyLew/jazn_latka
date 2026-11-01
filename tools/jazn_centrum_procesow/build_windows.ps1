
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot ".buildvenv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    py -3.14 -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udalo sie utworzyc srodowiska Python."
    }
}

& $python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Nie udalo sie zainstalowac PyInstaller."
}

& $python -m py_compile ".\jazn_centrum_procesow.py"
if ($LASTEXITCODE -ne 0) {
    throw "Blad skladni kodu Python."
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Jazn_Centrum_Procesow" `
    ".\jazn_centrum_procesow.py"

if ($LASTEXITCODE -ne 0) {
    throw "Budowanie EXE nie powiodlo sie."
}

Write-Host "`nWynik: $PSScriptRoot\dist\Jazn_Centrum_Procesow.exe"
