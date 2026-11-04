<#
.SYNOPSIS
    Starts all AI FAQ College Chat Bot services (User Side & Admin Side).
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    AI FAQ COLLEGE CHAT BOT (ALL)       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/2] Launching User Side (Backend :8000, Frontend :3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python user.py" -WorkingDirectory $ScriptDir

Write-Host "[2/2] Launching Admin Side (Backend :8001, Frontend :3001)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python admin.py" -WorkingDirectory $ScriptDir

Write-Host ""
Write-Host "Both services launched in independent process windows." -ForegroundColor Green
Write-Host "User Side:  Frontend http://localhost:3000 | Backend http://localhost:8000" -ForegroundColor Gray
Write-Host "Admin Side: Frontend http://localhost:3001 | Backend http://localhost:8001" -ForegroundColor Gray
Write-Host "Run .\status.ps1 anytime to check status and health." -ForegroundColor Gray

