[CmdletBinding()]
param(
    [ValidateSet("all", "server", "agent", "submit")]
    [string]$Target = "all",
    [string]$RepoRoot = "",
    [string]$PythonExe = "",
    [string]$OutputDir = "",
    [switch]$OneFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    param([string]$InputPath)
    if ([string]::IsNullOrWhiteSpace($InputPath)) {
        return [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    }
    return [System.IO.Path]::GetFullPath($InputPath)
}

function Resolve-Python {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [string]$Preferred = ""
    )

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        $resolved = [System.IO.Path]::GetFullPath($Preferred)
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "Python executable not found: $resolved"
        }
        return $resolved
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python not found. Provide -PythonExe or create .venv first."
}

function Run-PyInstallerBuild {
    param(
        [Parameter(Mandatory = $true)][string]$PyExe,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$DistPath,
        [Parameter(Mandatory = $true)][string]$WorkPath,
        [Parameter(Mandatory = $true)][string]$SpecPath,
        [Parameter(Mandatory = $true)][string]$ExeName,
        [Parameter(Mandatory = $true)][string]$EntryScript,
        [bool]$UseOneFile = $false
    )

    $modeArg = if ($UseOneFile) { "--onefile" } else { "--onedir" }
    $args = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        $modeArg,
        "--name", $ExeName,
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        "--hidden-import", "win32timezone",
        "--collect-submodules", "win32com",
        $EntryScript
    )

    & $PyExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $ExeName"
    }
}

$RepoRoot = Resolve-RepoRoot -InputPath $RepoRoot
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot not found: $RepoRoot"
}

$PythonExe = Resolve-Python -ProjectRoot $RepoRoot -Preferred $PythonExe

$versionFile = Join-Path $RepoRoot "VERSION"
$version = if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
    (Get-Content -LiteralPath $versionFile -Raw).Trim()
} else {
    "0.0.0"
}
if ([string]::IsNullOrWhiteSpace($version)) {
    $version = "0.0.0"
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot "artifacts\exe\v$version"
} else {
    if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
        $OutputDir = Join-Path $RepoRoot $OutputDir
    }
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

$workDir = Join-Path $RepoRoot "build\pyinstaller-work"
$specDir = Join-Path $RepoRoot "build\pyinstaller-spec"

New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null
New-Item -Path $workDir -ItemType Directory -Force | Out-Null
New-Item -Path $specDir -ItemType Directory -Force | Out-Null

Write-Host "Using Python: $PythonExe"
Write-Host "Output directory: $OutputDir"
Write-Host "Installing/updating PyInstaller..."
& $PythonExe -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install/update PyInstaller."
}

$builds = @()
if ($Target -in @("all", "server")) {
    $builds += [pscustomobject]@{ Name = "pdf2tspl-server"; Script = "scripts\run_server.py" }
}
if ($Target -in @("all", "agent")) {
    $builds += [pscustomobject]@{ Name = "pdf2tspl-agent"; Script = "scripts\run_agent.py" }
}
if ($Target -in @("all", "submit")) {
    $builds += [pscustomobject]@{ Name = "pdf2tspl-submit-job"; Script = "scripts\submit_job.py" }
}

Push-Location $RepoRoot
try {
    foreach ($build in $builds) {
        Write-Host ""
        Write-Host "Building $($build.Name)..."
        Run-PyInstallerBuild `
            -PyExe $PythonExe `
            -ProjectRoot $RepoRoot `
            -DistPath $OutputDir `
            -WorkPath $workDir `
            -SpecPath $specDir `
            -ExeName $build.Name `
            -EntryScript $build.Script `
            -UseOneFile $OneFile.IsPresent
    }

    Copy-Item -LiteralPath (Join-Path $RepoRoot "config") -Destination (Join-Path $OutputDir "config") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot "VERSION") -Destination (Join-Path $OutputDir "VERSION") -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot "README.md") -Destination (Join-Path $OutputDir "README.md") -Force

    Write-Host ""
    Write-Host "Build complete."
    Write-Host "Artifacts: $OutputDir"
} finally {
    Pop-Location
}
