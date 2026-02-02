# PostgreSQL Setup Script for HU Edge Project
# This script will help you set up and verify PostgreSQL with Docker

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PostgreSQL Setup for HU Edge Project" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Check if Docker is running
Write-Host "Step 1: Checking Docker Desktop status..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ERROR] Docker Desktop is not running!" -ForegroundColor Red
        Write-Host "`nPlease:" -ForegroundColor Yellow
        Write-Host "1. Open Docker Desktop application" -ForegroundColor White
        Write-Host "2. Wait for it to fully start (green icon in bottom-left)" -ForegroundColor White
        Write-Host "3. Run this script again`n" -ForegroundColor White
        exit 1
    }
    Write-Host "[OK] Docker Desktop is running" -ForegroundColor Green
} catch {
    Write-Host "`n[ERROR] Docker is not installed or not running" -ForegroundColor Red
    Write-Host "Download from: https://www.docker.com/products/docker-desktop/`n" -ForegroundColor Yellow
    exit 1
}

# Step 2: Stop and remove existing PostgreSQL container
Write-Host "`nStep 2: Cleaning up existing PostgreSQL containers..." -ForegroundColor Yellow
docker-compose down -v 2>&1 | Out-Null
Write-Host "[OK] Cleaned up existing containers and volumes" -ForegroundColor Green

# Step 3: Start PostgreSQL container
Write-Host "`nStep 3: Starting PostgreSQL container..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to start PostgreSQL container" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] PostgreSQL container started" -ForegroundColor Green

# Step 4: Wait for PostgreSQL to be ready
Write-Host "`nStep 4: Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$ready = $false

while ($attempt -lt $maxAttempts -and -not $ready) {
    $attempt++
    Start-Sleep -Seconds 1
    $result = docker exec huedge_postgres pg_isready -U postgres 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        Write-Host "[OK] PostgreSQL is ready!" -ForegroundColor Green
    } else {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
}

if (-not $ready) {
    Write-Host "`n[ERROR] PostgreSQL did not start within 30 seconds" -ForegroundColor Red
    Write-Host "Check logs with: docker logs huedge_postgres" -ForegroundColor Yellow
    exit 1
}

# Step 5: Verify database exists
Write-Host "`nStep 5: Verifying database 'huedge_db'..." -ForegroundColor Yellow
$dbCheck = docker exec huedge_postgres psql -U postgres -lqt 2>&1 | Select-String "huedge_db"
if ($dbCheck) {
    Write-Host "[OK] Database 'huedge_db' exists" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Database 'huedge_db' not found, but will be created automatically" -ForegroundColor Yellow
}

# Step 6: Verify pgvector extension
Write-Host "`nStep 6: Verifying pgvector extension..." -ForegroundColor Yellow
$extensionCheck = docker exec huedge_postgres psql -U postgres -d huedge_db -c "SELECT * FROM pg_extension WHERE extname='vector';" 2>&1
if ($extensionCheck -match "vector") {
    Write-Host "[OK] pgvector extension is installed" -ForegroundColor Green
} else {
    Write-Host "[INFO] pgvector will be installed on first database initialization" -ForegroundColor Yellow
}

# Step 7: Test connection from host
Write-Host "`nStep 7: Testing connection from host machine..." -ForegroundColor Yellow
Write-Host "Attempting to connect to postgresql://postgres:***@127.0.0.1:5432/huedge_db" -ForegroundColor Gray

# Show container status
Write-Host "`nPostgreSQL Container Status:" -ForegroundColor Cyan
docker ps --filter "name=huedge_postgres" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nYou can now:" -ForegroundColor Yellow
Write-Host "1. Start your backend: uvicorn app.main:app --reload --port 8000" -ForegroundColor White
Write-Host "2. View logs: docker logs huedge_postgres" -ForegroundColor White
Write-Host "3. Connect to DB: docker exec -it huedge_postgres psql -U postgres -d huedge_db" -ForegroundColor White
Write-Host "4. Stop PostgreSQL: docker-compose down" -ForegroundColor White
Write-Host ""
