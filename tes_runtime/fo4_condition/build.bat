@echo off
REM Build FalloutCondition.dll (F4SE plugin, Fallout4.exe 1.11.240) into ..\dist.
REM
REM Needs F4SE 0.7.9's source and ianpatt's common, built as static libraries
REM (docs/fork/fo4_condition.md#plugin-build). F4SE_ROOT and COMMON_ROOT
REM default to C:\Coding\tes4skyrim\tools_ext.

setlocal
call "%~dp0..\common\msvc.bat"
if errorlevel 1 exit /b 1
if not defined TOOLS_EXT set TOOLS_EXT=C:\Coding\tes4skyrim\tools_ext
set F4SE_ROOT=%TOOLS_EXT%\f4se_src\f4se-0.7.9
set COMMON_ROOT=%TOOLS_EXT%\extern

cd /d "%~dp0"
if not exist obj mkdir obj
del /q obj\*.obj 2>nul

echo [build] compiling FalloutCondition...
cl /nologo /c /EHsc /std:c++17 /O2 /MT /W3 /DNDEBUG /DRUNTIME /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS ^
   /I"%F4SE_ROOT%" /I"%COMMON_ROOT%\include" /FI"common/IPrefix.h" plugin.cpp pipboy.cpp repair.cpp transfer.cpp vendor.cpp pages.cpp /Fo:obj\
if errorlevel 1 (
    echo [build] ERROR: FalloutCondition compilation failed
    exit /b 1
)
link /nologo /DLL /OUT:..\dist\FalloutCondition.dll /IMPLIB:obj\FalloutCondition.lib obj\*.obj ^
     "%F4SE_ROOT%\build\f4se\Release\f4se_1_11_240.lib" ^
     "%F4SE_ROOT%\build\f4se\f4se_common\Release\f4se_common.lib" ^
     "%COMMON_ROOT%\lib\common.lib" kernel32.lib user32.lib shell32.lib ole32.lib advapi32.lib comdlg32.lib /LTCG
if errorlevel 1 (
    echo [build] ERROR: FalloutCondition link failed
    exit /b 1
)
echo [build] OK -^> %~dp0..\dist\FalloutCondition.dll
endlocal
