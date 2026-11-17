@echo off
rem Double-click: opens the scenarios page (scripts/scenari.py) in the browser.
rem Close this window to stop it. The coach (allenatore.bat) is separate.
cd /d "%~dp0.."
uv run python scripts\scenari.py %*
pause
