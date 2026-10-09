#Requires -Version 7
<#
Read a validated, allowlisted profile and run Jaźń with process-scoped
environment variables. Does not change machine/user environment or active daemon.
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

& $Python -X utf8 (Join-Path $root "tools/jazn_config_studio.py") --root $root --check-profile $profilePath
if ($LASTEXITCODE -ne 0) {
    throw "Configuration Studio rejected profile; no Jaźń launch."
}
$config = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.schema -ne "jazn_configuration_profile/v1") {
    throw "Unsupported configuration schema."
}
$allowed = @(
    "JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT", "LATKA_NLP_DATA_DIR",
    "JAZN_MEMORY_REBUILD_PROJECTS", "JAZN_MEMORY_REBUILD_SETTINGS",
    "JAZN_LEXICAL_RESOURCE_CACHE", "JAZN_MEMORY_MODE", "JAZN_LLM_ROUTE",
    "JAZN_MODEL_ADAPTER", "JAZN_STARTUP_STATUS_MODE", "JAZN_SQLITE_HEALTH_MODE"
)
$entries = @($config.values.PSObject.Properties)
foreach ($entry in $entries) {
    if ($entry.Name -cnotin $allowed -or $entry.Value -isnot [string]) {
        throw "Unsupported configuration key or value: $($entry.Name)"
    }
}
if ($DryRun) {
    Write-Host "Valid profile. No process was started and no variables were changed."
    Write-Host ("Keys: " + (($entries | ForEach-Object { $_.Name }) -join ", "))
    return
}
$saved = @{}
foreach ($entry in $entries) {
    $saved[$entry.Name] = [Environment]::GetEnvironmentVariable($entry.Name, "Process")
}
$saved["JAZN_ROOT"] = [Environment]::GetEnvironmentVariable("JAZN_ROOT", "Process")
Push-Location $root
try {
    [Environment]::SetEnvironmentVariable("JAZN_ROOT", $root, "Process")
    foreach ($entry in $entries) {
        [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, "Process")
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
