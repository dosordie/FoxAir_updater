@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist "dist\FoxAir_Updater\FoxAir_Updater.exe" (
  echo Portable Build fehlt. Fuehre zuerst updater\windows\build_windows_portable.bat aus.
  exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 nicht gefunden.
  echo Download: https://jrsoftware.org/isinfo.php
  exit /b 1
)

"%ISCC%" "updater\windows\installer\FoxAir_Updater.iss" || goto :err
echo.
echo Fertig: updater\windows\installer\Output\
goto :eof

:err
echo Fehler beim Installer-Build.
exit /b 1
