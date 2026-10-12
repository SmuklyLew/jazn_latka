param(
    [ValidateSet("core", "recommended")]
    [string]$Profile = "core",
    [string]$DataDir = "",
    [string]$Python = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "bootstrap_polish_reasoning_resources.py"
if (-not (Test-Path -LiteralPath $Script)) {
    throw "Missing installer: $Script"
}

if ([string]::IsNullOrWhiteSpace($DataDir)) {
    $DataDir = Join-Path $Root "latka_jazn\local_resources\nlp"
}
$DataDir = [System.IO.Path]::GetFullPath($DataDir)

if ([string]::IsNullOrWhiteSpace($Python)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    $Python = $PythonCommand.Source
}

$argsList = @($Script, "--profile", $Profile, "--data-dir", $DataDir)
if ($DryRun) { $argsList += "--dry-run" }

$env:LATKA_NLP_DATA_DIR = $DataDir
Write-Host "Python=$Python"
Write-Host "LATKA_NLP_DATA_DIR=$DataDir"
& $Python -X utf8 @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Polish reasoning resource bootstrap failed with exit code $LASTEXITCODE"
}

if ($DryRun) {
    Write-Host "Dry run completed. No packages or models were installed."
} else {
    Write-Host "Resources installed and verified in: $DataDir"
}
