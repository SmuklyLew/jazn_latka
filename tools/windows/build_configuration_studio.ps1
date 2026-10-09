#Requires -Version 7
<#
Build a Windows-only, one-folder operator EXE. No SYSTEM/MEMORY data is
embedded or copied. PyInstaller must be installed explicitly by the operator.
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Dist = "dist",
    [string]$Work = "build/configuration-studio"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $root
try {
    if (-not (Test-Path "./latka_jazn/version.py")) {
        throw "Verified Jaźń source not found."
    }
    & $Python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller must be installed first." }
    $options = @(
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "JaznConfigurationStudio",
        "--paths", $root,
        "--distpath", $Dist, "--workpath", $Work,
        "--hidden-import", "latka_jazn.tools.configuration_studio_ui",
        "tools/jazn_config_studio.py"
    )
    & $Python -m PyInstaller @options
    if ($LASTEXITCODE -ne 0) { throw "Configuration Studio EXE build failed." }
    $result = Join-Path $root "$Dist/JaznConfigurationStudio/JaznConfigurationStudio.exe"
    if (-not (Test-Path -LiteralPath $result)) { throw "Build reported success but EXE is absent." }
    Write-Host "Windows EXE built: $result"
    Write-Host "Runtime SYSTEM is external; set JAZN_ROOT when launching the program."
}
finally { Pop-Location }
