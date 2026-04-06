@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python.exe agent.py < nul >> "%APPDATA%\RemoteControlAgent\stdout.log" 2>&1
