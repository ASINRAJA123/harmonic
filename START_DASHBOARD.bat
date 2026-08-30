@echo off
title Harmonic EA V3 Dashboard
echo ========================================================
echo Starting Harmonic EA V3 Local Web Dashboard...
echo Open your browser to: http://localhost:15000
echo ========================================================
echo.
echo Make sure MongoDB Atlas is whitelisted for your IP!
echo.
python dashboard_server.py
pause
