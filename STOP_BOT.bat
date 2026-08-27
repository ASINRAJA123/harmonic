@echo off
title Harmonic EA V3 - Process Terminator
echo ===================================================================
echo Stopping Harmonic EA V3 Background Process...
echo ===================================================================
powershell -Command "
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*harmonic_live_exness.py*' }
if ($procs) {
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force
        Write-Host 'Stopped Process PID:' $p.ProcessId -ForegroundColor Green
    }
    Write-Host '[SUCCESS] Bot process stopped cleanly.' -ForegroundColor Green
} else {
    Write-Host 'No running Harmonic EA V3 bot process found.' -ForegroundColor Yellow
}
"
echo ===================================================================
pause
