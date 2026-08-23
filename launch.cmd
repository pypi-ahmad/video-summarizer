@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_VERSION=3.13.13"
set "VENV_DIR=%CD%\.venv"
set "UV_PROJECT_ENVIRONMENT=%VENV_DIR%"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found. Installing the official user-local uv tool...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 ^| iex"
    if errorlevel 1 goto :setup_failed
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>nul
    if errorlevel 1 (
        echo uv installed, but this process could not locate it.
        echo Open a new terminal and run launch.cmd again.
        exit /b 1
    )
)

echo Ensuring Python %PYTHON_VERSION% is available through uv...
uv python install "%PYTHON_VERSION%" --no-registry
if errorlevel 1 goto :setup_failed

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating project virtual environment at %VENV_DIR%...
    uv venv --python "%PYTHON_VERSION%" "%VENV_DIR%"
    if errorlevel 1 goto :setup_failed
)

echo Synchronizing locked dependencies into %VENV_DIR%...
uv sync --locked --all-groups --python "%PYTHON_VERSION%"
if errorlevel 1 goto :setup_failed

if not exist ".env" if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example - fill only keys missing from your user environment.
)

where ffmpeg >nul 2>nul
if errorlevel 1 echo Warning: ffmpeg is not on PATH; local video processing may fail.
where ffprobe >nul 2>nul
if errorlevel 1 echo Warning: ffprobe is not on PATH; local video inspection may fail.

echo Starting Video Summarizer from the project virtual environment...
"%VENV_DIR%\Scripts\python.exe" -m streamlit run app.py
exit /b %ERRORLEVEL%

:setup_failed
echo Setup failed. Review the error above, then run launch.cmd again.
exit /b 1
