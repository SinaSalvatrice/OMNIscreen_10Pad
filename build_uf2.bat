@echo off
setlocal EnableExtensions
rem One Windows entrypoint, one UF2 and one overwritten build log.
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
rem Optional isolated test output; normal use still publishes one UF2 under build.
if defined OMNIPAD_BUILD_OUTPUT set "ARTIFACT_DIR=%OMNIPAD_BUILD_OUTPUT%"
set "BUILD_LOG=%ARTIFACT_DIR%\OmniPad.log"
set "BUILD_OUTPUT_DIR=%ARTIFACT_DIR%"
rem Worker mode: run QMK without starting a second log or console session.
if /I "%~1"=="--worker" goto :run
if not exist "%ARTIFACT_DIR%" mkdir "%ARTIFACT_DIR%"
if errorlevel 1 (
    echo ERROR: Unable to create build output directory.
    call :hold_open
    exit /b 1
)

echo [OmniPad] QMK-Build gestartet. Log: "%BUILD_LOG%"
> "%BUILD_LOG%" echo === OmniPad QMK build ===
>> "%BUILD_LOG%" echo Source: %PROJECT_ROOT%
>> "%BUILD_LOG%" echo Output: %ARTIFACT_DIR%
>> "%BUILD_LOG%" echo Start: %DATE% %TIME%
rem Show every QMK line live while writing the same lines into OmniPad.log.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\build_uf2_live.ps1" -Launcher "%~f0" -Log "%BUILD_LOG%"
set "RESULT=%ERRORLEVEL%"
>> "%BUILD_LOG%" echo Exit code: %RESULT%
>> "%BUILD_LOG%" echo Finished: %DATE% %TIME%

if not "%RESULT%"=="0" (
    echo.
    echo BUILD FAILED [code %RESULT%].
    echo Full log: "%BUILD_LOG%"
    echo Previously working OmniPad.uf2 is left untouched.
    call :hold_open
    exit /b %RESULT%
)
echo.
echo BUILD SUCCESSFUL.
echo UF2: "%ARTIFACT_DIR%\OmniPad.uf2"
echo Log: "%BUILD_LOG%"
call :hold_open
exit /b 0

:hold_open
rem Double-click builds stay visible. Set OMNIPAD_NO_PAUSE=1 for automation.
if not defined OMNIPAD_NO_PAUSE (
    echo.
    echo Fertig. Taste druecken, um das Fenster zu schliessen.
    pause >nul
)
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
    py -3 "%PROJECT_ROOT%\scripts\generate_layer_system.py" --no-previews
) else (
    python "%PROJECT_ROOT%\scripts\generate_layer_system.py" --no-previews
)
if errorlevel 1 (
    echo ERROR: Layer metadata generation failed.
    exit /b 4
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%PROJECT_ROOT%\scripts\check_standalone_keymap.py"
) else (
    python "%PROJECT_ROOT%\scripts\check_standalone_keymap.py"
)
if errorlevel 1 (
    echo ERROR: Standalone keymap check failed.
    exit /b 5
)

git -C "%PROJECT_ROOT%" rev-parse HEAD
echo Building icst7789v:default from current source tree...
"%QMK_BASH%" --noprofile --norc "%PROJECT_ROOT:\=/%/scripts/build_uf2_internal.sh" <nul
exit /b %ERRORLEVEL%
