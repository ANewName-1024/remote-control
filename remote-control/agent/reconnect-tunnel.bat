@echo off
REM ============================================================
REM SSH 反向隧道自动重连脚本
REM 使用方式: 双击运行，或加入任务计划程序定时执行
REM ============================================================
setlocal enabledelayedexpansion

set "VPS_HOST=8.137.116.121"
set "VPS_PORT=2222"
set "VPS_KEY=C:\Users\Administrator\aliyun_key.pem"
set "LOCAL_PORT=18799"
set "REMOTE_PORT=9080"
set "CHECK_INTERVAL=30"
set "MAX_TUNNEL_AGE=3600

REM 清理旧SSH进程
taskkill /F /IM ssh.exe 2>nul

echo [%date% %time%] 建立SSH反向隧道: localhost:%LOCAL_PORT% ^-> %VPS_HOST%:%REMOTE_PORT%
echo 按 Ctrl+C 停止

:ssh_connect
ssh -p %VPS_PORT% -i "%VPS_KEY%" ^
    -o ServerAliveInterval=15 ^
    -o ServerAliveCountMax=3 ^
    -o ExitOnForwardFailure=yes ^
    -o StrictHostKeyChecking=no ^
    -R 127.0.0.1:%REMOTE_PORT%:127.0.0.1:%LOCAL_PORT% ^
    -N -f root@%VPS_HOST%

set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] SSH进程退出，代码: %EXIT_CODE%

REM 非0退出码说明连接断开，等待后重连
timeout /t %CHECK_INTERVAL% /nobreak >nul
goto :ssh_connect
