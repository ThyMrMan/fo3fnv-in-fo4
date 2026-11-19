@echo off
REM Build the Fallout 3 recorder into bin\ (test-only, never shipped):
REM   F3Recorder.dll  a 32-bit FOSE plugin writing the opening's timeline
REM See: docs/fork/fo4_story_tests.md#baseline

setlocal
call "%~dp0..\common\msvc.bat" x86
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist obj mkdir obj
if not exist bin mkdir bin

echo [build] compiling F3Recorder...
cl /nologo /c /EHsc /std:c++17 /O2 /MT /W3 /DNDEBUG /D_CRT_SECURE_NO_WARNINGS recorder.cpp /Fo:obj\recorder.obj
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:bin\F3Recorder.dll obj\recorder.obj kernel32.lib user32.lib
if errorlevel 1 exit /b 1
echo [build] OK -^> %~dp0bin
endlocal
