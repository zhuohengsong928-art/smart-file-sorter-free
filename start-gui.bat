@echo off
REM Smart File Sorter - GUI launcher (v2.4.0)
REM Starts the graphical interface. Requires Python 3.9+ in PATH.
cd /d %~dp0
python -m file_sorter.gui
if errorlevel 1 (
  echo.
  echo Failed to start. Please make sure Python 3.9+ is installed and in PATH.
  pause
)
