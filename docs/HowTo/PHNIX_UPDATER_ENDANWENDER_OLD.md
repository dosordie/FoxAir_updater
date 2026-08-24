# PHNIX-Firmware-Updater – Anleitung für Anwender

Stand: 23. August 2026

Diese Anleitung beschreibt den aktuell nutzbaren Raspberry-Pi-/Linux-Stand
des FoxAir-Updaters. Eine Windows-Oberfläche ist vorgesehen, aber noch nicht
implementiert.

## Wichtige Sicherheitsgrenze

Der Updater ist derzeit ein experimentelles Werkzeug für genau den geprüften
Originaldienst `phnixIot4G`:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

Der vollständige Aufruf wurde mit der bereits installierten Firmware V3.3
erfolgreich bis zur sicheren Gleichversionsablehnung getestet. Eine tatsächlich
neuere Firmware wurde noch nicht zum Mainboard übertragen. Ein erstes echtes
Update auf eine neue Version bleibt deshalb ein beaufsichtigter Test mit
stabiler Stromversorgung und vorbereitetem Recoveryweg.

## Benötigt werden

- Raspberry Pi oder Linux-Rechner mit Python 3;
- per USB angeschlossenes und über ADB erreichbares PHNIX-LTE-Modem;
- dieses Repository einschließlich `updater/common`;
- `phnix_ota_runtime_hook` passend zum geprüften Originaldienst;
- Firmwaredatei, zum Beispiel `FW3.4.bin`;
- dazugehöriges Manifest, zum Beispiel `FW3.4.json`.

Empfohlen wird ein vollständiger Checkout des Repositorys. Die Beispiele
werden aus dessen Hauptverzeichnis ausgeführt:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py ...
```

Wer Controller und Helfer direkt in sein Home-Verzeichnis kopiert, muss
zusätzlich sicherstellen, dass das Python-Paket `updater/common` vorhanden oder
installiert ist.

## Dateien auf den Raspberry Pi holen

### Empfohlen: vollständiges Repository mit Git

```sh
cd ~
git clone https://github.com/dosordie/FoxAir_updater.git
cd FoxAir_updater
```

Wurde das Repository bereits geklont, lässt es sich aktualisieren:

```sh
cd ~/FoxAir_updater
git pull --ff-only
```

Anschließend stehen Controller, Runtime-Helfer, Manifestwerkzeug,
Python-Module und Dokumentation gemeinsam in der erwarteten Verzeichnisstruktur
zur Verfügung.

### Alternative: jede benötigte Datei mit wget laden

Ohne Git müssen die Verzeichnisse und alle Python-Abhängigkeiten vollständig
angelegt werden:

```sh
mkdir -p ~/FoxAir_updater/tools/phnix_ota
mkdir -p ~/FoxAir_updater/updater/common
cd ~/FoxAir_updater

wget -O tools/phnix_ota/phnix_local_ota_controller.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_ota/phnix_local_ota_controller.py
wget -O tools/phnix_ota/phnix_ota_runtime_hook \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_ota/phnix_ota_runtime_hook
wget -O tools/phnix_ota/create_firmware_manifest.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_ota/create_firmware_manifest.py

wget -O updater/__init__.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/__init__.py
wget -O updater/common/__init__.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/common/__init__.py
wget -O updater/common/adb_transport.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/common/adb_transport.py
wget -O updater/common/firmware_manifest.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/common/firmware_manifest.py
wget -O updater/common/phnix_frames.py \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/common/phnix_frames.py

chmod 755 tools/phnix_ota/phnix_local_ota_controller.py
chmod 755 tools/phnix_ota/phnix_ota_runtime_hook
chmod 755 tools/phnix_ota/create_firmware_manifest.py
```

Danach kurz prüfen:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py --help
python3 tools/phnix_ota/create_firmware_manifest.py --help
adb get-state
```

`adb get-state` muss `device` ausgeben. Die Firmwaredatei selbst wird nicht
automatisch aus dem öffentlichen Repository geladen. Sie muss als geprüfte
Datei separat auf den Raspberry Pi kopiert werden.

## Manifest für eine Firmware erstellen

Jede Firmware benötigt eine eigene JSON-Manifestdatei. Sie enthält Zielgerät,
Version, Dateigröße sowie MD5 und SHA-256. Größe und Hashwerte werden vom
Werkzeug automatisch aus der Firmwaredatei berechnet.

Beispiel für eine analysierte V3.4:

```sh
cd ~/FoxAir_updater

python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063 \
  --output FW3.4.json
```

Das Werkzeug leitet aus `V3.4` automatisch die Busversion `0034` ab und setzt
standardmäßig die geprüfte Image-Basis `0x08050000`. Falls eine andere Basis
tatsächlich analysiert und freigegeben wurde, existiert dafür die Expertenoption
`--image-base`; derzeit akzeptiert das Manifestformat jedoch ausschließlich
`0x08050000`.

Die Werte dürfen nicht geraten werden:

- `--software-code` muss zum Zielimage und Mainboard passen;
- `--display-version` muss das Format `Vn.n` verwenden;
- `--target-ssid` ist die vierstellige hexadezimale Mainboard-SSID;
- Firmwaredatei und erzeugtes Manifest sollten im selben Verzeichnis liegen.

Erzeugtes Manifest anzeigen:

```sh
cat FW3.4.json
```

Der anschließende Dry-Run lädt das Manifest erneut, prüft alle Felder und
vergleicht Dateiname, Dateigröße, MD5 und SHA-256 mit der Firmwaredatei. Eine
nachträglich veränderte oder falsch benannte Firmware wird dadurch abgelehnt.

Hinweis: `wire_version`, `size`, `md5` und `sha256` werden automatisch erzeugt
und sind keine notwendigen Kommandozeilenschalter.

## Die vier normalen Anwenderbefehle

### 1. Originalzustand kontrollieren

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run --check status
```

Dieser Befehl ist vollständig lesend. Er benötigt weder Firmware noch Manifest
oder Runtime-Helfer. Geprüft werden unter anderem:

- Originaldienst, Programmpfad und SHA-256;
- Prozesszustand und fehlender Debugger;
- Update-, Injektions- und Transfermarker;
- Cloud-Sperren und aktuelle MQTT-Verbindung;
- beide Überwachungsdienste;
- lokaler Firmware-Webserver und Zwischendateien;
- Abwesenheit des temporären Runtime-Helfers;
- CRC der OTA-Statusdatei.

Eine kurzzeitig fehlende MQTT-Verbindung kann sich beim nächsten Aufruf wieder
aufgebaut haben. Solange keine Cloud-Sperre aktiv ist und Dienst sowie
Watchdogs laufen, ist dies zunächst ein Wiederverbindungszustand. Die aktuelle
Version zeigt ihn noch als Fehler an; die verständlichere Warnmeldung ist für
eine spätere Änderung vorgesehen.

### 2. Dry-Run vor einem Update

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run \
  --manifest FW3.4.json \
  --firmware FW3.4.bin
```

Ohne `--execute` wird nichts kopiert, kein Dienst angehalten und nichts zum
Mainboard gesendet. Der Dry-Run prüft Firmware, Manifest, ADB-Verbindung,
Originaldienst, Modemwerkzeuge, Speicherplatz, OTA_INFO und den lokalen
Runtime-Helfer.

Ist `firmware_file` im Manifest korrekt gesetzt und liegt die Firmware neben
dem Manifest, kann `--firmware` entfallen:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run --manifest FW3.4.json
```

### 3. Vollständiges Update starten

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run \
  --manifest FW3.4.json \
  --firmware FW3.4.bin \
  --execute \
  --confirm PHNIX-FULL-UPDATE \
  --state-dir phnix-ota-state
```

Der Controller führt dabei automatisch aus:

1. Firmware, Manifest, Modem und Originaldienst prüfen;
2. Runtime-Helfer lokal prüfen;
3. Helfer zunächst unter einem temporären Namen übertragen;
4. SHA-256 prüfen, Rechte `755` setzen und atomar aktivieren;
5. OTA_INFO und Statistik auf dem Rechner sichern;
6. Firmware zum Modem kopieren und über `127.0.0.1:8081` bereitstellen;
7. Originaldienst kontrolliert in den lokalen OTA-Pfad führen;
8. Status und Fortschritt anzeigen;
9. nach einem sicher bestätigten Ende Dienst, Watchdogs und Cloud prüfen;
10. Firmwareablage, Zustandsdateien und Runtime-Helfer wieder löschen.

Ein externer Buslogger ist für diesen normalen Vollupdate-Aufruf nicht
erforderlich. Er kann bei einem ersten Test einer neuen Firmware trotzdem als
zusätzliche Beobachtung verwendet werden.

### 4. Originalzustand wiederherstellen

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run --restore original
```

Dieser Befehl ist für einen vor dem Firmwaretransfer angehaltenen oder
unvollständig aufgeräumten lokalen OTA-Lauf vorgesehen. Er:

- installiert den geprüften Helfer automatisch, falls er fehlt;
- stellt gesicherte Persistenzdateien wieder her;
- entfernt lokale Cloud-Sperren;
- beendet übrig gebliebene Debugger und Helfer;
- stellt Originaldienst und Watchdogs wieder her;
- entfernt Firmwareablage, Marker und Runtime-Helfer;
- führt anschließend den vollständigen Statuscheck aus.

Sobald der erste C5A8-Firmwareblock beobachtet wurde, verweigert dieses Kommando
absichtlich den Eingriff. Ab diesem Zeitpunkt ist der Originaldienst für
Übertragung und Abschluss zuständig.

## Was geschieht bei einem Fehler?

Es gibt zwei unterschiedliche Fehlerklassen:

### Sicher terminal beendet

Beispiele sind Gleichversionsablehnung, Parserablehnung oder ein bestätigter
Fehlerabschluss mit Rückkehr auf Mainboard-Schritt 12. In diesem Fall räumt der
Controller automatisch auf und löscht auch den Runtime-Helfer.

### Guarded Hold

Bei einem unerwarteten oder nicht eindeutig terminalen Zustand hält der
Controller den Ablauf geschützt an. Cloud-Sperre, Diagnosezustand und
Runtime-Helfer bleiben absichtlich erhalten.

Dann:

- LTE-Modem und Wärmepumpe nicht stromlos machen;
- keinen neuen Updatebefehl starten;
- Status und Buslog sichern;
- anschließend den bewusst gewählten Recoveryweg verwenden.

`run --restore original` ist nur vor begonnenem C5A8 zulässig.

## Konsolenausgabe

- `[OK]` in Grün: Prüfung oder sicherer Meilenstein erfolgreich;
- `[..]` in Cyan: laufender Zustand;
- `[WARNUNG]` in Gelb: prüfen, aber nicht automatisch fehlgeschlagen;
- `[FEHLER]` in Rot: Abbruch, Guarded Hold oder unvollständiger Zustand.

Bei einem vollständigen Transfer zeigt der Controller den vom Originaldienst
gemeldeten Fortschritt an. Er greift aufgrund dieser Anzeige nicht in den
Transfer ein.

## Allgemeine Schalter

Diese Schalter stehen vor dem jeweiligen Unterbefehl:

| Schalter | Bedeutung |
|---|---|
| `--adb PFAD` | ADB-Programm auswählen, unter Linux meist `adb` |
| `--serial ID` | bestimmtes ADB-Gerät auswählen, falls mehrere verbunden sind |
| `--runtime-helper DATEI` | anderen lokalen Pfad zum mitgelieferten Helfer verwenden |
| `--output auto` | Terminalansicht automatisch auswählen; Standard |
| `--output human` | kurze, lesbare Benutzeransicht erzwingen |
| `--output json` | vollständige maschinenlesbare Ausgabe |
| `--no-color` | ANSI-Farben abschalten |

Beispiel mit fest gewähltem ADB-Gerät:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  --serial DEVICE_ID \
  run --check status
```

## Schalter des Updatebefehls

| Schalter | Bedeutung |
|---|---|
| `--manifest DATEI` | verpflichtende Firmware-Metadaten |
| `--firmware DATEI` | Firmwaredatei; optional, wenn das Manifest sie eindeutig findet |
| `--execute` | wechselt vom Dry-Run zur echten Ausführung |
| `--confirm PHNIX-FULL-UPDATE` | notwendige zweite Bestätigung für echte Hardware |
| `--state-dir VERZEICHNIS` | lokale Sicherungen und Laufzustände; Standard `phnix-ota-state` |
| `--firmware-url URL` | Expertenoption; Standard ist der lokale Modem-Webserver |
| `--poll-interval SEKUNDEN` | Abfrageintervall; Standard 2 Sekunden |
| `--start-timeout SEKUNDEN` | Zeitlimit vor Beginn des Handshakes; Standard 60 Sekunden |
| `--handshake-timeout SEKUNDEN` | Zeitlimit zwischen frühen Handshakephasen; Standard 20 Sekunden |
| `--block-timeout` | nur noch veraltete Kompatibilitätsoption; nicht verwenden |

Die Standardwerte sollten von Endanwendern nicht verändert werden.

## Gleichversionstest – nur für Entwicklung und Abnahme

Der bereits verwendete V3.3-Test ist kein normaler Endnutzerbefehl. Er verlangt
bewusst einen passiven Logger und eine eigene Bestätigung:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  same-version-test \
  --manifest FW3.3.json \
  --firmware FW3.3.bin \
  --execute \
  --confirm PHNIX-C350-SAME-V33 \
  --logger-confirm PASSIVE-LOGGER-RUNNING \
  --state-dir phnix-ota-state
```

Das Mainboard antwortet bei bereits installierter V3.3 mit C36E Status 0. Es
werden dann keine Firmwareblöcke übertragen. Auch hier werden Helfer und
Zwischendateien nach dem bestätigten Ende automatisch gelöscht.

## Entwickler- und Laborbefehle

Folgende Unterbefehle gehören nicht zum normalen Endnutzerablauf:

- `status`: rohe OTA_INFO-/Hook-Ausgabe;
- `cancel-probe-plan`: Analyse eines möglichen Cancel-Tests;
- `pre-c5a8-vm-test`: ausschließlich für den markierten VM-Simulator;
- `pre-c5a8-real-plan`: erzeugt nur einen beaufsichtigten Realtestplan;
- `same-version-test`: Abnahme- und Entwicklungstest;
- `cancel`: auf realer Hardware weiterhin absichtlich nicht als allgemeiner
  Live-Cancel freigegeben.

Für normale Anwender sind `run --check status`, der Dry-Run, `run --execute`
und bei Bedarf `run --restore original` ausreichend.

## Geplantes Installationsskript

Ein späteres Installationsskript soll Repository/Dateien, Verzeichnisstruktur,
Python-Voraussetzungen, ADB-Erreichbarkeit und Dateirechte automatisch
einrichten. Dieser Installer ist noch nicht Bestandteil des aktuellen Stands;
bis dahin gelten die Git- oder wget-Schritte aus dieser Anleitung.
