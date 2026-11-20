@echo off
setlocal
set "EDITOR_VENV=%LOCALAPPDATA%\OmniPad\EditorVenv"
if not exist "%EDITOR_VENV%\Scripts\python.exe" (
    py -3 -m venv "%EDITOR_VENV%" || goto failed
)
"%EDITOR_VENV%\Scripts\python.exe" -c "import hid" >nul 2>&1
if errorlevel 1 "%EDITOR_VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || goto failed
start "" "%EDITOR_VENV%\Scripts\pythonw.exe" "%~dp0start_editor.pyw" || goto failed
exit /b 0
:failed
echo Der OmniPad-Editor konnte nicht gestartet werden.
pause
exit /b 1
