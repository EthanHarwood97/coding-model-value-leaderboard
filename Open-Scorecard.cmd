@echo off
cd /d "%~dp0"
where git >nul 2>nul && git pull --ff-only --quiet
start "" "%~dp0simple.html"
