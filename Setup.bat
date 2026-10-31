@echo off
cd /d "%~dp0"
echo Setting up the film engine. This needs the internet and can take a few minutes.
echo.
call filmengine\findpython.bat
if not defined PY (
    echo Installing Python...
    winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    call filmengine\findpython.bat
)
if not defined PY (
    echo Python could not be installed. Ask the person who looks after the engine for help.
    pause
    exit /b 1
)
echo Installing the parts the engine needs...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Something went wrong while installing. Check the internet connection and try again.
    pause
    exit /b 1
)
%PY% -c "from filmengine.audio import find_ffmpeg; raise SystemExit(0 if find_ffmpeg() else 1)"
if errorlevel 1 (
    echo Installing ffmpeg, which lets the engine save MP3 files and read more kinds of sound file...
    winget install --id Gyan.FFmpeg --scope user --silent --accept-package-agreements --accept-source-agreements
)
echo.
echo All done. The film engine is ready.
pause
