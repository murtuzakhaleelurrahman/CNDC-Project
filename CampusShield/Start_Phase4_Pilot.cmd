@echo off
title CampusShield Phase 4 Pilot - ENTER PASSWORD HERE
color 0B

echo ================================================================
echo            CAMPUSSHIELD PHASE 4 ADAPTIVE ROUTING PILOT
echo ================================================================
echo.
echo Enter your Ubuntu password when prompted, then leave this window open.
echo No password characters will appear while you type. This is normal.
echo The controller will enforce a real 45-second routing hold-down.
echo.

wsl.exe -e bash "/mnt/d/CNDC Project/CampusShield/scripts/run_phase4_pilot.sh"

set "CAMPUSSHIELD_EXIT=%ERRORLEVEL%"
echo.
if "%CAMPUSSHIELD_EXIT%"=="0" (
    echo PHASE 4 PILOT COMPLETED SUCCESSFULLY.
) else (
    echo PHASE 4 PILOT STOPPED WITH ERROR %CAMPUSSHIELD_EXIT%.
)
pause
exit /b %CAMPUSSHIELD_EXIT%
