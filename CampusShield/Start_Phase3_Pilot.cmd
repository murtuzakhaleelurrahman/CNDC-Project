@echo off
title CampusShield Phase 3 Pilot - ENTER PASSWORD HERE
color 0B

echo ================================================================
echo                  CAMPUSSHIELD PHASE 3 PILOT
echo ================================================================
echo.
echo Enter your Ubuntu password when prompted, then leave this window open.
echo No password characters will appear while you type. This is normal.
echo The default OSPF trial needs about 40 seconds to detect silent failure.
echo.

wsl.exe -e bash "/mnt/d/CNDC Project/CampusShield/scripts/run_phase3_pilot.sh"

set "CAMPUSSHIELD_EXIT=%ERRORLEVEL%"
echo.
if "%CAMPUSSHIELD_EXIT%"=="0" (
    echo PHASE 3 PILOT COMPLETED SUCCESSFULLY.
) else (
    echo PHASE 3 PILOT STOPPED WITH ERROR %CAMPUSSHIELD_EXIT%.
)
pause
exit /b %CAMPUSSHIELD_EXIT%
