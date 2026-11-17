#!/bin/bash
# Double-click (Mac): opens the scenarios page (scripts/scenari.py) in the browser.
# Close this window to stop it. The coach is separate.
cd "$(dirname "$0")/.."
uv run python scripts/scenari.py "$@"
