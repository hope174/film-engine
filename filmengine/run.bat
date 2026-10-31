@echo off
rem Runs the film engine with whatever arguments it is given.
set "PYTHONIOENCODING=utf-8"
call "%~dp0findpython.bat"
if not defined PY (
    echo Python is not installed on this computer. Double-click Setup.bat first.
    exit /b 1
)
%PY% -c "import edge_tts, miniaudio, numpy, scipy, soundfile" >nul 2>&1
if errorlevel 1 (
    echo The film engine is not set up yet. Double-click Setup.bat first.
    exit /b 1
)
pushd "%~dp0.."
%PY% -m filmengine %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
