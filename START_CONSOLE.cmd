@echo off
setlocal
cd /d "%~dp0"
title Multi-model Debate Console
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 -X utf8 console_server.py --open --port 0
    goto done
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if not errorlevel 1 (
    python -X utf8 console_server.py --open --port 0
    goto done
)
echo Python 3.9+ was not found. Install Python from https://www.python.org/downloads/
echo Enable "Add Python to PATH", then run this launcher again.
:done
echo.
echo Console stopped. Press any key to close.
pause >nul
