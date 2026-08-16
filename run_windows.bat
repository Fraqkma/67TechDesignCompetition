@echo off
setlocal

REM Create an isolated Python environment only on the first run.
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python virtual environment...
    py -m venv .venv
)

REM Install all project dependencies inside the isolated environment.
echo [2/3] Installing project dependencies...
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt

REM Start the local server at http://127.0.0.1:5000
echo [3/3] Starting SkillGraph...
python app.py

endlocal
