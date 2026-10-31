@echo off
rem Writes the list of voices to "voice list.txt" and opens it in Notepad.
cd /d "%~dp0"
echo You can narrow the list with words such as: british female, american male, australian, all
set "WORDS="
set /p "WORDS=Type words to narrow the list, or just press Enter for all English voices: "
call filmengine\run.bat voices %WORDS% > "voice list.txt"
echo The voice list is open in Notepad.
start "" notepad "voice list.txt"
