# Windows Updater v0.1.1 (experimentell)

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
- manuellen `adb reconnect`.

Offizielle Downloadseite:

https://developer.android.com/tools/releases/platform-tools?hl=de#downloads

LTE-/USB-Anleitung:

https://github.com/dosordie/FoxAir_updater/blob/main/docs/HowTo/firmware_backup_lte.md

## Funktionen der GUI v0.1.1

### Verbindung

- ADB-Pfad auswählen und lokal merken;
- ADB-Gerät prüfen;
- `offline` erkennen und einmal `adb reconnect` versuchen.

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

1. Firmwaredatei auswählen;
2. **Vorschau aus Firmware (Full / Show)** ausführen;
3. die automatisch erkannten und berechneten Werte prüfen;
4. **Manifest automatisch erzeugen (Full)** verwenden.

Intern entsprechen diese beiden Aktionen:

```text
create_firmware_manifest.py --firmware FW.bin --full --show
create_firmware_manifest.py --firmware FW.bin --full --output FW.json
```

Die Full-Variante validiert das Cortex-M-Image, sucht die Firmware-Identität im Image, liest daraus Software-Code und Wire-/Display-Version und berechnet Dateigröße, MD5 und SHA-256. Feste FoxAir-Werte wie Target-SSID und Image-Basis werden weiterhin durch dasselbe gemeinsame Tool geprüft.

Wenn die automatische Firmwareanalyse nicht möglich ist, bleibt als letzter Fallback **Manifest manuell erzeugen** mit Software-Code, Display-Version und Target-SSID erhalten. Die eigentliche Manifestvalidierung erfolgt auch dabei weiterhin im gemeinsamen Tool.

### Protokoll

Das Protokoll kann gespeichert oder mit **Protokoll leeren** direkt in der GUI geleert werden.

## Experimenteller Stand

Ein echter Versionswechsel wurde weiterhin **nicht live bestätigt**. Bisher wurde auf realer Hardware nur V3.3 -> V3.3 getestet; das Mainboard hat diese gleiche Version erwartungsgemäß abgelehnt.

Die GUI ändert daran nichts. Sie macht den bestehenden Ablauf nur komfortabler bedienbar.

## Automatische Windows Releases

Der Workflow `.github/workflows/windows-build.yml` baut die Windows-Version nach relevanten Änderungen auf `main` automatisch.

Nach einem erfolgreichen Build wird für die in `foxair_updater_gui.py` eingetragene `APP_VERSION` automatisch ein öffentliches GitHub-**Prerelease** erzeugt, sofern das Release noch nicht existiert.

Namensschema:

```text
Tag:     windows-v0.1.1
Release: FoxAir Updater Windows v0.1.1
```

Damit sind Windows-Versionen in der gemeinsamen GitHub-Release-Liste klar an `windows-v...` und dem Release-Titel erkennbar. GitHub bietet innerhalb eines Repositorys keine getrennte eigene Release-Kategorie nur für Windows.

Das Release enthält direkt:

```text
FoxAir_Updater_Portable_v0.1.1.zip
FoxAir_Updater_Setup_v0.1.1.exe
```

Diese Release-Dateien sind bei einem öffentlichen Repository auch ohne GitHub-Anmeldung herunterladbar.

### Warum das Actions-Portable vorher doppelt gezippt erschien

GitHub Actions verpackt jedes heruntergeladene Artifact selbst als ZIP. Zuvor wurde darin noch unser bereits erzeugtes Portable-ZIP abgelegt. Dadurch entstand beim Download aus **Actions** effektiv ZIP-in-ZIP.

Der Workflow lädt dort jetzt stattdessen direkt den Portable-Ordner als Artifact hoch. Ein Actions-Download enthält dadurch nur noch die eine von GitHub erzeugte ZIP-Hülle.

Für **Releases** wird weiterhin das eigentliche einmal gepackte `FoxAir_Updater_Portable_v0.1.1.zip` direkt als Release-Asset veröffentlicht.

## Portable Build

Voraussetzungen auf dem **Build-PC**:

- Windows x64;
- installierte Python-Version mit `py` Launcher;
- Internetzugriff beim ersten Build.

Aus dem Repository-Root:

```bat
updater\windows\build_windows_portable.bat
```

Der Build:

1. installiert PySide6/PyInstaller für den Build-PC;
2. baut `FoxAir_Updater.exe` als PyInstaller-One-Folder-Anwendung;
3. kopiert das bestehende Backend bytegleich nach `dist\FoxAir_Updater\backend`;
4. lädt von `python.org` die offizielle Python-3.11.9-Embeddable-Runtime;
5. prüft die gepinnte MD5 `6d9aa08531d48fcc261ba667e2df17c4`;
6. prüft Controller und Manifest-Tool mit dieser privaten Runtime;
7. legt GPL-/Python-Lizenzen und HowTo-Dokumentation bei;
8. erzeugt ein Portable-ZIP.

Ergebnis:

```text
dist/FoxAir_Updater/
dist/FoxAir_Updater_Portable_v0.1.1.zip
```

Der Endanwender benötigt **keine Python-Installation**.

Die private Runtime ist nur dazu da, die unveränderten Backend-`.py`-Dateien auszuführen. ADB ist ausdrücklich nicht Bestandteil des Pakets.

## Setup bauen

Nach erfolgreichem Portable-Build wird zusätzlich **Inno Setup 6** benötigt.

```bat
updater\windows\build_windows_setup.bat
```

Ergebnis:

```text
updater/windows/installer/Output/FoxAir_Updater_Setup_v0.1.1.exe
```

Das Setup installiert denselben Inhalt wie die Portable-Version nach `Program Files`. Laufzeitdaten und OTA-State werden von der GUI in das lokale Benutzer-Anwendungsdatenverzeichnis geschrieben, nicht in `Program Files`.

## Entwicklungsstart ohne Packaging

Für GUI-Entwicklung kann die Datei direkt aus dem Repository gestartet werden, wenn PySide6 installiert ist:

```bat
py -m pip install -r updater\windows\requirements-build.txt
py updater\windows\foxair_updater_gui.py
```

In diesem Modus verwendet die GUI denselben Repository-Controller direkt und den aktuell gestarteten Python-Interpreter als Backend-Runtime.
