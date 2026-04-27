@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "WORKSPACE=%%~fI"

set "PYTHONPATH=%WORKSPACE%\src"
pushd "%WORKSPACE%" >nul || (
    echo Failed to change directory to "%WORKSPACE%".
    exit /b 1
)

start "" "%WORKSPACE%\.venv\Scripts\python.exe" -m dune_winder %*
timeout /t 2 /nobreak >nul
start "" "http://localhost:8080"
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
