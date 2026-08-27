@echo off
title Harmonic EA V3 - Web Dashboard Server
echo ===================================================================
echo Starting Harmonic EA V3 Web Dashboard...
echo URL: http://localhost:5000
echo Database: MongoDB Atlas (cluster0.tt1v1.mongodb.net)
echo ===================================================================
start "" "http://localhost:5000"
python dashboard_server.py
pause
