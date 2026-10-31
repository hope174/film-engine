@echo off
rem Sets PY to a Python that can run the engine. Called by the other .bat files.
set "PY="
for %%V in (313 312 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
if not defined PY (
    py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
exit /b 0
