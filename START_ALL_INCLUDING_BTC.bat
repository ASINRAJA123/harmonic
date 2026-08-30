@echo off
title Harmonic EA V3 - Multi-Portfolio Master Launcher
echo ===================================================================
echo 🚀 LAUNCHING MULTI-PORTFOLIO SYSTEMS (FOREX + BITCOIN + DASHBOARD)
echo ===================================================================
echo 🧹 TERMINATING EXISTING BOTS TO PREVENT DUPLICATES...
call STOP_ALL_INCLUDING_BTC.bat

echo 1. Starting Forex/Gold 6-Pair Trading Bot in the Background...
wscript.exe START_BOT_BACKGROUND.vbs
timeout /t 2 >nul

echo 2. Starting Bitcoin Dedicated Trading Bot in the Background...
wscript.exe START_BTC_BOT_BACKGROUND.vbs
timeout /t 2 >nul

echo 3. Launching Unified Dashboard on http://localhost:12000...
start "" "http://localhost:12000"
python dashboard_server.py
pause
