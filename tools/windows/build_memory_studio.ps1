#Requires -Version 7
<#
Windows-only OPTIONAL PyInstaller build. Does not install dependencies and
does not package private MEMORY or account exports.
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Dist = "dist",
    [string]$Work = "build/memory-studio"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $root
try {
    if (-not (Test-Path "./latka_jazn/__init__.py")) {
        throw "Jaźń repository root unavailable."
    }
    & $Python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller is not installed." }
    $argsList = @("--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "JaznMemoryStudio", "--paths", $root,
        "--distpath", $Dist, "--workpath", $Work,
        "--collect-submodules", "latka_jazn.tools.memory_rebuild_app",
        "tools/jazn_memory_studio.py")
    & $Python -m PyInstaller @argsList
    if ($LASTEXITCODE -ne 0) { throw "Build failed: do not distribute." }
    Write-Host "Output: $root/$Dist/JaznMemoryStudio/JaznMemoryStudio.exe"
    Write-Host "Set JAZN_ROOT to verified Jaźń source root. Native smoke tests required."
}
finally { Pop-Location }
