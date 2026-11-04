<#
.SYNOPSIS
    Starts User Side services (Backend :8000, Frontend :3000).
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
python user.py

