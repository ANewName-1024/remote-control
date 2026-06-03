<#
.SYNOPSIS
    Install Remote-Control Windows Agent v2.0 (dual-process).

.DESCRIPTION
    v2.0 architecture: a single Windows service runs the SYSTEM/Session 0
    "service" process. It auto-spawns a "helper" process in the active
    user session via WTSQueryUserToken + CreateProcessAsUser. The two
    communicate over two named pipes. We do NOT need a separate
    scheduled task for the helper — the service handles it.

    This script:
      - Creates %APPDATA%\RemoteControlAgent\
      - Installs Python deps into a venv at that location
      - Registers a Windows Service via nssm (auto-restart on crash)
      - Configures log rotation
      - Optionally verifies the helper spawn works

.PARAMETER EnvFile
    Path to agent env file. Defaults to deploy\.env.windows (or .env.windows.example as template).

.PARAMETER NssmPath
    Path to nssm.exe. If absent, downloads nssm 2.24 into tools\nssm\nssm.exe

.PARAMETER SkipNssm
    If set, skip service registration (manual start with run.bat).

.PARAMETER SkipVerify
    If set, skip the helper-spawn verification step.

.EXAMPLE
    pwsh ./install-windows-agent.ps1
#>
[CmdletBinding()]
param(
    [string]$EnvFile   = '',
    [string]$NssmPath  = '',
    [switch]$SkipNssm,
    [switch]$SkipVerify
)

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $EnvFile)  { $EnvFile  = Join-Path $scriptDir '.env.windows' }
if (-not $NssmPath) { $NssmPath = Join-Path $scriptDir 'tools\nssm\nssm.exe' }
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $scriptDir -Parent)  # project root

$AppName     = 'RemoteControlAgent'
$DataDir     = Join-Path $env:APPDATA $AppName
$PythonExe   = (Get-Command python -ErrorAction Stop).Source
$VenvDir     = Join-Path $DataDir 'venv'
$VenvPy      = Join-Path $VenvDir 'Scripts\python.exe'
$AgentPkg    = Join-Path (Get-Location).Path 'agent'
$ServiceName = 'RemoteControlAgent'
$HelperName  = 'RemoteControlAgent.Helper'  # not a service, just a log marker

# 1. Prepare env file
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $PSScriptRoot '.env.windows.example') $EnvFile
    Write-Host "[install] created $EnvFile -- please edit WS_URL / ACCESS_PASSWORD / AGENT_ID"
    notepad.exe $EnvFile
    $answer = Read-Host "[install] env ready? (type 'yes' to continue)"
    if ($answer -ne 'yes') { exit 1 }
}
$envContent = Get-Content $EnvFile -Raw
if ($envContent -match 'change-me') { throw "ACCESS_PASSWORD / WS_URL still has placeholder; edit $EnvFile" }
Write-Host "[install] env file: $EnvFile"

# 2. Data dir + venv
$null = New-Item -ItemType Directory -Path $DataDir -Force
$logsDir = Join-Path $DataDir 'logs'
$null = New-Item -ItemType Directory -Path $logsDir -Force
$envContent | Set-Content (Join-Path $DataDir 'agent.env') -Encoding UTF8

if (-not (Test-Path $VenvPy)) {
    Write-Host "[install] creating venv at $VenvDir"
    & $PythonExe -m venv $VenvDir
}
Write-Host "[install] installing deps"
& $VenvPy -m pip install --upgrade pip | Out-Host
& $VenvPy -m pip install -r (Join-Path $AgentPkg 'requirements.txt') | Out-Host
# dxcam needs numpy pre-installed; pull it explicitly to avoid lock contention
& $VenvPy -m pip install --target="$VenvDir\Lib\site-packages" numpy 2>$null | Out-Null
& $VenvPy -m pip install --target="$VenvDir\Lib\site-packages" comtypes 2>$null | Out-Null
& $VenvPy -m pip install --target="$VenvDir\Lib\site-packages" dxcam 2>$null | Out-Null
Write-Host "[install] import sanity check"
& $VenvPy -c "import sys; sys.path.insert(0, r'$((Get-Location).Path)'); from agent import service, helper, capture, ws_bridge, protocol; print('  all 5 agent modules import OK')"

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

    # Use a .bat wrapper so nssm can reliably set env + cwd + workdir
    $startScript = @"
@echo off
setlocal
set PYTHONIOENCODING=utf-8
"$VenvPy" -m agent --mode=service
"@
    $bat = Join-Path $DataDir 'run.bat'
    [System.IO.File]::WriteAllText($bat, $startScript, [System.Text.Encoding]::ASCII)

    # Remove existing service if any
    & $NssmPath stop  $ServiceName 2>$null
    & $NssmPath remove $ServiceName confirm 2>$null

    & $NssmPath install $ServiceName $bat
    & $NssmPath set    $ServiceName AppDirectory          $DataDir
    & $NssmPath set    $ServiceName DisplayName           "Remote Control Agent (v2.0 dual-process)"
    & $NssmPath set    $ServiceName Description           "WebSocket agent + user-session helper for remote-control VPS relay"
    & $NssmPath set    $ServiceName Start                 SERVICE_AUTO_START
    & $NssmPath set    $ServiceName AppStdout             (Join-Path $logsDir 'service-stdout.log')
    & $NssmPath set    $ServiceName AppStderr             (Join-Path $logsDir 'service-stderr.log')
    & $NssmPath set    $ServiceName AppRotateFiles        1
    & $NssmPath set    $ServiceName AppRotateBytes        10485760
    & $NssmPath set    $ServiceName AppRotateOnline       1
    # Parse env file (skip blank lines + comments) and merge into
    # nssm's AppEnvironmentExtra so the agent process actually sees
    # WS_URL / ACCESS_PASSWORD / AGENT_ID. Previously these vars were
    # only written to agent.env for human reference — the running
    # Python process never read them.
    $envExtras = @(
        'PYTHONIOENCODING=utf-8'
        "PYTHONPATH=$((Get-Location).Path)"
        'RC_MODE=service'
        "RC_CONFIG_DIR=$DataDir"
    )
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([A-Z_][A-Z0-9_]*)=(.*)$') {
            $envExtras += "$($Matches[1])=$($Matches[2])"
        }
    }
    $envExtraJoined = $envExtras -join "`n"
    & $NssmPath set    $ServiceName AppEnvironmentExtra   $envExtraJoined
    & $NssmPath set    $ServiceName AppRestartDelay       5000
    & $NssmPath set    $ServiceName AppExitTypes          All
    # Need SeTcbPrivilege for CreateProcessAsUser to spawn helper. nssm by
    # default runs as LocalSystem which already has this. No extra change.

    Write-Host "[install] service registered: $ServiceName"
    & $NssmPath start $ServiceName
    Start-Sleep -Seconds 3
    Get-Service $ServiceName

    # 5. Verify helper-spawn (Session 1 process should appear within 5s)
    if (-not $SkipVerify) {
        Write-Host "[install] waiting for helper process in user session..."
        $found = $false
        for ($i = 0; $i -lt 10; $i++) {
            $helpers = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
                Where-Object { $_.CommandLine -like '*agent*--mode=helper*' }
            if ($helpers) {
                foreach ($h in $helpers) {
                    Write-Host "  helper pid=$($h.ProcessId) session=$($h.SessionId) cmd=$($h.CommandLine)"
                }
                $found = $true
                break
            }
            Start-Sleep -Seconds 1
        }
        if (-not $found) {
            Write-Warning "[install] helper not detected in user session yet. Check logs:"
            Write-Warning "  Get-Content '$logsDir\service-stderr.log' -Tail 50"
        }
    }
}

# 6. Print summary
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "`n[install] DONE -- Agent running as Windows service '$ServiceName'"
    Write-Host "  status:    Get-Service $ServiceName"
    Write-Host "  logs:      Get-Content '$logsDir\service-stderr.log' -Tail 50 -Wait"
    Write-Host "  restart:   Restart-Service $ServiceName"
    Write-Host "  uninstall: pwsh ./uninstall-windows-agent.ps1"
    Write-Host ""
    Write-Host "[install] Architecture:"
    Write-Host "  service (nssm) -> Session 0 (SYSTEM)"
    Write-Host "                    spawns -> helper -> Session 1 (user)"
    Write-Host "                    pipes  -> \\.\pipe\RemoteControlAgent_Cmd / _Frame"
    Write-Host "                    ws     -> $((Get-Content $envFileAt -Raw | Select-String 'WS_URL=' | Select-Object -First 1))"
}
