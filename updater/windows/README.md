# Windows Updater v0.1.2 (experimentell)

Die Windows-Version ist bewusst als **dünne GUI vor dem bestehenden Linux-/Raspberry-Pi-Backend** gebaut.

## Wichtig: keine Refaktorierung der OTA-Logik

Die sicherheitsrelevanten Dateien werden beim Windows-Build **nicht in eine zweite Implementierung übertragen und nicht für Windows umgeschrieben**. Der Build kopiert insbesondere diese vorhandenen Repository-Dateien bytegleich in das Windows-Paket:

```text
tools/phnix_ota/phnix_local_ota_controller.py
tools/phnix_ota/create_firmware_manifest.py
tools/phnix_ota/phnix_ota_runtime_hook
updater/__init__.py
updater/common/*.py
```

`build_windows_portable.bat` prüft die kopierten Backend-Dateien mit `fc /b`. Bei einer Abweichung wird der Build abgebrochen.

Die Windows-GUI startet den bestehenden Controller lediglich als separaten Prozess und wertet dessen vorhandene JSON-Ausgabe aus. Entscheidungen über Preflight, Update, Guarded Hold, C5A8-Grenze oder Restore verbleiben ausschließlich im bestehenden Controller.

Damit gilt für Linux und Windows weiterhin dieselbe OTA-Quelle.

## ADB

**ADB wird nicht mitgeliefert.**

Die GUI bietet:

- automatische Suche nach einer bereits vorhandenen `adb.exe`;
- manuelle Auswahl der `adb.exe`;
- Link zur offiziellen Google-Seite für Android SDK Platform Tools;
- Link zur zentralen LTE-/USB-Anleitung;
- `adb devices -l`;
- bei `offline` einen einmaligen automatischen `adb reconnect`;
- manuellen `adb reconnect`;
- optionalen **Remote-ADB-Modus über einen Raspberry Pi**.

Offizielle Downloadseite:

https://developer.android.com/tools/releases/platform-tools?hl=de#downloads

LTE-/USB-Anleitung:

https://github.com/dosordie/FoxAir_updater/blob/main/docs/HowTo/firmware_backup_lte.md

## Remote ADB über Raspberry Pi

Dieser Modus ist für Spezialfälle gedacht, in denen das LTE-Modem per USB an einem Raspberry Pi hängt, die Windows-GUI aber auf einem anderen Rechner läuft.

Auf dem Raspberry Pi kann der ADB-Server kurzfristig im lokalen LAN freigegeben werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Der zweite Befehl bleibt im Vordergrund. Zum Beenden einfach **Strg+C** drücken.

In der Windows-GUI anschließend auswählen:

```text
Remote – ADB-Server auf Raspberry Pi
Raspberry-Pi-IP: <IP_DES_PI>
ADB-Server-Port: 5038
```

Die GUI setzt für ihre gestarteten Prozesse nur:

```text
ADB_SERVER_SOCKET=tcp:<IP_DES_PI>:5038
```

Dadurch verwenden auch der bestehende Controller und alle `adb pull`-Aufrufe denselben entfernten ADB-Server, **ohne Änderung am gemeinsamen OTA-Code**.

Auch im Remote-Modus wird auf Windows weiterhin eine lokale `adb.exe` als ADB-Client benötigt. Der Remote-Port sollte nur kurzfristig in einem vertrauenswürdigen LAN offen sein.

## Funktionen der GUI v0.1.2

### Verbindung

- lokaler oder Remote-ADB-Modus;
- ADB-Pfad auswählen und lokal merken;
- ADB-Gerät prüfen;
- `offline` erkennen und einmal `adb reconnect` versuchen;
- Remote-Host und Port lokal merken.

### Backup / Firmware Downloader

Read-only Backup per `adb pull`:

```text
/cache/phnixIot_device_OTA
/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic
/data/phnixIot4G
```

Der Originaldienst ist standardmäßig nicht angehakt; Firmware, OTA_INFO und Statistik sind vorausgewählt.

### Firmware Update

Die GUI verwendet direkt:

```text
phnix_local_ota_controller.py
```

für:

- Originalstatus;
- Dry-Run;
- vollständiges Update mit `PHNIX-FULL-UPDATE`;
- Restore `original`;
- Gleichversionstest mit den bekannten V3.3-Bestätigungen.

Die GUI zeigt die vom Controller ausgegebenen JSON-Events und OTA-Fortschritte an. Ein `Guarded Hold` wird deutlich angezeigt. Die GUI enthält keine eigene Recovery- oder OTA-State-Machine.

### Manifest

Die GUI verwendet weiterhin unverändert:

```text
create_firmware_manifest.py
```

Der empfohlene Ablauf entspricht der Linux-Funktionalität:

1. originale Firmwaredatei auswählen;
2. **Vorschau aus Firmware (Full / Show)** ausführen;
3. die automatisch erkannten und berechneten Werte prüfen;
4. **Manifest automatisch erzeugen (Full)** verwenden.

Intern entsprechen diese beiden Aktionen:

```text
create_firmware_manifest.py --firmware FIRMWARE --full --show
create_firmware_manifest.py --firmware FIRMWARE --full --output FIRMWARE.json
```

Die Firmwaredatei muss **keine `.bin`-Endung** besitzen. Der Dateidialog zeigt daher standardmäßig alle Dateien an. Die originale Firmware wird nicht verändert.

Die Full-Variante validiert das Cortex-M-Image, sucht die Firmware-Identität im Image, liest daraus Software-Code und Wire-/Display-Version und berechnet Dateigröße, MD5 und SHA-256. Feste FoxAir-Werte wie Target-SSID und Image-Basis werden weiterhin durch dasselbe gemeinsame Tool geprüft.

Wenn die automatische Firmwareanalyse nicht möglich ist, bleibt als letzter Fallback **Manifest manuell erzeugen** mit Software-Code, Display-Version und Target-SSID erhalten.

### Protokoll

Das Protokoll kann gespeichert oder mit **Protokoll leeren** direkt in der GUI geleert werden.

## Programmlogo

Die Windows-Version verwendet dasselbe `app_icon.ico` wie `FoxAir_Control`.

Der Build lädt die Datei direkt aus dem öffentlichen `FoxAir_Control`-Repository und prüft anschließend mit `git hash-object`, dass exakt der gepinnte Git-Blob

```text
0ae281034216f69c4f18dbdb55cc70d8b78e47e1
```

verwendet wird. Das Logo wird als EXE-Icon, Fenster-Icon und Setup-Icon verwendet.

## Experimenteller Stand

Ein echter Versionswechsel wurde weiterhin **nicht live bestätigt**. Bisher wurde auf realer Hardware nur V3.3 -> V3.3 getestet; das Mainboard hat diese gleiche Version erwartungsgemäß abgelehnt.

Die GUI ändert daran nichts. Sie macht den bestehenden Ablauf nur komfortabler bedienbar.

## GitHub Actions: Build und Release getrennt

### Windows Updater Build

`.github/workflows/windows-build.yml` läuft nach relevanten Änderungen auf `main` beziehungsweise manuell. Dieser Workflow ist nur zum Bauen und Testen gedacht und veröffentlicht **kein GitHub Release** mehr.

Die Actions-Artefakte enthalten:

- den Portable-Ordner als ein von GitHub einmal gepacktes ZIP;
- die Setup-EXE.

Dadurch gibt es beim Actions-Download kein ZIP-in-ZIP mehr.

### Release Windows

Für eine öffentliche Version unter **GitHub Releases** gibt es den separaten Workflow:

```text
Actions → Release Windows → Run workflow
```

Dort wird nur die Zielversion eingetragen, zum Beispiel:

```text
0.1.2
```

Optional kann festgelegt werden, ob das Release als Prerelease markiert wird.

Der Workflow:

1. setzt die eingegebene Version synchron in GUI, Portable-Build und Inno-Setup-Datei;
2. prüft die Python-Syntax der GUI;
3. baut Portable und Setup;
4. prüft, dass beide Release-Dateien vorhanden sind;
5. committed eine eventuell geänderte Versionsnummer nach `main`;
6. erzeugt den Tag `windows-v<Version>`;
7. veröffentlicht ein normales GitHub Release mit Portable-ZIP und Setup-EXE.

Beispiel:

```text
Tag:     windows-v0.1.2
Release: FoxAir Updater Windows v0.1.2
```

Release-Assets:

```text
FoxAir_Updater_Portable_v0.1.2.zip
FoxAir_Updater_Setup_v0.1.2.exe
```

Diese Dateien sind bei einem öffentlichen Repository auch ohne GitHub-Anmeldung über die normale Releases-Seite herunterladbar.

## Portable Build

Voraussetzungen auf dem **Build-PC**:

- Windows x64;
- installierte Python-Version mit `py` Launcher;
- Git;
- Internetzugriff beim ersten Build.

Aus dem Repository-Root:

```bat
updater\windows\build_windows_portable.bat
```

Der Build:

1. installiert PySide6/PyInstaller für den Build-PC;
2. lädt und verifiziert das FoxAir-Control-Programmlogo;
3. baut `FoxAir_Updater.exe` als PyInstaller-One-Folder-Anwendung;
4. kopiert das bestehende Backend bytegleich nach `dist\FoxAir_Updater\backend`;
5. prüft die Bytegleichheit des gemeinsamen Backends;
6. lädt von `python.org` die offizielle Python-3.11.9-Embeddable-Runtime;
7. prüft die gepinnte MD5 `6d9aa08531d48fcc261ba667e2df17c4`;
8. prüft Controller und Manifest-Tool mit dieser privaten Runtime;
9. legt Dokumentation/Lizenzen bei und erzeugt das Portable-ZIP.

Ergebnis:

```text
dist/FoxAir_Updater/
dist/FoxAir_Updater_Portable_v0.1.2.zip
```

Der Endanwender benötigt **keine Python-Installation**. ADB ist ausdrücklich nicht Bestandteil des Pakets.

## Setup bauen

Nach erfolgreichem Portable-Build wird zusätzlich **Inno Setup 6** benötigt.

```bat
updater\windows\build_windows_setup.bat
```

Ergebnis:

```text
updater/windows/installer/Output/FoxAir_Updater_Setup_v0.1.2.exe
```

Das Setup installiert denselben Inhalt wie die Portable-Version nach `Program Files`. Laufzeitdaten und OTA-State werden von der GUI in das lokale Benutzer-Anwendungsdatenverzeichnis geschrieben, nicht in `Program Files`.

## Entwicklungsstart ohne Packaging

Für GUI-Entwicklung kann die Datei direkt aus dem Repository gestartet werden, wenn PySide6 installiert ist:

```bat
py -m pip install -r updater\windows\requirements-build.txt
py updater\windows\foxair_updater_gui.py
```

In diesem Modus verwendet die GUI denselben Repository-Controller direkt und den aktuell gestarteten Python-Interpreter als Backend-Runtime.
