@echo off
rem Makes a new film folder with a starter script, then opens the script in Notepad.
cd /d "%~dp0"
set "NAME=%*"
if not "%NAME%"=="" goto new
set /p "NAME=Type a name for the new film, then press Enter: "
:new
call filmengine\run.bat new %NAME% --open
echo.
pause
