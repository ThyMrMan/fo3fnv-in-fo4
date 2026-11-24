@echo off
rem Double-click to set up and start the Fallout 3 / New Vegas to Fallout 4 app.
rem TES Auto-Convert.cmd does the setup (Python, packages); FO4_APP sends it to the Fallout 4 app.
set "FO4_APP=1"
call "%~dp0TES Auto-Convert.cmd"
