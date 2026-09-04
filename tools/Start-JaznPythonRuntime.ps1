param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$JaznArgs = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-ChildPath([string]$Base, [string]$Candidate) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    $prefix = $baseFull + [IO.Path]::DirectorySeparatorChar
    if (-not $candidateFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "runtime_path_escape:$Candidate"
    }
    return $candidateFull
}

function Get-WorkspaceRoot([string]$AppRoot) {
    $configured = [string]$env:JAZN_RUNTIME_WORKSPACE_DIR
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        if ([IO.Path]::IsPathRooted($configured)) {
            return [IO.Path]::GetFullPath($configured)
        }
        return [IO.Path]::GetFullPath((Join-Path $AppRoot $configured))
    }
    return [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $AppRoot) "workspace_runtime"))
}

function Assert-RuntimeSetIntegrity([string]$AppRoot, [string]$SetPath) {
    $allowUnmanifested = ([string]$env:JAZN_ALLOW_UNMANIFESTED_RUNTIME_SET).Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
    $manifestPath = Join-Path $AppRoot "PACKAGE_INTEGRITY_MANIFEST.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        if ($allowUnmanifested) { return }
        throw "package_integrity_manifest_missing_for_runtime_set"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $entry = @($manifest.files | Where-Object { [string]$_.path -eq "JAZN_PYTHON_RUNTIME_SET.json" })
    if ($entry.Count -ne 1) {
        if ($allowUnmanifested) { return }
        throw "runtime_set_not_protected_by_package_manifest"
    }
    $size = (Get-Item -LiteralPath $SetPath).Length
    if ([int64]$entry[0].size_bytes -ne [int64]$size) {
        throw "runtime_set_size_mismatch"
    }
    if (([string]$entry[0].sha256).ToLowerInvariant() -ne (Get-Sha256 $SetPath)) {
        throw "runtime_set_sha256_mismatch"
    }
}

$Root = [IO.Path]::GetFullPath($Root)
$runtimeSetPath = Join-Path $Root "JAZN_PYTHON_RUNTIME_SET.json"
if (-not (Test-Path -LiteralPath $runtimeSetPath -PathType Leaf)) {
    throw "JAZN_PYTHON_RUNTIME_SET.json not found"
}
Assert-RuntimeSetIntegrity $Root $runtimeSetPath
$runtimeSet = Get-Content -LiteralPath $runtimeSetPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$runtimeSet.schema_version -ne "jazn_python_runtime_set/v1") {
    throw "unsupported_python_runtime_set_schema:$($runtimeSet.schema_version)"
}

$architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
switch ($architecture) {
    "x64" { $targetAlias = "windows-x64" }
    "arm64" { $targetAlias = "windows-arm64" }
    default { throw "unsupported_windows_runtime_architecture:$architecture" }
}

$preference = @()
if (-not [string]::IsNullOrWhiteSpace([string]$env:JAZN_PYTHON_VERSION)) {
    $preference = @([string]$env:JAZN_PYTHON_VERSION)
} elseif ($null -ne $runtimeSet.python_preference) {
    $preference = @($runtimeSet.python_preference | ForEach-Object { [string]$_ })
} else {
    $preference = @("3.14", "3.13", "3.12")
}

$selected = $null
foreach ($version in $preference) {
    $selected = @(
        $runtimeSet.artifacts | Where-Object {
            [string]$_.target.alias -eq $targetAlias -and
            [string]$_.target.python_version -eq $version -and
            [string]$_.target.implementation -eq "cp"
        } | Sort-Object -Property filename
    ) | Select-Object -First 1
    if ($null -ne $selected) { break }
}
if ($null -eq $selected) {
    throw "no_compatible_python_runtime:$targetAlias preference=$($preference -join ',')"
}

$filename = [string]$selected.filename
if ([IO.Path]::GetFileName($filename) -ne $filename) {
    throw "unsafe_python_runtime_filename:$filename"
}
$candidates = @(
    (Join-Path $Root $filename),
    (Join-Path $Root (Join-Path "runtime_bundles" $filename)),
    (Join-Path (Split-Path -Parent $Root) $filename)
)
$bundle = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace([string]$bundle)) {
    throw "python_runtime_bundle_missing:$filename"
}
$bundle = [IO.Path]::GetFullPath([string]$bundle)
$expectedBundleSha = ([string]$selected.sha256).ToLowerInvariant()
if ((Get-Sha256 $bundle) -ne $expectedBundleSha) {
    throw "python_runtime_bundle_sha256_mismatch:$filename"
}

$workspace = Get-WorkspaceRoot $Root
$runtimeBase = Join-Path $workspace "local_resources\python_runtime\runtimes"
New-Item -ItemType Directory -Path $runtimeBase -Force | Out-Null
$targetId = [string]$selected.target_id
if ($targetId -notmatch '^[A-Za-z0-9._-]+$') {
    throw "unsafe_python_runtime_target_id:$targetId"
}
$runtimeRoot = Join-Path $runtimeBase ($targetId + "--" + $expectedBundleSha.Substring(0, 12))
$readyMarker = Join-Path $runtimeRoot "JAZN_PYTHON_RUNTIME_READY.json"

if (-not (Test-Path -LiteralPath $readyMarker -PathType Leaf)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($bundle)
    try {
        foreach ($entry in $zip.Entries) {
            $name = ([string]$entry.FullName).Replace('\', '/')
            $trimmed = $name.TrimEnd('/')
            if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
            if ($name.StartsWith('/') -or $name.StartsWith('\') -or $name -match '^[A-Za-z]:' -or $name.Contains('\')) {
                throw "unsafe_python_runtime_member:$name"
            }
            $parts = $trimmed.Split('/')
            if ($parts -contains '..' -or $parts -contains '.') {
                throw "unsafe_python_runtime_member:$name"
            }
        }
    } finally {
        $zip.Dispose()
    }

    $staging = Join-Path $runtimeBase ("." + $targetId + ".staging-" + [Guid]::NewGuid().ToString("N"))
    try {
        Expand-Archive -LiteralPath $bundle -DestinationPath $staging -Force
        $manifestPath = Join-Path $staging "JAZN_PYTHON_RUNTIME_MANIFEST.json"
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "python_runtime_manifest_missing_after_extract"
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$manifest.schema_version -ne "jazn_python_runtime_manifest/v1") {
            throw "unsupported_python_runtime_manifest_schema:$($manifest.schema_version)"
        }
        if ([string]$manifest.target.target_id -ne $targetId) {
            throw "python_runtime_manifest_target_mismatch"
        }
        foreach ($file in @($manifest.files)) {
            $relative = ([string]$file.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
            $candidate = Assert-ChildPath $staging (Join-Path $staging $relative)
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                throw "python_runtime_file_missing:$($file.path)"
            }
            if ([int64](Get-Item -LiteralPath $candidate).Length -ne [int64]$file.size_bytes) {
                throw "python_runtime_file_size_mismatch:$($file.path)"
            }
            if ((Get-Sha256 $candidate) -ne ([string]$file.sha256).ToLowerInvariant()) {
                throw "python_runtime_file_sha256_mismatch:$($file.path)"
            }
        }
        $actualFiles = @(Get-ChildItem -LiteralPath $staging -File -Recurse)
        if ($actualFiles.Count -ne ([int]$manifest.file_count + 1)) {
            throw "python_runtime_unlisted_file_count_mismatch"
        }
        $markerPayload = [ordered]@{
            schema_version = "jazn_python_runtime_ready/v1"
            bundle_sha256 = $expectedBundleSha
            target_id = $targetId
        } | ConvertTo-Json
        Set-Content -LiteralPath (Join-Path $staging "JAZN_PYTHON_RUNTIME_READY.json") -Value $markerPayload -Encoding UTF8
        if (Test-Path -LiteralPath $runtimeRoot) {
            Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
        }
        Move-Item -LiteralPath $staging -Destination $runtimeRoot
    } catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

$runtimeManifestPath = Join-Path $runtimeRoot "JAZN_PYTHON_RUNTIME_MANIFEST.json"
$runtimeManifest = Get-Content -LiteralPath $runtimeManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$interpreterRelative = ([string]$runtimeManifest.interpreter_relative_path).Replace('/', [IO.Path]::DirectorySeparatorChar)
$python = Assert-ChildPath $runtimeRoot (Join-Path $runtimeRoot $interpreterRelative)
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "python_runtime_interpreter_missing:$python"
}
$bootstrap = Join-Path $Root "jazn_runtime_bootstrap.py"
if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
    throw "jazn_runtime_bootstrap_missing:$bootstrap"
}

foreach ($name in @("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__")) {
    Remove-Item -Path ("Env:" + $name) -ErrorAction SilentlyContinue
}
$env:PYTHONUTF8 = "1"
$env:PYTHONNOUSERSITE = "1"
$env:JAZN_PYTHON_RUNTIME_ACTIVE = "1"
$env:JAZN_PYTHON_RUNTIME_ROOT = $runtimeRoot

$launchArgs = @(
    "-I", "-X", "utf8", $bootstrap,
    "--app-root", $Root,
    "--runtime-root", $runtimeRoot,
    "--packages-relative-path", [string]$runtimeManifest.packages_relative_path,
    "--"
)
$launchArgs += $JaznArgs
& $python @launchArgs
exit $LASTEXITCODE
