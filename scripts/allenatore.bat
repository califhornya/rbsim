@echo off
rem Double-click: opens the coach page (scripts/coach.py) in the browser.
rem Close this window to stop it.
cd /d "%~dp0.."
uv run python scripts\coach.py %*
pause
