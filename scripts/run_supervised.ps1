[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("server", "agent")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [string]$PythonExe = "python",
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
    [string]$SupervisorLogPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function To-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,
        [Parameter(Mandatory = $true)]
        [string]$InputPath
    )
    if ([System.IO.Path]::IsPathRooted($InputPath)) {
        return [System.IO.Path]::GetFullPath($InputPath)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $InputPath))
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot does not exist: $RepoRoot"
}

if ([string]::IsNullOrWhiteSpace($TemplatesPath)) {
    $TemplatesPath = Join-Path $RepoRoot "config\templates.json"
} else {
    $TemplatesPath = To-AbsolutePath -BasePath $RepoRoot -InputPath $TemplatesPath
}

if ([string]::IsNullOrWhiteSpace($DbPath)) {
    $DbPath = Join-Path $RepoRoot "print_automation.db"
} else {
    $DbPath = To-AbsolutePath -BasePath $RepoRoot -InputPath $DbPath
}

if ([string]::IsNullOrWhiteSpace($AgentConfigPath)) {
    $AgentConfigPath = Join-Path $RepoRoot "config\agent.local.json"
} else {
    $AgentConfigPath = To-AbsolutePath -BasePath $RepoRoot -InputPath $AgentConfigPath
}

if (-not [string]::IsNullOrWhiteSpace($PythonExe) -and (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    $PythonExe = [System.IO.Path]::GetFullPath($PythonExe)
}

if ([string]::IsNullOrWhiteSpace($SupervisorLogPath)) {
    $logsDir = Join-Path $RepoRoot "logs"
    if (-not (Test-Path -LiteralPath $logsDir -PathType Container)) {
        New-Item -Path $logsDir -ItemType Directory -Force | Out-Null
    }
    if ($Mode -eq "server") {
        $SupervisorLogPath = Join-Path $logsDir "server-supervisor.log"
    } else {
        $SupervisorLogPath = Join-Path $logsDir "agent-supervisor.log"
    }
} else {
    $SupervisorLogPath = To-AbsolutePath -BasePath $RepoRoot -InputPath $SupervisorLogPath
    $logDir = Split-Path -Parent $SupervisorLogPath
    if (-not (Test-Path -LiteralPath $logDir -PathType Container)) {
        New-Item -Path $logDir -ItemType Directory -Force | Out-Null
    }
}

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $SupervisorLogPath -Value $line
}

Set-Location -LiteralPath $RepoRoot
Write-Log "Supervisor started in '$Mode' mode. RepoRoot='$RepoRoot', PythonExe='$PythonExe'"

while ($true) {
    $scriptPath = ""
    $args = @()

    if ($Mode -eq "server") {
        $scriptPath = Join-Path $RepoRoot "scripts\run_server.py"
        $args = @(
            $scriptPath,
            "--host", $Host,
            "--port", "$Port",
            "--db", $DbPath,
            "--templates", $TemplatesPath,
            "--auth-token", $AuthToken,
            "--routing-mode", $RoutingMode,
            "--log-level", $LogLevel
        )
    } else {
        $scriptPath = Join-Path $RepoRoot "scripts\run_agent.py"
        $args = @(
            $scriptPath,
            "--config", $AgentConfigPath,
            "--templates", $TemplatesPath,
            "--log-level", $LogLevel
        )
    }

    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        Write-Log "ERROR: script not found: $scriptPath"
        Start-Sleep -Seconds ([Math]::Max(5, $RestartDelaySeconds))
        continue
    }

    Write-Log "Starting child process: $PythonExe $($args -join ' ')"
    $exitCode = 0
    try {
        & $PythonExe @args
        $exitCode = $LASTEXITCODE
    } catch {
        $exitCode = -1
        Write-Log ("Process launch failed: " + $_.Exception.Message)
    }

    Write-Log "Child process exited with code $exitCode. Restarting in $RestartDelaySeconds second(s)."
    Start-Sleep -Seconds ([Math]::Max(1, $RestartDelaySeconds))
}

