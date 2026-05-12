@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "WORKSPACE=%%~fI"

set "PYTHONPATH=%WORKSPACE%\src"
set "PLC_SHADOW_MODE=False"
pushd "%WORKSPACE%" >nul || (
    echo Failed to change directory to "%WORKSPACE%".
    exit /b 1
)

"%WORKSPACE%\.venv\Scripts\python.exe" -m dune_winder %*
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
