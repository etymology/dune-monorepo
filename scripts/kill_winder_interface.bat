@echo off
setlocal

set "PORT=8080"
set "FOUND_PID="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "FOUND_PID=%%P"
    goto :kill_pid
)

echo No listening process found on localhost:%PORT%.
exit /b 1

:kill_pid
echo Killing process with PID %FOUND_PID% on port %PORT%...
taskkill /PID %FOUND_PID% /F
exit /b %ERRORLEVEL%
