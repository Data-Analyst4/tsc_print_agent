[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("server", "agent")]
    [string]$Mode,

    [string]$TaskName = "",
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
    [ValidateSet("system", "current_user")]
    [string]$RunAs = "system"
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

Assert-Admin

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot does not exist: $RepoRoot"
}

if ([string]::IsNullOrWhiteSpace($TaskName)) {
    if ($Mode -eq "server") {
        $TaskName = "Pdf2Tspl-Server"
    } else {
        $TaskName = "Pdf2Tspl-Agent-$env:COMPUTERNAME"
    }
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $PythonExe = $venvPython
    } else {
        $PythonExe = "python"
    }
}

if ([string]::IsNullOrWhiteSpace($TemplatesPath)) {
    $TemplatesPath = Join-Path $RepoRoot "config\templates.json"
}
if ([string]::IsNullOrWhiteSpace($AgentConfigPath)) {
    $AgentConfigPath = Join-Path $RepoRoot "config\agent.local.json"
}
if ([string]::IsNullOrWhiteSpace($DbPath)) {
    $DbPath = Join-Path $RepoRoot "print_automation.db"
}

$supervisorScript = Join-Path $RepoRoot "scripts\run_supervised.ps1"
if (-not (Test-Path -LiteralPath $supervisorScript -PathType Leaf)) {
    throw "Missing supervisor script: $supervisorScript"
}

$pwshExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
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

$actionArguments = $argTokens -join " "
$action = New-ScheduledTaskAction -Execute $pwshExe -Argument $actionArguments -WorkingDirectory $RepoRoot
$triggers = @(
    (New-ScheduledTaskTrigger -AtStartup)
    (New-ScheduledTaskTrigger -AtLogOn)
)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if ($RunAs -eq "system") {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description "Auto-start PDF->TSPL $Mode process on boot/logon with auto-restart" `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Scheduled task installed and started: $TaskName"
Write-Host "Mode: $Mode"
Write-Host "RunAs: $RunAs"
Write-Host "To remove: .\scripts\uninstall_windows_autostart.ps1 -TaskName $TaskName"
