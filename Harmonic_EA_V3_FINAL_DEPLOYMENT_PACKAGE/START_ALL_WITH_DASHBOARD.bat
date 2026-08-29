@echo off
title Harmonic EA V3 - Master Launcher
echo ===================================================================
echo 🚀 LAUNCHING HARMONIC EA V3 TRADING BOT + LIVE MONGODB DASHBOARD
echo ===================================================================
echo 1. Starting Live Trading Engine in the Background...
wscript.exe START_BOT_BACKGROUND.vbs
timeout /t 2 >nul

echo 2. Launching Live Web Dashboard on http://localhost:12000...
start "" "http://localhost:12000"
python dashboard_server.py
pause
