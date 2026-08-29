@echo off
title Harmonic EA V3 - Stop Bot
echo ===================================================================
echo 🛑 STOPPING HARMONIC EA V3 TRADING BOT...
echo ===================================================================

:: Terminate pythonw.exe background processes
taskkill /F /IM pythonw.exe /T >nul 2>&1

:: Also terminate any python.exe running harmonic_live_exness.py
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*harmonic_live_exness.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo ===================================================================
echo [SUCCESS] Harmonic EA V3 Bot has been completely STOPPED.
echo All background and live trading processes are terminated.
echo ===================================================================
timeout /t 3
