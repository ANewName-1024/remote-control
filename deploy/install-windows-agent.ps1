<#
.SYNOPSIS
    Install Remote-Control Windows Agent as a system service (nssm).
.DESCRIPTION
    - Creates %APPDATA%\RemoteControlAgent\
    - Installs Python deps into a venv at that location
    - Registers a Windows Service via nssm (auto-restart on crash)
    - Starts the service
.PARAMETER EnvFile
    Path to agent env file. Defaults to deploy\.env.windows (or .env.windows.example as template).
.PARAMETER NssmPath
    Path to nssm.exe. If absent, downloads nssm 2.24 into tools\nssm\nssm.exe
.PARAMETER SkipNssm
    If set, skip service registration (manual start with run.bat).
.EXAMPLE
    pwsh ./install-windows-agent.ps1
#>
[CmdletBinding()]
param(
    [string]$EnvFile  = '',
    [string]$NssmPath = '',
    [switch]$SkipNssm
)

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $EnvFile)  { $EnvFile  = Join-Path $scriptDir '.env.windows' }
if (-not $NssmPath) { $NssmPath = Join-Path $scriptDir 'tools\nssm\nssm.exe' }
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $scriptDir -Parent)  # project root

$AppName    = 'RemoteControlAgent'
$DataDir    = Join-Path $env:APPDATA $AppName
$PythonExe  = (Get-Command python -ErrorAction Stop).Source
$VenvDir    = Join-Path $DataDir 'venv'
$VenvPy     = Join-Path $VenvDir 'Scripts\python.exe'
$AgentSrc   = Join-Path (Get-Location).Path 'agent'
$ServiceName = 'RemoteControlAgent'

# 1. Prepare env file
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $PSScriptRoot '.env.windows.example') $EnvFile
    Write-Host "[install] created $EnvFile — please edit WS_URL / ACCESS_PASSWORD / AGENT_ID"
    notepad.exe $EnvFile
    $answer = Read-Host "[install] env ready? (type 'yes' to continue)"
    if ($answer -ne 'yes') { exit 1 }
}
$envContent = Get-Content $EnvFile -Raw
if ($envContent -match 'change-me') { throw "ACCESS_PASSWORD / WS_URL still has placeholder; edit $EnvFile" }
Write-Host "[install] env file: $EnvFile"

# 2. Data dir + venv
$null = New-Item -ItemType Directory -Path $DataDir -Force
$envContent | Set-Content (Join-Path $DataDir 'agent.env') -Encoding UTF8

if (-not (Test-Path $VenvPy)) {
    Write-Host "[install] creating venv at $VenvDir"
    & $PythonExe -m venv $VenvDir
}
Write-Host "[install] installing deps"
& $VenvPy -m pip install --upgrade pip | Out-Host
& $VenvPy -m pip install -r (Join-Path $AgentSrc 'requirements.txt') | Out-Host
# Make pyautogui FAILSAFE work on resumption
& $VenvPy -m pip install pywin32-ctypes 2>$null | Out-Null

# 3. nssm (download if missing)
if (-not $SkipNssm) {
    if (-not (Test-Path $NssmPath)) {
        Write-Host "[install] nssm not found, downloading to $NssmPath"
        $nssmDir = Split-Path $NssmPath -Parent
        $null = New-Item -ItemType Directory -Path $nssmDir -Force
        $zip = Join-Path $nssmDir 'nssm.zip'
        # 2.24 stable release
        Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $nssmDir -Force
        $src = Get-ChildItem $nssmDir -Recurse -Filter 'nssm.exe' |
            Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1
        Move-Item $src.FullName $NssmPath -Force
    }
    Write-Host "[install] nssm: $NssmPath"

    # 4. Register service
    $envFileAt = Join-Path $DataDir 'agent.env'
    $startScript = @"
@echo off
set PYTHONIOENCODING=utf-8
"$VenvPy" "$AgentSrc\agent.py"
"@
    $bat = Join-Path $DataDir 'run.bat'
    Set-Content -Path $bat -Value $startScript -Encoding ASCII

    # Remove existing service if any
    & $NssmPath stop  $ServiceName 2>$null
    & $NssmPath remove $ServiceName confirm 2>$null

    & $NssmPath install $ServiceName $bat
    & $NssmPath set    $ServiceName AppDirectory          $DataDir
    & $NssmPath set    $ServiceName DisplayName           "Remote Control Agent"
    & $NssmPath set    $ServiceName Description           "WebSocket agent for remote-control VPS relay"
    & $NssmPath set    $ServiceName Start                 SERVICE_AUTO_START
    & $NssmPath set    $ServiceName AppStdout             (Join-Path $DataDir 'agent_stdout.log')
    & $NssmPath set    $ServiceName AppStderr             (Join-Path $DataDir 'agent_stderr.log')
    & $NssmPath set    $ServiceName AppRotateFiles        1
    & $NssmPath set    $ServiceName AppRotateBytes        10485760
    & $NssmPath set    $ServiceName AppRotateOnline       1
    & $NssmPath set    $ServiceName AppEnvironmentExtra   "PYTHONIOENCODING=utf-8`nAGENT_ENV_FILE=$envFileAt"
    & $NssmPath set    $ServiceName AppRestartDelay       5000
    & $NssmPath set    $ServiceName AppExitTypes           All

    Write-Host "[install] service registered: $ServiceName"
    & $NssmPath start $ServiceName
    Start-Sleep -Seconds 2
    Get-Service $ServiceName
}

# 5. Verify
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "`n[install] DONE — Agent running as Windows service '$ServiceName'"
    Write-Host "  status:    Get-Service $ServiceName"
    Write-Host "  logs:      Get-Content '$DataDir\agent_stderr.log' -Tail 50 -Wait"
    Write-Host "  uninstall: sc.exe delete $ServiceName"
} else {
    Write-Host "`n[install] Manual mode (no nssm). Start with:"
    Write-Host "  $VenvPy $AgentSrc\agent.py"
    Write-Host "  or run.bat:  $DataDir\run.bat"
}
