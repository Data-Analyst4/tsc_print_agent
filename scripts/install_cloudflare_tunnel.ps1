[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$ServiceName = "Pdf2Tspl-Tunnel",
    [string]$DisplayName = "PDF2TSPL Cloudflare Tunnel",
    [string]$TunnelToken = "",
    [string]$TokenFilePath = "",
    [string]$ConfigPath = "",
    [string]$TunnelHostname = "tspl.k95foods.com",
    [int]$LocalPort = 8089,
    [string]$CloudflaredPath = "",
    [string]$NssmPath = "",
    [switch]$NoCloudflaredDownload,
    [switch]$NoNssmDownload,
    [int]$RestartDelaySeconds = 5
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
        [string]$ExplicitPath,
        [bool]$AllowDownload = $true
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

    if (-not $AllowDownload) {
        throw "NSSM not found. Install nssm or provide -NssmPath."
    }

    $targetDir = Join-Path $RepoRootPath "scripts"
    if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
        New-Item -Path $targetDir -ItemType Directory -Force | Out-Null
    }
    $targetExe = Join-Path $targetDir "nssm.exe"

    $zipPath = Join-Path $env:TEMP "nssm-2.24.zip"
    $extractRoot = Join-Path $env:TEMP "nssm-2.24-extract"
    $extractPath = Join-Path $extractRoot "nssm-2.24"

    Write-Host "NSSM not found. Downloading nssm-2.24..."
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zipPath
    if (Test-Path -LiteralPath $extractRoot -PathType Container) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    $sourceExe = Join-Path $extractPath "win64\nssm.exe"
    if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
        throw "Downloaded NSSM archive did not contain win64\nssm.exe."
    }

    Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
    Write-Host "NSSM installed locally: $targetExe"
    return $targetExe
}

function Resolve-CloudflaredPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRootPath,
        [string]$ExplicitPath,
        [bool]$AllowDownload = $true
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $resolved = Resolve-AbsolutePath -BasePath $RepoRootPath -InputPath $ExplicitPath
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "cloudflared not found at explicit path: $resolved"
        }
        return $resolved
    }

    $candidates = @(
        (Join-Path $RepoRootPath "scripts\cloudflared.exe"),
        (Join-Path $RepoRootPath "cloudflared.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -ne $cloudflaredCommand) {
        return $cloudflaredCommand.Source
    }

    if (-not $AllowDownload) {
        throw "cloudflared not found. Install cloudflared or provide -CloudflaredPath."
    }

    $targetDir = Join-Path $RepoRootPath "scripts"
    if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
        New-Item -Path $targetDir -ItemType Directory -Force | Out-Null
    }
    $targetExe = Join-Path $targetDir "cloudflared.exe"
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

    Write-Host "cloudflared not found. Downloading latest Windows build..."
    Invoke-WebRequest -Uri $downloadUrl -OutFile $targetExe
    if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
        throw "Unable to download cloudflared to: $targetExe"
    }

    Write-Host "cloudflared installed locally: $targetExe"
    return $targetExe
}

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)][string]$ExePath,
        [Parameter(Mandatory = $true)][string[]]$Args
    )
    & $ExePath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM command failed ($LASTEXITCODE): $ExePath $($Args -join ' ')"
    }
}

function Read-TunnelToken {
    param(
        [string]$InlineToken,
        [string]$TokenPath
    )

    if (-not [string]::IsNullOrWhiteSpace($InlineToken)) {
        return $InlineToken.Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($TokenPath) -and (Test-Path -LiteralPath $TokenPath -PathType Leaf)) {
        $fromFile = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
        if (-not [string]::IsNullOrWhiteSpace($fromFile)) {
            if ($fromFile -match '^(#|PASTE_YOUR_TUNNEL_TOKEN_HERE)') {
                return ""
            }
            return $fromFile
        }
    }

    return ""
}

Assert-Admin

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot does not exist: $RepoRoot"
}

if ([string]::IsNullOrWhiteSpace($TokenFilePath)) {
    $TokenFilePath = Join-Path $RepoRoot "config\cloudflared.token"
} else {
    $TokenFilePath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $TokenFilePath
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $RepoRoot "config\cloudflared.yml"
} else {
    $ConfigPath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $ConfigPath
}

$resolvedToken = Read-TunnelToken -InlineToken $TunnelToken -TokenPath $TokenFilePath
$useConfigFile = (-not [string]::IsNullOrWhiteSpace($resolvedToken)) -eq $false -and (Test-Path -LiteralPath $ConfigPath -PathType Leaf)

if (-not $useConfigFile -and [string]::IsNullOrWhiteSpace($resolvedToken)) {
    throw @"
Cloudflare tunnel token not found.

Provide one of:
  1) -TunnelToken '<token-from-cloudflare-dashboard>'
  2) Create config\cloudflared.token with your tunnel token (one line)
  3) Create config\cloudflared.yml (see config\cloudflared.yml.example)

Expected public hostname: $TunnelHostname -> http://127.0.0.1:$LocalPort
"@
}

$cloudflaredExe = Resolve-CloudflaredPath -RepoRootPath $RepoRoot -ExplicitPath $CloudflaredPath -AllowDownload (-not $NoCloudflaredDownload)
$nssmExe = Resolve-NssmPath -RepoRootPath $RepoRoot -ExplicitPath $NssmPath -AllowDownload (-not $NoNssmDownload)

$serviceArguments = ""
if (-not [string]::IsNullOrWhiteSpace($resolvedToken)) {
    $serviceArguments = "tunnel run --token $resolvedToken"
} else {
    $serviceArguments = "tunnel --config `"$ConfigPath`" run"
}

$logsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir -PathType Container)) {
    New-Item -Path $logsDir -ItemType Directory -Force | Out-Null
}
$serviceStdout = Join-Path $logsDir "tunnel-service-output.log"
$serviceStderr = Join-Path $logsDir "tunnel-service-error.log"

Write-Host "Using cloudflared: $cloudflaredExe"
Write-Host "Using NSSM: $nssmExe"
Write-Host "Tunnel hostname target: $TunnelHostname"
Write-Host "Local upstream: http://127.0.0.1:$LocalPort"

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -ne $existingService) {
    try { & $nssmExe stop $ServiceName *> $null } catch { }
    try { & $nssmExe remove $ServiceName confirm *> $null } catch { }
    try { & sc.exe delete $ServiceName *> $null } catch { }
}

Invoke-Nssm -ExePath $nssmExe -Args @("install", $ServiceName, $cloudflaredExe, $serviceArguments)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "DisplayName", $DisplayName)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "Description", "Cloudflare tunnel for PDF2TSPL server ($TunnelHostname)")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppDirectory", $RepoRoot)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "DependOnService", "Pdf2Tspl-Server")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppStdout", $serviceStdout)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppStderr", $serviceStderr)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppRotateFiles", "1")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppRotateOnline", "1")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppRotateBytes", "10485760")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppExit", "Default", "Restart")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppRestartDelay", "$($RestartDelaySeconds * 1000)")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppThrottle", "1500")

& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 *> $null
& sc.exe failureflag $ServiceName 1 *> $null

Start-Sleep -Seconds 2
Start-Service -Name $ServiceName

Write-Host "Cloudflare tunnel service installed and started: $ServiceName"
Write-Host "Public URL (after DNS/tunnel config): https://$TunnelHostname"
Write-Host "StdOut log: $serviceStdout"
Write-Host "StdErr log: $serviceStderr"
Write-Host "To remove: .\scripts\uninstall_cloudflare_tunnel.ps1"
