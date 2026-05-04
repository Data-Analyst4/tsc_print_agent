[CmdletBinding()]
param(
    [ValidateSet("server", "agent", "both")]
    [string]$Mode = "both",

    [string]$InstallDir = "C:\Pdf2Tspl",
    [string]$SourceDir = "",
    [string]$PythonExe = "",
    [bool]$InstallPythonIfMissing = $true,
    [switch]$SkipServiceInstall,

    [string]$AuthToken = "change-me-token",
    [string]$ServerHost = "0.0.0.0",
    [int]$ServerPort = 8089,
    [ValidateSet("server_managed", "webapp_managed")]
    [string]$RoutingMode = "server_managed",

    [string]$ServerUrl = "",
    [string]$AgentConfigPath = "",
    [string]$AgentId = "",
    [string]$AgentName = "",
    [string]$WorkstationId = "",
    [string]$PrinterName = "TSC_TE244",
    [string[]]$Groups = @("shipping"),
    [string[]]$Templates = @("label_4x3_pdf_3x4", "label_4x6"),
    [int]$RollWidthMm = 100,
    [int]$RollHeightMm = 75,
    [string]$SizeCode = "4x3",
    [switch]$OverwriteAgentConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run setup_windows.ps1 from an elevated PowerShell window (Run as Administrator)."
    }
}

function Resolve-AbsolutePath {
    param([Parameter(Mandatory = $true)][string]$PathValue)
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host ""
    Write-Host "==> $Label"
    & $Action
}

function Read-AppVersion {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    $versionFile = Join-Path $ProjectRoot "VERSION"
    if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) {
        return "0.0.0"
    }
    $value = (Get-Content -LiteralPath $versionFile -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return "0.0.0"
    }
    return $value
}

function Copy-ProjectFiles {
    param(
        [Parameter(Mandatory = $true)][string]$FromDir,
        [Parameter(Mandatory = $true)][string]$ToDir
    )

    if ($FromDir -ieq $ToDir) {
        Write-Host "Using in-place source as install dir: $ToDir"
        return
    }

    if ($ToDir.StartsWith($FromDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "InstallDir cannot be inside SourceDir. Choose a different -InstallDir."
    }

    if (-not (Test-Path -LiteralPath $ToDir -PathType Container)) {
        New-Item -Path $ToDir -ItemType Directory -Force | Out-Null
    }

    $robocopyArgs = @(
        $FromDir,
        $ToDir,
        "/E",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/XD", ".git", ".venv", "__pycache__", "logs", "agent_work",
        "/XF", "*.pyc"
    )
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }

    Write-Host "Project copied to: $ToDir"
}

function Resolve-PythonPath {
    param(
        [string]$PreferredPython = "",
        [string]$InstallRoot = ""
    )

    if (-not [string]::IsNullOrWhiteSpace($PreferredPython)) {
        $candidate = Resolve-AbsolutePath -PathValue $PreferredPython
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Provided PythonExe does not exist: $candidate"
        }
        return $candidate
    }

    if (-not [string]::IsNullOrWhiteSpace($InstallRoot)) {
        $venvCandidate = Join-Path $InstallRoot ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $venvCandidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($venvCandidate)
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        try {
            $pyPath = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
            if (-not [string]::IsNullOrWhiteSpace($pyPath) -and (Test-Path -LiteralPath $pyPath -PathType Leaf)) {
                return [System.IO.Path]::GetFullPath($pyPath)
            }
        } catch {
            # Fall through to next candidate.
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCmd -and -not [string]::IsNullOrWhiteSpace($pythonCmd.Source)) {
        return [System.IO.Path]::GetFullPath($pythonCmd.Source)
    }

    return ""
}

function Install-Python311 {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($null -ne $winget) {
        Write-Host "Installing Python 3.11 using winget..."
        & winget install --id Python.Python.3.11 -e --accept-package-agreements --accept-source-agreements --scope machine
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Write-Warning "winget install returned exit code $LASTEXITCODE. Falling back to python.org installer."
    }

    $installerPath = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
    Write-Host "Downloading Python installer..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $installerPath
    Write-Host "Running Python installer..."
    $proc = Start-Process -FilePath $installerPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Python installer failed with exit code $($proc.ExitCode)."
    }
}

function Ensure-VenvAndRequirements {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$BasePython
    )

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        & $BasePython -m venv (Join-Path $ProjectRoot ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment."
        }
    }

    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip inside .venv"
    }

    $requirementsPath = Join-Path $ProjectRoot "requirements.txt"
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements.txt"
    }

    return [System.IO.Path]::GetFullPath($venvPython)
}

function Ensure-AgentConfig {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigPath,
        [Parameter(Mandatory = $true)][string]$ServerBaseUrl,
        [Parameter(Mandatory = $true)][string]$Token
    )

    $configDir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path -LiteralPath $configDir -PathType Container)) {
        New-Item -Path $configDir -ItemType Directory -Force | Out-Null
    }

    $machine = $env:COMPUTERNAME.ToLowerInvariant()
    $resolvedAgentId = if ([string]::IsNullOrWhiteSpace($AgentId)) { "agent_$machine" } else { $AgentId }
    $resolvedWorkstationId = if ([string]::IsNullOrWhiteSpace($WorkstationId)) { "ws_$machine" } else { $WorkstationId }
    $resolvedAgentName = if ([string]::IsNullOrWhiteSpace($AgentName)) { "$env:COMPUTERNAME Agent" } else { $AgentName }
    $normalizedSizeCode = $SizeCode.Trim().ToLowerInvariant()

    $configObject = $null
    if ((Test-Path -LiteralPath $ConfigPath -PathType Leaf) -and -not $OverwriteAgentConfig) {
        $configObject = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    }

    if ($null -eq $configObject) {
        $configObject = [ordered]@{
            agent_id = $resolvedAgentId
            agent_name = $resolvedAgentName
            workstation_id = $resolvedWorkstationId
            server_url = $ServerBaseUrl
            auth_token = $Token
            poll_interval_seconds = 2.0
            heartbeat_interval_seconds = 8.0
            download_timeout_seconds = 20.0
            download_max_retries = 4
            work_dir = "./agent_work"
            printer_name = $PrinterName
            printers = @(
                [ordered]@{
                    name = $PrinterName
                    roll_width_mm = $RollWidthMm
                    roll_height_mm = $RollHeightMm
                    size_code = $normalizedSizeCode
                    is_default = $true
                }
            )
            templates = $Templates
            groups = $Groups
            max_job_retries = 2
        }
    } else {
        $configObject.agent_id = $resolvedAgentId
        $configObject.agent_name = $resolvedAgentName
        $configObject.workstation_id = $resolvedWorkstationId
        $configObject.server_url = $ServerBaseUrl
        $configObject.auth_token = $Token
        if ([string]::IsNullOrWhiteSpace([string]$configObject.printer_name)) {
            $configObject.printer_name = $PrinterName
        }
        if ($null -eq $configObject.groups -or @($configObject.groups).Count -eq 0) {
            $configObject.groups = $Groups
        }
        if ($null -eq $configObject.templates -or @($configObject.templates).Count -eq 0) {
            $configObject.templates = $Templates
        }
        if ($null -eq $configObject.printers -or @($configObject.printers).Count -eq 0) {
            $configObject.printers = @(
                [ordered]@{
                    name = $PrinterName
                    roll_width_mm = $RollWidthMm
                    roll_height_mm = $RollHeightMm
                    size_code = $normalizedSizeCode
                    is_default = $true
                }
            )
        }
    }

    $json = $configObject | ConvertTo-Json -Depth 10
    Set-Content -LiteralPath $ConfigPath -Value $json -Encoding UTF8
}

function Install-Services {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$VenvPythonPath,
        [Parameter(Mandatory = $true)][string]$EffectiveAgentConfigPath
    )

    $serviceInstaller = Join-Path $ProjectRoot "scripts\install_windows_service.ps1"
    if (-not (Test-Path -LiteralPath $serviceInstaller -PathType Leaf)) {
        throw "Service installer missing: $serviceInstaller"
    }

    if ($Mode -in @("server", "both")) {
        & $serviceInstaller `
            -Mode server `
            -RepoRoot $ProjectRoot `
            -PythonExe $VenvPythonPath `
            -Host $ServerHost `
            -Port $ServerPort `
            -AuthToken $AuthToken `
            -RoutingMode $RoutingMode
    }

    if ($Mode -in @("agent", "both")) {
        & $serviceInstaller `
            -Mode agent `
            -RepoRoot $ProjectRoot `
            -PythonExe $VenvPythonPath `
            -AgentConfigPath $EffectiveAgentConfigPath
    }
}

Assert-Admin

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = $scriptRoot
}

$SourceDir = Resolve-AbsolutePath -PathValue $SourceDir
$InstallDir = Resolve-AbsolutePath -PathValue $InstallDir

if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
    throw "SourceDir does not exist: $SourceDir"
}

Invoke-Step -Label "Copying project files" -Action {
    Copy-ProjectFiles -FromDir $SourceDir -ToDir $InstallDir
}

$resolvedPython = Resolve-PythonPath -PreferredPython $PythonExe -InstallRoot $InstallDir
if ([string]::IsNullOrWhiteSpace($resolvedPython)) {
    if (-not $InstallPythonIfMissing) {
        throw "Python 3.11+ not found. Re-run with -InstallPythonIfMissing `$true or provide -PythonExe."
    }
    Invoke-Step -Label "Installing Python 3.11" -Action {
        Install-Python311
    }
    $resolvedPython = Resolve-PythonPath -PreferredPython "" -InstallRoot $InstallDir
    if ([string]::IsNullOrWhiteSpace($resolvedPython)) {
        throw "Python install completed but python executable was not found. Restart terminal and re-run setup."
    }
}

$venvPython = ""
Invoke-Step -Label "Creating virtualenv and installing dependencies" -Action {
    $script:venvPython = Ensure-VenvAndRequirements -ProjectRoot $InstallDir -BasePython $resolvedPython
}

$effectiveServerUrl = $ServerUrl.Trim()
if ([string]::IsNullOrWhiteSpace($effectiveServerUrl)) {
    if ($Mode -in @("server", "both")) {
        $effectiveServerUrl = "http://127.0.0.1:$ServerPort"
    } else {
        throw "For Mode=agent, provide -ServerUrl (example: http://192.168.1.20:8089)."
    }
}

$effectiveAgentConfigPath = $AgentConfigPath.Trim()
if ([string]::IsNullOrWhiteSpace($effectiveAgentConfigPath)) {
    $effectiveAgentConfigPath = Join-Path $InstallDir "config\agent.local.json"
} else {
    if (-not [System.IO.Path]::IsPathRooted($effectiveAgentConfigPath)) {
        $effectiveAgentConfigPath = Join-Path $InstallDir $effectiveAgentConfigPath
    }
    $effectiveAgentConfigPath = Resolve-AbsolutePath -PathValue $effectiveAgentConfigPath
}

if ($Mode -in @("agent", "both")) {
    Invoke-Step -Label "Preparing agent config" -Action {
        Ensure-AgentConfig -ConfigPath $effectiveAgentConfigPath -ServerBaseUrl $effectiveServerUrl -Token $AuthToken
    }
}

if (-not $SkipServiceInstall) {
    Invoke-Step -Label "Installing Windows services" -Action {
        Install-Services -ProjectRoot $InstallDir -VenvPythonPath $venvPython -EffectiveAgentConfigPath $effectiveAgentConfigPath
    }
}

$appVersion = Read-AppVersion -ProjectRoot $InstallDir

Write-Host ""
Write-Host "Setup completed."
Write-Host "App version: $appVersion"
Write-Host "InstallDir: $InstallDir"
Write-Host "Mode: $Mode"
Write-Host "Python: $venvPython"
if ($Mode -in @("agent", "both")) {
    Write-Host "Agent config: $effectiveAgentConfigPath"
    Write-Host "Agent server_url: $effectiveServerUrl"
}
if ($Mode -in @("server", "both")) {
    Write-Host "Health URL: http://127.0.0.1:$ServerPort/health"
    Write-Host "Admin URL: http://127.0.0.1:$ServerPort/admin"
}
if ($SkipServiceInstall) {
    Write-Host "Service install skipped. Start manually with:"
    Write-Host "  $venvPython .\scripts\run_server.py --host $ServerHost --port $ServerPort --auth-token $AuthToken --routing-mode $RoutingMode"
    Write-Host "  $venvPython .\scripts\run_agent.py --config $effectiveAgentConfigPath --templates .\config\templates.json"
}
