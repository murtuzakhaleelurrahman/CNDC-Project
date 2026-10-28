@echo off
title CampusShield Phase 4 Adaptive Routing - ENTER PASSWORD HERE
color 0B

echo ================================================================
echo       CAMPUSSHIELD PHASE 4 CLOSED-LOOP ADAPTIVE ROUTING
echo ================================================================
echo.
echo This window runs 10 fresh-topology adaptive-routing repetitions.
echo When Ubuntu asks for a password, type it and press Enter.
echo Your password will remain invisible while you type. This is normal.
echo.

wsl.exe -e bash "/mnt/d/CNDC Project/CampusShield/scripts/run_formal_phase4.sh"

set "CAMPUSSHIELD_EXIT=%ERRORLEVEL%"
echo.
if "%CAMPUSSHIELD_EXIT%"=="0" (
    echo CAMPUSSHIELD PHASE 4 COMPLETED SUCCESSFULLY.
) else (
    echo CAMPUSSHIELD PHASE 4 STOPPED WITH ERROR %CAMPUSSHIELD_EXIT%.
)
pause
exit /b %CAMPUSSHIELD_EXIT%
