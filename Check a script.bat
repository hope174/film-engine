@echo off
rem Looks for mistakes in a script without making the film.
cd /d "%~dp0"
set "FILM=%~1"
if not "%FILM%"=="" goto check
echo These are the films:
call filmengine\run.bat films
echo.
set /p "FILM=Type the name of the film to check, then press Enter: "
:check
call filmengine\run.bat check "%FILM%"
echo.
pause
