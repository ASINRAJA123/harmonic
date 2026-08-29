@echo off
title Harmonic EA V3 - Live Real-Time Logs Monitor
echo ===================================================================
echo Streaming Live Logs from logs\harmonic_live.log
echo Press Ctrl+C anytime to close this viewer (Bot will keep running!)
echo ===================================================================
powershell -Command "if (Test-Path 'logs\harmonic_live.log') { Get-Content 'logs\harmonic_live.log' -Wait -Tail 40 } else { Write-Host 'Waiting for log file to initialize...' ; Start-Sleep -Seconds 3 ; Get-Content 'logs\harmonic_live.log' -Wait -Tail 40 }"
pause
