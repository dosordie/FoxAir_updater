# PHNIX-Firmware-Updater – Anleitung für Anwender

Stand: 24. August 2026

> [!CAUTION]
> ## Experimentelles Tool – echtes Firmwareupdate noch nicht live getestet
>
> Dieser Updater befindet sich weiterhin im **experimentellen Entwicklungs- und Teststadium**.
> Ein vollständiges Firmwareupdate von einer installierten Version auf eine andere Version
> wurde auf realer Hardware **noch nicht erfolgreich durchgeführt und bestätigt**.
>
> Bisher wurde der reale Ablauf nur mit der bereits installierten Firmware **V3.3 → V3.3**
> getestet. Das Mainboard hat dieses Angebot erwartungsgemäß als Gleichversion abgelehnt,
> weil V3.3 bereits installiert war. Dabei wurden keine Firmwareblöcke geschrieben.
>
> Daraus folgt ausdrücklich **nicht**, dass beispielsweise ein echtes Update
> **V3.3 → V3.4** bereits als sicher oder funktionsfähig nachgewiesen ist.
>
> Bei der Verwendung können Fehler auftreten. Im ungünstigsten Fall können unter anderem
> das Mainboard, das LTE-Modem oder der normale Betrieb der Wärmepumpe beeinträchtigt
> werden und ein manueller Recovery- oder Reparatureingriff erforderlich werden.
>
> **Nutzung ausschließlich auf eigenes Risiko.** Jeder Anwender muss selbst entscheiden,
> ob er dieses experimentelle Werkzeug verwendet und die möglichen Folgen verantworten
> kann. Der Ersteller übernimmt, **soweit gesetzlich zulässig**, keine Gewährleistung,
> Sachmängelhaftung oder Haftung für Schäden oder Folgeschäden, die aus der Verwendung
> oder Fehlfunktion dieses Tools entstehen.

Diese Anleitung beschreibt im Hauptteil den aktuellen Linux-/Raspberry-Pi-Ablauf des
FoxAir-Updaters. Die Installation und der normale Linux-Betrieb erfolgen über den
Linux-Installer und den Launcher `./foxair-updater`.

Für Windows steht zusätzlich eine grafische Version als Portable-ZIP und Setup-EXE zur Verfügung.

Der vorherige Stand der Anleitung ist zur Referenz unter
[`PHNIX_UPDATER_ENDANWENDER_OLD.md`](PHNIX_UPDATER_ENDANWENDER_OLD.md)
archiviert.

## Windows-GUI als alternative Endanwender-Version

Die Windows-Version kann über die normale GitHub-Releases-Seite heruntergeladen werden:

**[FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)**

Der aktuelle Repository-Entwicklungsstand der Windows-GUI ist **v0.1.4**. ADB wird bewusst nicht mitgeliefert; die GUI verlinkt die offiziellen Android SDK Platform Tools und erlaubt anschließend die Auswahl einer vorhandenen `adb.exe`.

> [!IMPORTANT]
> Unter Windows wurden **ADB-Verbindung, Remote-ADB über Raspberry Pi, Originalstatus und das read-only LTE-Backup/Firmware-Download real getestet**.
>
> Ein **echtes Firmwareupdate auf eine andere Mainboard-Version wurde mit der Windows-GUI noch nicht live durchgeführt**. Die Update-, Recovery- und Same-Version-Funktionen bleiben daher experimentell.

Die Windows-GUI verwendet weiterhin dieselbe gemeinsame OTA-Logik. Der gemeinsame Controller wird beim Build bytegleich übernommen; eine kleine Windows-Sicherheitshülle bildet nur die zusätzlichen Linux-Launcher-Funktionen für Full-Abgleich und LTE-Cache-Sicherung nach.

Für Backup und ADB-Einrichtung ist die zentrale Anleitung maßgeblich:

[`firmware_backup_lte.md`](firmware_backup_lte.md)

Die Windows-Build-/Release-Details stehen unter:

[`../../updater/windows/README.md`](../../updater/windows/README.md)

## LTE-Modem per USB / ADB verbinden

Die mechanische Freilegung des Micro-USB-Anschlusses, der Anschluss des
LTE-Modems sowie die Einrichtung und Prüfung von **ADB (Android Debug Bridge)**
werden bewusst nicht in dieser Anleitung dupliziert.

Die zentrale Anleitung dafür ist:

**[Firmware-Backup des LTE-Modems über Micro-USB – Verbindung, ADB und Windows-/Linux-Anleitung](firmware_backup_lte.md)**

Dort sind unter anderem beschrieben:

- Micro-USB-Anschluss am LTE-Modem und Umgang mit vorhandener Vergussmasse;
- Windows-Treiber und Android SDK Platform Tools / ADB;
- die **empfohlene Windows-GUI für Backup und Firmware-Download**;
- die manuelle PowerShell-Alternative unter Windows;
- optionaler Remote-ADB-Betrieb über einen Raspberry Pi;
- der alternative Linux-/Raspberry-Pi-Weg ohne zusätzliche Windows-Treiber;
- `adb devices -l`, `adb shell` und die grundlegende ADB-Verbindungsprüfung;
- das Auslesen und Sichern vorhandener LTE-Dateien.

Diese Datei ist für die Verbindungsherstellung die **maßgebliche Anleitung**.
Änderungen an Treibern, Anschluss oder ADB-Grundsetup sollen dort gepflegt werden,
damit dieselben Informationen nicht an mehreren Stellen synchron gehalten werden müssen.

Für den FoxAir-Updater gilt anschließend nur noch: Das LTE-Modem muss bei

```sh
adb devices -l
```

im Status `device` erscheinen.

## Wichtige technische Sicherheitsgrenze

Der Updater ist derzeit für genau den geprüften Originaldienst `phnixIot4G`
ausgelegt:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

Der vollständige Ablauf wurde mit der bereits installierten Firmware V3.3 bis
zur sicheren Gleichversionsablehnung getestet. Ein erstes echtes Update auf
eine neuere Mainboard-Firmware bleibt ein beaufsichtigter Test mit stabiler
Stromversorgung und vorbereitetem Recoveryweg.

Der Controller arbeitet absichtlich fail-closed: unbekannte oder nicht sicher
terminale Zustände führen nicht zu einem aggressiven automatischen Cleanup,
sondern zu einem geschützten Halt.

## Voraussetzungen für den folgenden Linux-/Raspberry-Pi-Weg

Benötigt werden:

- Raspberry Pi OS, Debian oder Ubuntu;
- Python 3.10 oder neuer;
- USB-Verbindung zum PHNIX-LTE-Modem;
- ADB;
- Git;
- die geprüfte Firmwaredatei, zum Beispiel `FW3.4.bin`;
- ein dazu passendes Manifest, zum Beispiel `FW3.4.json`.

Fehlende Systempakete werden vom Installer auf apt-basierten Systemen bei
Bedarf automatisch installiert.

## Installation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Der Installer verwendet `sudo` nur für Systempakete und die udev-Regel.
Standardmäßig wird nach folgendem Pfad installiert:

```text
~/FoxAir_updater
```

### Was der Installer erledigt

Der Installer:

- prüft `python3`, `adb`, `lsusb`, `git` und CA-Zertifikate;
- installiert fehlende Pakete per `apt-get`;
- verlangt Python 3.10 oder neuer;
- verwendet einen schlanken Git-Sparse-Checkout;
- richtet die benötigten Datei- und Ausführungsrechte ein;
- erstellt den lokalen Firmwareordner `~/FoxAir_updater/firmware`;
- installiert eine udev-Regel für das PHNIX-LTE-Modem `1e0e:9001`;
- lädt die udev-Regeln neu;
- startet den ADB-Server neu;
- berücksichtigt ein kurzzeitig `offline` erscheinendes ADB-Gerät und versucht einmal `adb reconnect`;
- prüft Controller, Manifestwerkzeug und Launcher;
- zeigt den erkannten ADB-Status und den installierten Git-Commit an.

Die udev-Regel lautet bewusst einfach:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"
```

Der Updater ist für einen kontrollierten, kurzfristigen internen Einsatz
gedacht. Deshalb ist keine zusätzliche `plugdev`-Gruppenverwaltung und kein
Logout/Login notwendig.

## Schlanker Endanwender-Checkout

Der Installer lädt nicht das komplette Entwicklungsrepository in den
Arbeitsbaum. Ausgecheckt werden nur die für Linux benötigten Bereiche:

```text
updater/common
updater/linux
tools/phnix_ota
docs/HowTo
```

Dateien im Projekt-Hauptverzeichnis wie `foxair-updater`, `.gitignore` und
`README.md` bleiben ebenfalls sichtbar.

Entwicklungsbereiche wie `devtools`, `tests`, `docs/reverse_engineering`,
`updater/windows` und `firmware_manifests` bleiben auf GitHub erhalten, werden
beim Linux-Endanwender aber nicht ausgecheckt.

## Verzeichnisstruktur nach der Installation

Für den Anwender ist hauptsächlich folgende Struktur relevant:

```text
~/FoxAir_updater/
├── firmware/          # Firmware + Manifest hier ablegen
├── foxair-updater     # einfacher Launcher
├── docs/HowTo/
├── tools/phnix_ota/   # interne OTA-Werkzeuge
└── updater/           # gemeinsame Module + Linux-Installer
```

Der Ordner `firmware/` ist lokal und von Git ausgeschlossen. Ein Update des
Programms verändert oder löscht dort abgelegte Firmwaredateien und Manifeste
nicht.

## Vorhandene Installation aktualisieren

Der installierte Installer dient gleichzeitig als Updater:

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Dabei wird nur per Fast-Forward aktualisiert. Lokale Änderungen an versionierten
Projektdateien werden nicht automatisch überschrieben. Der Installer verwendet
absichtlich weder `git reset --hard` noch ein Repository-Cleanup.

## ADB-Verbindung kurz prüfen

Die vollständige Einrichtung steht in
[`firmware_backup_lte.md`](firmware_backup_lte.md). Für den Updater genügt die
kurze Kontrolle:

```sh
adb devices -l
```

Normal ist zum Beispiel:

```text
0123456789ABCDEF       device usb:1-1.1.3 transport_id:2
```

Direkt nach einem ADB-Neustart kann das PHNIX-Modem kurzzeitig als `offline`
erscheinen. Der Installer wartet in diesem Fall und versucht einmal automatisch
`adb reconnect`. Für einen Updatevorgang muss das Gerät anschließend im Status
`device` stehen.

## Firmware und Manifest bereitstellen

Firmwaredateien werden **nicht** über das öffentliche GitHub-Repository
verteilt und vom Installer nicht heruntergeladen.

Firmware und Manifest werden gemeinsam in den lokalen Ordner kopiert:

```text
~/FoxAir_updater/firmware/FW3.4.bin
~/FoxAir_updater/firmware/FW3.4.json
```

Das Manifest enthält den Firmware-Dateinamen, zum Beispiel:

```json
"firmware_file": "FW3.4.bin"
```

Wenn Firmware und Manifest im selben Verzeichnis liegen, findet der Controller
die `.bin`-Datei automatisch. Der Anwender muss `--firmware` deshalb im
normalen Launcher-Ablauf nicht mehr angeben.

Vor einem Lauf werden unter anderem Dateiname, Dateigröße, MD5 und SHA-256
gegen das Manifest geprüft.

## Bedienung über `./foxair-updater`

Zuerst in das Installationsverzeichnis wechseln:

```sh
cd ~/FoxAir_updater
```

Hilfe:

```sh
./foxair-updater --help
```

Die normalen Befehle sind:

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST --confirm
./foxair-updater restore
./foxair-updater manifest FIRMWARE --software-code CODE --display-version VERSION --target-ssid SSID
./foxair-updater version
```

Für Entwicklung und Abnahme steht zusätzlich zur Verfügung:

```text
./foxair-updater same-version MANIFEST --confirm
```

Wird bei Manifest oder Firmware nur ein Dateiname angegeben, sucht der Launcher
automatisch im lokalen Ordner `./firmware/`.

## 1. Originalzustand kontrollieren

```sh
./foxair-updater status
```

Dieser Befehl ist vollständig lesend. Er benötigt weder Firmware noch Manifest.
Geprüft werden unter anderem:

- Originaldienst und Programmpfad;
- SHA-256 der Originaldatei;
- Prozesszustand und fehlender Debugger;
- Update-, Injektions- und Transfermarker;
- lokale Cloud-Sperren;
- aktuelle Cloud-/MQTT-Verbindung;
- beide Überwachungsdienste;
- lokaler Firmware-Webserver und Zwischendateien;
- Abwesenheit des temporären Runtime-Helfers;
- CRC der OTA-Statusdatei.

Ein vollständig sauberer Zustand endet mit:

```text
[OK] Originalzustand vollstaendig bestaetigt
```

## 2. Dry-Run vor einem Update

Beispiel mit `FW3.4.json` im lokalen Firmwareordner:

```sh
./foxair-updater check FW3.4.json
```

Ohne echte Ausführungsfreigabe wird nichts zum Mainboard übertragen und kein
Dienst für einen Updatevorgang angehalten.

Der Dry-Run prüft insbesondere:

- Manifest und Firmwaredatei;
- Dateiname, Größe, MD5 und SHA-256;
- ADB-Verbindung;
- geprüften Originaldienst;
- benötigte Werkzeuge auf dem LTE-Modem;
- Speicherplatz;
- OTA_INFO;
- lokalen Runtime-Helfer.

Vor einem echten Update sollte dieser Dry-Run erfolgreich sein.

## 3. Vollständiges Firmwareupdate starten

> [!WARNING]
> Dieser Befehl startet den bislang **nicht mit einer anderen Firmwareversion live validierten**
> Schreibpfad. Ein erfolgreicher Dry-Run beweist nicht, dass das anschließende echte Update
> fehlerfrei abgeschlossen wird.

Beispiel:

```sh
./foxair-updater update FW3.4.json --confirm
```

Der Launcher setzt intern die notwendige explizite Freigabe
`PHNIX-FULL-UPDATE` und verwendet den lokalen Zustandsordner
`~/FoxAir_updater/phnix-ota-state`.

Der Controller führt dabei automatisch aus:

1. Firmware, Manifest, Modem und Originaldienst prüfen;
2. Runtime-Helfer lokal prüfen;
3. Helfer unter einem temporären Namen übertragen;
4. SHA-256 prüfen, Rechte setzen und Helfer atomar aktivieren;
5. OTA_INFO und Statistik auf dem Rechner sichern;
6. Firmware zum LTE-Modem kopieren;
7. Firmware lokal über `127.0.0.1:8081` bereitstellen;
8. Originaldienst kontrolliert in den lokalen OTA-Pfad führen;
9. Status und Fortschritt beobachten;
10. nach sicher bestätigtem Abschluss Originaldienst, Watchdogs und Cloud prüfen;
11. temporäre Firmwareablage, Marker und Runtime-Helfer wieder entfernen.

Ein externer Buslogger ist für den normalen Vollupdate-Aufruf nicht erforderlich.
Bei einem ersten Test einer neuen Firmware kann er trotzdem als zusätzliche
Beobachtung verwendet werden.

## 4. Originalzustand wiederherstellen

```sh
./foxair-updater restore
```

Dieser Befehl ist für einen vor dem Firmwaretransfer angehaltenen oder
unvollständig aufgeräumten lokalen OTA-Lauf vorgesehen.

Er kann unter anderem:

- den geprüften Runtime-Helfer erneut installieren, falls er fehlt;
- gesicherte Persistenzdateien wiederherstellen;
- lokale Cloud-Sperren entfernen;
- übrig gebliebene Debugger und Helfer beenden;
- Originaldienst und Watchdogs wiederherstellen;
- lokale Firmwareablage und Marker entfernen;
- anschließend den vollständigen Statuscheck durchführen.

**Wichtig:** Sobald der erste C5A8-Firmwareblock beobachtet wurde, verweigert
dieser Recoveryweg absichtlich den Eingriff. Ab diesem Zeitpunkt ist der
Originaldienst für Übertragung und Abschluss zuständig.

## Manifest für eine Firmware erstellen

Liegt beispielsweise folgende Firmware vor:

```text
~/FoxAir_updater/firmware/FW3.4.bin
```

kann das Manifest über den Launcher erzeugt werden:

```sh
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

Standardmäßig wird daneben automatisch erzeugt:

```text
~/FoxAir_updater/firmware/FW3.4.json
```

Das Werkzeug berechnet automatisch:

- `wire_version` aus der Displayversion, zum Beispiel `V3.4` → `0034`;
- Dateigröße;
- MD5;
- SHA-256;
- standardmäßig die geprüfte Image-Basis `0x08050000`.

Ein eigener Schalter `--wire-version` ist deshalb nicht notwendig.

Die manuell angegebenen Werte dürfen nicht geraten werden:

- `--software-code` muss zum Zielimage und Mainboard passen;
- `--display-version` muss das Format `Vn.n` verwenden;
- `--target-ssid` ist die vierstellige hexadezimale Mainboard-SSID.

Das erzeugte Manifest kann anschließend angesehen werden:

```sh
cat firmware/FW3.4.json
```

Danach sollte immer zuerst ein Dry-Run erfolgen:

```sh
./foxair-updater check FW3.4.json
```

Unter Windows steht dieselbe Manifest-Logik komfortabel auf der Registerkarte **Manifest** zur Verfügung. Empfohlen sind dort **Vorschau aus Firmware (Full / Show)** und anschließend **Manifest automatisch erzeugen (Full)**. Die originale Firmwaredatei muss dafür keine `.bin`-Endung besitzen.

## Gleichversionstest – nur für Entwicklung und Abnahme

Der bekannte V3.3-Gleichversionstest ist **kein normaler Endanwenderbefehl**.
Er dient dazu, den Reaktionsweg des Updaters auf eine bereits installierte
Firmware zu prüfen.

Mit `FW3.3.bin` und `FW3.3.json` im Firmwareordner:

```sh
./foxair-updater same-version FW3.3.json --confirm
```

Der Launcher setzt intern die für diesen Test festgelegten Freigaben:

```text
PHNIX-C350-SAME-V33
PASSIVE-LOGGER-RUNNING
```

Der passive Buslogger muss bei diesem Test tatsächlich laufen.

Bei bereits installierter V3.3 antwortet das Mainboard mit der bekannten
Gleichversionsablehnung. Es werden dann keine Firmwareblöcke übertragen und
der temporäre Updatezustand wird nach sicher bestätigtem Ende wieder entfernt.

Dieser Test validiert damit den frühen Handshake und den sicheren Abbruch bei
einer bereits installierten Version. Er validiert **nicht** den späteren
Firmware-Schreibpfad eines echten Versionswechsels.

## Installierten Programmstand anzeigen

```sh
./foxair-updater version
```

Damit wird der aktuell installierte Git-Commit angezeigt. Diese Angabe ist bei
Support- oder Testmeldungen hilfreich.

## Was geschieht bei einem Fehler?

Es gibt zwei grundsätzlich unterschiedliche Fehlerklassen.

### Sicher terminal beendet

Beispiele sind:

- sichere Gleichversionsablehnung;
- Parserablehnung;
- bestätigter Fehlerabschluss mit Rückkehr auf Mainboard-Schritt 12.

In einem eindeutig terminalen Zustand kann der Controller automatisch
aufräumen und den Runtime-Helfer wieder entfernen.

### Guarded Hold

Bei einem unerwarteten oder nicht eindeutig terminalen Zustand hält der
Controller den Ablauf geschützt an.

Dabei können Cloud-Sperre, Diagnosezustand und Runtime-Helfer absichtlich
bestehen bleiben, damit keine unkontrollierte Zustandsänderung erfolgt.

Dann gilt:

- LTE-Modem und Wärmepumpe **nicht** stromlos machen;
- keinen neuen Updatebefehl starten;
- Konsolenausgabe und gegebenenfalls Buslog sichern;
- Status nur gezielt prüfen;
- anschließend den passenden Recoveryweg verwenden.

`./foxair-updater restore` ist nur vor begonnenem C5A8-Firmwaretransfer zulässig.

## Konsolenausgabe

Die normale Terminalansicht verwendet:

- `[OK]`: Prüfung oder sicherer Meilenstein erfolgreich;
- `[..]`: laufender Zustand;
- `[WARNUNG]`: Prüfung erforderlich, aber nicht automatisch fehlgeschlagen;
- `[FEHLER]`: Abbruch, Guarded Hold oder unvollständiger Zustand.

Bei einem vollständigen Transfer zeigt der Controller den vom Originaldienst
gemeldeten Fortschritt an. Die Fortschrittsanzeige selbst löst keine Eingriffe
in einen laufenden C5A8-Transfer aus.

## Experten- und Laborzugriff

Der Launcher ist nur eine komfortable Hülle. Die eigentliche Sicherheits- und
OTA-Logik bleibt vollständig im bestehenden Controller:

```text
tools/phnix_ota/phnix_local_ota_controller.py
```

Für Entwicklung und Diagnose können dessen vollständige Optionen weiterhin
direkt verwendet werden. Dazu gehören unter anderem:

- rohe `status`-Ausgabe;
- `cancel-probe-plan`;
- `pre-c5a8-vm-test`;
- `pre-c5a8-real-plan`;
- `same-version-test`;
- die weiterhin bewusst eingeschränkten Cancel-Pfade.

Für den normalen Linux-Anwender sollten jedoch die Befehle über
`./foxair-updater` verwendet werden. Für Windows-Endanwender ist die GUI der vorgesehene Bedienweg; die technischen Laborbefehle bleiben separate Entwicklungswerkzeuge.

## Lizenz

Der Quellcode dieses Repositorys steht unter der **GNU General Public License v3.0
(GPL-3.0-only)**. Siehe [`LICENSE`](../../LICENSE).

Die GPL-Lizenz ändert nichts an den oben beschriebenen technischen Risiken des
experimentellen Firmware-Updaters und ist keine Zusage, dass ein Firmwareupdate
auf realer Hardware funktioniert.

## Kurzfassung

### Windows

Windows-Version herunterladen:

[GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)

ADB/Backup einrichten:

[`firmware_backup_lte.md`](firmware_backup_lte.md)

Real bestätigt sind derzeit ADB-Verbindung, Originalstatus und Backup. **Ein echtes Versionsupdate unter Windows ist noch nicht live getestet.**

### Linux / Raspberry Pi

Verbindung zum LTE-Modem / ADB einrichten:

[`firmware_backup_lte.md`](firmware_backup_lte.md)

Installation:

```sh
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Firmware und Manifest ablegen:

```text
~/FoxAir_updater/firmware/
```

Danach:

```sh
cd ~/FoxAir_updater
./foxair-updater status
./foxair-updater check FW3.4.json
./foxair-updater update FW3.4.json --confirm
```

Bei Bedarf vor begonnenem Firmwaretransfer:

```sh
./foxair-updater restore
```
