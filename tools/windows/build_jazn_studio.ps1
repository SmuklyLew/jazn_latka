#Requires -Version 7
<#
Build a Windows Jaźń Studio one-folder EXE. Neither SYSTEM nor MEMORY data
are bundled. PyInstaller must be installed deliberately by the operator.
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Dist = "dist",
    [string]$Work = "build/jazn-studio"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $root
try {
    if (-not (Test-Path "./latka_jazn/version.py") -or -not (Test-Path "./run.py")) {
        throw "Jaźń SYSTEM source not found."
    }
    & $Python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller must be installed explicitly." }
    $options = @(
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "JaznStudio",
        "--paths", $root,
        "--distpath", $Dist, "--workpath", $Work,
        "--hidden-import", "latka_jazn.tools.jazn_studio.core",
        "--hidden-import", "latka_jazn.tools.jazn_studio.ui",
        "tools/jazn_studio.py"
    )
    & $Python -m PyInstaller @options
    if ($LASTEXITCODE -ne 0) { throw "Jaźń Studio EXE build failed." }
    $result = Join-Path $root "$Dist/JaznStudio/JaznStudio.exe"
    if (-not (Test-Path -LiteralPath $result)) {
        throw "Jaźń Studio EXE not found after build."
    }
    Write-Host "Windows EXE: $result"
    Write-Host "SYSTEM is external: set JAZN_ROOT to a verified checkout."
    Write-Host "If Python is not found beside SYSTEM, set JAZN_STUDIO_PYTHON to a verified interpreter."
}
finally { Pop-Location }
