@echo off
cd /d "%~dp0"
rem Chinese output from Python and the CLI is UTF-8; the default console code page would garble it.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist opencode.json (
  echo Run setup first: python debate_tools.py setup --mapping model_map.json --non-interactive
  pause
  exit /b 1
)

rem The debate runs through run_debate.py: each seat is a real `opencode run`
rem session. The harness subagent tool in 2.0.30 fails with
rem "Subagent session not found", so the chair cannot launch seats itself.
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found in PATH.
  pause
  exit /b 1
)

python debate_tools.py doctor
if errorlevel 1 (
  echo Preflight failed. Fix the checks above before starting the debate.
  pause
  exit /b 1
)

python run_debate.py all
pause
