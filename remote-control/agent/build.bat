@echo off
echo ========================================
echo RemoteControlAgent Build Script
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.8+ first.
    pause
    exit /b 1
)

REM Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip not found.
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM Build with PyInstaller
echo [2/3] Building executable...
pyinstaller --clean --noconfirm --onedir --windowed --name RemoteControlAgent agent.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo [3/3] Done!
echo.
echo Executable location:
echo   dist\RemoteControlAgent\RemoteControlAgent.exe
echo.
echo To run:
echo   dist\RemoteControlAgent\RemoteControlAgent.exe
echo.
echo To copy to another PC, copy the entire folder:
echo   dist\RemoteControlAgent\
echo.
pause
