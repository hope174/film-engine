@echo off
rem Lists the built-in sounds and the sound files in the shared sounds folder.
cd /d "%~dp0"
call filmengine\run.bat sounds
echo.
pause
