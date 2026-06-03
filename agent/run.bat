@echo off
rem -m agent requires the parent dir on sys.path (so the gent package is importable). We cd to the parent and explicitly point to the agent/ directory.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
python.exe -m agent --mode=auto < nul >> "%APPDATA%\RemoteControlAgent\stdout.log" 2>&1
