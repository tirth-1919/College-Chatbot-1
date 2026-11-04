<#
.SYNOPSIS
    Starts Admin Side services (Backend :8001, Frontend :3001).
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
python admin.py

