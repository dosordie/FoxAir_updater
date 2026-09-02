# FoxAir Updater

Firmware-Update- und Reverse-Engineering-Tool für FoxAir-/PHNIX-Wärmepumpen.

> [!CAUTION]
> ## V1.2 → V3.4 und V3.3 → V3.4 live validiert
>
> Ein vollständiges Firmwareupdate von Mainboard V3.3 auf V3.4 wurde auf realer Hardware **erfolgreich durchgeführt und anschließend über Status 5 / Board-Step 12 sowie die neue C544-Versionsmeldung `0034` bestätigt**.
>
> Zusätzlich wurde auch ein direktes Update von **V1.2 (Auslieferungszustand) auf V3.4** auf realer Hardware erfolgreich durchgeführt.
>
> **V3.3 → V3.3** wurde bis zur erwarteten Gleichversionsablehnung getestet. Weitere Firmwarestände, Mainboardfamilien und Fehlerfälle sind weiterhin nicht vollständig live validiert.
>
> Ein Firmwareupdate bleibt ein Eingriff in das Mainboard. Im ungünstigsten Fall können Mainboard, LTE-Modem oder der normale Betrieb der Wärmepumpe beeinträchtigt werden und ein manueller Recovery- oder Reparatureingriff erforderlich werden.
>
> **Nutzung ausschließlich auf eigenes Risiko.** Der Ersteller übernimmt keine Gewährleistung, Sachmängelhaftung oder Haftung für Schäden oder Folgeschäden, die aus der Verwendung oder Fehlfunktion dieses Tools entstehen.

Das Repository trennt Firmwareanalyse und Update-Werkzeuge bewusst vom Projekt [`FoxAir_Control`](https://github.com/dosordie/FoxAir_Control), das weiterhin für normale Steuerung, Modbus-Auswertung und Diagnose zuständig ist.

## Windows GUI v0.4.0

Die Windows-Version ist der hauptsächliche Endanwenderweg des Projekts. Sie steht als **Portable-ZIP** und **Setup-EXE** auf der GitHub-Releases-Seite bereit:

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
- Vorprüfung ohne Firmwareübertragung zum Mainboard;
- Manifest-Erzeugung direkt aus einer Firmwaredatei;
- Full-Abgleich von Manifest, Firmwareidentität, Größe, MD5 und SHA256;
- autonomen DTU-OTA-Runner: nach dem Start führt das LTE-Modem den Mainboard-OTA selbstständig weiter;
- persistenten Updatezustand auf dem LTE-Modem und erneutes read-only Einlesen über **Status prüfen**;
- serielle und Runner-basierte Fortschrittsanzeige mit Fallback;
- klare Trennung zwischen 100 % Datenübertragung und terminalem Mainboard-Erfolg;
- optional kontrollierten Neustart von `phnixIot4G` vor dem Update mit Verifikation der neuen Dienstinstanz;
- standardmäßig verbundene MQTT-Cloud während des Vollupdates;
- optionale MQTT-Isolierung unter **Erweitert → MQTT bei Update aus** für besondere Testfälle;
- read-only Modem-, SIM-, LTE-, Cloud-/MQTT- und Mainboarddiagnose;
- optionale detaillierte Modem-/Traffic-Diagnose unter **Erweitert**;
- Wartungsfunktion für ausgewählte persistente Statistikzähler;
- Loganzeige, Logexport und automatische Update-/LTE-Protokolle;
- Portable- und Setup-Build ohne notwendige Python-Installation beim Anwender.

### Neu bzw. maßgeblich in v0.4.0

- Der produktive Mainboard-OTA läuft über den autonomen Runner unter `updater/dtu_ota`.
- Nach erfolgreichem Start ist Windows nicht mehr Teil der eigentlichen OTA-Ausführung: ein kurzfristiger Windows-/ADB-Verbindungsverlust beendet den laufenden Updatevorgang nicht.
- Der aktuelle Zustand wird auf dem LTE-Modem persistent gespeichert und kann über **Status prüfen** erneut eingelesen werden, ohne einen zweiten OTA zu starten.
- Ein zweiter Start darf einen bereits aktiven Runner nicht verändern; aktive Runs werden über einen persistenten Lock geschützt.
- Nach Übergabe der Autorität an den Originaldienst darf ein reiner Monitoringverlust keinen unsicheren Cleanup des laufenden OTA auslösen.
- Ein Restore vor der Authority-Grenze gilt nur dann als erfolgreich, wenn der Originalzustand eindeutig bestätigt wurde.
- Runner-Statusschreibfehler werden fail-closed behandelt; nach Authority werden Lock und lokaler Firmware-HTTP-Zugriff bei unklarem Zustand erhalten.
- Ein DTU-Reboot wird anhand eines Boot-Fingerprints von einem reinen Runner-/Prozessverlust unterschieden.
- Der optionale `phnixIot4G`-Neustart vor dem Update wird anhand einer neuen PID, einer einzelnen stabilen Dienstinstanz und `TracerPid=0` verifiziert.
- Shell-Payloads des autonomen Runners werden vor Hashing und Übertragung robust auf LF-Zeilenenden normalisiert. Dadurch funktionieren Hook und Supervisor unabhängig von Windows-/Git-Checkout-Zeilenenden.
- **100 % bedeutet weiterhin nur: alle C5A8-Firmwaredaten wurden übertragen.** Anschließend laufen Mainboard-Prüfung, Übernahme/Promotion und Abschluss weiter.
- Erst **C36E Status 5 / Board-Step 12** gilt als terminaler Mainboard-Erfolg.
- MQTT bleibt beim normalen Vollupdate **standardmäßig verbunden**. Die Firewall-Isolierung ist nur optional.
- Die Wartungsoberfläche kann gezielt die bekannten persistenten Zähler **DTU-OTA-Vorgänge**, **Mainboard OTA-Vorgänge**, **Dienststarts (Power-Reset-t)** und **Aktive Modem-Neustarts (Active-Reset-t)** ändern. Die vollständige Statistikdatei wird vorher gesichert und Datei/RAM werden anschließend verifiziert.

### MQTT und der 30-Minuten-Rebootpfad

Der Originaldienst besitzt einen eigenen Rebootmechanismus, wenn der Aliyun-MQTT-Client intern länger als 1800 Sekunden als offline gilt.

Der 1800-s-Zähler startet **nicht zwingend in dem Moment, in dem Netzwerkpakete per Firewall geblockt werden**. Bei einer stillen `iptables DROP`-Sperre kann der Aliyun-SDK mehrere 180-s-Keepalive-Zyklen benötigen, bevor sein interner Clientzustand von „connected“ auf „offline“ wechselt. Erst danach läuft der PHNIX-1800-s-Zähler.

Damit ist der Rebootpfad weiterhin real vorhanden; es gibt keinen bekannten OTA-Sonderzweig, der ihn während eines Mainboardupdates deaktiviert. Für normale Updates ist es deshalb einfacher und risikoärmer, MQTT verbunden zu lassen.

Details:
[`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](docs/reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md)

### Screenshots

> [!NOTE]
> Die Screenshots zeigen den grundsätzlichen Aufbau der Windows-GUI. Einzelne Texte und Optionen können gegenüber v0.4.0 abweichen.

| Verbindung | Backup |
|---|---|
| <img src="docs/DTU_1_connect.png" width="520" alt="FoxAir Updater Verbindung"> | <img src="docs/DTU_2_Backup.png" width="520" alt="FoxAir Updater Backup"> |

| Firmwareupdate | Modem Info / LTE Diagnose |
|---|---|
| <img src="docs/DTU_3_update.png" width="520" alt="FoxAir Updater Firmwareupdate"> | <img src="docs/DTU_4_info.png" width="520" alt="FoxAir Updater Modem Info"> |

### Aktuell real bestätigt

Real getestet bzw. bestätigt sind unter anderem:

- lokale und Remote-ADB-Verbindung;
- Originalstatus;
- read-only LTE-Backup/Firmware-Download;
- Vorprüfung;
- normaler Windows-Firmware-Update-Aufruf mit **V3.3 → V3.3** bis zur sicheren Gleichversionsablehnung;
- vollständiger realer Versionswechsel **V3.3 → V3.4**, einschließlich kompletter C5A8-Übertragung, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließender C544-Versionsbestätigung `0034`;
- vollständiger realer Versionswechsel **V1.2 (Auslieferungszustand) → V3.4**;
- autonomer Runner-End-to-End-Ablauf auf realer Hardware einschließlich persistentem Status und kontrolliertem `phnixIot4G`-Neustart;
- Mainboard-OTA-/Statistik-Wartung einschließlich Sicherung, kontrolliertem Dienstneustart und Datei-/RAM-Verifikation.

Beim V3.3→V3.3-Test erkannte das Mainboard die bereits installierte Firmware und beendete den Ablauf vor C357/C5A8. Es wurden keine Firmwaredaten übertragen.

Beim dokumentierten V3.3→V3.4-Lauf dauerte die C5A8-Datenübertragung rund **28:56 Minuten**. Vom letzten Datenblock bis Status 5 vergingen weitere rund **5:16 Minuten**. Bis zur ersten neuen C544-Versionsmeldung dauerte der vollständige beobachtete Ablauf rund **35 Minuten**.

Details zum dokumentierten V3.3→V3.4-Lauf stehen in:
[`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)

### Windows-Architektur

Der normale Firmwareupdate-Pfad ist bewusst in Host- und DTU-Aufgaben getrennt:

```text
FoxAir_Updater.exe
        ↓
Windows-GUI / Statusdarstellung
        ↓
private Python Runtime
        ↓
updater/dtu_ota (Host-Client)
        ↓  ADB nur für Prepare/Start/Status/Log/Recovery-Kommandos
PHNIX LTE-Modem
        ↓
/data/foxair_ota_runner/... (persistenter Run)
        ↓
dtu_ota_supervisor.sh
        ↓
phnix_ota_runtime_hook + originaler phnixIot4G
        ↓
Mainboard-OTA
```

Nach erfolgreichem `start` läuft der Updatevorgang auf dem LTE-Modem weiter. Windows pollt nur den gespeicherten Status und kann nach einem Verbindungsverlust wieder an diesen Zustand anknüpfen.

Der ältere PHNIX-Controller bleibt für Diagnose-/Bestandsfunktionen im Paket erhalten, ist aber nicht mehr der produktive Orchestrator des normalen autonomen Firmwareupdates.

### Remote ADB über Raspberry Pi

Wenn das LTE-Modem per USB an einem Raspberry Pi hängt, kann der ADB-Server im lokalen LAN bereitgestellt werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Zum Beenden auf dem Raspberry Pi **Strg+C** drücken. In der Windows-GUI werden IP-Adresse und Port eingetragen. Auch im Remote-Modus wird unter Windows eine lokale `adb.exe` als Client benötigt.

Der Remote-ADB-Port sollte nur in einem vertrauenswürdigen lokalen Netz freigegeben werden.

### Windows-Firmwareupdate-Anleitung

Der normale Endanwenderablauf ist hier beschrieben:

**[`docs/HowTo/firmware_update_windows.md`](docs/HowTo/firmware_update_windows.md)**

## Linux / Raspberry Pi

Der Linux-/Raspberry-Pi-Weg bleibt weiterhin nutzbar.

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
- prüft die benötigten Updater-/Runner-Komponenten.

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

## Projektstruktur

Produktiver Updater-Code liegt unter `updater/`. Der autonome DTU-Runner befindet sich unter `updater/dtu_ota/`, gemeinsame Host-Komponenten unter `updater/common/`.

`tools/` und insbesondere `tools/testvm/` enthalten Analyse-, Entwicklungs- und Simulatorwerkzeuge. Die QEMU-/Fake-ADB-Testumgebung bleibt bewusst vom produktiven Runner getrennt.

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
