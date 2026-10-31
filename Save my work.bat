@echo off
rem Saves a copy of everything in the history, so nothing is lost.
cd /d "%~dp0"
where git >nul 2>&1
if errorlevel 1 (
    echo Git is not installed, so I can't save a copy. Ask the person who looks after the engine.
    pause
    exit /b 1
)
git add -A
git diff --cached --quiet
if not errorlevel 1 (
    echo Nothing has changed since the last save.
    pause
    exit /b 0
)
git commit -q -m "Saved work on %date% at %time:~0,5%"
if errorlevel 1 (
    echo Something went wrong while saving. Ask the person who looks after the engine.
) else (
    echo Saved. A copy of your work is safe in the history.
)
pause
