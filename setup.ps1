# Jaźń operator setup. All package mutations are delegated to Dependency Studio.
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("doctor", "wizard", "install", "repair", "verify", "venv", "preflight", "online")]
    [string]$Mode = "doctor",
    [string[]]$Profile = @(),
    [string]$Bundle = "",
    [switch]$Online,
    [ValidateSet("project", "managed")]
    [string]$Layout = "project",
    [switch]$Yes,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Entry = Join-Path $Root "tools\jazn_setup.py"

if (-not (Test-Path -LiteralPath $Entry -PathType Leaf)) {
    throw "Nie znaleziono instalatora: $Entry"
}

$ArgsList = @("-X", "utf8", $Entry, $Mode)
foreach ($name in $Profile) {
    if (-not [string]::IsNullOrWhiteSpace($name)) {
        $ArgsList += @("--profile", $name)
    }
}
if (-not [string]::IsNullOrWhiteSpace($Bundle)) { $ArgsList += @("--bundle", $Bundle) }
if ($Online) { $ArgsList += "--online" }
$ArgsList += @("--layout", $Layout)
if ($Yes) { $ArgsList += "--yes" }
if ($Json) { $ArgsList += "--json" }

Push-Location $Root
try {
    $env:PYTHONUTF8 = "1"
    & $Python @ArgsList
    $Code = $LASTEXITCODE
    if ($null -eq $Code) { $Code = 1 }
}
finally {
    Pop-Location
}
exit $Code
