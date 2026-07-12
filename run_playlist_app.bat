@echo off
setlocal
set "APP_DIR=%~dp0"
set "APP_FILE=%APP_DIR%music_player.py"
set "LOG_FILE=%APP_DIR%playlist_app.log"
set "VENDOR_DIR=%APP_DIR%vendor"

cd /d "%APP_DIR%"

echo ---- %DATE% %TIME% ---- >> "%LOG_FILE%"
echo Launching Playlist Offline >> "%LOG_FILE%"

if exist "%APP_DIR%.venv\Scripts\python.exe" (
    "%APP_DIR%.venv\Scripts\python.exe" "%APP_FILE%" %* >> "%LOG_FILE%" 2>&1
    exit /b %ERRORLEVEL%
)

if exist "%VENDOR_DIR%\PySide6" (
    set "PYTHONPATH=%VENDOR_DIR%;%PYTHONPATH%"
    python "%APP_FILE%" %* >> "%LOG_FILE%" 2>&1
    exit /b %ERRORLEVEL%
)

python -c "import PySide6" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python "%APP_FILE%" %* >> "%LOG_FILE%" 2>&1
    exit /b %ERRORLEVEL%
)

echo PySide6 is not installed. Please install it using: pip install PySide6 >> "%LOG_FILE%"
exit /b 1
