[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$SourceManifest,
    [string]$TargetRoot,
    [string]$BaselineTest03Root,
    [string]$LegacyMemoryRoot,
    [string]$RecallCases,
    [string]$MultiTurnReview,
    [switch]$PlanOnly,
    [switch]$RunRebuild,
    [switch]$RunIdempotence,
    [switch]$RunFreshRebuildComparison,
    [switch]$RunRecall,
    [switch]$RunHtmlDryRun,
    [ValidateRange(1, 2147483647)]
    [int]$HtmlLimitConversations = 0,
    [switch]$RestartDaemon,
    [ValidateRange(5, 3600)]
    [int]$RestartTimeoutSeconds = 90,
    [switch]$Resume,
    [switch]$AllowDirty,
    [switch]$WriteTemplates,
    [string]$PythonCommand = "py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedBranch = "feature/memory-sqlite-test-04"
$Root = [System.IO.Path]::GetFullPath($Root)

function Resolve-PrivatePath {
    param([Parameter(Mandatory)][string]$Value)
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Value))
}

function Assert-ParameterContract {
    $executionFlags = @(
        [bool]$RunRebuild,
        [bool]$RunIdempotence,
        [bool]$RunFreshRebuildComparison,
        [bool]$RunRecall,
        [bool]$RestartDaemon
    )
    $hasExecutionFlag = $executionFlags -contains $true

    if ($WriteTemplates) {
        if ($PlanOnly -or $hasExecutionFlag -or $Resume) {
            throw "-WriteTemplates nie moze byc laczone z planem, wykonaniem ani -Resume."
        }
        return
    }
    if ([string]::IsNullOrWhiteSpace($SourceManifest)) {
        throw "Podaj jawnie -SourceManifest."
    }
    if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
        throw "Podaj jawnie -TargetRoot."
    }
    if ($PlanOnly -and $hasExecutionFlag) {
        throw "-PlanOnly nie moze byc laczone z flagami wykonania."
    }
    if (-not $PlanOnly -and -not $RunRebuild) {
        throw "Wybierz -PlanOnly albo jawne -RunRebuild."
    }
    if (($RunIdempotence -or $RunFreshRebuildComparison -or $RunRecall -or $RestartDaemon) -and -not $RunRebuild) {
        throw "Fazy wykonawcze wymagaja -RunRebuild."
    }
    if ($RunRecall -and [string]::IsNullOrWhiteSpace($RecallCases)) {
        throw "-RunRecall wymaga -RecallCases."
    }
}

Assert-ParameterContract

if (-not (Test-Path -LiteralPath (Join-Path $Root "run.py") -PathType Leaf)) {
    throw "Nie znaleziono run.py pod rootem: $Root"
}

$branchOutput = & git -C $Root branch --show-current 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Nie udalo sie odczytac biezacego brancha Git."
}
$branch = ([string]($branchOutput | Select-Object -First 1)).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Niewlasciwy branch. Oczekiwano '$ExpectedBranch', otrzymano '$branch'. Nie zapisano plikow."
}

$arguments = New-Object "System.Collections.Generic.List[string]"
[void]$arguments.Add("-X")
[void]$arguments.Add("utf8")
[void]$arguments.Add("-m")
[void]$arguments.Add("latka_jazn.tools.memory_sqlite_test04")
[void]$arguments.Add("--root")
[void]$arguments.Add($Root)
[void]$arguments.Add("--json")

if ($WriteTemplates) {
    [void]$arguments.Add("--write-templates")
}
else {
    $resolvedManifest = Resolve-PrivatePath -Value $SourceManifest
    $resolvedTarget = Resolve-PrivatePath -Value $TargetRoot
    if (-not (Test-Path -LiteralPath $resolvedManifest -PathType Leaf)) {
        throw "Nie znaleziono prywatnego manifestu zrodel."
    }
    [void]$arguments.Add("--source-manifest")
    [void]$arguments.Add($resolvedManifest)
    [void]$arguments.Add("--target-root")
    [void]$arguments.Add($resolvedTarget)

    if (-not [string]::IsNullOrWhiteSpace($BaselineTest03Root)) {
        [void]$arguments.Add("--baseline-test03-root")
        [void]$arguments.Add((Resolve-PrivatePath -Value $BaselineTest03Root))
    }
    if (-not [string]::IsNullOrWhiteSpace($LegacyMemoryRoot)) {
        [void]$arguments.Add("--legacy-memory-root")
        [void]$arguments.Add((Resolve-PrivatePath -Value $LegacyMemoryRoot))
    }
    if (-not [string]::IsNullOrWhiteSpace($RecallCases)) {
        $resolvedRecall = Resolve-PrivatePath -Value $RecallCases
        if (-not (Test-Path -LiteralPath $resolvedRecall -PathType Leaf)) {
            throw "Nie znaleziono prywatnego pliku przypadkow recall."
        }
        [void]$arguments.Add("--recall-cases")
        [void]$arguments.Add($resolvedRecall)
    }
    if (-not [string]::IsNullOrWhiteSpace($MultiTurnReview)) {
        $resolvedReview = Resolve-PrivatePath -Value $MultiTurnReview
        if (-not (Test-Path -LiteralPath $resolvedReview -PathType Leaf)) {
            throw "Nie znaleziono prywatnego pliku recznej oceny wieloturowej."
        }
        [void]$arguments.Add("--multi-turn-review")
        [void]$arguments.Add($resolvedReview)
    }
    if ($PlanOnly) { [void]$arguments.Add("--plan-only") }
    if ($RunRebuild) { [void]$arguments.Add("--run-rebuild") }
    if ($RunIdempotence) { [void]$arguments.Add("--run-idempotence") }
    if ($RunFreshRebuildComparison) { [void]$arguments.Add("--run-fresh-rebuild-comparison") }
    if ($RunRecall) { [void]$arguments.Add("--run-recall") }
    if ($RunHtmlDryRun) { [void]$arguments.Add("--run-html-dry-run") }
    if ($HtmlLimitConversations -gt 0) {
        [void]$arguments.Add("--html-limit-conversations")
        [void]$arguments.Add([string]$HtmlLimitConversations)
    }
    if ($RestartDaemon) {
        [void]$arguments.Add("--restart-daemon")
        [void]$arguments.Add("--restart-timeout-seconds")
        [void]$arguments.Add([string]$RestartTimeoutSeconds)
    }
    if ($Resume) { [void]$arguments.Add("--resume") }
}
if ($AllowDirty) { [void]$arguments.Add("--allow-dirty") }

Push-Location -LiteralPath $Root
try {
    & $PythonCommand @arguments
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    [Console]::Error.WriteLine("Memory SQLite Test 04 zakonczyl sie kodem $exitCode. Sprawdz prywatny raport przebiegu.")
}
exit $exitCode
