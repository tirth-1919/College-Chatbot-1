<#
.SYNOPSIS
    Stops all project-managed services (User Side and Admin Side).
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Stopping all AI FAQ College Chat Bot services..." -ForegroundColor Cyan
python user.py stop
python admin.py stop
Write-Host "All project services have been stopped." -ForegroundColor Green

