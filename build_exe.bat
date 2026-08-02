@echo off
echo =======================================================
echo Dang dong goi ung dung Playlist Offline thanh file EXE
echo =======================================================
echo.

REM Kiem tra moi truong ao va PyInstaller
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [ERROR] PyInstaller chua duoc cai dat trong moi truong ao .venv.
    echo Vui long chay: .venv\Scripts\pip.exe install pyinstaller
    pause
    exit /b 1
)

REM Kiem tra file yt-dlp.exe
if not exist "APP\yt-dlp.exe" (
    echo [INFO] Thieu yt-dlp.exe. Dang tai tu dong...
    .venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe', 'APP/yt-dlp.exe')"
)

REM Bien dich native C module fast_core.dll neu co gcc
where gcc >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [INFO] Bien dich native C accelerator module fast_core.dll...
    gcc -O3 -shared -o APP\fast_core.dll APP\fast_core.c
)

echo [INFO] Bat dau bien dich bang PyInstaller...
.venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --name "PlaylistOffline" --paths APP --add-data "APP/style.qss;." --add-data "APP/app_icon.ico;." --add-data "APP/yt-dlp.exe;." --add-data "APP/fast_core.dll;." --icon "APP/app_icon.ico" APP/music_player.py


if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Dong goi thanh cong! File chay cua ban nam tai: dist\PlaylistOffline.exe
) else (
    echo.
    echo [ERROR] Qua trinh dong goi gap loi!
)
pause
