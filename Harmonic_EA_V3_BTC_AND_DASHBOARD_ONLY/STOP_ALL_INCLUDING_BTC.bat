@echo off
title Harmonic EA V3 - Stop All Portfolios
echo ===================================================================
echo 🛑 STOPPING ALL HARMONIC EA V3 ENGINES & DASHBOARDS...
echo ===================================================================

echo 1. Terminating background VBS Python processes...
taskkill /F /IM pythonw.exe /T >nul 2>&1

echo 2. Terminating active Forex and BTC engines...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*harmonic_live_exness.py*' -or $_.CommandLine -like '*harmonic_live_btc.py*' -or $_.CommandLine -like '*dashboard_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo ===================================================================
echo [SUCCESS] Forex Bot, Bitcoin Bot, and Dashboard have been STOPPED.
echo ===================================================================
timeout /t 3
