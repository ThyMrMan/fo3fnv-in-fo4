@echo off
REM Build the test instance's DLLs into bin\ (test-only, never shipped):
REM   TESSandbox.dll  My Games / LocalAppData redirect and mute (MSVC only)
REM   F3NVTest.dll    the F4SE control pipe (CommonLibF4, built with xmake)
REM See: docs/fork/fo4_story_tests.md#instance

setlocal
call "%~dp0..\common\msvc.bat"
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist obj mkdir obj
if not exist bin mkdir bin

echo [build] compiling TESSandbox...
cl /nologo /c /EHsc /std:c++17 /O2 /MD /W3 /DNDEBUG sandbox.cpp /Fo:obj\sandbox.obj
if errorlevel 1 exit /b 1
link /nologo /DLL /OUT:bin\TESSandbox.dll obj\sandbox.obj kernel32.lib user32.lib shell32.lib ole32.lib uuid.lib
if errorlevel 1 exit /b 1

if not defined TOOLS_EXT for %%I in ("%~dp0..\..\..\tools_ext") do if exist "%%~fI" set TOOLS_EXT=%%~fI
if not defined TOOLS_EXT for %%I in ("%~dp0..\..\..\..\..\..\tools_ext") do if exist "%%~fI" set TOOLS_EXT=%%~fI
if not defined TOOLS_EXT (
    echo [build] ERROR: no tools_ext beside the checkout; set TOOLS_EXT
    exit /b 1
)
echo [build] building F3NVTest...
robocopy "%TOOLS_EXT%\commonlibf4-template\lib\commonlibf4" bridge\lib\commonlibf4 /MIR /XF *.py /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 exit /b 1
cd bridge
if exist ..\bin\F3NVTest.dll del ..\bin\F3NVTest.dll
xmake f -p windows -a x64 -m release -y
xmake build -y F3NVTest
if not exist ..\bin\F3NVTest.dll (
    echo [build] ERROR: F3NVTest build failed
    exit /b 1
)
echo [build] OK -^> %~dp0bin
endlocal
