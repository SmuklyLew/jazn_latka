#Requires -Version 7
<#
Launch Jaźń with a single Python-validated profile snapshot.
Never modify global OS settings, MEMORY or the running daemon.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Profile,
    [string]$Python = "python",
    [switch]$DryRun,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$JaznArguments
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$profilePath = (Resolve-Path -LiteralPath $Profile).Path

# A single read/validate/serialize in Python, no PowerShell file reread.
$validated = @(& $Python -X utf8 (Join-Path $root "tools/jazn_config_studio.py") --root $root --check-profile $profilePath --emit-validated-env)
if ($LASTEXITCODE -ne 0 -or $validated.Count -ne 1) {
    throw "Configuration Studio rejected profile snapshot; no Jaźń launch."
}
$config = $validated[0] | ConvertFrom-Json -AsHashtable
if ($config["schema"] -cne "jazn_configuration_profile/v1" -or
    $config["values"] -isnot [System.Collections.IDictionary]) {
    throw "Invalid validated snapshot schema."
}
$allowed = @(
    "JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT", "JAZN_MEMORY_TIER_DB", "LATKA_NLP_DATA_DIR",
    "JAZN_MEMORY_REBUILD_PROJECTS", "JAZN_MEMORY_REBUILD_SETTINGS",
    "JAZN_LEXICAL_RESOURCE_CACHE", "JAZN_MEMORY_MODE", "JAZN_LLM_ROUTE",
    "JAZN_MODEL_ADAPTER", "JAZN_STARTUP_STATUS_MODE", "JAZN_SQLITE_HEALTH_MODE"
)
$entries = @($config["values"].GetEnumerator())
foreach ($entry in $entries) {
    if ($entry.Key -cnotin $allowed -or $entry.Value -isnot [string]) {
        throw "Unexpected entry in validated snapshot."
    }
}
if ($DryRun) {
    Write-Host "Validated one-read profile snapshot. No Jaźń process started."
    Write-Host ("Keys: " + (($entries | ForEach-Object { $_.Key }) -join ", "))
    return
}
$saved = @{}
foreach ($entry in $entries) {
    $saved[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
}
$saved["JAZN_ROOT"] = [Environment]::GetEnvironmentVariable("JAZN_ROOT", "Process")
Push-Location $root
try {
    [Environment]::SetEnvironmentVariable("JAZN_ROOT", $root, "Process")
    foreach ($entry in $entries) {
        [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
    }
    & $Python -X utf8 (Join-Path $root "run.py") @JaznArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Jaźń exited with code $LASTEXITCODE"
    }
}
finally {
    foreach ($key in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($key, $saved[$key], "Process")
    }
    Pop-Location
}
