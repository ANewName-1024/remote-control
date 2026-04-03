# SSH Tunnel Watchdog - auto-reconnect SSH reverse tunnel
param(
    $VPS_HOST = "8.137.116.121",
    $VPS_PORT = "2222",
    $VPS_KEY = "C:\Users\Administrator\aliyun_key.pem",
    $LOCAL_PORT = "21112",
    $REMOTE_PORT = "9081",
    $CHECK_INTERVAL = 15
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-LocalPort {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $LOCAL_PORT)
        if ($c.Connected) { $c.Close() }
        return $true
    } catch {
        return $false
    }
}

function Test-VpsConnection {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect($VPS_HOST, [int]$VPS_PORT)
        if ($c.Connected) { $c.Close() }
        return $true
    } catch {
        return $false
    }
}

function New-Tunnel {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Creating tunnel: localhost:$LOCAL_PORT -> ${VPS_HOST}:$REMOTE_PORT"
    $proc = Start-Process ssh -ArgumentList "-p $VPS_PORT -i `"$VPS_KEY`" -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes -R 127.0.0.1:${REMOTE_PORT}:127.0.0.1:$LOCAL_PORT -N -f root@$VPS_HOST" -NoNewWindow -PassThru -Wait:$false
    return $proc.Id
}

Write-Host "SSH Tunnel Watchdog started"
Write-Host "Local port: $LOCAL_PORT -> VPS:$REMOTE_PORT"
Write-Host ""

# Initial tunnel
New-Tunnel
Start-Sleep 3

while ($true) {
    Start-Sleep $CHECK_INTERVAL
    
    $localOk = Test-LocalPort
    $vpsOk = Test-VpsConnection
    
    if (-not $localOk -or -not $vpsOk) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Check failed (local=$localOk, vps=$vpsOk), reconnecting..."
        
        Get-Process ssh -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep 2
        
        New-Tunnel
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Reconnection initiated"
    }
}
