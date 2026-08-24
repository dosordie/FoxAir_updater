# Windows Updater v0.1.5 (experimentell)

Die Windows-Version ist bewusst als **dünne GUI vor dem bestehenden gemeinsamen OTA-Backend** gebaut.

> [!IMPORTANT]
> **Real getestet sind derzeit:** lokale/Remote-ADB-Verbindung, Originalstatus, das read-only LTE-Backup/Firmware-Download per `adb pull` und der Dry-Run.
>
> Zusätzlich wurde mit Windows v0.1.3 der normale **Firmware-Update**-Button über Remote-ADB real mit **V3.3 → V3.3** ausgeführt. Das Mainboard erkannte die bereits installierte Firmware und beendete den Ablauf sicher mit `same-version`; `C357` und `C5A8` wurden nicht erreicht und der Originalbetrieb wurde danach wieder bestätigt. Es wurden keine Firmwaredaten übertragen.
>
> Die seit v0.1.4 vorgeschaltete Windows-Sicherheitshülle mit zusätzlichem Full-Abgleich und LTE-Cache-Sicherung ist noch nicht in genau diesem Live-Test nachgetestet worden. Ein **echtes Firmwareupdate auf eine andere Mainboard-Version mit C5A8-Datenübertragung wurde unter Windows weiterhin noch nicht live durchgeführt und bestätigt**.

Öffentliche Windows-Versionen stehen als Portable-ZIP und Setup-EXE auf der normalen GitHub-Releases-Seite bereit:

https://github.com/dosordie/FoxAir_updater/releases

## Wichtig: keine Refaktorierung der OTA-Logik

Die sicherheitsrelevante gemeinsame OTA-Logik wird beim Windows-Build **nicht in eine zweite Implementierung übertragen und nicht für Windows umgeschrieben**.

Der Build kopiert insbesondere:

```text
tools/phnix_ota/phnix_local_ota_controller.py
updater/common/*.py
tools/phnix_ota/create_firmware_manifest.py
tools/phnix_ota/phnix_ota_runtime_hook
```

bytegleich in das Windows-Paket und prüft die Kopien mit `fc /b`.

Seit v0.1.4 liegt davor zusätzlich eine kleine Windows-Sicherheitshülle. Seit v0.1.5 liegt darüber außerdem nur eine Windows-UI-Schicht für die lesbare Statusdarstellung:

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
        ↑ bytegleiche Kopie von
          tools/phnix_ota/phnix_local_ota_controller.py
```

Der Wrapper bildet ausschließlich die Linux-Launcher-Funktionen nach, die **außerhalb** des eigentlichen Controllers liegen:

- Full-Firmware-/Manifest-Abgleich unmittelbar vor einem echten Update;
- Sicherung einer eventuell vorhandenen `/cache/phnixIot_device_OTA`;
- Erhalt dieses Backups bei nicht sicher terminalem Updatezustand;
- Wiederherstellung des Cachezustands nach erfolgreichem Same-Version-Test bzw. nach einem vom Controller freigegebenen Restore.

Die neue v0.1.5-UI-Schicht interpretiert nur die bereits vorhandenen JSON-Ereignisse für den Benutzer. Entscheidungen über Preflight, Update, Guarded Hold, C5A8-Grenze und Zulässigkeit eines Restore verbleiben weiterhin im bestehenden gemeinsamen Controller.

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

Die GUI setzt für ihre gestarteten Prozesse:

```text
ADB_SERVER_SOCKET=tcp:<IP_DES_PI>:5038
```

Dadurch verwenden GUI, Windows-Sicherheitswrapper, gemeinsamer Controller und `adb pull`/`push`-Aufrufe denselben entfernten ADB-Server, **ohne Änderung am gemeinsamen OTA-Code**.

Auch im Remote-Modus wird auf Windows weiterhin eine lokale `adb.exe` als ADB-Client benötigt. Der Remote-Port sollte nur kurzfristig in einem vertrauenswürdigen LAN offen sein.

## Funktionen der GUI v0.1.5

### Verbindung

- lokaler oder Remote-ADB-Modus;
- ADB-Pfad auswählen und lokal merken;
- ADB-Gerät prüfen;
- `offline` erkennen und einmal `adb reconnect` versuchen;
- Remote-Host und Port lokal merken;
- erfolgreiche Verbindung grün, `offline` orange und Fehler rot darstellen.

### Backup / Firmware Downloader

Der Backup-Pfad wurde real getestet und verwendet ausschließlich read-only `adb pull`:

```text
/cache/phnixIot_device_OTA
/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic
/data/phnixIot4G
```

Firmware, OTA_INFO und Statistik sind vorausgewählt; der Originaldienst kann zusätzlich angehakt werden.

Die Registerkarte bietet:

- frei wählbaren Zielordner;
- **Backup erstellen**;
- **Zielordner öffnen**, um den tatsächlich verwendeten Sicherungsordner direkt im Windows-Explorer zu kontrollieren.

Der Button **Zielordner…** ist nur ein Ordner-Auswahldialog und zeigt deshalb nicht wie ein normaler Explorer-Browser den Ordnerinhalt an.

### Status / Recovery

Der Originalzustand kann über den bestehenden Controller geprüft werden. Erfolgreiche Einzelprüfungen und der Gesamtstatus werden grün, Fehler rot dargestellt.

Restore bleibt an die Sicherheitsentscheidung des bestehenden Controllers gebunden. Sobald die C5A8-Grenze überschritten wurde, darf die Windows-Hülle diese Entscheidung nicht umgehen.

### Firmware Update / Dry-Run

Die GUI verwendet für den eigentlichen OTA-Ablauf weiterhin den bytegleichen gemeinsamen Controller-Core.

Vor einem echten Update führt die Windows-Sicherheitshülle zusätzlich automatisch denselben Full-Abgleich durch, den der Linux-Launcher mit `--full` anbietet. Verglichen werden unter anderem:

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

Erst wenn diese Prüfung erfolgreich ist, wird der ursprüngliche LTE-Firmware-Cache gesichert und anschließend der gemeinsame Controller mit `PHNIX-FULL-UPDATE` gestartet.

v0.1.5 zeigt die vorhandenen Controller-Ereignisse zusätzlich als lesbaren Ablauf an:

- **grüne Punkte** für erfolgreiche Prüfungen und sicher bestätigte Zustände;
- **gelbe Punkte** für Warte-/Transferzustände und erwartete Warnungen wie gleiche Firmware;
- **rote Punkte** für Fehler, Guarded Hold oder notwendigen manuellen Recovery-Schritt.

Beispiele für lesbare Zustände sind:

```text
● Firmwaredatei und Manifest sind konsistent.
● ADB-Verbindung zum LTE-Modem ist bereit.
● Geprüfter PHNIX-Originaldienst ist aktiv und unverändert.
● OTA-Statusdatei ist gültig und CRC-geprüft.
● Vorprüfung vollständig bestanden.
● Firmware wurde auf dem LTE-Modem bereitgestellt.
● Gleiche Firmware erkannt – keine Firmwaredaten übertragen.
● Originaldienst, Watchdogs und Cloud/MQTT laufen wieder.
```

Das technische Rohprotokoll mit allen JSON-Zeilen bleibt unverändert darunter erhalten und kann weiterhin gespeichert werden.

Abschluss-Popups zeigen keine bloßen technischen `Exit 0`-Texte mehr, sondern unterscheiden unter anderem:

- **Dry-Run erfolgreich – nichts wurde verändert**;
- **Update nicht durchgeführt – gleiche Firmware**;
- **Firmwareupdate erfolgreich**;
- **Update sicher angehalten / Guarded Hold**;
- **Firmwareupdate wegen Fehler abgebrochen**;
- **Wiederherstellung erfolgreich/fehlgeschlagen**.

### Fortschrittsbalken

Ein Fortschrittsbalken ist vorhanden. Sobald der Controller während der C5A8-Phase eine gültige `OTA_INFO` mit `offset > 0` und `length > 0` meldet, zeigt die GUI:

```text
67 % – 192.000 / 287.598 Byte
```

Die Prozentzahl wird ausschließlich aus den vom Originaldienst gemeldeten `offset/length`-Werten berechnet. Bei einer Gleichversionsablehnung bleibt der Balken bewusst bei 0 und zeigt **Keine Übertragung – gleiche Firmware**, weil keine C5A8-Firmwaredaten gesendet wurden.

> [!WARNING]
> Die C5A8-Fortschrittsanzeige ist softwareseitig implementiert, konnte aber noch nicht an einem echten Windows-Versionswechsel beobachtet werden, weil ein solcher Transfer bislang nicht live ausgeführt wurde.

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

Ein echter Versionswechsel wurde weiterhin **nicht live bestätigt**. Bisher wurde auf realer Hardware V3.3 → V3.3 bis zur erwarteten Gleichversionsablehnung getestet; dabei wurden keine Firmwareblöcke geschrieben.

Für Windows sind ADB, Remote-ADB, Originalstatus, Backup und Dry-Run bestätigt. Zusätzlich wurde unter Windows v0.1.3 der normale Update-Aufruf über Remote-ADB bis zur sicheren Gleichversionsablehnung real bestätigt. Die später ergänzte Windows-Sicherheitshülle muss in diesem Pfad noch nachgetestet werden; die C5A8-Schreibphase einer anderen Firmware bleibt weiterhin ungetestet.

## GitHub Actions: Build und Release getrennt

### Windows Updater Build

`.github/workflows/windows-build.yml` läuft nach relevanten Änderungen auf `main` beziehungsweise manuell. Dieser Workflow ist nur zum Bauen und Testen gedacht und veröffentlicht **kein GitHub Release**.

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
0.1.5
```

Optional kann festgelegt werden, ob das Release als Prerelease markiert wird.

Der Workflow:

1. setzt die eingegebene Version synchron in GUI-Einstieg, Basis-GUI, Portable-Build und Inno-Setup-Datei;
2. prüft die Python-Syntax beider GUI-Dateien;
3. baut Portable und Setup;
4. prüft, dass beide Release-Dateien vorhanden sind;
5. committed eine eventuell geänderte Versionsnummer nach `main`;
6. erzeugt den Tag `windows-v<Version>`;
7. veröffentlicht ein normales GitHub Release mit Portable-ZIP und Setup-EXE.

Beispiel:

```text
Tag:     windows-v0.1.5
Release: FoxAir Updater Windows v0.1.5
```

Release-Assets:

```text
FoxAir_Updater_Portable_v0.1.5.zip
FoxAir_Updater_Setup_v0.1.5.exe
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
3. baut `FoxAir_Updater.exe` aus `foxair_updater_app.py` als PyInstaller-One-Folder-Anwendung;
4. kopiert den gemeinsamen Controller bytegleich als `phnix_local_ota_controller_core.py`;
5. legt davor den Windows-Sicherheitswrapper unter dem von der GUI erwarteten Controller-Dateinamen ab;
6. prüft Wrapper und gemeinsamen Backend-Code mit `fc /b`;
7. lädt von `python.org` die offizielle Python-3.11.9-Embeddable-Runtime;
8. prüft die gepinnte MD5 `6d9aa08531d48fcc261ba667e2df17c4`;
9. prüft Wrapper, Controller-Core und Manifest-Tool mit dieser privaten Runtime und erzeugt das Portable-ZIP.

Ergebnis:

```text
dist/FoxAir_Updater/
dist/FoxAir_Updater_Portable_v0.1.5.zip
```

Der Endanwender benötigt **keine Python-Installation**. ADB ist ausdrücklich nicht Bestandteil des Pakets.

## Setup bauen

Nach erfolgreichem Portable-Build wird zusätzlich **Inno Setup 6** benötigt.

```bat
updater\windows\build_windows_setup.bat
```

Ergebnis:

```text
updater/windows/installer/Output/FoxAir_Updater_Setup_v0.1.5.exe
```

Das Setup installiert denselben Inhalt wie die Portable-Version nach `Program Files`. Laufzeitdaten und OTA-State werden von der GUI bzw. der Windows-Sicherheitshülle in das lokale Benutzer-Anwendungsdatenverzeichnis geschrieben, nicht in `Program Files`.

## Entwicklungsstart ohne Packaging

Für GUI-Entwicklung können Basis-GUI und Erweiterung direkt aus dem Repository gestartet werden, wenn PySide6 installiert ist:

```bat
py -m pip install -r updater\windows\requirements-build.txt
py updater\windows\foxair_updater_app.py
```

Im Entwicklungsmodus läuft die GUI direkt gegen die Repository-Dateien. Die Release-Builds verwenden zusätzlich die oben beschriebene Windows-Sicherheitshülle, ohne die gemeinsame OTA-Logik zu verändern.
