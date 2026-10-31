@echo off
rem Writes every word a script can use in brackets to "word list.txt" and opens it in Notepad.
cd /d "%~dp0"
call filmengine\run.bat words > "word list.txt"
echo The word list is open in Notepad.
start "" notepad "word list.txt"
