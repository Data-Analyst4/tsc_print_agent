[CmdletBinding()]
param(
    [string]$TaskName = "",
    [ValidateSet("server", "agent")]
    [string]$Mode = "agent"
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

Assert-Admin

if ([string]::IsNullOrWhiteSpace($TaskName)) {
    if ($Mode -eq "server") {
        $TaskName = "Pdf2Tspl-Server"
    } else {
        $TaskName = "Pdf2Tspl-Agent-$env:COMPUTERNAME"
    }
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Task not found: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task removed: $TaskName"

