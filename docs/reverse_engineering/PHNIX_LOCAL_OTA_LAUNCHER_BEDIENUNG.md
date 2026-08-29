# Lokaler PHNIX-OTA-Launcher – technische Bedienung

Stand: 29. August 2026

Diese Datei beschreibt die technische Bedienung des gemeinsamen lokalen PHNIX-OTA-Controllers. Für normale Endanwender ist unter Windows die GUI und unter Linux/Raspberry Pi der Launcher `./foxair-updater` vorgesehen.

> [!IMPORTANT]
> Der vollständige Pfad **V3.3 → V3.4** wurde auf realer Hardware erfolgreich durchgeführt. Beobachtet wurden kompletter C5A8-Transfer, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließend C544-Version `0034`.
>
> Der Controller bleibt buildspezifisch auf den untersuchten Originaldienst begrenzt. Andere Hardware-/Firmwarekombinationen sind nicht automatisch freigegeben.

Für Simulator-/Fehlertests steht zusätzlich der [OTA-Simulator](PHNIX_OTA_VM_SIMULATOR.md) zur Verfügung.

## Dateien

- `tools/phnix_ota/phnix_local_ota_controller.py` – gemeinsamer OTA-Controller;
- `tools/phnix_ota/phnix_ota_runtime_hook` – buildgebundener Runtime-Helfer;
- `tools/phnix_ota/create_firmware_manifest.py` – Manifestanalyse/-erzeugung.

Der Runtime-Helfer akzeptiert ausschließlich den verifizierten Originaldienst:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

## Empfohlener Endanwenderzugang

### Windows

GUI aus dem aktuellen GitHub Release verwenden:

https://github.com/dosordie/FoxAir_updater/releases

### Linux / Raspberry Pi

```sh
cd ~/FoxAir_updater
./foxair-updater status
./foxair-updater check FW3.4.json
./foxair-updater update FW3.4.json --confirm
```

Details:

- [`../HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../HowTo/PHNIX_UPDATER_ENDANWENDER.md)
- [`../../updater/linux/README.md`](../../updater/linux/README.md)

## 1. Read-only Vorprüfung

Direkter Controller-Aufruf:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  preflight \
  --manifest FW3.4.json \
  --firmware FW3.4.bin
```

Geprüft werden unter anderem:

- ADB-Zustand `device`;
- Originaldienst und Build-Hash;
- Watchdogs;
- benötigte Werkzeuge;
- OTA_INFO und CRC;
- Dateigröße/Hash/Manifest;
- Speicherplatz;
- normaler LTE-/MQTT-Zustand.

## 2. Runtime-Helfer

Bei einem echten Lauf verwaltet der Controller den Runtime-Helfer automatisch:

1. lokale Datei und Buildbindung prüfen;
2. als `/data/.phnix_ota_runtime_hook.new` übertragen;
3. SHA-256 prüfen;
4. Rechte setzen;
5. atomar als `/data/phnix_ota_runtime_hook` aktivieren;
6. aktive Kopie erneut prüfen;
7. nach sicherem terminalem Ende wieder entfernen.

Der Helfer wird nicht dauerhaft installiert.

## 3. Dry-Run

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py run \
  --manifest FW3.4.json \
  --firmware FW3.4.bin
```

Ohne `--execute` wird kein Firmwaretransfer gestartet.

## 4. Vollupdate

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py run \
  --manifest FW3.4.json \
  --firmware FW3.4.bin \
  --execute \
  --confirm PHNIX-FULL-UPDATE
```

Der normale Vollupdatepfad:

1. prüft Firmware/Manifest und Originalzustand;
2. installiert/verifiziert den Runtime-Helfer;
3. sichert relevante persistente Ausgangsdaten;
4. kopiert die geprüfte Firmware auf das LTE-Modem;
5. stellt sie lokal über `127.0.0.1:8081` bereit;
6. pausiert die externen `helloworld`-Watchdogs während der kontrollierten Hookphase;
7. führt den Originaldienst in den lokalen `0033`-OTA-Pfad;
8. lässt den originalen C350-/C357-/C5A8-/C371-/C36E-Ablauf arbeiten;
9. beobachtet den persistenten Firmwareoffset;
10. lässt nach begonnenem Transfer den Originaldienst autoritativ weiterarbeiten;
11. wartet auf terminalen Status 5 / Board-Step 12;
12. gibt dem normalen LTE-/Cloudzustand danach bis zu 120 Sekunden zur Normalisierung;
13. entfernt temporäre Helfer/Artefakte und prüft den Originalzustand.

## 5. MQTT-Verhalten

Der aktuelle Standard ist:

```text
MQTT bleibt verbunden
```

Die frühere vollständige MQTT-Isolierung ist nur noch optional:

```sh
--isolate-mqtt
```

Alias:

```sh
--update-no-mqtt
```

Unter Windows entspricht dies **Erweitert → MQTT bei Update aus**.

### Warum die Isolation nicht mehr Standard ist

`phnixIot4G` besitzt einen eigenen Rebootpfad, wenn `get_ALI_Connt_State()` länger als 1800 Sekunden offline meldet.

Wichtig: Der 1800-s-Zähler beginnt nicht zwingend mit dem Einsetzen einer Firewallregel. Eine stille `iptables DROP`-Blockade kann vom Aliyun-MQTT-SDK zunächst noch als intern verbunden behandelt werden. Erst nach mehreren fehlenden 180-s-Keepalive-Zyklen kippt der SDK-Zustand auf offline; **danach** beginnt der PHNIX-1800-s-Zähler.

Es gibt keinen bekannten OTA-Sonderzweig, der den Rebootpfad während eines Mainboardupdates deaktiviert.

Der reale V3.3→V3.4-Lauf benötigte bereits knapp 29 Minuten für C5A8 und weitere rund fünf Minuten bis Status 5. Deshalb bleibt MQTT im Normalbetrieb verbunden.

## 6. Fortschrittsanzeige

Während C5A8 verwendet der Controller den CRC-gültigen persistenten OTA_INFO-Offset:

```text
offset / length
```

Unvollständige oder CRC-ungültige Momentaufnahmen während gleichzeitiger Dateischreibvorgänge sind kein Grund, in den laufenden Transfer einzugreifen.

> [!WARNING]
> **100 % = Datenübertragung vollständig, nicht Update vollständig.**

Realer Ablauf:

```text
100 % C5A8
→ C36E Status 3
→ Mainboard Flash/Promotion
→ C36E Status 5
→ Board-Step 12
→ neue C544-Version 0034
```

Gemessen beim V3.3→V3.4-Lauf:

```text
C5A8:                     ca. 28:56 min
letzter C5A8 → Status 3:  ca. 2 s
letzter C5A8 → Status 5:  ca. 5:16 min
bis neuer C544-Version:   rund 35 min Gesamtbeobachtung
```

## 7. Sicherheitsgrenze vor/nach C5A8

### Vor dem ersten C5A8

Ein kontrollierter Restore-/Recoverypfad kann abhängig vom exakten Zustand noch zulässig sein.

### Ab dem ersten C5A8

Der Originaldienst ist autoritativ.

Der Controller legt einen `transfer-started`-Marker an. Ein generisches `restore original` wird danach absichtlich verweigert.

Das ist wichtig, weil das Mainboard ab diesem Punkt Flashdaten im Stagingbereich besitzt und spätere Promotionzustände selbstständig durchlaufen kann.

`C36E Status 3` ist ausdrücklich **kein** sicherer Stop-/Restorepunkt.

## 8. Monitoring-/ADB-Verlust

Ein Verlust der Host-/ADB-Beobachtung nach begonnenem C5A8 darf nicht dazu führen, den Originaldienst zu stoppen oder automatisch einen Restore zu erzwingen.

Nach Reconnect wird der bestehende Zustand read-only geprüft. Es wird kein zweiter OTA-Auftrag gestartet.

## 9. Guarded Hold

Vor C5A8 kann bei einem nicht eindeutig sicheren Fehler ein geschützter Halt auftreten:

```json
{"phase":"guarded-hold","terminal":false,"recovery_required":true}
```

Dann nicht blind Prozesse fortsetzen, Schutzregeln entfernen oder einen zweiten Updateauftrag starten. Zuerst Status und Logs auswerten.

Nach begonnenem C5A8 gilt diese generische Vor-C5A8-Strategie nicht mehr; der Originaldienst bleibt autoritativ.

## 10. Gleichversionstest

Der separate V3.3-Gleichversionstest bleibt als Labor-/Regressionstest erhalten:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  same-version-test \
  --manifest FW3.3.json \
  --firmware FW3.3.bin \
  --execute \
  --confirm PHNIX-C350-SAME-V33 \
  --logger-confirm PASSIVE-LOGGER-RUNNING
```

Der reale V3.3→V3.3-Test endete erwartungsgemäß mit C36E Status 0 vor C357/C5A8.

In der normalen Windows-Endanwender-GUI ist dieser separate Labortest nicht mehr sichtbar.

## 11. Status lesen

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py status
```

Für den lesbaren Originalzustandscheck kann je nach Frontend/Wrapper der gemeinsame Statuspfad verwendet werden. Geprüft werden insbesondere:

- Originaldienst/Pfad/SHA;
- Prozess- und Debuggerzustand;
- lokale OTA-Marker;
- Cloud-/MQTT-Sperrregeln;
- MQTT-Verbindung;
- Watchdogs;
- lokaler Firmware-Webserver;
- OTA_INFO/CRC.

## 12. Restore

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run --restore original
```

Nur verwenden, wenn der Controller bestätigt, dass noch **kein C5A8-Transfer begonnen** hat.

Ab `transfer-started` verweigert der Helfer den Eingriff absichtlich.

## 13. Konsolenausgabe

- grün: erfolgreich geprüfter Meilenstein;
- cyan: laufende Phase;
- gelb: Warnung;
- rot: Fehler/Guarded Hold/manueller Recoverybedarf.

JSON für Integration:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py --output json ...
```

Farben abschalten:

```sh
--no-color
```

## 14. Live-Beleg

Der erfolgreiche V3.3→V3.4-Lauf ist separat dokumentiert:

[`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)

Dort sind Firmwarehashes, Buszeitpunkte, Status 3/5, Board-Step 12, Prozessbeobachtung und C544-Version dokumentiert.

## 15. Weiterführende Dokumente

- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md)
- [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md)
- [`../HowTo/FIRMWARE_MANIFEST.md`](../HowTo/FIRMWARE_MANIFEST.md)
- [`../HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../HowTo/PHNIX_UPDATER_ENDANWENDER.md)