[CmdletBinding()]
param(
    [ValidateSet("server", "agent", "both")]
    [string]$Mode = "both",
    [string]$RepoRoot = "",
    [string]$IsccExe = "",
    [string]$OutputDir = "",
    [string]$AuthToken = "change-me-token",
    [string]$ServerHost = "0.0.0.0",
    [int]$ServerPort = 8089,
    [ValidateSet("server_managed", "webapp_managed")]
    [string]$RoutingMode = "server_managed",
    [string]$ServerUrl = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-Absolute {
    param([Parameter(Mandatory = $true)][string]$Value)
    return [System.IO.Path]::GetFullPath($Value)
}

function Resolve-Iscc {
    param([string]$Preferred = "")

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        $resolved = Resolve-Absolute -Value $Preferred
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "ISCC.exe not found at: $resolved"
        }
        return $resolved
    }

    $candidates = @(
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return $cmd.Source
    }

    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 first."
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Resolve-Absolute -Value (Join-Path $PSScriptRoot "..")
} else {
    $RepoRoot = Resolve-Absolute -Value $RepoRoot
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repo root not found: $RepoRoot"
}

$isccPath = Resolve-Iscc -Preferred $IsccExe

$versionFile = Join-Path $RepoRoot "VERSION"
$appVersion = if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
    (Get-Content -LiteralPath $versionFile -Raw).Trim()
} else {
    "0.0.0"
}
if ([string]::IsNullOrWhiteSpace($appVersion)) {
    $appVersion = "0.0.0"
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot "artifacts\installer\v$appVersion"
} else {
    if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
        $OutputDir = Join-Path $RepoRoot $OutputDir
    }
}
$OutputDir = Resolve-Absolute -Value $OutputDir
New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null

$issPath = Join-Path $RepoRoot "installer\windows\Pdf2TsplInstaller.iss"
if (-not (Test-Path -LiteralPath $issPath -PathType Leaf)) {
    throw "Installer script missing: $issPath"
}

Write-Host "Using ISCC: $isccPath"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "AppVersion: $appVersion"
Write-Host "OutputDir: $OutputDir"

$defines = @(
    "/DAppVersion=$appVersion",
    "/DSourceRoot=$RepoRoot",
    "/DOutputDir=$OutputDir",
    "/DSetupMode=$Mode",
    "/DSetupAuthToken=$AuthToken",
    "/DSetupServerHost=$ServerHost",
    "/DSetupServerPort=$ServerPort",
    "/DSetupRoutingMode=$RoutingMode",
    "/DSetupServerUrl=$ServerUrl"
)

& $isccPath @defines $issPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC compile failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Installer build complete."
Write-Host "Artifacts: $OutputDir"
