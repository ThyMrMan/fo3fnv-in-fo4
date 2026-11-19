@echo off
REM Puts an MSVC toolchain on the calling script's environment: x64 by default,
REM or the architecture given as %1 (x86 for the 32-bit Fallout 3 test plugin).
REM Every project's build.bat calls this first; it does nothing when that
REM toolchain is already set up (tes_runtime\build.bat sets x64 up once).
REM The newest Visual Studio with the C++ x64 tools is found with vswhere.

set "MSVC_ARCH=%~1"
if not defined MSVC_ARCH set "MSVC_ARCH=x64"
if /i "%VSCMD_ARG_TGT_ARCH%"=="%MSVC_ARCH%" exit /b 0
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
set VS=
for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set VS=%%I
if not defined VS (
    echo [build] ERROR: no Visual Studio with the C++ x64 tools found
    exit /b 1
)
call "%VS%\VC\Auxiliary\Build\vcvarsall.bat" %MSVC_ARCH% >nul 2>&1
if errorlevel 1 (
    echo [build] ERROR: could not initialise MSVC %MSVC_ARCH% environment in %VS%
    exit /b 1
)
exit /b 0
