@echo off
rem Daily sync for Marketing Data Hub - run by Windows Task Scheduler.
rem Portable: finds the repo from this script's own location, so it works
rem on any machine without editing. Logs to logs\sync.log.
rem
rem If "python" is not on PATH in the Task Scheduler context, set the full
rem path once, e.g.:  set PYTHON=C:\Users\you\AppData\...\python.exe
setlocal
pushd "%~dp0.."
set "HUB_DIR=%CD%"
if not defined PYTHON set "PYTHON=python"
if not exist "%HUB_DIR%\logs" mkdir "%HUB_DIR%\logs"
echo [%date% %time%] sync starting >> "%HUB_DIR%\logs\sync.log"
"%PYTHON%" -m hub.cli sync all --config "%HUB_DIR%\config.yaml" >> "%HUB_DIR%\logs\sync.log" 2>&1
echo [%date% %time%] sync finished with exit code %errorlevel% >> "%HUB_DIR%\logs\sync.log"
popd
endlocal
