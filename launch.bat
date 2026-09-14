@echo off
@rem Minimal Windows local launcher for Video Summarizer.
@rem Responsible for quick startup when uv is already installed globally.
@rem Must not attempt self-bootstrapping installation of uv or Python.
@rem Next: launch.cmd (for full self-bootstrapping) or app.py (the main application).
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Install it from https://docs.astral.sh/uv/ and re-run this script.
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    uv venv
    if errorlevel 1 exit /b 1
)

if not exist ".env" if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example - fill only keys missing from your user environment.
)

echo Installing dependencies...
uv sync --all-groups
if errorlevel 1 (
    echo Dependency install failed.
    exit /b 1
)

echo Starting Video Summarizer...
uv run streamlit run app.py
