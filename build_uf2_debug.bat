@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ================================================================
echo OMNIscreen 10Pad - QMK Build mit Diagnoseprotokoll
echo ================================================================
echo.
echo Der gesamte Build wird in build_diagnostic.log geschrieben.
echo Das Fenster bleibt auch bei Fehlern offen.
echo.
call "%~dp0build_uf2.bat" > "%~dp0build_diagnostic.log" 2>&1
set "RESULT=%ERRORLEVEL%"
type "%~dp0build_diagnostic.log"
echo.
echo ================================================================
echo Build-Exitcode: %RESULT%
echo Log: %~dp0build_diagnostic.log
echo ================================================================
echo.
pause
exit /b %RESULT%
