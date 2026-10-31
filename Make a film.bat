@echo off
rem Double-click to make a film, or drag a film's script.txt onto this file.
cd /d "%~dp0"
set "FILM=%~1"
if not "%FILM%"=="" goto make
echo These are the films:
call filmengine\run.bat films
echo.
set /p "FILM=Type the name of the film to make, then press Enter: "
:make
call filmengine\run.bat make "%FILM%" --ask-play
echo.
pause
