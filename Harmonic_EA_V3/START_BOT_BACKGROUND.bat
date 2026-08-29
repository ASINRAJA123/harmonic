@echo off
title Harmonic EA V3 - Background Launcher
echo ===================================================================
echo Starting Harmonic EA V3 in the BACKGROUND (Hidden)...
echo ===================================================================
wscript.exe START_BOT_BACKGROUND.vbs
timeout /t 2 >nul
echo [OK] Bot process launched in background!
echo You can view live streaming logs anytime by running: VIEW_LIVE_LOGS.bat
echo You can check status anytime by running: STATUS_BOT.bat
echo ===================================================================
pause
