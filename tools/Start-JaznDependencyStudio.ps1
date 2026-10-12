param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("audit", "download", "verify", "install", "update", "benchmark")]
    [string]$Command,

    [string[]]$Profile = @(),
    [string]$Python = "",
    [ValidateSet("current", "windows-x64", "windows-arm64")]
    [string]$Platform = "current",
    [string]$PythonExecutable = "",
    [string]$WheelhouseRoot = "",
    [string]$EnvironmentRoot = "",
    [string]$Bundle = "",
    [switch]$Offline,
    [switch]$DryRun,
    [switch]$Json,
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    $PythonExecutable = $PythonCommand.Source
}

$argsList = @(
    "-X", "utf8",
    "-m", "latka_jazn.tools.dependency_studio",
    "--root", $Root,
    "--timeout-seconds", $TimeoutSeconds
)

if ($Json) { $argsList += "--json" }
if (-not [string]::IsNullOrWhiteSpace($WheelhouseRoot)) {
    $argsList += @("--wheelhouse-root", [System.IO.Path]::GetFullPath($WheelhouseRoot))
}
$argsList += $Command

if ($Profile.Count -gt 0) {
    $argsList += @("--profile", ($Profile -join ","))
}
if (-not [string]::IsNullOrWhiteSpace($Python)) {
    $argsList += @("--python-version", $Python)
}
if ($Command -in @("download", "update")) {
    $argsList += @("--platform", $Platform)
    if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $argsList += @("--python-executable", $PythonExecutable)
    }
}
if ($Command -eq "verify") {
    if (-not [string]::IsNullOrWhiteSpace($Platform) -and $Platform -ne "current") {
        $argsList += @("--platform", $Platform)
    }
    if (-not [string]::IsNullOrWhiteSpace($Bundle)) {
        $argsList += @("--bundle", [System.IO.Path]::GetFullPath($Bundle))
    }
}
if ($Command -eq "install") {
    if ($Offline) { $argsList += "--offline" }
    if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $argsList += @("--python-executable", $PythonExecutable)
    }
    if (-not [string]::IsNullOrWhiteSpace($EnvironmentRoot)) {
        $argsList += @("--environment-root", [System.IO.Path]::GetFullPath($EnvironmentRoot))
    }
    if (-not [string]::IsNullOrWhiteSpace($Bundle)) {
        $argsList += @("--bundle", [System.IO.Path]::GetFullPath($Bundle))
    }
}
if ($DryRun -and $Command -in @("download", "update", "install")) {
    $argsList += "--dry-run"
}

$env:PYTHONUTF8 = "1"
& $PythonExecutable @argsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
