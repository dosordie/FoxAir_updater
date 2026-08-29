# PHNIX-Firmware-Updater – Anleitung für Anwender

Stand: 29. August 2026

> [!CAUTION]
> ## V3.3 → V3.4 wurde auf realer Hardware erfolgreich durchgeführt
>
> Ein vollständiger Mainboard-Firmwarewechsel von **V3.3 auf V3.4** wurde mit dem FoxAir Updater auf realer FoxAir-/PHNIX-Hardware erfolgreich durchgeführt und anschließend über **C36E Status 5 / Board-Step 12** sowie die neue C544-Version `0034` bestätigt.
>
> Zusätzlich wurde **V3.3 → V3.3** bis zur erwarteten Gleichversionsablehnung getestet; dabei wurden keine C5A8-Firmwaredaten übertragen.
>
> Andere Firmwarestände, Mainboardfamilien und Fehlerfälle sind weiterhin nicht in gleicher Tiefe live validiert. Ein Firmwareupdate bleibt ein Eingriff in das Mainboard und erfolgt **auf eigenes Risiko**.

Diese Anleitung beschreibt den normalen Endanwenderweg. Für Windows ist die grafische Anwendung der empfohlene Bedienweg. Unter Linux/Raspberry Pi steht weiterhin der Launcher `./foxair-updater` mit demselben gemeinsamen OTA-Kern zur Verfügung.

Der vorherige historische Stand der Anleitung liegt unter [`PHNIX_UPDATER_ENDANWENDER_OLD.md`](PHNIX_UPDATER_ENDANWENDER_OLD.md).

## Windows-GUI – empfohlener Weg unter Windows

Die aktuelle Windows-Version steht als Portable-ZIP und Setup-EXE auf der GitHub-Releases-Seite bereit:

**[FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)**

Aktueller dokumentierter Stand: **Windows v0.3.9**.

Release-Details:

[`../RELEASE_NOTES_WINDOWS_v0.3.9.md`](../RELEASE_NOTES_WINDOWS_v0.3.9.md)

ADB wird bewusst nicht mitgeliefert. Die GUI verlinkt die offiziellen Android SDK Platform Tools und den passenden SIMCom-USB-Treiber.

Real bestätigt sind unter Windows bzw. über den Windows-/Remote-ADB-Pfad unter anderem:

- lokale ADB-Verbindung;
- Remote-ADB über Raspberry Pi;
- Originalstatus;
- read-only LTE-Backup/Firmware-Download;
- Dry-Run;
- V3.3→V3.3 bis zur sicheren Gleichversionsablehnung;
- vollständiger realer Firmwarewechsel **V3.3 → V3.4**;
- Mainboard-OTA-Vorgangszähler-Wartung.

Die Windows-GUI verwendet weiterhin dieselbe gemeinsame OTA-Logik wie der Linux-Weg. Der Windows-Sicherheitswrapper ergänzt nur Hostfunktionen wie Full-Abgleich, lokale Zustandsverwaltung und LTE-Cache-Sicherung.

Details zur Windows-Architektur:

[`../../updater/windows/README.md`](../../updater/windows/README.md)

## LTE-Modem per USB / ADB verbinden

Die mechanische Freilegung des Micro-USB-Anschlusses, Windows-Treiber, Android Platform Tools / ADB, Remote-ADB und Backup werden zentral hier beschrieben:

**[`firmware_backup_lte.md`](firmware_backup_lte.md)**

Für den Updater muss das LTE-Modem bei

```sh
adb devices -l
```

im Status `device` erscheinen.

## Technische Sicherheitsgrenze

Der aktuell live verwendete Pfad ist auf den untersuchten Originaldienst `phnixIot4G` begrenzt:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

Der Controller arbeitet bewusst fail-closed.

Wichtige Grenze:

- **vor dem ersten C5A8** kann ein kontrollierter Recovery-/Restorepfad zulässig sein;
- **ab dem ersten C5A8** ist der originale PHNIX-Dienst für Transfer und Abschluss autoritativ;
- `C36E Status 3` ist kein sicherer Stopppunkt;
- ein fehlendes `C37B/3` ist kein Promotion-Gate;
- **100 % C5A8 bedeutet nur: alle Firmwaredaten übertragen**;
- erst **C36E Status 5 / Board-Step 12** ist ein terminaler Mainboard-Erfolg.

Bei einem Monitoring-/ADB-Fehler nach begonnenem C5A8 darf der laufende Mainboardprozess nicht durch einen generischen Restore unterbrochen werden.

## Windows: normaler Ablauf

1. **Verbindung** öffnen und ADB prüfen.
2. Optional unter **Backup** die vorhandenen LTE-Dateien sichern.
3. Unter **Manifest** die originale Firmware auswählen.
4. **Vorschau aus Firmware (Full / Show)** ausführen.
5. Werte prüfen und **Manifest automatisch erzeugen (Full)** verwenden.
6. Unter **Firmware Update** Firmware/Manifest prüfen bzw. Dry-Run ausführen.
7. Risikobestätigung aktivieren.
8. Firmwareupdate starten.
9. Den Ablauf bis zum terminalen Abschluss beobachten.

Während eines Updates sind parallele Wartungs-/Diagnoseeingriffe absichtlich eingeschränkt.

## MQTT während eines normalen Updates

Seit Windows v0.3.9 und dem dazugehörigen Controllerstand gilt:

> **MQTT bleibt beim normalen Vollupdate standardmäßig verbunden.**

Damit bleibt der originale `phnixIot4G`-Dienst in seinem normalen Cloudzustand und der eigene Offline-/Rebootmechanismus wird nicht künstlich provoziert.

Unter **Erweitert** existiert die optionale Checkbox:

```text
MQTT bei Update aus
```

Sie ist standardmäßig **aus**.

- Checkbox aus: kein `--isolate-mqtt`, MQTT bleibt verbunden.
- Checkbox an: `--isolate-mqtt`, alte MQTT-Isolierung für besondere Labor-/Testfälle.

Die Einstellung wird gespeichert.

### Was bedeutet der bekannte 1800-s-Reboot?

Der Originaldienst besitzt einen Rebootpfad, wenn der Aliyun-MQTT-Client intern länger als 1800 Sekunden als offline gilt.

Diese 1800 Sekunden beginnen **nicht zwingend beim Setzen einer Firewall-DROP-Regel**. Bei einer stillen Paketblockade kann der Aliyun-SDK mehrere 180-s-Keepalive-Zyklen benötigen, bevor der Clientstatus überhaupt auf offline wechselt. Erst danach läuft der PHNIX-Offlinezähler.

Es wurde kein OTA-Sonderzweig gefunden, der diesen Rebootpfad während eines Mainboardupdates deaktiviert. Deshalb bleibt MQTT im Normalbetrieb verbunden.

Technische Details:

[`../reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md`](../reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md)

## Reale V3.3→V3.4-Laufzeit

Der bestätigte Live-Lauf zeigte:

```text
C350 / C36E Status 1
C357 / C36E Status 2
C5A8-Firmwaretransfer
C36E Status 3
Mainboard-Prüfung / Flash / Promotion
C36E Status 5
Board-Step 12
neue C544-Version 0034
```

Gemessen wurden:

- reine C5A8-Datenübertragung: ca. **28 min 56 s**;
- letzter C5A8 → Status 3: ca. **2 s**;
- letzter C5A8 → Status 5: ca. **5 min 16 s**;
- vollständiger beobachteter Ablauf bis zur ersten neuen C544-Versionsmeldung: rund **35 Minuten**.

Deshalb bleibt der Fortschrittsbalken nach 100 % bei 100 %, während die Mainboard-Verarbeitung als eigene Phase weiterläuft.

Nach dem terminalen Mainboardergebnis wartet der Updater bis zu **120 Sekunden** auf einen vollständig normalen LTE-/Cloudzustand.

Details zum Live-Lauf:

[`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)

## Firmware und Manifest

Firmwaredateien werden **nicht** über dieses öffentliche GitHub-Repository verteilt und vom Installer nicht automatisch heruntergeladen.

Das Manifest bindet unter anderem:

- Firmwaredateiname;
- Softwarecode;
- Display-/Wire-Version;
- Target-SSID;
- Dateigröße;
- MD5;
- SHA-256;
- Image-Basis.

Unter Windows ist der Full-Modus der empfohlene Weg. Die Firmware wird dabei nur gelesen und nicht verändert.

Ausführliche Manifest-Dokumentation:

[`FIRMWARE_MANIFEST.md`](FIRMWARE_MANIFEST.md)

# Linux / Raspberry Pi

## Voraussetzungen

Benötigt werden:

- Raspberry Pi OS, Debian oder Ubuntu;
- Python 3.10 oder neuer;
- USB-Verbindung zum PHNIX-LTE-Modem;
- ADB;
- Git;
- geprüfte Firmwaredatei;
- passendes Manifest.

## Installation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Standardpfad:

```text
~/FoxAir_updater
```

Der Installer prüft/installiert unter anderem `python3`, `adb`, `usbutils`, `git` und CA-Zertifikate, richtet den USB-Zugriff für `1e0e:9001` ein und prüft Controller, Manifestwerkzeug und Launcher.

## Vorhandene Installation aktualisieren

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Der Installer aktualisiert per Fast-Forward und löscht keine lokalen Firmwaredateien im lokalen Firmwareordner.

## Firmwareordner

```text
~/FoxAir_updater/firmware/
```

Beispiel:

```text
~/FoxAir_updater/firmware/FW3.4.bin
~/FoxAir_updater/firmware/FW3.4.json
```

## Normale Launcher-Befehle

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST --confirm
./foxair-updater restore
./foxair-updater manifest FIRMWARE ...
./foxair-updater version
```

### 1. Originalzustand prüfen

```sh
./foxair-updater status
```

Der Befehl ist read-only und prüft unter anderem:

- Originaldienst und SHA-256;
- Prozess-/Debuggerzustand;
- Update-/Transfermarker;
- lokale Cloud-Sperren;
- Cloud-/MQTT-Verbindung;
- Watchdogs;
- temporäre OTA-Artefakte;
- CRC der OTA-Statusdatei.

### 2. Dry-Run

```sh
./foxair-updater check FW3.4.json
```

Der Dry-Run prüft Firmware, Manifest, ADB, Originaldienst, Werkzeuge, Speicherplatz und OTA_INFO, ohne einen Firmwaretransfer zu starten.

### 3. Firmwareupdate

```sh
./foxair-updater update FW3.4.json --confirm
```

Der Launcher setzt intern die explizite Freigabe `PHNIX-FULL-UPDATE`.

Der Ablauf prüft Firmware/Manifest und Originalzustand, sichert relevante Zustände, stellt die Firmware lokal bereit, führt den Originaldienst kontrolliert in den OTA-Pfad und beobachtet anschließend Transfer und Mainboardabschluss.

MQTT bleibt auch hier beim normalen Vollupdate standardmäßig verbunden.

### 4. Restore

```sh
./foxair-updater restore
```

Dieser Recoveryweg ist nur für Zustände **vor begonnenem C5A8-Firmwaretransfer** vorgesehen. Sobald der erste C5A8-Block beobachtet wurde, verweigert der Controller den generischen Restore absichtlich.

## Manifest unter Linux erzeugen

Empfohlen:

```sh
./foxair-updater manifest FW3.4.bin --full --show
./foxair-updater manifest FW3.4.bin --full
```

Alternativ können bekannte Sollwerte explizit angegeben werden:

```sh
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

Anschließend immer zuerst einen Dry-Run durchführen.

## Gleichversionstest – nur Entwicklung/Labor

Der V3.3-Gleichversionstest bleibt als Entwicklungs-/Abnahmewerkzeug im Backend erhalten. Er ist **nicht mehr Bestandteil der normalen Windows-Endanwender-GUI**.

Historisch und real bestätigt ist V3.3→V3.3 bis zur Gleichversionsablehnung ohne C357/C5A8.

Technische Anleitung:

[`PHNIX_GLEICHVERSIONSTEST.md`](PHNIX_GLEICHVERSIONSTEST.md)

## Was geschieht bei einem Fehler?

### Vor C5A8

Bei einem nicht eindeutig terminalen Zustand kann der Controller in einen geschützten Halt gehen. Dann keine neuen Updatebefehle starten und zunächst Status/Logs auswerten.

### Nach begonnenem C5A8

Ab dem ersten Firmwareblock bleibt der Originaldienst autoritativ. Ein Monitoringverlust ist **kein Grund**, den laufenden Transfer per Restore zu unterbrechen.

Wenn ADB verloren geht, zunächst ADB reconnecten und den vorhandenen Zustand read-only erneut prüfen.

## Konsolenausgabe

- `[OK]`: Prüfung oder sicherer Meilenstein erfolgreich;
- `[..]`: laufender Zustand;
- `[WARNUNG]`: Prüfung erforderlich;
- `[FEHLER]`: Fehler, Guarded Hold oder manueller Recoverybedarf.

## Experten- und Laborzugriff

Die eigentliche OTA-Logik liegt in:

```text
tools/phnix_ota/phnix_local_ota_controller.py
```

Laborfunktionen wie Same-Version-, Pre-C5A8- oder Cancel-Tests sind nicht Teil des normalen Endanwenderablaufs und sollten nur gezielt verwendet werden.

## Lizenz

Der Quellcode dieses Repositorys steht unter der **GNU General Public License v3.0 (GPL-3.0-only)**. Siehe [`LICENSE`](../../LICENSE).

Die Lizenz ist keine Zusage, dass ein Firmwareupdate auf jeder Hardware-/Firmwarekombination funktioniert.

## Kurzfassung

### Windows

1. [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases) öffnen.
2. ADB/USB nach [`firmware_backup_lte.md`](firmware_backup_lte.md) einrichten.
3. Firmware analysieren und Manifest erzeugen.
4. Dry-Run durchführen.
5. Firmwareupdate starten und bis Status 5 / Board-Step 12 beobachten.

**V3.3 → V3.4 wurde real erfolgreich durchgeführt.**

### Linux / Raspberry Pi

```sh
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh

cd ~/FoxAir_updater
./foxair-updater status
./foxair-updater check FW3.4.json
./foxair-updater update FW3.4.json --confirm
```

Restore nur vor begonnenem C5A8 verwenden.