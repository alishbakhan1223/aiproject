@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Starting Smart Surveillance System
echo ===================================================

:: 1. Add Docker to PATH if it exists in AppData or Program Files
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin" (
    set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
)
if exist "C:\Program Files\Docker\Docker\resources\bin" (
    set "PATH=C:\Program Files\Docker\Docker\resources\bin;%PATH%"
)

:: 2. Check if Docker daemon is responsive; if not, open Docker Desktop
docker ps >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Docker daemon not responding. Launching Docker Desktop...
    if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" (
        start "" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
    ) else if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    )
    echo [INFO] Waiting 20 seconds for Docker engine to initialize...
    timeout /t 20 /nobreak >nul
)

:: 3. Start PostgreSQL and Redis containers
echo [INFO] Starting PostgreSQL and Redis containers...
docker compose up postgres redis -d

:: 4. Launch backend and frontend together
echo [INFO] Starting Backend (FastAPI) and Frontend (Vite)...
if exist "backend\venv\Scripts\python.exe" (
    backend\venv\Scripts\python.exe run_all.py
) else (
    python run_all.py
)

pause

