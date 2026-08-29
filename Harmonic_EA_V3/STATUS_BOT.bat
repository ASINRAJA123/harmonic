@echo off
title Harmonic EA V3 - Status Checker
echo ===================================================================
echo HARMONIC EA V3 BOT STATUS
echo ===================================================================
powershell -Command "
$procs = Get-Process -Name 'python', 'pythonw' -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*harmonic_live_exness.py*' -or $_.Path -like '*python*' }
if ($procs) {
    Write-Host 'STATUS: [RUNNING ONLINE] (PID: ' $procs.Id ')' -ForegroundColor Green
} else {
    Write-Host 'STATUS: [OFFLINE / STOPPED]' -ForegroundColor Red
}
Write-Host '`n--- LAST 10 LOG LINES ---' -ForegroundColor Yellow
if (Test-Path 'logs\harmonic_live.log') {
    Get-Content 'logs\harmonic_live.log' -Tail 10
} else {
    Write-Host 'No log file found yet.'
}
"
echo ===================================================================
pause
