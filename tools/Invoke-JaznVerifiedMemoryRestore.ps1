[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("Validate", "Prepare", "SealL2", "ApplyL2", "Activate")]
    [string]$Mode = "Validate",

    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Test04Root,
    [string]$Test04Summary,

    [switch]$RunTest04,
    [string]$SourceManifest,
    [string]$BaselineTest03Root,
    [string]$LegacyMemoryRoot,
    [string]$RecallCases,
    [string]$MultiTurnReview,

    [switch]$Publish,
    [switch]$StopDaemon,
    [string]$ConfirmPublish,

    [string]$L2Draft,
    [string]$L2Manifest,
    [string]$L2ManifestSha256,
    [string]$ReviewedBy,
    [ValidateRange(1, 10000)]
    [int]$L2Limit = 120,

    [string]$L3Manifest,
    [string]$L3ManifestSha256,
    [string]$ApprovedBy,
    [ValidateRange(0, 10000)]
    [int]$L3Limit = 25,
    [string]$ConfirmActivation,

    [string]$Output,
    [string]$PythonCommand = "py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($Root)

function Resolve-LocalPath {
    param(
        [Parameter(Mandatory)]
        [string]$Value,
        [switch]$AllowMissing
    )
    $candidate = if ([System.IO.Path]::IsPathRooted($Value)) {
        [System.IO.Path]::GetFullPath($Value)
    }
    else {
        [System.IO.Path]::GetFullPath((Join-Path $Root $Value))
    }
    if (-not $AllowMissing -and -not (Test-Path -LiteralPath $candidate)) {
        throw "Nie znaleziono ścieżki: $candidate"
    }
    return $candidate
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$Label
    )
    Write-Host ""
    Write-Host "==> $Label"
    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "$Label zakończyło się kodem $code."
    }
}

function Find-LatestTest04Summary {
    $workspace = Join-Path $Root "workspace_runtime\memory_sqlite_test_04"
    if (-not (Test-Path -LiteralPath $workspace -PathType Container)) {
        throw "Nie znaleziono workspace Testu 04: $workspace"
    }
    $summary = Get-ChildItem -LiteralPath $workspace -Recurse -Filter "summary.sanitized.json" -File |
        Sort-Object LastWriteTimeUtc, FullName |
        Select-Object -Last 1
    if ($null -eq $summary) {
        throw "Nie znaleziono summary.sanitized.json Testu 04."
    }
    return $summary.FullName
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "run.py") -PathType Leaf)) {
    throw "Brak run.py pod rootem: $Root"
}
if (-not (Test-Path -LiteralPath (Join-Path $Root "latka_jazn\tools\verified_memory_restore.py") -PathType Leaf)) {
    throw "Najpierw zastosuj patch dodający verified_memory_restore.py."
}

if ($RunTest04) {
    if ($Mode -notin @("Validate", "Prepare")) {
        throw "-RunTest04 można łączyć wyłącznie z Mode Validate albo Prepare."
    }
    foreach ($required in @("SourceManifest", "Test04Root", "RecallCases")) {
        if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $required -ValueOnly))) {
            throw "-RunTest04 wymaga -$required."
        }
    }
    $test04Script = Join-Path $Root "tools\Invoke-JaznMemorySqliteTest04.ps1"
    if (-not (Test-Path -LiteralPath $test04Script -PathType Leaf)) {
        throw "Brak istniejącego operatora Testu 04: $test04Script"
    }
    $test04Args = @{
        Root = $Root
        SourceManifest = (Resolve-LocalPath $SourceManifest)
        TargetRoot = (Resolve-LocalPath $Test04Root -AllowMissing)
        RecallCases = (Resolve-LocalPath $RecallCases)
        RunRebuild = $true
        RunIdempotence = $true
        RunFreshRebuildComparison = $true
        RunRecall = $true
        PythonCommand = $PythonCommand
    }
    if (-not [string]::IsNullOrWhiteSpace($BaselineTest03Root)) {
        $test04Args["BaselineTest03Root"] = Resolve-LocalPath $BaselineTest03Root
    }
    if (-not [string]::IsNullOrWhiteSpace($LegacyMemoryRoot)) {
        $test04Args["LegacyMemoryRoot"] = Resolve-LocalPath $LegacyMemoryRoot
    }
    if (-not [string]::IsNullOrWhiteSpace($MultiTurnReview)) {
        $test04Args["MultiTurnReview"] = Resolve-LocalPath $MultiTurnReview
    }
    Write-Host "Uruchamiam istniejący pełny Memory SQLite Test 04."
    & $test04Script @test04Args
    if ($LASTEXITCODE -ne 0) {
        throw "Test 04 zakończył się kodem $LASTEXITCODE."
    }
    $Test04Summary = Find-LatestTest04Summary
}

$baseArgs = @(
    "-X", "utf8",
    "-m", "latka_jazn.tools.verified_memory_restore"
)

switch ($Mode) {
    "Validate" {
        if ([string]::IsNullOrWhiteSpace($Test04Root)) {
            throw "Mode Validate wymaga -Test04Root."
        }
        if ([string]::IsNullOrWhiteSpace($Test04Summary)) {
            $Test04Summary = Find-LatestTest04Summary
        }
        $arguments = $baseArgs + @(
            "validate-test04",
            "--test04-root", (Resolve-LocalPath $Test04Root),
            "--test04-summary", (Resolve-LocalPath $Test04Summary),
            "--json"
        )
        Invoke-NativeChecked $PythonCommand $arguments "Walidacja Testu 04"
    }

    "Prepare" {
        if ([string]::IsNullOrWhiteSpace($Test04Root)) {
            throw "Mode Prepare wymaga -Test04Root."
        }
        if ([string]::IsNullOrWhiteSpace($Test04Summary)) {
            $Test04Summary = Find-LatestTest04Summary
        }
        if ($Publish -and $ConfirmPublish -ne "PUBLISH_VERIFIED_MEMORY") {
            throw "Publikacja wymaga -ConfirmPublish PUBLISH_VERIFIED_MEMORY."
        }
        $arguments = $baseArgs + @(
            "prepare",
            "--root", $Root,
            "--test04-root", (Resolve-LocalPath $Test04Root),
            "--test04-summary", (Resolve-LocalPath $Test04Summary),
            "--l2-limit", [string]$L2Limit,
            "--json"
        )
        if ($Publish) { $arguments += "--publish" }
        if ($StopDaemon) { $arguments += "--stop-daemon" }
        if (-not [string]::IsNullOrWhiteSpace($Output)) {
            $arguments += @("--report", (Resolve-LocalPath $Output -AllowMissing))
        }
        Invoke-NativeChecked $PythonCommand $arguments "Konwersja, recovery, normalizacja i wake-state"
        Write-Host ""
        Write-Host "Po publikacji znajdź l2_review_draft.json w:"
        Write-Host "  $Root\workspace_runtime\verified_memory_restore\<run-id>\"
        Write-Host "Ustaw dla każdego kandydata decision=approved albo decision=rejected."
    }

    "SealL2" {
        foreach ($required in @("L2Draft", "L2Manifest", "ReviewedBy")) {
            if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $required -ValueOnly))) {
                throw "Mode SealL2 wymaga -$required."
            }
        }
        $arguments = $baseArgs + @(
            "seal-l2",
            "--draft", (Resolve-LocalPath $L2Draft),
            "--reviewed-by", $ReviewedBy,
            "--output", (Resolve-LocalPath $L2Manifest -AllowMissing),
            "--json"
        )
        Invoke-NativeChecked $PythonCommand $arguments "Zapieczętowanie ręcznego przeglądu L2"
    }

    "ApplyL2" {
        foreach ($required in @("L2Manifest", "L2ManifestSha256", "ReviewedBy")) {
            if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $required -ValueOnly))) {
                throw "Mode ApplyL2 wymaga -$required."
            }
        }
        $arguments = $baseArgs + @(
            "apply-l2",
            "--root", $Root,
            "--manifest", (Resolve-LocalPath $L2Manifest),
            "--expected-sha256", $L2ManifestSha256,
            "--reviewed-by", $ReviewedBy,
            "--l3-limit", [string]$L3Limit,
            "--json"
        )
        if (-not [string]::IsNullOrWhiteSpace($Output)) {
            $arguments += @("--report", (Resolve-LocalPath $Output -AllowMissing))
        }
        Invoke-NativeChecked $PythonCommand $arguments "Zapis zatwierdzonych L2 i budowa manifestu L3"
    }

    "Activate" {
        foreach ($required in @("L3Manifest", "L3ManifestSha256", "ApprovedBy")) {
            if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $required -ValueOnly))) {
                throw "Mode Activate wymaga -$required."
            }
        }
        if ($ConfirmActivation -ne "ACTIVATE_VERIFIED_MEMORY") {
            throw "Aktywacja wymaga -ConfirmActivation ACTIVATE_VERIFIED_MEMORY."
        }
        $arguments = $baseArgs + @(
            "activate",
            "--root", $Root,
            "--l3-manifest", (Resolve-LocalPath $L3Manifest),
            "--expected-sha256", $L3ManifestSha256,
            "--approved-by", $ApprovedBy,
            "--start-daemon",
            "--json"
        )
        if (-not [string]::IsNullOrWhiteSpace($Output)) {
            $arguments += @("--report", (Resolve-LocalPath $Output -AllowMissing))
        }
        Invoke-NativeChecked $PythonCommand $arguments "Końcowa walidacja, doctor i aktywacja"
    }
}
