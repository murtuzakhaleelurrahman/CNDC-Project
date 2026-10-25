@echo off
title CampusShield Phase 3 OSPF Experiment - ENTER PASSWORD HERE
color 0B

echo ================================================================
echo             CAMPUSSHIELD PHASE 3 OSPF EXPERIMENT
echo ================================================================
echo.
echo This window compares default and tuned OSPF over 10 repetitions.
echo When Ubuntu asks for a password, type it and press Enter.
echo Your password will remain invisible while you type. This is normal.
echo.

wsl.exe -e bash "/mnt/d/CNDC Project/CampusShield/scripts/run_formal_phase3.sh"

set "CAMPUSSHIELD_EXIT=%ERRORLEVEL%"
echo.
if "%CAMPUSSHIELD_EXIT%"=="0" (
    echo CAMPUSSHIELD PHASE 3 COMPLETED SUCCESSFULLY.
) else (
    echo CAMPUSSHIELD PHASE 3 STOPPED WITH ERROR %CAMPUSSHIELD_EXIT%.
)
echo Keep this window open so the result can be reviewed.
pause
exit /b %CAMPUSSHIELD_EXIT%
