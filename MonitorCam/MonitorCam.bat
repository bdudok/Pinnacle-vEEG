@echo off
rem Starts the MonitorCam recorder.
rem Uses the repo's .venv (made by "uv sync") and ffmpeg on PATH (winget install Gyan.FFmpeg).
setlocal
set "REPO=%~dp0.."
set "PYW=%REPO%\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo The Python environment is missing. In the repo folder %REPO%, run:
    echo     uv sync --locked
    pause
    exit /b 1
)
rem winget adds this folder to PATH at install, but Explorer only sees it after the next login
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ffmpeg was not found. Install it with:
    echo     winget install Gyan.FFmpeg
    pause
    exit /b 1
)
cd /d "%REPO%"
start "" "%PYW%" -m MonitorCam.gui %*
