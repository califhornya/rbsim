@echo off
rem Double-click: opens the coach page (scripts/coach.py) in the browser.
rem Close this window to stop it. Engine: Rust (rules 6427b90+D72-D80) when Rust is
rem installed (https://rustup.rs), the extension built here at every start; else Python.
cd /d "%~dp0.."
uv sync --extra rl || exit /b 1
where rustc >nul 2>nul
if %errorlevel%==0 (
  uv pip install maturin
  set "VIRTUAL_ENV=%CD%\.venv"
  pushd rust\rbsim-py
  ..\..\.venv\Scripts\maturin develop --release
  popd
) else (
  echo Rust missing: the page plays on Python, rules 6427b90
)
.venv\Scripts\python scripts\coach.py %*
pause
