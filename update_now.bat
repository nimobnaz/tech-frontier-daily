@echo off
rem Tech Frontier Daily: fetch the latest news now, then open the page.
rem Extra arguments are passed through, e.g.  update_now.bat --rebuild
setlocal
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% update.py --open %*
if errorlevel 1 (
  echo.
  echo Update did not finish cleanly. See logs\update.log for details.
  pause
)
