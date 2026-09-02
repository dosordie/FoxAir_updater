@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\..\.."

set "APP_VERSION=0.4.0"
set "APP_NAME=FoxAir_Updater"
set "OUT=dist\%APP_NAME%"
set "CACHE=build\windows-cache"
set "ICON_FILE=updater\windows\app_icon.ico"
set "ICON_URL=https://raw.githubusercontent.com/dosordie/FoxAir_Control/main/app_icon.ico"
set "ICON_GIT_SHA=0ae281034216f69c4f18dbdb55cc70d8b78e47e1"

rem Use the Python selected by PATH/setup-python.  The Windows py launcher may
rem point at a different globally installed version (for example 3.14 on CI).
set "PY_CMD=python"

rem Backend runtime intentionally pinned close to the tested Raspberry-Pi Python 3.11 line.
set "PY_EMBED_VERSION=3.11.9"
set "PY_EMBED_FILE=python-%PY_EMBED_VERSION%-embed-amd64.zip"
set "PY_EMBED_URL=https://www.python.org/ftp/python/%PY_EMBED_VERSION%/%PY_EMBED_FILE%"
set "PY_EMBED_MD5=6d9aa08531d48fcc261ba667e2df17c4"

echo [1/9] Build-Abhaengigkeiten pruefen/installieren ...
%PY_CMD% -m pip install -r updater\windows\requirements-build.txt || goto :err

echo [2/9] Programmlogo aus FoxAir_Control bereitstellen ...
if not exist "%ICON_FILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%ICON_URL%' -OutFile '%ICON_FILE%'" || goto :err
)
for /f %%H in ('git hash-object "%ICON_FILE%"') do set "ICON_HASH=%%H"
if /I not "!ICON_HASH!"=="%ICON_GIT_SHA%" (
  echo FEHLER: Programmlogo entspricht nicht der gepinnten FoxAir_Control-Datei.
  echo Erwartet: %ICON_GIT_SHA%
  echo Gefunden: !ICON_HASH!
  goto :err
)
echo [OK] FoxAir_Control-Programmlogo verifiziert.

echo [3/9] PySide6-GUI als One-Folder-App bauen ...
rem Produktlogik bleibt in updater\windows\foxair_updater_runner_product.py; der Release-Entrypoint erweitert sie nur um Diagnoseexport.
%PY_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%APP_NAME%" ^
  --icon "%ICON_FILE%" ^
  updater\windows\foxair_updater_release_product.py || goto :err

if not exist "%OUT%\%APP_NAME%.exe" (
  echo FEHLER: %OUT%\%APP_NAME%.exe fehlt.
  goto :err
)
copy /y "%ICON_FILE%" "%OUT%\app_icon.ico" >nul || goto :err

echo [4/9] Gemeinsames Backend und produktiven DTU-Runner kopieren ...
if exist "%OUT%\backend" rmdir /s /q "%OUT%\backend"
mkdir "%OUT%\backend\tools\phnix_ota" || goto :err
mkdir "%OUT%\backend\tools\phnix_traffic" || goto :err
mkdir "%OUT%\backend\updater\common" || goto :err
mkdir "%OUT%\backend\updater\dtu_ota\payload" || goto :err

copy /y updater\__init__.py "%OUT%\backend\updater\__init__.py" >nul || goto :err
xcopy /y /i updater\common\*.py "%OUT%\backend\updater\common\" >nul || goto :err

rem Der verifizierte Controller-Core bleibt fuer Diagnose-/Bestandsfunktionen erhalten.
copy /y tools\phnix_ota\phnix_local_ota_controller.py "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_core.py" >nul || goto :err
copy /y tools\phnix_ota\phnix_local_ota_controller_hardened.py "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_hardened.py" >nul || goto :err
copy /y updater\windows\phnix_windows_controller_wrapper.py "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller.py" >nul || goto :err
copy /y tools\phnix_ota\create_firmware_manifest.py "%OUT%\backend\tools\phnix_ota\" >nul || goto :err
rem Legacy Controller validiert historisch explizit #!/bin/sh. Die kanonische Runner-Version nutzt
rem #!/system/bin/sh. Fuer den Legacy-Restore wird deshalb nur die Shebang der separaten Paketkopie
rem angepasst; der gepruefte Hook-Inhalt darunter bleibt identisch.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='updater\dtu_ota\payload\phnix_ota_runtime_hook'; $o='%OUT%\backend\tools\phnix_ota\phnix_ota_runtime_hook'; $t=[IO.File]::ReadAllText($p); if(-not $t.StartsWith('#!/system/bin/sh')){throw 'Unerwartete Hook-Shebang'}; $i=$t.IndexOf([char]10); if($i -lt 0){throw 'Hook hat keine erste Zeile'}; $rest=$t.Substring($i+1); [IO.File]::WriteAllText($o,('#!/bin/sh'+[char]10+$rest),(New-Object Text.UTF8Encoding($false)))" || goto :err
copy /y tools\phnix_traffic\foxair_traffic_trace "%OUT%\backend\tools\phnix_traffic\" >nul || goto :err

rem Produktiver OTA-Pfad: Host paketiert/liest Status; Supervisor und Hook werden auf die DTU uebertragen.
xcopy /y /i updater\dtu_ota\*.py "%OUT%\backend\updater\dtu_ota\" >nul || goto :err
copy /y updater\dtu_ota\payload\dtu_ota_supervisor.sh "%OUT%\backend\updater\dtu_ota\payload\dtu_ota_supervisor.sh" >nul || goto :err
copy /y updater\dtu_ota\payload\phnix_ota_runtime_hook "%OUT%\backend\updater\dtu_ota\payload\phnix_ota_runtime_hook" >nul || goto :err

echo [5/9] SHA-256 des kopierten Backends pruefen ...
rem FC /B liefert auf einigen Windows-Versionen fuer einzelne leere/sonderbehandelte
rem Dateien unzuverlaessige Exitcodes.  Wir vergleichen deshalb die Inhalte per SHA-256
rem und geben im Fehlerfall den exakten Dateinamen aus.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$pairs=@(" ^
  "@('tools\phnix_ota\phnix_local_ota_controller.py','%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_core.py')," ^
  "@('tools\phnix_ota\phnix_local_ota_controller_hardened.py','%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_hardened.py')," ^
  "@('updater\windows\phnix_windows_controller_wrapper.py','%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller.py')," ^
  "@('tools\phnix_ota\create_firmware_manifest.py','%OUT%\backend\tools\phnix_ota\create_firmware_manifest.py')," ^
  "@('tools\phnix_traffic\foxair_traffic_trace','%OUT%\backend\tools\phnix_traffic\foxair_traffic_trace')," ^
  "@('updater\dtu_ota\payload\dtu_ota_supervisor.sh','%OUT%\backend\updater\dtu_ota\payload\dtu_ota_supervisor.sh')," ^
  "@('updater\dtu_ota\payload\phnix_ota_runtime_hook','%OUT%\backend\updater\dtu_ota\payload\phnix_ota_runtime_hook')" ^
  ");" ^
  "$pairs += Get-ChildItem 'updater\dtu_ota\*.py' | ForEach-Object { ,@($_.FullName,(Join-Path '%OUT%\backend\updater\dtu_ota' $_.Name)) };" ^
  "$pairs += Get-ChildItem 'updater\common\*.py' | ForEach-Object { ,@($_.FullName,(Join-Path '%OUT%\backend\updater\common' $_.Name)) };" ^
  "foreach($p in $pairs){if(-not(Test-Path $p[1])){Write-Error ('Backend-Datei fehlt: '+$p[1]); exit 1}; $a=(Get-FileHash -Algorithm SHA256 $p[0]).Hash; $b=(Get-FileHash -Algorithm SHA256 $p[1]).Hash; if($a -ne $b){Write-Error ('Backend-Datei weicht ab: '+$p[0]+' -> '+$p[1]); exit 1}};" ^
  "$legacy='%OUT%\backend\tools\phnix_ota\phnix_ota_runtime_hook'; $bytes=[IO.File]::ReadAllBytes($legacy); $prefix=[Text.Encoding]::ASCII.GetString($bytes,0,[Math]::Min(10,$bytes.Length)); if(-not $prefix.StartsWith(('#!/bin/sh'+[char]10))){Write-Error 'Legacy-Restore-Hook hat keinen exakten LF-Header #!/bin/sh'; exit 1}" || goto :backenderr

echo [OK] Gemeinsamer Controller/Common-Code und produktiver DTU-Runner wurden inhaltlich verifiziert.

echo [6/9] Private Python-%PY_EMBED_VERSION%-Runtime vorbereiten ...
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

echo [7/9] Backend mit privater Runtime pruefen ...
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_hardened.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\phnix_local_ota_controller_core.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\tools\phnix_ota\create_firmware_manifest.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\updater\dtu_ota\cli.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\updater\dtu_ota\diagnostics.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\updater\dtu_ota\cleanup.py" --help >nul || goto :err
"%OUT%\runtime\python.exe" "%OUT%\backend\updater\common\phnix_statistics_maintenance.py" --help >nul || goto :err
echo [OK] Windows-Sicherheitshuette, DTU-Runner-CLI, Diagnose-/Cleanup-Core, Controller-Core, Manifest-Tool und Maintenance-Core starten mit der privaten Runtime.

echo [8/9] Dokumentation und Lizenzen beilegen ...
copy /y LICENSE "%OUT%\LICENSE" >nul || goto :err
copy /y README.md "%OUT%\README.md" >nul || goto :err
if not exist "%OUT%\docs\HowTo" mkdir "%OUT%\docs\HowTo"
xcopy /y /i docs\HowTo\*.md "%OUT%\docs\HowTo\" >nul || goto :err
if exist "%OUT%\runtime\LICENSE.txt" (
  if not exist "%OUT%\THIRD_PARTY_LICENSES" mkdir "%OUT%\THIRD_PARTY_LICENSES"
  copy /y "%OUT%\runtime\LICENSE.txt" "%OUT%\THIRD_PARTY_LICENSES\Python-%PY_EMBED_VERSION%.txt" >nul
)

echo [9/9] Portable ZIP erzeugen ...
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
echo FEHLER: Kopiertes Backend konnte nicht inhaltlich verifiziert werden.
goto :err

:err
echo.
echo FEHLER beim Windows-Portable-Build.
exit /b 1
