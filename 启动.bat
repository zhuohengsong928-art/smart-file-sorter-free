@echo off
title Smart File Sorter v2.3

:: Ensure Python is in PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

cd /d "%~dp0"

echo.
echo ==============================================
echo     Smart File Sorter v2.3.0
echo     Intelligent File Management System
echo ==============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo Please install Python 3.12+
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo   [1] Dry run (preview only, safe)
echo   [2] Organize Desktop
echo   [3] Organize Downloads
echo   [4] Organize Desktop + Downloads
echo   [5] Custom folder
echo   [0] Exit
echo.
set /p choice=Select (0-5): 

if "%choice%"=="1" goto dryrun
if "%choice%"=="2" goto desktop
if "%choice%"=="3" goto downloads
if "%choice%"=="4" goto both
if "%choice%"=="5" goto custom
if "%choice%"=="0" goto end
echo Invalid choice
pause
goto end

:dryrun
echo.
echo [Dry Run Mode]
python -m file_sorter "%USERPROFILE%\Desktop" "%USERPROFILE%\Downloads" --dry-run
goto finish

:desktop
echo.
echo [Organizing Desktop...]
python -m file_sorter "%USERPROFILE%\Desktop"
goto finish

:downloads
echo.
echo [Organizing Downloads...]
python -m file_sorter "%USERPROFILE%\Downloads"
goto finish

:both
echo.
echo [Organizing Desktop + Downloads...]
python -m file_sorter "%USERPROFILE%\Desktop" "%USERPROFILE%\Downloads"
goto finish

:custom
echo.
set /p folder=Folder path: 
echo [Organizing...]
python -m file_sorter "%folder%"
goto finish

:finish
echo.
echo ----------------------------------------------
echo   Done! Logs saved to logs/ folder
echo ----------------------------------------------
echo.
pause

:end
