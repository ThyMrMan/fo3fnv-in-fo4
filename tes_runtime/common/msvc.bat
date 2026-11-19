@echo off
REM Puts the MSVC x64 toolchain on the calling script's environment. Every
REM project's build.bat calls this first; it does nothing when the toolchain
REM is already set up (tes_runtime\build.bat sets it up once for all of them).
REM The newest Visual Studio with the C++ x64 tools is found with vswhere.

if defined VSCMD_VER exit /b 0
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
set VS=
for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set VS=%%I
if not defined VS (
    echo [build] ERROR: no Visual Studio with the C++ x64 tools found
    exit /b 1
)
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (
    echo [build] ERROR: could not initialise MSVC x64 environment in %VS%
    exit /b 1
)
exit /b 0
