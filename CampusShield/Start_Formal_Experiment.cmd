@echo off
title CampusShield Formal Experiment - ENTER PASSWORD HERE
color 0B

echo ================================================================
echo                  CAMPUSSHIELD FORMAL EXPERIMENT
echo ================================================================
echo.
echo This window will run the 10-repetition, three-scenario Phase 2 test.
echo When Ubuntu asks for a password, type it and press Enter.
echo Your password will remain invisible while you type. This is normal.
echo.

wsl.exe -e bash "/mnt/d/CNDC Project/CampusShield/scripts/run_formal_phase2.sh"

set "CAMPUSSHIELD_EXIT=%ERRORLEVEL%"
echo.
if "%CAMPUSSHIELD_EXIT%"=="0" (
    echo CAMPUSSHIELD FORMAL EXPERIMENT COMPLETED SUCCESSFULLY.
) else (
    echo CAMPUSSHIELD FORMAL EXPERIMENT STOPPED WITH ERROR %CAMPUSSHIELD_EXIT%.
)
echo Keep this window open so the result can be reviewed.
pause
exit /b %CAMPUSSHIELD_EXIT%
