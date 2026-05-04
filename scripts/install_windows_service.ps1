[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("server", "agent")]
    [string]$Mode,

    [string]$ServiceName = "",
    [string]$DisplayName = "",
    [string]$RepoRoot = "",
    [string]$PythonExe = "",
    [string]$TemplatesPath = "",
    [string]$AgentConfigPath = "",
    [string]$Host = "0.0.0.0",
    [int]$Port = 8089,
    [string]$DbPath = "",
    [string]$AuthToken = "change-me-token",
    [ValidateSet("server_managed", "webapp_managed")]
    [string]$RoutingMode = "server_managed",
    [string]$LogLevel = "INFO",
    [int]$RestartDelaySeconds = 5,
    [string]$SupervisorLogPath = "",
    [string]$NssmPath = "",
    [switch]$NoNssmDownload
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

function Quote-Arg {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + ($Value -replace '"', '""') + '"'
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
        throw "Downloaded NSSM archive did not contain win64\\nssm.exe."
    }

    Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
    if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
        throw "Unable to place nssm.exe at: $targetExe"
    }

    Write-Host "NSSM installed locally: $targetExe"
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

Assert-Admin

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot does not exist: $RepoRoot"
}

if ([string]::IsNullOrWhiteSpace($ServiceName)) {
    if ($Mode -eq "server") {
        $ServiceName = "Pdf2Tspl-Server"
    } else {
        $ServiceName = "Pdf2Tspl-Agent-$env:COMPUTERNAME"
    }
}
if ([string]::IsNullOrWhiteSpace($DisplayName)) {
    if ($Mode -eq "server") {
        $DisplayName = "PDF2TSPL Server"
    } else {
        $DisplayName = "PDF2TSPL Agent ($env:COMPUTERNAME)"
    }
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $PythonExe = $venvPython
    } else {
        $PythonExe = "python"
    }
} elseif (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
    $PythonExe = [System.IO.Path]::GetFullPath($PythonExe)
}

if ([string]::IsNullOrWhiteSpace($TemplatesPath)) {
    $TemplatesPath = Join-Path $RepoRoot "config\templates.json"
} else {
    $TemplatesPath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $TemplatesPath
}
if ([string]::IsNullOrWhiteSpace($AgentConfigPath)) {
    $AgentConfigPath = Join-Path $RepoRoot "config\agent.local.json"
} else {
    $AgentConfigPath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $AgentConfigPath
}
if ([string]::IsNullOrWhiteSpace($DbPath)) {
    $DbPath = Join-Path $RepoRoot "print_automation.db"
} else {
    $DbPath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $DbPath
}
if (-not [string]::IsNullOrWhiteSpace($SupervisorLogPath)) {
    $SupervisorLogPath = Resolve-AbsolutePath -BasePath $RepoRoot -InputPath $SupervisorLogPath
}

$supervisorScript = Join-Path $RepoRoot "scripts\run_supervised.ps1"
if (-not (Test-Path -LiteralPath $supervisorScript -PathType Leaf)) {
    throw "Missing supervisor script: $supervisorScript"
}

$pwshExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $pwshExe -PathType Leaf)) {
    throw "PowerShell executable not found at expected path: $pwshExe"
}

$argTokens = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", (Quote-Arg $supervisorScript),
    "-Mode", $Mode,
    "-RepoRoot", (Quote-Arg $RepoRoot),
    "-PythonExe", (Quote-Arg $PythonExe),
    "-TemplatesPath", (Quote-Arg $TemplatesPath),
    "-LogLevel", $LogLevel,
    "-RestartDelaySeconds", "$RestartDelaySeconds"
)
if (-not [string]::IsNullOrWhiteSpace($SupervisorLogPath)) {
    $argTokens += @("-SupervisorLogPath", (Quote-Arg $SupervisorLogPath))
}
if ($Mode -eq "server") {
    $argTokens += @(
        "-Host", $Host,
        "-Port", "$Port",
        "-DbPath", (Quote-Arg $DbPath),
        "-AuthToken", (Quote-Arg $AuthToken),
        "-RoutingMode", $RoutingMode
    )
} else {
    $argTokens += @(
        "-AgentConfigPath", (Quote-Arg $AgentConfigPath)
    )
}
$serviceArguments = $argTokens -join " "

$logsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir -PathType Container)) {
    New-Item -Path $logsDir -ItemType Directory -Force | Out-Null
}
if ($Mode -eq "server") {
    $serviceStdout = Join-Path $logsDir "server-service-output.log"
    $serviceStderr = Join-Path $logsDir "server-service-error.log"
} else {
    $serviceStdout = Join-Path $logsDir "agent-service-output.log"
    $serviceStderr = Join-Path $logsDir "agent-service-error.log"
}

$nssmExe = Resolve-NssmPath -RepoRootPath $RepoRoot -ExplicitPath $NssmPath -AllowDownload (-not $NoNssmDownload)
Write-Host "Using NSSM: $nssmExe"

& $nssmExe stop $ServiceName *> $null
& $nssmExe remove $ServiceName confirm *> $null
& sc.exe delete $ServiceName *> $null

Invoke-Nssm -ExePath $nssmExe -Args @("install", $ServiceName, $pwshExe, $serviceArguments)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "DisplayName", $DisplayName)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "Description", "PDF->TSPL $Mode process managed by NSSM and run_supervised.ps1")
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "AppDirectory", $RepoRoot)
Invoke-Nssm -ExePath $nssmExe -Args @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
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

Start-Service -Name $ServiceName

Write-Host "Windows service installed and started: $ServiceName"
Write-Host "Mode: $Mode"
Write-Host "DisplayName: $DisplayName"
Write-Host "StdOut log: $serviceStdout"
Write-Host "StdErr log: $serviceStderr"
Write-Host "To remove: .\scripts\uninstall_windows_service.ps1 -ServiceName `"$ServiceName`""
