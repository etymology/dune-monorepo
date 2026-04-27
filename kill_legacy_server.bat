@echo off
setlocal enabledelayedexpansion

REM Kill process serving http://localhost
REM Usage: kill_server.bat [port]
REM Default: port 80

if "%1"=="" (
    set PORT=80
) else (
    set PORT=%1
)

echo Searching for process listening on localhost:%PORT%...

REM Find the PID listening on the specified port
for /f "tokens=5 delims= " %%A in ('netstat -ano 2^>nul ^| findstr /R ":%PORT%.*LISTENING"') do (
    set PID=%%A
    if not "!PID!"=="" (
        echo Found process PID: !PID!
        taskkill /PID !PID! /F
        if !errorlevel! equ 0 (
            echo Successfully killed process on port %PORT%
            exit /b 0
        )
    )
)

echo No process found on port %PORT%
exit /b 1
