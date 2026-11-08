$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Starting Smart Surveillance System" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# 1. Add Docker to PATH if needed
$dockerBins = @(
    "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin",
    "C:\Program Files\Docker\Docker\resources\bin"
)
foreach ($bin in $dockerBins) {
    if ((Test-Path $bin) -and ($env:PATH -notlike "*$bin*")) {
        $env:PATH = "$bin;$env:PATH"
    }
}

# 2. Check if Docker is running
try {
    & docker ps 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Not running" }
} catch {
    Write-Host "[INFO] Docker Desktop is not running. Starting Docker Desktop..." -ForegroundColor Yellow
    $dockerApp = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    if (-not (Test-Path $dockerApp)) {
        $dockerApp = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    }
    if (Test-Path $dockerApp) {
        Start-Process $dockerApp
        Write-Host "[INFO] Waiting 20 seconds for Docker engine to start..." -ForegroundColor Yellow
        Start-Sleep -Seconds 20
    }
}

# 3. Start containers
Write-Host "[INFO] Starting PostgreSQL & Redis via Docker..." -ForegroundColor Green
& docker compose up postgres redis -d

# 4. Start backend and frontend via run_all.py
Write-Host "[INFO] Starting Backend and Frontend..." -ForegroundColor Green
$py = "backend\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py run_all.py

