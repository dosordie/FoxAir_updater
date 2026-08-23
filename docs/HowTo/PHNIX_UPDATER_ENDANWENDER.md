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

