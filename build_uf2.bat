@echo off
setlocal EnableExtensions
rem One Windows entrypoint, one UF2, one overwritten build log.
set "MSYSTEM=MINGW64"
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "CANONICAL_ROOT="
rem A build from any temporary Git worktree still publishes into the primary checkout.
for /f "tokens=1,*" %%A in ('git -C "%PROJECT_ROOT%" worktree list --porcelain 2^>nul') do (
    if not defined CANONICAL_ROOT if "%%A"=="worktree" set "CANONICAL_ROOT=%%B"
)
if not defined CANONICAL_ROOT set "CANONICAL_ROOT=%PROJECT_ROOT%"
set "ARTIFACT_DIR=%CANONICAL_ROOT%\build"
set "BUILD_LOG=%ARTIFACT_DIR%\OmniPad-build.log"
set "BUILD_OUTPUT_DIR=%ARTIFACT_DIR%"
if not exist "%ARTIFACT_DIR%" mkdir "%ARTIFACT_DIR%"
if errorlevel 1 (
    echo ERROR: Unable to create build output directory.
    exit /b 1
)

> "%BUILD_LOG%" echo === OmniPad QMK build ===
>> "%BUILD_LOG%" echo Source: %PROJECT_ROOT%
>> "%BUILD_LOG%" echo Output: %ARTIFACT_DIR%
>> "%BUILD_LOG%" echo Start: %DATE% %TIME%
call :run >> "%BUILD_LOG%" 2>&1
set "RESULT=%ERRORLEVEL%"
>> "%BUILD_LOG%" echo Exit code: %RESULT%
>> "%BUILD_LOG%" echo Finished: %DATE% %TIME%

if not "%RESULT%"=="0" (
    echo.
    echo BUILD FAILED [code %RESULT%].
    echo Full log: "%BUILD_LOG%"
    echo Previously working OmniPad.uf2 is left untouched.
    powershell -NoProfile -Command "Get-Content -LiteralPath '%BUILD_LOG%' -Tail 25" 2>nul
    exit /b %RESULT%
)
echo.
echo BUILD SUCCESSFUL.
echo UF2: "%ARTIFACT_DIR%\OmniPad.uf2"
echo Log: "%BUILD_LOG%"
exit /b 0

:run
if not defined QMK_HOME set "QMK_HOME=%USERPROFILE%\qmk_firmware"
if not exist "%QMK_HOME%\Makefile" (
    echo ERROR: Missing QMK checkout: "%QMK_HOME%"
    exit /b 2
)
set "QMK_BASH=C:\QMK_MSYS\usr\bin\bash.exe"
if not exist "%QMK_BASH%" (
    echo ERROR: QMK MSYS not found: "%QMK_BASH%"
    exit /b 3
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%PROJECT_ROOT%\scripts\generate_layer_system.py"
) else (
    python "%PROJECT_ROOT%\scripts\generate_layer_system.py"
)
if errorlevel 1 exit /b 4

git -C "%PROJECT_ROOT%" rev-parse HEAD
echo Building icst7789v:default from current source tree...
"%QMK_BASH%" --noprofile --norc -c "export HOME=\"$(cygpath -u \"$USERPROFILE\")\"; export PROJECT_ROOT=\"$(cygpath -u \"$PROJECT_ROOT\")\"; export QMK_HOME=\"$(cygpath -u \"$QMK_HOME\")\"; export BUILD_OUTPUT_DIR=\"$(cygpath -u \"$BUILD_OUTPUT_DIR\")\"; export PATH=\"$HOME/bin:/c/QMK_MSYS/mingw64/bin:/c/QMK_MSYS/usr/bin:/opt/qmk/bin:$PATH\"; bash \"$PROJECT_ROOT/scripts/build_uf2_internal.sh\""
exit /b %ERRORLEVEL%
