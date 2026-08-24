@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\..\.."

set "APP_VERSION=0.1.1"
set "APP_NAME=FoxAir_Updater"
set "OUT=dist\%APP_NAME%"
set "CACHE=build\windows-cache"

where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
) else (
  set "PY_CMD=py"
)

rem Backend runtime intentionally pinned close to the tested Raspberry-Pi Python 3.11 line.
set "PY_EMBED_VERSION=3.11.9"
set "PY_EMBED_FILE=python-%PY_EMBED_VERSION%-embed-amd64.zip"
set "PY_EMBED_URL=https://www.python.org/ftp/python/%PY_EMBED_VERSION%/%PY_EMBED_FILE%"
set "PY_EMBED_MD5=6d9aa08531d48fcc261ba667e2df17c4"

echo [1/8] Build-Abhaengigkeiten pruefen/installieren ...
%PY_CMD% -m pip install -r updater\windows\requirements-build.txt || goto :err

echo [2/8] PySide6-GUI als One-Folder-App bauen ...
%PY_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%APP_NAME%" ^
  updater\windows\foxair_updater_gui.py || goto :err

if not exist "%OUT%\%APP_NAME%.exe" (
  echo FEHLER: %OUT%\%APP_NAME%.exe fehlt.
  goto :err
)

echo [3/8] Unveraendertes gemeinsames Backend kopieren ...
if exist "%OUT%\backend" rmdir /s /q "%OUT%\backend"
mkdir "%OUT%\backend\tools\phnix_ota" || goto :err
mkdir "%OUT%\backend\updater\common" || goto :err

copy /y updater\__init__.py "%OUT%\backend\updater\__init__.py" >nul || goto :err
xcopy /y /i updater\common\*.py "%OUT%\backend\updater\common\" >nul || goto :err
copy /y tools\phnix_ota\phnix_local_ota_controller.py "%OUT%\backend\tools\phnix_ota\" >nul || goto :err
copy /y tools\phnix_ota\create_firmware_manifest.py "%OUT%\backend\tools\phnix_ota\" >nul || goto :err
copy /y tools\phnix_ota\phnix_ota_runtime_hook "%OUT%\backend\tools\phnix_ota\" >nul || goto :err

echo [4/8] Bytegleichheit der sicherheitsrelevanten Backend-Dateien pruefen ...
fc /b tools\phnix_ota\phnix_local_ota_controller.py "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller.py" >nul || goto :backenderr
fc /b tools\phnix_ota\create_firmware_manifest.py "%OUT%\backend\tools\phnix_ota\create_firmware_manifest.py" >nul || goto :backenderr
fc /b tools\phnix_ota\phnix_ota_runtime_hook "%OUT%\backend\tools\phnix_ota\phnix_ota_runtime_hook" >nul || goto :backenderr
for %%F in (updater\common\*.py) do (
  fc /b "%%F" "%OUT%\backend\updater\common\%%~nxF" >nul || goto :backenderr
)
echo [OK] Backend wurde unveraendert kopiert.

echo [5/8] Private Python-%PY_EMBED_VERSION%-Runtime vorbereiten ...
if not exist "%CACHE%" mkdir "%CACHE%"
if not exist "%CACHE%\%PY_EMBED_FILE%" (
  echo Lade offizielle Python Embeddable Runtime von python.org ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PY_EMBED_URL%' -OutFile '%CACHE%\%PY_EMBED_FILE%'" || goto :err
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm MD5 '%CACHE%\%PY_EMBED_FILE%').Hash.ToLower()"') do set "PY_HASH=%%H"
if /I not "!PY_HASH!"=="%PY_EMBED_MD5%" (
  echo FEHLER: MD5 der Python Runtime stimmt nicht.
  echo Erwartet: %PY_EMBED_MD5%
  echo Gefunden: !PY_HASH!
  goto :err
)
echo [OK] Python Runtime MD5 verifiziert.

if exist "%OUT%\runtime" rmdir /s /q "%OUT%\runtime"
mkdir "%OUT%\runtime" || goto :err
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -Force '%CACHE%\%PY_EMBED_FILE%' '%OUT%\runtime'" || goto :err
if not exist "%OUT%\runtime\python.exe" (
  echo FEHLER: Eingebettete Python Runtime unvollstaendig.
  goto :err
)

echo [6/8] Backend mit privater Runtime pruefen ...
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\create_firmware_manifest.py" --help >nul || goto :err
echo [OK] Controller und Manifest-Tool starten mit der privaten Runtime.

echo [7/8] Dokumentation und Lizenzen beilegen ...
copy /y LICENSE "%OUT%\LICENSE" >nul || goto :err
copy /y README.md "%OUT%\README.md" >nul || goto :err
if not exist "%OUT%\docs\HowTo" mkdir "%OUT%\docs\HowTo"
xcopy /y /i docs\HowTo\*.md "%OUT%\docs\HowTo\" >nul || goto :err
if exist "%OUT%\runtime\LICENSE.txt" (
  if not exist "%OUT%\THIRD_PARTY_LICENSES" mkdir "%OUT%\THIRD_PARTY_LICENSES"
  copy /y "%OUT%\runtime\LICENSE.txt" "%OUT%\THIRD_PARTY_LICENSES\Python-%PY_EMBED_VERSION%.txt" >nul
)

echo [8/8] Portable ZIP erzeugen ...
if exist "dist\%APP_NAME%_Portable_v%APP_VERSION%.zip" del /q "dist\%APP_NAME%_Portable_v%APP_VERSION%.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%OUT%\*' -DestinationPath 'dist\%APP_NAME%_Portable_v%APP_VERSION%.zip' -CompressionLevel Optimal" || goto :err

echo.
echo Fertig:
echo   Portable Ordner: %OUT%\
echo   Portable ZIP:    dist\%APP_NAME%_Portable_v%APP_VERSION%.zip
echo.
echo ADB ist NICHT enthalten. Der Anwender waehlt eine separat von Google bezogene adb.exe aus.
goto :eof

:backenderr
echo.
echo FEHLER: Kopiertes Backend ist nicht bytegleich mit dem Repository-Source.
goto :err

:err
echo.
echo FEHLER beim Windows-Portable-Build.
exit /b 1
