<#
.SYNOPSIS
    One-shot VPS deploy: build tarball, upload, run install on remote.
.DESCRIPTION
    - Builds server/ + deploy/ tarball via build-tar.ps1
    - SCPs tarball + .env + systemd unit to VPS
    - SSHes in and runs vps-install.sh
    - Verifies service is up
.PARAMETER VpsHost
    VPS hostname or IP (default 8.137.116.121)
.PARAMETER VpsPort
    SSH port (default 2222)
.PARAMETER VpsUser
    SSH user (default root)
.PARAMETER KeyPath
    Path to SSH private key (default %USERPROFILE%\.ssh\id_rsa_vps)
.PARAMETER EnvFile
    Path to .env file to upload. If omitted, prompts for password.
.EXAMPLE
    pwsh ./deploy-vps.ps1
    pwsh ./deploy-vps.ps1 -EnvFile C:\secrets\rc-server.env
#>
[CmdletBinding()]
param(
    [string]$VpsHost  = '8.137.116.121',
    [int]   $VpsPort  = 2222,
    [string]$VpsUser  = 'root',
    [string]$KeyPath  = (Join-Path $env:USERPROFILE '.ssh\id_rsa_vps'),
    [string]$EnvFile  = ''
)

# PS 5.1 quirk: $PSScriptRoot is empty when invoked via -File under some hosts.
# Fall back to MyInvocation.Definition for portability.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $scriptDir -Parent)  # project root

# ----------------------------------------------------------------------
# Helper: run a command on the remote via ssh, routing through cmd /c.
#
# PowerShell 5.1 has known issues with `& ssh ...` and `& scp ...`:
#   - `< file` and `<<< here-string` redirections are not supported
#   - argument splitting on `$variable "arg"` produces a single argv
#     element (e.g. "root@hostbash -c ..." as the hostname)
#   - $LASTEXITCODE on warnings (e.g. BSD tar stderr) reports non-zero
#
# Routing through `cmd /c "..."` sidesteps all of these: cmd handles its
# own quoting, redirections, and we check the tarball exists instead of
# relying on $LASTEXITCODE alone.
#
# IMPORTANT — exit code capture.
#   `cmd /c $Cmd` writes the command's stdout to PowerShell's output
#   stream. If we let that flow out of the function and the caller does
#   `$rc = Invoke-Remote ...`, $rc becomes an *array* of [output_lines,
#   return_value] and `if ($rc -ne 0)` does element-wise comparison,
#   sometimes matching a stray "0)" in the output and passing.
#   We must capture cmd /c output to a *local* variable so the function
#   emits only the integer exit code.
# ----------------------------------------------------------------------
function Invoke-Remote {
    param(
        [Parameter(Mandatory)]
        [string]$Cmd,
        [switch]$SuppressOutput
    )
    # The script sets $ErrorActionPreference = 'Stop' at the top, which on
    # PowerShell 5.1 turns ANY stderr line from a native command into a
    # terminating NativeCommandError — even harmless `Warning:` from
    # systemd. Temporarily relax to SilentlyContinue so cmd /c's output
    # (including stderr) flows cleanly to $output without aborting.
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $output = cmd /c $Cmd 2>&1
    } finally {
        $ErrorActionPreference = $prevPref
    }
    $exitCode = $LASTEXITCODE
    if (-not $SuppressOutput) {
        # Out-Host writes to the host display without polluting the
        # function's output stream. Write-Host/Write-Output would make
        # the caller see an array `[output_lines, $exitCode]` instead of
        # a clean integer when they do `$rc = Invoke-Remote ...`.
        $output | Out-Host
    }
    if ($exitCode -ne 0) {
        Write-Host "[deploy] non-zero exit ($exitCode): $Cmd" -ForegroundColor Yellow
    }
    return $exitCode
}

$remote      = "$VpsUser@${VpsHost}"
$remoteColon = "${remote}:"
$remoteTar   = "/tmp/remote-control-server.tar.gz"

# 1. Build tarball
$distDir = Join-Path $scriptDir 'dist'
& (Join-Path $scriptDir 'build-tar.ps1') -OutDir $distDir
$tarball = Get-ChildItem $distDir -Filter '*.tar.gz' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $tarball) { throw "no tarball produced" }
Write-Host "[deploy] tarball: $($tarball.FullName)"

# 2. Resolve .env (file or prompt)
if (-not $EnvFile) {
    $EnvFile = Join-Path $scriptDir '.env.vps'
    if (-not (Test-Path $EnvFile)) {
        Copy-Item (Join-Path $scriptDir '.env.vps.example') $EnvFile
        Write-Host "[deploy] created template at $EnvFile - please edit ACCESS_PASSWORD then re-run"
        Write-Host "  (you can also pass -EnvFile <path> to use a custom env file)"
        notepad.exe $EnvFile
        $answer = Read-Host "[deploy] .env ready? (type 'yes' to continue)"
        if ($answer -ne 'yes') { Write-Host "aborted"; exit 1 }
    }
}
$envPasswordLine = Get-Content $EnvFile | Where-Object { $_ -match '^\s*ACCESS_PASSWORD\s*=' } | Select-Object -First 1
if (-not $envPasswordLine -or $envPasswordLine -match 'change-me|change-ring') {
    throw "ACCESS_PASSWORD still has placeholder value; edit $EnvFile"
}
Write-Host "[deploy] .env: $EnvFile"

# 3. SCP upload
Write-Host "[deploy] uploading tarball to ${VpsHost}:/tmp/"
$rc = Invoke-Remote "scp -P $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no `"$($tarball.FullName)`" `"${remoteColon}${remoteTar}`""
if ($rc -ne 0) { throw "scp tarball failed (exit $rc)" }

Write-Host "[deploy] ensuring deploy dir exists on VPS"
$rc = Invoke-Remote "ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote mkdir -p /opt/remote-control/server /opt/remote-control/deploy"
if ($rc -ne 0) { throw "remote mkdir failed (exit $rc)" }

Write-Host "[deploy] uploading .env"
$rc = Invoke-Remote "scp -P $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no `"$EnvFile`" `"${remoteColon}/opt/remote-control/server/.env.tmp`""
if ($rc -ne 0) { throw "scp .env failed (exit $rc)" }

Write-Host "[deploy] uploading systemd unit"
$rc = Invoke-Remote "scp -P $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no `"$scriptDir\remote-control.service`" `"${remoteColon}/etc/systemd/system/remote-control.service`""
if ($rc -ne 0) { throw "scp service file failed (exit $rc)" }

# 4. Run install remotely
Write-Host "[deploy] running vps-install.sh on $VpsHost"
# 1) move .env into final location and chmod 600
#    Use `&&` to chain — avoids needing nested `bash -c "..."` quotes
#    (which PowerShell+cmd quoting has been painful with).
$mvCmd = "mkdir -p /opt/remote-control/server && mv -f /opt/remote-control/server/.env.tmp /opt/remote-control/server/.env && chmod 600 /opt/remote-control/server/.env"
$rc = Invoke-Remote "ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote `"$mvCmd`""
if ($rc -ne 0) { throw "remote mkdir/mv failed (exit $rc)" }

# 2) stream vps-install.sh through ssh stdin (via type + pipe to avoid
#    PS 5.1's `<` redirect limitation with &-invocation).
# IMPORTANT: Write WITHOUT UTF-8 BOM. PS 5.1's Set-Content -Encoding UTF8
# emits a BOM, which causes bash to error on the shebang line.
$installStdin = Join-Path ([System.IO.Path]::GetTempPath()) "rc-install-$(Get-Random).sh"
$utf8NoBom    = [System.Text.UTF8Encoding]::new($false)
$scriptText   = [System.IO.File]::ReadAllText((Join-Path $scriptDir 'vps-install.sh'))
[System.IO.File]::WriteAllText($installStdin, $scriptText, $utf8NoBom)
try {
    $rc = Invoke-Remote "type `"$installStdin`" | ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote bash -s -- $remoteTar"
}
finally {
    Remove-Item $installStdin -ErrorAction SilentlyContinue
}
if ($rc -ne 0) { throw "vps-install.sh failed (exit $rc)" }

# 5. Verify
Write-Host "[deploy] verifying service status"
$rc = Invoke-Remote "ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote systemctl is-active remote-control"
if ($rc -ne 0) { throw "service not active (exit $rc)" }
Invoke-Remote "ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote systemctl status remote-control --no-pager"

Write-Host "[deploy] verifying HTTP probe (local on VPS)"
$rc = Invoke-Remote "ssh -p $VpsPort -i `"$KeyPath`" -o StrictHostKeyChecking=no $remote curl -fsS -o /dev/null -w `"status=%{http_code}\n`" http://127.0.0.1:21112/"
if ($rc -ne 0) { throw "HTTP probe failed (exit $rc)" }

Write-Host ""
Write-Host "[deploy] DONE - VPS relay deployed"
Write-Host "  nginx proxies:  http://${VpsHost}:9080  https://${VpsHost}:8443  ->  relay:21112"
Write-Host "  logs:           ssh $remote journalctl -u remote-control -f"
Write-Host "  status:         ssh $remote systemctl status remote-control"
Write-Host ""
