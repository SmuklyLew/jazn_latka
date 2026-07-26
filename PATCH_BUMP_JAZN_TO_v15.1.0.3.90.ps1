#requires -Version 5.1
<#
.SYNOPSIS
    Bezpiecznie podnosi PACKAGE_VERSION Jaźni z v15.1.0.3.89 do v15.1.0.3.90.

.DESCRIPTION
    Patch:
      - wymaga czystego repozytorium Git;
      - domyślnie tworzy branch update/version-15.1.0.3.90;
      - pozostawia DISTRIBUTION_VERSION = "15.1.0.3";
      - pozostawia PACKAGE_RELEASE_NAME = "Memory Sqlite Pipeline";
      - zmienia wyłącznie latka_jazn/version.py;
      - zapisuje tymczasową kopię bezpieczeństwa;
      - wykonuje kontrolę importu, py_compile i git diff --check;
      - nie wykonuje commita, pushu, PR-a ani ręcznej edycji manifestów.

    PACKAGE_INTEGRITY_MANIFEST.json i SOURCE_PROVENANCE.json powinny zostać
    zsynchronizowane kanonicznym workflow release-metadata-sync po otwarciu PR.

.EXAMPLE
    PS D:\.AI\jazn_latka_master> .\PATCH_BUMP_JAZN_TO_v15.1.0.3.90.ps1

.EXAMPLE
    PS D:\.AI\jazn_latka_master> .\PATCH_BUMP_JAZN_TO_v15.1.0.3.90.ps1 -SkipBranch
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Root = (Get-Location).Path,

    [Parameter()]
    [string]$Branch = "update/version-15.1.0.3.90",

    [Parameter()]
    [switch]$SkipBranch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedDistributionVersion = "15.1.0.3"
$OldPackageVersion = "v15.1.0.3.89"
$NewPackageVersion = "v15.1.0.3.90"
$ExpectedReleaseName = "Memory Sqlite Pipeline"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Polecenie zakończyło się kodem ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git zakończył się kodem ${LASTEXITCODE}: git $($Arguments -join ' ')"
    }
    return ($output | Out-String).Trim()
}

$resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
$versionPath = Join-Path $resolvedRoot "latka_jazn\version.py"
$pyprojectPath = Join-Path $resolvedRoot "pyproject.toml"

if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
    throw "Brak kanonicznego pliku wersji: $versionPath"
}
if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
    throw "Brak pyproject.toml: $pyprojectPath"
}

Push-Location $resolvedRoot
$backupPath = $null
$branchCreated = $false

try {
    $gitRoot = Get-GitOutput -Arguments @("rev-parse", "--show-toplevel")
    $gitRootResolved = (Resolve-Path -LiteralPath $gitRoot).Path
    if ($gitRootResolved -ne $resolvedRoot) {
        throw "Podany Root nie jest katalogiem głównym repozytorium. Git root: $gitRootResolved"
    }

    $statusBefore = Get-GitOutput -Arguments @("status", "--porcelain")
    if ($statusBefore) {
        throw "Repozytorium nie jest czyste. Zapisz lub wycofaj zmiany przed zastosowaniem patcha.`n$statusBefore"
    }

    $headBefore = Get-GitOutput -Arguments @("rev-parse", "HEAD")
    $currentBranch = Get-GitOutput -Arguments @("branch", "--show-current")

    if (-not $SkipBranch) {
        if ($currentBranch -eq $Branch) {
            Write-Host "Branch już aktywny: $Branch"
        }
        elseif ($currentBranch -ne "master") {
            throw "Oczekiwano brancha master albo $Branch, aktywny jest: $currentBranch"
        }
        else {
            & git show-ref --verify --quiet "refs/heads/$Branch"
            $branchExists = ($LASTEXITCODE -eq 0)

            if ($branchExists) {
                throw "Branch $Branch już istnieje. Przełącz się na niego ręcznie albo podaj inną nazwę przez -Branch."
            }

            Invoke-Checked -Command "git" -Arguments @("switch", "-c", $Branch)
            $branchCreated = $true
            Write-Host "Utworzono branch: $Branch"
        }
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $source = [System.IO.File]::ReadAllText($versionPath, $utf8NoBom)

    $expectedDistributionLine = 'DISTRIBUTION_VERSION = "' + $ExpectedDistributionVersion + '"'
    $expectedOldPackageLine = 'PACKAGE_VERSION = "' + $OldPackageVersion + '"'
    $expectedNewPackageLine = 'PACKAGE_VERSION = "' + $NewPackageVersion + '"'
    $expectedReleaseLine = 'PACKAGE_RELEASE_NAME = "' + $ExpectedReleaseName + '"'

    if (($source.Split($expectedDistributionLine).Count - 1) -ne 1) {
        throw "Nie znaleziono dokładnie jednej oczekiwanej linii DISTRIBUTION_VERSION."
    }
    if (($source.Split($expectedReleaseLine).Count - 1) -ne 1) {
        throw "Nie znaleziono dokładnie jednej oczekiwanej linii PACKAGE_RELEASE_NAME."
    }

    $oldCount = $source.Split($expectedOldPackageLine).Count - 1
    $newCount = $source.Split($expectedNewPackageLine).Count - 1

    if ($oldCount -eq 0 -and $newCount -eq 1) {
        Write-Host "PACKAGE_VERSION jest już ustawione na $NewPackageVersion. Patch nie wymaga ponownej zmiany."
    }
    elseif ($oldCount -ne 1 -or $newCount -ne 0) {
        throw "Nieoczekiwany stan PACKAGE_VERSION. Patch wymaga dokładnie: $expectedOldPackageLine"
    }
    else {
        $backupDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("jazn-version-patch-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $backupDirectory | Out-Null
        $backupPath = Join-Path $backupDirectory "version.py"
        Copy-Item -LiteralPath $versionPath -Destination $backupPath -Force

        $updated = $source.Replace($expectedOldPackageLine, $expectedNewPackageLine)
        [System.IO.File]::WriteAllText($versionPath, $updated, $utf8NoBom)

        Write-Host "Zmieniono PACKAGE_VERSION:"
        Write-Host "  $OldPackageVersion -> $NewPackageVersion"
        Write-Host "Kopia bezpieczeństwa: $backupPath"
    }

    # Jawna kontrola, że DISTRIBUTION_VERSION pozostaje źródłem wersji pakietu setuptools.
    $pyproject = [System.IO.File]::ReadAllText($pyprojectPath, $utf8NoBom)
    if ($pyproject -notmatch 'version\s*=\s*\{\s*attr\s*=\s*"latka_jazn\.version\.DISTRIBUTION_VERSION"\s*\}') {
        throw "pyproject.toml nie wskazuje już na latka_jazn.version.DISTRIBUTION_VERSION. Wymagana jest osobna analiza kontraktu pakowania."
    }

    Invoke-Checked -Command "py" -Arguments @(
        "-X", "utf8",
        "-m", "py_compile",
        ".\latka_jazn\version.py"
    )

    $validationCode = @'
from latka_jazn.version import (
    DISTRIBUTION_VERSION,
    PACKAGE_RELEASE_NAME,
    PACKAGE_VERSION,
    PACKAGE_VERSION_FULL,
)
assert DISTRIBUTION_VERSION == "15.1.0.3", DISTRIBUTION_VERSION
assert PACKAGE_VERSION == "v15.1.0.3.90", PACKAGE_VERSION
assert PACKAGE_RELEASE_NAME == "Memory Sqlite Pipeline", PACKAGE_RELEASE_NAME
assert PACKAGE_VERSION_FULL == "v15.1.0.3.90-Memory Sqlite Pipeline", PACKAGE_VERSION_FULL
print(PACKAGE_VERSION_FULL)
'@
    Invoke-Checked -Command "py" -Arguments @("-X", "utf8", "-c", $validationCode)

    Invoke-Checked -Command "git" -Arguments @("diff", "--check")

    $changedFiles = Get-GitOutput -Arguments @("status", "--short")
    $expectedStatus = " M latka_jazn/version.py"
    if ($changedFiles -ne $expectedStatus) {
        throw "Po patchu oczekiwano wyłącznie zmiany latka_jazn/version.py, otrzymano:`n$changedFiles"
    }

    Write-Host ""
    Write-Host "Patch zastosowany poprawnie."
    Write-Host "HEAD przed zmianą: $headBefore"
    Write-Host "DISTRIBUTION_VERSION pozostawiono jako $ExpectedDistributionVersion."
    Write-Host "PACKAGE_VERSION ustawiono na $NewPackageVersion."
    Write-Host ""
    Write-Host "Sprawdź diff:"
    Write-Host "  git diff -- .\latka_jazn\version.py"
    Write-Host ""
    Write-Host "Następne kroki wykonywane ręcznie:"
    Write-Host "  git add .\latka_jazn\version.py"
    Write-Host '  git commit -m "release: bump package version to v15.1.0.3.90"'
    if (-not $SkipBranch) {
        Write-Host "  git push -u origin $Branch"
    }
    Write-Host ""
    Write-Host "Po otwarciu PR workflow release-metadata-sync powinien kanonicznie"
    Write-Host "zaktualizować PACKAGE_INTEGRITY_MANIFEST.json i SOURCE_PROVENANCE.json."
}
catch {
    if ($backupPath -and (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $backupPath -Destination $versionPath -Force
        Write-Warning "Przywrócono latka_jazn/version.py z kopii: $backupPath"
    }

    if ($branchCreated) {
        Write-Warning "Branch $Branch pozostał utworzony, ale plik wersji został przywrócony."
    }

    throw
}
finally {
    Pop-Location
}
