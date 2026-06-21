[CmdletBinding()]
param(
    [string]$ServiceName = "Pdf2Tspl-Tunnel",
    [string]$RepoRoot = "",
    [string]$NssmPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated PowerShell window (Run as Administrator)."
    }
}

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$InputPath
    )
    if ([System.IO.Path]::IsPathRooted($InputPath)) {
        return [System.IO.Path]::GetFullPath($InputPath)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $InputPath))
}

function Resolve-NssmPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRootPath,
        [string]$ExplicitPath
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $resolved = Resolve-AbsolutePath -BasePath $RepoRootPath -InputPath $ExplicitPath
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "NSSM not found at explicit path: $resolved"
        }
        return $resolved
    }

    $candidates = @(
        (Join-Path $RepoRootPath "scripts\nssm.exe"),
        (Join-Path $RepoRootPath "nssm.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $nssmCommand = Get-Command nssm -ErrorAction SilentlyContinue
    if ($null -ne $nssmCommand) {
        return $nssmCommand.Source
    }

    return ""
}

Assert-Admin

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}

$nssmExe = Resolve-NssmPath -RepoRootPath $RepoRoot -ExplicitPath $NssmPath

if (-not [string]::IsNullOrWhiteSpace($nssmExe)) {
    & $nssmExe stop $ServiceName *> $null
    & $nssmExe remove $ServiceName confirm *> $null
} else {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
}

& sc.exe delete $ServiceName *> $null

Write-Host "Cloudflare tunnel service removed (if present): $ServiceName"
