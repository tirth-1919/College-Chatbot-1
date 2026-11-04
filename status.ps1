<#
.SYNOPSIS
    Displays comprehensive status and health checks for User and Admin services.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   AI FAQ COLLEGE CHAT BOT STATUS       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

python user.py status
python admin.py status

