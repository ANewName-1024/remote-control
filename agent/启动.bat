@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start /b pythonw.exe agent.py > nul 2>&1
