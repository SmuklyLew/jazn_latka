#requires -Version 7.0
<#
.SYNOPSIS
  Read-only check of the currently running Jaźń daemon and local MCP catalog.
.DESCRIPTION
  Resolves a dedicated MCP Python from the canonical Dependency Studio
  environments each time PowerShell starts. Does not depend on $McpPython
  from a different shell and never starts, stops or publishes any service.
#>
[CmdletBinding()]
param(
    [string] $Root = (Join-Path $PSScriptRoot '..\..'),
    [string] $McpPythonPath = '',
    [ValidateRange(1,65535)][int] $Port = 18086
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $Root 'run.py') -PathType Leaf)) {
    throw 'Verified SYSTEM root must contain run.py'
}
$resolved = $null
$candidates = @()
if ($McpPythonPath) {
    $candidates = @($McpPythonPath)
} else {
    $envRoot = Join-Path $Root 'workspace_runtime\local_resources\python\environments'
    if (Test-Path -LiteralPath $envRoot -PathType Container) {
        $candidates = @(Get-ChildItem -LiteralPath $envRoot -Directory | ForEach-Object {
            Join-Path $_.FullName 'Scripts\python.exe'
        })
    }
}
foreach ($candidate in $candidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    # Import check is performed in the candidate interpreter, never in the
    # unrelated activated prompt's global virtualenv.
    & $candidate -c 'import mcp, pydantic, pydantic_core, starlette, uvicorn' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        break
    }
}
if (-not $resolved) {
    throw 'No complete MCP Python found. Prepare core+mcp-http via Dependency Studio (not global pip).'
}

$supervisor = & $resolved -X utf8 (Join-Path $Root 'run.py') supervisor-status --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'supervisor-status failed' }
$daemon = & $resolved -X utf8 (Join-Path $Root 'run.py') status --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'status failed' }

$health = $null
$ready = $null
$catalog = $null
$url = "http://127.0.0.1:$Port"
try {
    $health = Invoke-RestMethod -Uri "$url/healthz" -TimeoutSec 6
    $ready = Invoke-RestMethod -Uri "$url/readyz" -TimeoutSec 12
} catch {
    # A missing endpoint is not an invitation to start another gateway.
}
if ($health -and $ready -and $ready.ready -eq $true) {
    try {
        $raw = & $resolved -X utf8 (Join-Path $Root 'run.py') mcp-probe `
            --url "$url/mcp" --timeout 15 --check-chatgpt-tool-catalog --json
        if ($LASTEXITCODE -eq 0) { $catalog = $raw | ConvertFrom-Json }
    } catch {
        # Do not claim four tools merely because the gateway is live.
    }
}
$expected = [string]$daemon.runtime_version
$actual = [string]$daemon.daemon.ping.runtime_version
[PSCustomObject]@{
    schema_version = 'jazn_local_mcp_operator_check/v1'
    system_root = $Root
    python_executable = $resolved
    daemon_version_matches = [bool]($expected -and $actual -and $expected -ceq $actual)
    daemon_package_version = $expected
    daemon_live_version = $actual
    daemon_readiness = [bool]($daemon.daemon.readiness.readiness_ok -eq $true)
    supervisor_active = [bool]($supervisor.supervisor_active -eq $true)
    supervisor_identity_confirmed = [bool]($supervisor.supervisor_identity_confirmed -eq $true)
    supervisor_heartbeat_fresh = [bool]($supervisor.supervisor_heartbeat_fresh -eq $true)
    gateway_health_verified = [bool]($health.gateway_live -eq $true)
    gateway_ready_verified = [bool]($ready.ready -eq $true)
    gateway_runtime_version_matches = [bool]($expected -and $ready.runtime_version -ceq $expected)
    tool_catalog_verified = [bool]($catalog.tool_catalog_verified -eq $true)
    missing_required_tool_names = if ($catalog) { @($catalog.missing_required_tool_names) } else { @('unverified') }
    chatgpt_current_message_toolset_verified = $false
    accepted_visible_turn_verified = $false
    deployed_public_oauth_verified = $false
    truth_boundary = 'Local-only observations. Never infer public OAuth, ChatGPT capability or accepted finalization.'
} | ConvertTo-Json -Depth 6
