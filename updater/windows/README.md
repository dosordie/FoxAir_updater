# Windows Updater v0.3.9

Die Windows-Version ist bewusst als **dünne GUI vor dem bestehenden gemeinsamen OTA-Backend** gebaut. Die sicherheitsrelevante OTA-Logik wird nicht als separate Windows-Implementierung gepflegt.

> [!IMPORTANT]
> **Real bestätigt sind derzeit:** lokale und Remote-ADB-Verbindung, Originalstatus, read-only LTE-Backup/Firmware-Download, Dry-Run, V3.3→V3.3 bis zur sicheren Gleichversionsablehnung sowie ein vollständiger realer Mainboard-Firmwarewechsel **V3.3 → V3.4**.
>
> Beim V3.3→V3.4-Lauf wurden die vollständige C5A8-Datenübertragung, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließend die neue C544-Version `0034` beobachtet. Andere Firmwarestände und Hardwarevarianten sind weiterhin nicht vollständig live validiert.

Öffentliche Windows-Versionen stehen als Portable-ZIP und Setup-EXE auf der normalen GitHub-Releases-Seite bereit:

https://github.com/dosordie/FoxAir_updater/releases

Release-Details zu v0.3.9:

[`../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md`](../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md)

## Windows SmartScreen beim ersten Start

Die Windows-Builds sind derzeit **nicht mit einem kommerziellen Code-Signing-Zertifikat signiert**. Windows SmartScreen kann deshalb beim ersten Start des Setup oder der EXE die Meldung **„Der Computer wurde durch Windows geschützt“** anzeigen.

Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite geladen wurde:

1. **Weitere Informationen** anklicken;
2. anschließend **Trotzdem ausführen** wählen.

Eine Datei aus einer anderen oder unbekannten Quelle sollte dagegen nicht einfach freigegeben werden.

## Architektur: gemeinsame OTA-Logik

Der Build übernimmt insbesondere:

```text
tools/phnix_ota/phnix_local_ota_controller.py
updater/common/*.py
tools/phnix_ota/create_firmware_manifest.py
tools/phnix_ota/phnix_ota_runtime_hook
```

in das Windows-Paket. Die Windows-Schicht ergänzt Host-spezifische Bedienung, Statusdarstellung, Full-Abgleich und Cache-Sicherung, ohne einen zweiten OTA-Protokollkern einzuführen.

```text
FoxAir_Updater.exe
        ↓
foxair_updater_app.py
  lesbare Ablauf-/Ergebnisdarstellung
        ↓
foxair_updater_gui.py
  Basis-GUI
        ↓
private Python Runtime
        ↓
phnix_windows_controller_wrapper.py
        ↓
phnix_local_ota_controller_core.py
        ↑ gemeinsame OTA-Logik
```

Entscheidungen über Preflight, OTA-Handshakes, C5A8-Grenze, Guarded Hold und Restore-Zulässigkeit verbleiben im gemeinsamen Controller.

## ADB

**ADB wird nicht mitgeliefert.**

Die GUI bietet:

- Link zum SIMCom Windows USB Driver V1.0.2;
- automatische Suche nach einer vorhandenen `adb.exe`;
- manuelle Auswahl der `adb.exe`;
- Link zu den offiziellen Android SDK Platform Tools;
- Link zur LTE-/USB-Anleitung;
- `adb devices -l`-Prüfung;
- automatischen und manuellen `adb reconnect`;
- optionalen **Remote-ADB-Modus über einen Raspberry Pi**.

SIMCom-Treiber:

https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip

Android Platform Tools:

https://developer.android.com/tools/releases/platform-tools?hl=de#downloads

LTE-/USB-Anleitung:

[`../../docs/HowTo/firmware_backup_lte.md`](../../docs/HowTo/firmware_backup_lte.md)

## Remote ADB über Raspberry Pi

Auf dem Raspberry Pi kann der ADB-Server kurzfristig im lokalen LAN bereitgestellt werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

In der Windows-GUI anschließend:

```text
Remote – ADB-Server auf Raspberry Pi
Raspberry-Pi-IP: <IP_DES_PI>
ADB-Server-Port: 5038
```

Die GUI setzt für ihre gestarteten Prozesse:

```text
ADB_SERVER_SOCKET=tcp:<IP_DES_PI>:5038
```

Auch im Remote-Modus wird unter Windows eine lokale `adb.exe` als Client benötigt. Der Remote-Port sollte nur kurzfristig in einem vertrauenswürdigen LAN offen sein.

Die Verbindungswerte werden über `QSettings("FoxAir", "FoxAir Updater")` gespeichert. Dazu gehören unter anderem ADB-Modus, Raspberry-Pi-IP/Port, ADB-Pfad und Backup-Ziel.

## Funktionen der GUI v0.3.9

### Verbindung

- lokaler oder Remote-ADB-Modus;
- ADB-Pfad auswählen und speichern;
- ADB-Gerät prüfen;
- `offline` erkennen und Reconnect versuchen;
- Remote-Host und Port speichern;
- Status farblich verständlich darstellen.

### Backup / Firmware Downloader

Der Backup-Pfad wurde real getestet und verwendet ausschließlich read-only `adb pull`:

```text
/cache/phnixIot_device_OTA
/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic
/data/phnixIot4G
```

Firmware, OTA_INFO und Statistik sind vorgesehen; der Originaldienst kann zusätzlich gesichert werden. Das Backup verändert die Dateien auf dem LTE-Modem nicht.

### Status / Recovery

Der Originalzustand wird read-only geprüft. Dazu gehören unter anderem:

- Originaldienst läuft;
- erwartete SHA-256 des Dienstes;
- kein Debugger;
- keine lokale OTA-Injection;
- keine verbliebene Cloud-/MQTT-Sperre;
- Watchdogs laufen;
- MQTT/Cloud verbunden;
- temporärer lokaler OTA-Zustand bereinigt.

Restore bleibt an die Sicherheitsentscheidung des Controllers gebunden. Sobald der erste C5A8-Firmwareblock begonnen hat, darf die Windows-Hülle diese Grenze nicht umgehen.

### Firmware Update / Dry-Run

Vor einem echten Update führt die Windows-Sicherheitshülle einen Full-Abgleich von Firmware und Manifest durch. Verglichen werden unter anderem:

```text
schema
firmware_file
software_code
display_version
wire_version
target_ssid
size
md5
sha256
image_base
```

Erst nach erfolgreicher Prüfung wird der gemeinsame Controller mit der expliziten Freigabe `PHNIX-FULL-UPDATE` gestartet.

Die GUI übersetzt die technischen JSON-Ereignisse in lesbare Phasen und lässt das Rohprotokoll weiterhin sichtbar und speicherbar.

## MQTT während des Updates

Seit v0.3.9 bleibt MQTT beim normalen Vollupdate **standardmäßig verbunden**.

Unter **Erweitert** existiert die persistente Checkbox:

```text
MQTT bei Update aus
```

- **aus** = Standard; kein `--isolate-mqtt`, MQTT bleibt verbunden;
- **an** = `--isolate-mqtt`, frühere MQTT-Isolierung für besondere Testfälle.

Die Isolation ist nicht der empfohlene Normalbetrieb. Der Originaldienst besitzt einen eigenen Rebootpfad, wenn der Aliyun-MQTT-Client intern länger als 1800 Sekunden offline ist.

Wichtig: Diese 1800 Sekunden beginnen nicht zwingend beim Einsetzen einer `iptables DROP`-Regel. Der Aliyun-SDK kann mehrere 180-s-Keepalive-Zyklen benötigen, bevor der interne Clientzustand überhaupt auf offline wechselt. Erst danach beginnt der PHNIX-Offlinezähler. Es gibt keinen bekannten OTA-Sonderzweig, der diesen Rebootmechanismus während des Mainboardupdates deaktiviert.

## Fortschritts- und Abschlusslogik

Während C5A8 zeigt die GUI den vom Originaldienst gemeldeten `offset/length`-Fortschritt.

> [!WARNING]
> **100 % bedeutet nur: alle Firmwaredaten wurden übertragen.** Es bedeutet noch nicht, dass das Mainboard bereits geflasht, promoted und neu gestartet ist.

Der reale V3.3→V3.4-Lauf zeigte:

```text
C5A8 vollständig übertragen
→ C36E Status 3
→ Mainboard-Verarbeitung / Flash / Promotion
→ C36E Status 5
→ Board-Step 12
→ neuer normaler Mainboard-/C544-Verkehr mit Version 0034
```

Gemessene Zeiten:

- C5A8-Transfer: ca. **28:56 min**;
- letzter C5A8 → Status 3: ca. **2 s**;
- letzter C5A8 → Status 5: ca. **5:16 min**;
- bis zur ersten neuen C544-Versionsmeldung insgesamt rund **35 min**.

Erst **Status 5 / Board-Step 12** ist der terminale Mainboard-Erfolg.

Nach diesem terminalen Ergebnis wartet der Controller bis zu **120 Sekunden** auf einen vollständig normalen LTE-/Cloudzustand. Damit wird ein erfolgreich geflashtes Mainboard nicht vorschnell als Fehler bewertet, nur weil MQTT unmittelbar danach noch nicht in `netstat` sichtbar ist.

## ADB-Verlust während eines laufenden Updates

Nach begonnenem C5A8 bleibt der originale `phnixIot4G`-Dienst autoritativ. Ein Windows-/ADB-Monitoringfehler darf den Transfer nicht aktiv stoppen oder einen generischen Restore erzwingen.

Die GUI kann nach einem ADB-Verbindungsverlust read-only reconnecten und den bestehenden OTA-Zustand erneut prüfen. Dabei wird kein zweiter Updateauftrag gestartet.

## Manifest

Empfohlener Windows-Ablauf:

1. originale Firmwaredatei auswählen;
2. **Vorschau aus Firmware (Full / Show)** ausführen;
3. erkannte Werte prüfen;
4. **Manifest automatisch erzeugen (Full)** verwenden;
5. Manifest im Firmware-Update-Tab auswählen;
6. Dry-Run/Prüfung vor dem echten Update durchführen.

Die Firmwaredatei muss keine `.bin`-Endung besitzen und wird durch die Analyse nicht verändert.

Details:
[`../../docs/HowTo/FIRMWARE_MANIFEST.md`](../../docs/HowTo/FIRMWARE_MANIFEST.md)

## Was real bestätigt ist

Auf realer Hardware wurden bestätigt:

- lokale und Remote-ADB-Verbindung;
- Originalstatus;
- read-only Backup/Firmware-Download;
- Dry-Run;
- V3.3→V3.3 bis zur sicheren Gleichversionsablehnung ohne C5A8;
- vollständiger V3.3→V3.4-Transfer mit C5A8;
- C36E Status 3 und Status 5;
- terminaler Board-Step 12;
- anschließende C544-Versionsmeldung `0034`;
- Rückkehr des normalen LTE-/MQTT-Zustands;
- Mainboard-OTA-Vorgangszähler-Wartung.

Nicht automatisch auf andere PHNIX-Mainboards, Softwarecodes oder Firmwarekombinationen übertragbar ist die Aussage, dass jeder beliebige Updatepfad identisch funktioniert.

## Programmlogo

Die Windows-Version verwendet `app_icon.ico` aus `FoxAir_Control`. Der Build verifiziert den gepinnten Git-Blob vor Verwendung als EXE-, Fenster- und Setup-Icon.

## GitHub Actions: Build und Release

### Windows Updater Build

`.github/workflows/windows-build.yml` baut und testet relevante Windows-Änderungen, veröffentlicht aber kein öffentliches GitHub Release.

### Release Windows

Öffentliche Windows-Releases werden über den separaten Workflow erstellt:

```text
Actions → Release Windows → Run workflow
```

Die Zielversion wird als `x.y.z` angegeben. Der Workflow synchronisiert die Versionsnummer in GUI, Portable-Build und Inno-Setup, baut Portable und Setup, erzeugt den Tag und veröffentlicht das GitHub Release.

Beispiel für v0.3.9:

```text
Tag:     windows-v0.3.9
Release: FoxAir Updater Windows v0.3.9
Assets:
  FoxAir_Updater_Portable_v0.3.9.zip
  FoxAir_Updater_Setup_v0.3.9.exe
```

## Portable Build

Voraussetzungen auf dem Build-PC:

- Windows x64;
- Python mit `py` Launcher;
- Git;
- Internetzugriff beim ersten Build.

Aus dem Repository-Root:

```bat
updater\windows\build_windows_portable.bat
```

Der Endanwender benötigt **keine Python-Installation**. ADB ist ausdrücklich nicht Bestandteil des Pakets.

## Setup bauen

Nach erfolgreichem Portable-Build wird zusätzlich Inno Setup 6 benötigt:

```bat
updater\windows\build_windows_setup.bat
```

Das Setup installiert denselben Inhalt wie die Portable-Version nach `Program Files`. Laufzeitdaten und OTA-State werden im Benutzer-Anwendungsdatenverzeichnis gespeichert.

## Entwicklungsstart ohne Packaging

```bat
py -m pip install -r updater\windows\requirements-build.txt
py updater\windows\foxair_updater_app.py
```

Im Entwicklungsmodus läuft die GUI über denselben Windows-Backendpfad wie das Release.

## Technische Referenzen

- [`../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md`](../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md)
- [`../../docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../../docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)
- [`../../docs/reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md`](../../docs/reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md)
- [`../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)