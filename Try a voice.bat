@echo off
rem Plays a voice so you can hear it before using it in a film.
cd /d "%~dp0"
:again
echo.
set "VOICE="
set /p "VOICE=Type a voice name, such as Ryan, Sonia or Microsoft David. Press Enter on its own to finish: "
if "%VOICE%"=="" goto :eof
set "WORDS="
set /p "WORDS=Type what it should say, or just press Enter for a hello: "
set "STYLE="
set /p "STYLE=Type a style such as whisper, echo, telephone, or just press Enter: "
call filmengine\run.bat try "%VOICE%" %WORDS% --style "%STYLE%"
goto again
