# PHNIX-OTA-Simulator auf der Offline-VM

Stand: 2026-08-23

## Zweck

Der Simulator bildet die vom lokalen OTA-Launcher benutzte ADB- und
Modemoberfläche nach. Er verändert weder das LTE-Modem noch die Wärmepumpe und
sendet keine RS485-Frames. Die kopierten Originaldateien auf der VM bleiben
unverändert; alle veränderlichen Simulatordaten liegen unter:

```text
/home/lte/.local/share/phnix-ota-simulator
```

Der Launcher selbst wird unverändert benutzt. Nur der mit `--adb` ausgewählte
Transport zeigt auf den Simulator.

## Installation auf der vorhandenen VM

Die eingerichteten Dateien liegen in:

```text
/home/lte/phnix-ota-lab
```

Die Kurzkommandos `phnix-ota-sim` und `phnix-sim-adb` sind in
`/home/lte/.local/bin` verlinkt.

## Start, Status, Reset und Stop

Simulator mit erfolgreichem Ablauf starten:

```sh
phnix-ota-sim start --scenario success
```

Status anzeigen:

```sh
phnix-ota-sim status
```

Definierten Ausgangszustand wiederherstellen:

```sh
phnix-ota-sim reset --scenario success
```

Simulator stoppen:

```sh
phnix-ota-sim stop
```

`stop` beendet einen eventuell laufenden Simulator-Helfer und setzt simulierte
Cloudsperre, Watchdogpause und HTTP-Server zurück. Es löscht keine Originaldaten
der VM.

## Preflight des Launchers

```sh
cd /home/lte/phnix-ota-lab

./phnix_local_ota_controller.py \
  --adb ./phnix-sim-adb \
  preflight \
  --manifest FW3.3.json \
  --firmware FW3.3.bin
```

## Vollständiger virtueller Updateablauf

```sh
cd /home/lte/phnix-ota-lab
phnix-ota-sim reset --scenario success

./phnix_local_ota_controller.py \
  --adb ./phnix-sim-adb \
  run \
  --manifest FW3.3.json \
  --firmware FW3.3.bin \
  --execute \
  --confirm VM-FULL-UPDATE
```

Der Launcher führt dabei wirklich seine normalen Hostschritte aus:

1. Firmwaregröße und lokalen MD5 prüfen;
2. OTA_INFO und Statistik sichern;
3. Firmware mit dem simulierten `adb push` nach
   `/data/phnix_local_ota/phnixIot_device_OTA.bin` kopieren;
4. den MD5 der kopierten Datei prüfen;
5. die lokale HTTP-Bereitstellung prüfen;
6. das OTA-Kommando kopieren;
7. Phasen und CRC-validierten Fortschritt überwachen;
8. ausschließlich nach bestätigtem `board_ota_step == 12` Erfolg melden.

Der simulierte Zielpfad befindet sich physisch unter:

```text
/home/lte/.local/share/phnix-ota-simulator/root/data/phnix_local_ota
```

Auf dem echten LTE-Modem verwendet derselbe Launcher über echtes ADB den
tatsächlichen Pfad `/data/phnix_local_ota/phnixIot_device_OTA.bin`.

## Fehlerszenarien

Ein Szenario wird so ausgewählt:

```sh
phnix-ota-sim scenario crc-error
```

Verfügbar sind:

| Szenario | Simuliertes Ergebnis |
|---|---|
| `success` | vollständiger Transfer und bestätigter Step 12 |
| `same-version` | C36E Status 0, Persistenz-Restore und sauberes Ende ohne C5A8 |
| `parser-rejected` | Original-0033 wird abgelehnt; sichere Aufräumphase |
| `crc-error` | ungültiger Beobachtungswert; Originaldienst meldet danach Fehler |
| `metadata-mismatch` | abweichende Metadaten; Originaldienst meldet danach Fehler |
| `offset-backwards` | Offset läuft rückwärts; Originaldienst meldet danach Fehler |
| `offset-overflow` | Offset über Dateilänge; Originaldienst meldet danach Fehler |
| `stall-c350` | Timeout im ersten Handshake |
| `stall-c5a8` | Transfer pausiert; Originaldienst beendet ihn mit Fehlerstatus |
| `helper-exit` | Runtime-Helfer endet ohne terminalen Status |
| `success-without-step12` | falsche Erfolgsmeldung bei Board-Step 11 |

Fehler vor Beginn der Firmwareblöcke müssen in `guarded-hold` enden.
Ab C5A8 greift der Launcher aufgrund beobachteter OTA_INFO-Werte nicht mehr ein;
der Simulator lässt deshalb den Originaldienst selbst einen terminalen
Fehlerstatus melden. `parser-rejected` ist ebenfalls ein sicherer terminaler
Zustand und wird sauber aufgeräumt.

### Cancel-/Recovery-Szenarien

Nach einem provozierten `guarded-hold` wird ein Cancel-Szenario ausgewählt:

```sh
phnix-ota-sim cancel-scenario success
```

Verfügbar sind:

| Szenario | Erwartung |
|---|---|
| `success` | C36A, C36C Status 1, Step 10 und terminaler Step 12 |
| `retry-success` | zweiter C36A-Versuch führt zum sicheren Abschluss |
| `no-response` | kein C36C; `guarded-hold` bleibt bestehen |
| `rejected` | C36C Status 0; `guarded-hold` bleibt bestehen |
| `wrong-ssid` | Antwort gehört nicht zur Sitzung; Hold bleibt bestehen |
| `c36c-only` | Status 1 ohne terminalen Step 12; Hold bleibt bestehen |

Ausführung:

```sh
./phnix_local_ota_controller.py \
  --adb ./phnix-sim-adb \
  cancel --execute --confirm CANCEL-PHNIX-OTA
```

Die Cancel-Simulation ist ein Testvertrag. Sie ist kein Beweis, dass der reale
Modem-Helfer bereits sicher senden kann; dieser verweigert Live-Cancel weiterhin
absichtlich.

## Gesamte Testmatrix

```sh
cd /home/lte/phnix-ota-lab
phnix-ota-sim start --scenario success

./run_simulator_matrix.py \
  --firmware FW3.3.bin \
  --manifest FW3.3.json

phnix-ota-sim stop
```

Die Matrix umfasst elf Update-, sechs Cancel-/Recovery- und sechs
Handshake-Szenarien. Die
Simulation deckte dabei zwei
Zeitfehler im Launcher auf, die anschließend korrigiert wurden:

- Der C5A8-Fortschritts-Timer wird nun erst beim Eintritt in C5A8 gestartet.
- Nach dem Ende des Runtime-Helfers wird ein unmittelbar zuvor geschriebener
  terminaler Status innerhalb einer kurzen Nachlesefrist noch akzeptiert.

## Grenze der Simulation

Der Simulator prüft Hostablauf, Kopieren, Zustandsüberwachung, Timeouts und
Fehlerbehandlung. Er emuliert nicht den ARM-Prozessor, GPIO, reale
GDB-Breakpoints oder das echte RS485-Mainboard. Diese dynamischen Eigenschaften
müssen weiterhin separat und möglichst sparsam am Originalgerät bestätigt
werden.
