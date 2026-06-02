<#
.SYNOPSIS
    Uninstall Remote-Control Windows Agent v2.0.

.DESCRIPTION
    Stops and removes the nssm-registered service. Does NOT delete
    the data dir or venv (so logs are preserved for inspection).
    Pass -Purge to also delete %APPDATA%\RemoteControlAgent\.

.EXAMPLE
    pwsh ./uninstall-windows-agent.ps1         # just remove service
    pwsh ./uninstall-windows-agent.ps1 -Purge  # also wipe data dir
#>
[CmdletBinding()]
param(
    [switch]$Purge
)

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
$NssmPath  = Join-Path $scriptDir 'tools\nssm\nssm.exe'
$ServiceName = 'RemoteControlAgent'
$DataDir   = Join-Path $env:APPDATA $ServiceName
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $NssmPath)) {
    Write-Warning "nssm not found at $NssmPath; trying sc.exe instead"
    Stop-Service $ServiceName -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName
} else {
    & $NssmPath stop   $ServiceName
    & $NssmPath remove $ServiceName confirm
}

# Also kill any orphan helper process running in user session
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*agent*--mode=helper*' } |
    ForEach-Object {
        Write-Host "killing helper pid=$($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

if ($Purge -and (Test-Path $DataDir)) {
    Write-Host "purging $DataDir"
    Remove-Item $DataDir -Recurse -Force
}
Write-Host "[uninstall] done"
