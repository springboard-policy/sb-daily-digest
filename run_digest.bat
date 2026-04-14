@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python generate_digest.py
if errorlevel 1 (
    echo.
    echo ERROR: Digest generation failed. See above for details.
    pause
) else (
    echo.
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set TODAY=%%c-%%b-%%a
    start "" "digest_%TODAY%.html"
)
