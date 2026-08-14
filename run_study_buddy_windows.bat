@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python virtual environment...
    py -m venv .venv
)

echo [2/3] Installing required packages...
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt

echo [3/3] Starting SkillGraph with Study Buddy...
python study_buddy_app.py

endlocal
