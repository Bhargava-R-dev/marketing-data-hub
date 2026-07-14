@echo off
rem Daily sync for Marketing Data Hub - run by Windows Task Scheduler.
rem Logs to logs\sync.log so failures are visible after the fact.
set HUB_DIR=C:\Users\Laptop-577\Documents\data collection
if not exist "%HUB_DIR%\logs" mkdir "%HUB_DIR%\logs"
echo [%date% %time%] sync starting >> "%HUB_DIR%\logs\sync.log"
"C:\Users\Laptop-577\AppData\Local\Programs\Python\Python312\python.exe" -m hub.cli sync all --config "%HUB_DIR%\config.yaml" >> "%HUB_DIR%\logs\sync.log" 2>&1
echo [%date% %time%] sync finished with exit code %errorlevel% >> "%HUB_DIR%\logs\sync.log"
