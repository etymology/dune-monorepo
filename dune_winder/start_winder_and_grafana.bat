@echo off
setlocal

set "REPO_DIR=C:\DUNE\py3-ex-UK\dune_winder"
set "WINDER_EXE=%REPO_DIR%\.venv\Scripts\dune-winder.exe"
set "COMPOSE_FILE=%REPO_DIR%\docker-compose.yml"
set "GRAFANA_URL=http://localhost:3000"

if not exist "%REPO_DIR%" (
  echo Repo directory not found:
  echo   %REPO_DIR%
  exit /b 1
)

if not exist "%WINDER_EXE%" (
  echo Winder executable not found:
  echo   %WINDER_EXE%
  exit /b 1
)

if not exist "%COMPOSE_FILE%" (
  echo Docker Compose file not found:
  echo   %COMPOSE_FILE%
  exit /b 1
)

pushd "%REPO_DIR%"

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is not available on PATH. Start Docker Desktop, then retry.
  popd
  exit /b 1
)

echo Starting Grafana and Prometheus...
docker compose -f "%COMPOSE_FILE%" up -d
if errorlevel 1 (
  echo docker compose failed.
  popd
  exit /b 1
)

echo Starting DUNE Winder...
start "DUNE Winder" "%WINDER_EXE%"

echo Opening Grafana...
start "" "%GRAFANA_URL%"

popd
exit /b 0
