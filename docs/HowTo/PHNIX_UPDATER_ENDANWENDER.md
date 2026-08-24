# PHNIX-Firmware-Updater – Anleitung für Anwender

Stand: 24. August 2026

Diese Anleitung beschreibt den aktuellen Linux-/Raspberry-Pi-Ablauf des
FoxAir-Updaters. Die Installation und der normale Betrieb erfolgen inzwischen
über den Linux-Installer und den einfachen Launcher `./foxair-updater`.

Der vorherige Stand der Anleitung ist zur Referenz unter
[`PHNIX_UPDATER_ENDANWENDER_OLD.md`](PHNIX_UPDATER_ENDANWENDER_OLD.md)
archiviert.

## Wichtige Sicherheitsgrenze

Der Updater ist derzeit ein experimentelles Werkzeug für genau den geprüften
Originaldienst `phnixIot4G`:

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

## Voraussetzungen

Benötigt werden:

- Raspberry Pi OS, Debian oder Ubuntu;
- Python 3.10 oder neuer;
- USB-Verbindung zum PHNIX-LTE-Modem;
- ADB (Android Debug Bridge);
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

## ADB-Verbindung prüfen

Nach der Installation kann die Verbindung direkt kontrolliert werden:

```sh
adb devices -l
```

Normal ist zum Beispiel:

```text
0123456789ABCDEF       device usb:1-1.1.3 transport_id:2
```

Direkt nach einem ADB-Neustart kann das PHNIX-Modem kurzzeitig als `offline`
erscheinen:

```text
0123456789ABCDEF       offline usb:1-1.1.3 transport_id:1
```

Das bedeutet normalerweise nicht, dass die USB-Berechtigung fehlt. Das Gerät
wurde bereits erkannt, aber der ADB-Handshake ist noch nicht vollständig.

Der aktuelle Installer berücksichtigt dieses Verhalten automatisch, wartet
kurz und führt bei `offline` einmal `adb reconnect` aus. Manuell kann derselbe
Vorgang so durchgeführt werden:

```sh
adb reconnect
sleep 2
adb devices -l
```

Für einen Updatevorgang muss das Gerät anschließend im Status `device` stehen.

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

Die verfügbare Hilfe zeigt:

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
`./foxair-updater` verwendet werden.

## Kurzfassung

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
