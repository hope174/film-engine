@echo off
rem Opens Film Maker, the window for writing and making films.
cd /d "%~dp0"
call filmengine\findpython.bat
if not defined PY (
    echo Python is not installed on this computer. Double-click Setup.bat first.
    pause
    exit /b 1
)
%PY% -c "import wx, edge_tts, miniaudio, numpy, scipy, soundfile" >nul 2>&1
if errorlevel 1 (
    echo Film Maker is not set up yet. Double-click Setup.bat first.
    pause
    exit /b 1
)
rem pythonw runs the window without a black console window behind it.
set PYW=%PY:python.exe=pythonw.exe%
if "%PY%"=="py -3" set "PYW=pyw -3"
if "%PY%"=="python" set "PYW=pythonw"
start "" %PYW% -m filmengine.app
