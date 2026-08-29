# FoxAir Updater

Experimentelles Firmware-Update- und Reverse-Engineering-Tool für FoxAir-/PHNIX-Wärmepumpen.

> [!CAUTION]
> ##  V3.3 → V3.4 live validiert
>
> Dieses Projekt befindet sich weiterhin im **Entwicklungs- und Teststadium**.
> Ein vollständiges Firmwareupdate von Mainboard V3.3 auf V3.4 wurde auf realer Hardware **erfolgreich durchgeführt und per RS485-Versionsmeldung bestätigt**.
>
> Zusätzlich wurde **V3.3 → V3.3** bis zur erwarteten Gleichversionsablehnung getestet. Andere Firmwarestände, Mainboardfamilien und Fehlerfälle sind weiterhin nicht vollständig live validiert.
>
> Bei der Verwendung kann etwas schiefgehen. Im ungünstigsten Fall können Mainboard, LTE-Modem oder der normale Betrieb der Wärmepumpe beeinträchtigt werden und ein manueller Recovery- oder Reparatureingriff erforderlich werden.
>
> **Nutzung ausschließlich auf eigenes Risiko.** Jeder Anwender muss selbst entscheiden, ob er dieses experimentelle Werkzeug verwendet und die möglichen Folgen verantworten kann. Der Ersteller übernimmt, **soweit gesetzlich zulässig**, keine Gewährleistung, Sachmängelhaftung oder Haftung für Schäden oder Folgeschäden, die aus der Verwendung oder Fehlfunktion dieses Tools entstehen.

Das Repository trennt Firmwareanalyse und Update-Werkzeuge bewusst vom Projekt [`FoxAir_Control`](https://github.com/dosordie/FoxAir_Control), das weiterhin für normale Steuerung, Modbus-Auswertung und Diagnose zuständig ist.

## Windows GUI v0.3.1

Die Windows-Version ist inzwischen der hauptsächliche Entwicklungsweg des Projekts. Sie steht als **Portable-ZIP** und **Setup-EXE** auf der GitHub-Releases-Seite bereit:

**[FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)**

ADB wird weiterhin **nicht mitgeliefert**. Die GUI verlinkt den SIMCom-USB-Treiber, die offiziellen Android Platform Tools und die LTE-/USB-Anleitung. Eine vorhandene `adb.exe` kann ausgewählt und gespeichert werden.

> [!NOTE]
> Die Windows-Builds sind derzeit nicht mit einem kommerziellen Code-Signing-Zertifikat signiert. Windows SmartScreen kann deshalb beim ersten Start **„Der Computer wurde durch Windows geschützt“** anzeigen. Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite geladen wurde, **Weitere Informationen** und anschließend **Trotzdem ausführen** wählen.

### Was die Windows-Version bietet

- lokale ADB-Verbindung direkt per USB;
- optional Remote-ADB über einen Raspberry Pi;
- automatische bzw. manuelle ADB-Reconnect-Funktion;
- read-only Backup/Firmware-Download per `adb pull`;
- Sicherung von Firmware-Cache, `OTA_INFO`, Statistik und optional dem Originaldienst `phnixIot4G`;
- Originalstatus- und Recovery-Prüfung;
- Firmware-Dry-Run;
- Manifest-Erzeugung direkt aus einer Firmwaredatei;
- automatischen Full-Abgleich von Manifest, Firmwareidentität, Größe, MD5 und SHA256;
- lesbare Ablauf- und Fortschrittsanzeige für den Firmwareupdate-Pfad;
- standardmäßig verbundene MQTT-Cloud während des Vollupdates sowie eine optionale, ausdrücklich nicht empfohlene MQTT-Isolierung für Labortests;
- read-only Modem-, SIM-, LTE-, Cloud-/MQTT- und Mainboarddiagnose;
- optionale detaillierte Modem-/Traffic-Diagnose unter **Erweitert**;
- Wartungsfunktion für den Mainboard-OTA-Vorgangszähler;
- Loganzeige und Logexport;
- Portable- und Setup-Build ohne notwendige Python-Installation beim Anwender.

### Neu bzw. überarbeitet in v0.3.1

- Die **OTA-Vorprüfung verlangt eine aktive MQTT-/Cloud-Verbindung**, bevor ein echtes Update gestartet wird. Hintergrund ist der originale PHNIX-Rebootmechanismus nach längerer Cloud-Offlinezeit.
- Die Firmware-Update-Seite zeigt Fortschritt, übertragene Datenmenge und die seit Beginn der lokalen Cloud-Sperre **verstrichene Zeit** deutlicher an.
- Bei einem kurzzeitigen ADB-Verbindungsverlust kann die GUI den vorhandenen OTA-Zustand erneut read-only prüfen, ohne einen zweiten Updatevorgang zu starten.
- Nach begonnenem C5A8-Firmwaretransfer bleibt der originale `phnixIot4G`-Dienst autoritativ; ein reiner Windows-/ADB-Monitoringfehler darf den laufenden Transfer nicht aktiv stoppen.
- Die Backup-Seite erklärt die einzelnen Sicherungsoptionen genauer.
- Die Manifest-Seite beschreibt jetzt, wofür das Manifest benötigt wird und wie Firmwareidentität und Prüfsummen damit abgesichert werden.
- Die Verbindungsseite wurde aufgeräumt und die Remote-ADB-Hilfe für Raspberry Pi optisch abgegrenzt.
- `Modem Info / LTE Diagnose` bleibt normal sichtbar; nur die detaillierte `Modem Diagnose / Traffic`-Seite wird über **Erweitert** ein- oder ausgeblendet.
- Der frühere separate Gleichversionstest und die zugehörige passive-Logger-Checkbox wurden aus der normalen Endanwender-GUI entfernt. Die Backend-/Lab-Funktionen bleiben erhalten.
- Die getestete Mainboard-OTA-Zählerfunktion wird als **Wartung – Mainboard OTA-Vorgänge** geführt.
- Modem- und Wartungsfunktionen werden während eines laufenden Firmwareupdates gesperrt, damit keine parallelen Eingriffe stattfinden.

### Screenshots

| Verbindung | Backup |
|---|---|
| <img src="docs/DTU_1_connect.png" width="520" alt="FoxAir Updater Verbindung"> | <img src="docs/DTU_2_Backup.png" width="520" alt="FoxAir Updater Backup"> |

| Firmware Update | Modem Info / LTE Diagnose |
|---|---|
| <img src="docs/DTU_3_update.png" width="520" alt="FoxAir Updater Firmware Update"> | <img src="docs/DTU_4_info.png" width="520" alt="FoxAir Updater Modem Info"> |

### Aktuell real bestätigt

Real getestet bzw. bestätigt sind unter anderem:

- lokale und Remote-ADB-Verbindung;
- Originalstatus;
- read-only LTE-Backup/Firmware-Download;
- Dry-Run;
- normaler Windows-Firmware-Update-Aufruf mit **V3.3 → V3.3** bis zur sicheren Gleichversionsablehnung;
- vollständiger realer Versionswechsel **V3.3 → V3.4**, einschließlich C5A8-Übertragung, Status 5 und anschließender C544-Versionsbestätigung `0034`;
- Mainboard-OTA-Vorgangszähler-Wartung einschließlich Sicherung, kontrolliertem Dienstneustart und Verifikation.

Beim V3.3→V3.3-Test erkannte das Mainboard die bereits installierte Firmware und beendete den Ablauf vor C357/C5A8. Es wurden keine Firmwaredaten übertragen.

Beim V3.3→V3.4-Lauf dauerte die C5A8-Datenübertragung rund 28:56 Minuten;
bis Status 5 vergingen danach weitere rund 5:16 Minuten. Details stehen in
[`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md).

### Windows-Architektur

Die Windows-Version hält die gemeinsame OTA-Logik bewusst zentral:

```text
FoxAir_Updater.exe
        ↓
Windows-GUI / Statusdarstellung
        ↓
private Python Runtime
        ↓
Windows-Sicherheitswrapper
        ↓
gemeinsamer PHNIX OTA-Controller
        ↓
extern ausgewählte adb.exe
        ↓
PHNIX LTE-Modem
```

Der Windows-Build verwendet die gemeinsamen Controller- und `updater/common`-Quellen und hält damit keine separate zweite OTA-Implementierung vor.

Details zum Windows-Build und zur internen Architektur stehen unter [`updater/windows/README.md`](updater/windows/README.md).

### Remote ADB über Raspberry Pi

Wenn das LTE-Modem per USB an einem Raspberry Pi hängt, kann der ADB-Server im lokalen LAN bereitgestellt werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Zum Beenden auf dem Raspberry Pi **Strg+C** drücken. In der Windows-GUI werden IP-Adresse und Port eingetragen. Auch im Remote-Modus wird unter Windows eine lokale `adb.exe` als Client benötigt.

Der Remote-ADB-Port sollte nur in einem vertrauenswürdigen lokalen Netz freigegeben werden.

## Linux / Raspberry Pi

Der Linux-/Raspberry-Pi-Weg bleibt weiterhin nutzbar und verwendet denselben gemeinsamen OTA-Kern.

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Danach stehen unter anderem zur Verfügung:

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST --confirm
./foxair-updater restore
./foxair-updater manifest FIRMWARE ...
./foxair-updater version
```

Der Installer:

- prüft bzw. installiert `python3`, `adb`, `usbutils`, `git` und CA-Zertifikate;
- verlangt Python 3.10 oder neuer;
- verwendet einen schlanken Git-Sparse-Checkout;
- richtet den USB-Zugriff für das PHNIX-LTE-Modem `1e0e:9001` ein;
- berücksichtigt ein kurzzeitig `offline` erscheinendes ADB-Gerät und versucht `adb reconnect`;
- erstellt den lokalen Firmwareordner `~/FoxAir_updater/firmware`;
- prüft Controller, Manifestwerkzeug und Launcher.

Ausführliche Updater-Anleitung:
[`docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`](docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)

Anschluss des LTE-Modems, Micro-USB, Windows-/Linux-ADB und Backup:
[`docs/HowTo/firmware_backup_lte.md`](docs/HowTo/firmware_backup_lte.md)

## Firmware-Backup / Firmware-Download

Unter Windows ist die grafische Backup-Funktion der empfohlene Weg. Sie verwendet ausschließlich read-only `adb pull`.

Gesichert werden können:

- `/cache/phnixIot_device_OTA` – aktuell im LTE-Cache vorhandene Firmware-/OTA-Datei;
- `/data/phnixIot_device_OTA_INFO` – persistenter OTA-/Resume-Zustand;
- `/data/phnixIot_device_statisic` – persistente Betriebs-, Reset-, Kommunikations- und OTA-Zähler;
- `/data/phnixIot4G` – originaler PHNIX-LTE-Dienst.

Die vollständige Anleitung steht unter:

**[`docs/HowTo/firmware_backup_lte.md`](docs/HowTo/firmware_backup_lte.md)**

Firmware- und Datendateien aus dem LTE-Modem werden nicht automatisch veröffentlicht und sollen insbesondere nicht in dieses öffentliche Repository eingecheckt werden.

## Firmware und Manifest

Firmwaredateien werden **nicht über dieses öffentliche GitHub-Repository verteilt**. Der Installer lädt keine Mainboard-Firmware herunter.

Das Manifest beschreibt die zu übertragende Firmware eindeutig und enthält bzw. bindet unter anderem:

- Software-/Produktcode;
- Firmwareversion;
- Ziel-/SSID;
- Dateigröße;
- MD5;
- SHA256;
- Referenz auf die zugehörige Firmwaredatei.

Damit prüft der Updater vor dem eigentlichen OTA, dass die ausgewählte Firmwaredatei exakt zu den erwarteten Metadaten und Prüfsummen passt.

Unter Windows ist die automatische Full-Variante der empfohlene Weg: Firmware auswählen, analysieren lassen und Manifest automatisch erzeugen. Die Firmwaredatei wird dabei nicht verändert und muss keine `.bin`-Endung besitzen.

Unter Linux kann ein Manifest ebenfalls lokal erzeugt werden, zum Beispiel:

```sh
cd ~/FoxAir_updater
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

## Technische Sicherheitsgrenze

Der aktuelle Live-Pfad ist für genau den untersuchten Originaldienst `phnixIot4G` ausgelegt:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

Der frühe OTA-Vorhandshake und der eigentliche Firmwaretransfer werden bewusst unterschiedlich behandelt:

- **Vor dem ersten C5A8** kann ein kontrollierter Guarded-Hold-/Recoverypfad verwendet werden.
- **Ab dem ersten C5A8** ist der originale PHNIX-Dienst autoritativ; ein Monitoringfehler darf den Transfer nicht automatisch abbrechen.
- `C36E Status 3` ist **kein sicherer Stopppunkt**.
- Ein fehlendes `C37B/3` stoppt die anschließende Mainboard-Promotion nicht; das ACK gehört zur Status-/Retrylogik und ist kein Promotion-Gate.

Diese Erkenntnisse basieren auf der analysierten Mainboard-Firmware V3.3. Details befinden sich unter [`docs/reverse_engineering/`](docs/reverse_engineering/).

## Repository-Struktur

```text
FoxAir_updater/
├─ docs/
│  ├─ reverse_engineering/  # Mainboard-, OTA- und LTE-Analyse
│  └─ HowTo/                # Anwender- und Testanleitungen
├─ firmware_manifests/      # geprüfte/analysierte Manifest-Metadaten
├─ updater/
│  ├─ common/               # gemeinsam genutzte Python-Module
│  ├─ linux/                # Linux-/Raspberry-Pi-Installer
│  └─ windows/              # Windows-GUI, Portable-/Setup-Build
├─ tools/phnix_ota/         # OTA-Controller, Runtime-Helfer, Manifestwerkzeug
├─ devtools/                # Simulatoren und Laborwerkzeuge
├─ tests/                   # Regressionstests
└─ foxair-updater           # Linux-Endanwender-Launcher
```

## Projektumfang

Enthalten sind unter anderem Firmware-Reverse-Engineering, PHNIX-LTE-Modem-/Runtime-Analyse, OTA-/IAP-Protokollanalyse, Firmwareupdate-, Recovery- und Validierungswerkzeuge, Manifest-/Hashprüfung sowie Simulatoren und Regressionstests.

Nicht Schwerpunkt dieses Repositorys sind die normale FoxAir-Control-GUI, normale Endanwender-Steuerlogik oder allgemeine Modbus-Werkzeuge ohne direkten Firmware-/Updater-Bezug.

## 💙 Unterstützung

Ich bastle an diesem Tool in meiner Freizeit.  
Wenn er dir gefällt oder dir weiterhilft, freue ich mich über eine kleine Spende:

[![Spenden via PayPal](https://img.shields.io/badge/Spenden-PayPal-blue.svg?logo=paypal)](https://www.paypal.com/paypalme/AuhuberD)

## Lizenz

Dieses Repository steht unter der **GNU General Public License v3.0**, SPDX-Kennung **`GPL-3.0-only`**.

Siehe [`LICENSE`](LICENSE).

Weitergabe und Änderungen sind damit erlaubt, abgeleitete Werke müssen bei Weitergabe jedoch ebenfalls unter den Bedingungen der GPLv3 stehen und der zugehörige Quellcode muss gemäß den Lizenzbedingungen verfügbar gemacht werden.

Die GPL enthält ausdrücklich einen Gewährleistungs- und Haftungsausschluss.
