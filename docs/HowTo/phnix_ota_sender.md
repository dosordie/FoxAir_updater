# Kontrollierter PHNIX-Mainboard-OTA-Sender

Stand: 29. August 2026

> [!NOTE]
> Für Endanwender existiert inzwischen der **FoxAir Updater Windows** als Portable-ZIP und Setup-EXE unter [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases).
>
> Der normale Updater arbeitet über ADB mit dem originalen `phnixIot4G`-Dienst. Der vollständige Pfad **V3.3 → V3.4** wurde damit auf realer Hardware erfolgreich durchgeführt.
>
> Das hier beschriebene `devtools/phnix_ota_sender.py` ist **nicht** der Endanwender-Updater, sondern ein separates Laborwerkzeug für direkte RS485-Protokolltests.

Für passive Buslogger und die vollständige Benennung der Startup-/OTA-Register siehe [`PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md).

## Zweck

[`devtools/phnix_ota_sender.py`](../../devtools/phnix_ota_sender.py) bildet die LTE→Mainboard-Seite des rekonstruierten PHNIX-OTA-Protokolls direkt nach.

Das Werkzeug kontaktiert weder PHNIX-Cloud noch MQTT oder HTTP. Es kann einen Transfer offline planen und simulieren sowie – erst nach einer starken manuellen Freigabe – über ser2net oder einen lokalen USB-RS485-Adapter senden.

## Sicherheitsgrenze dieses Werkzeugs

Der Sender implementiert:

```text
C350  Softwarecode und interne Version
C357  Dateigröße und MD5
C36E  Status 1/2 empfangen
C5A8  Firmwareblöcke senden
C371  Blockbestätigungen prüfen
```

Der direkte Sender stoppt nach dem finalen C371 mit `ackB=2`. Er sendet ausdrücklich **kein C37B** als Antwort auf C36E Status 3 oder Status 5.

Damit ist der vollständige Commit-/Handoff-/Bootloaderabschluss **nicht Bestandteil dieses direkten Senders**.

Wichtig: Schon der erste C5A8-Block wird vom echten Mainboard in den OTA-Stagingbereich geschrieben. Ein Abbruch vor Status 5 bedeutet nicht, dass bis dahin kein Flash verändert wurde.

Der erfolgreiche V3.3→V3.4-Live-Update-Nachweis des normalen FoxAir Updaters darf deshalb nicht mit einer Live-Freigabe des direkten RS485-Senders verwechselt werden.

## Voraussetzungen

- Python 3.10 oder neuer;
- für USB-RS485 zusätzlich `pyserial`;
- Firmwaredatei;
- erwartete Größe und erwarteter MD5;
- achtstelliger Softwarecode;
- Zielversion und OTA-SSID.

Firmwaredateien werden nicht in dieses öffentliche Repository eingecheckt.

## 1. Reine Planung – ohne Verbindung

```powershell
python devtools/phnix_ota_sender.py plan `
  --firmware C:\Pfad\zur\phnixIot_device_OTA `
  --software-code 82400644 `
  --version V3.4 `
  --ssid 0063 `
  --expected-md5 <MD5-DER-V3.4> `
  --expected-size <GROESSE-DER-V3.4> `
  --json-output ota-plan-v34.json
```

`plan` öffnet weder Socket noch COM-Port. Es prüft Datei und Metadaten und gibt unter anderem C350, C357, ersten/letzten C5A8-Frame, Blockzahl, Final-Padding und den SHA-256 des erzeugten Bytestroms aus.

`V3.4` wird für C350 automatisch in `0034` umgewandelt.

## 2. Vollständige interne Simulation

```powershell
python devtools/phnix_ota_sender.py simulate `
  --firmware C:\Pfad\zur\phnixIot_device_OTA `
  --software-code 82400644 `
  --version V3.4 `
  --ssid 0063 `
  --expected-md5 <MD5-DER-V3.4> `
  --expected-size <GROESSE-DER-V3.4>
```

Die Simulation:

- erzeugt jedes C5A8-Frame;
- prüft jeden Modbus-CRC;
- rekonstruiert die Firmware aus den Frames;
- prüft Blocknummern und `0xFF`-Padding;
- simuliert C371 mit `ackB=1` und am letzten Block `ackB=2`;
- vergleicht die Rekonstruktion bytegenau mit der Quelldatei.

Dieser Modus besitzt keinen Hardware-Transportpfad.

## 3. Vergleich mit einem Originalmitschnitt

Beispiel V3.3:

```powershell
python devtools/phnix_ota_sender.py compare-capture `
  --firmware C:\Pfad\zur\phnixIot_device_OTA `
  --software-code 82400644 `
  --version V3.3 `
  --ssid 0063 `
  --expected-md5 CEB6A4BF386FF644E23E410023E74673 `
  --expected-size 287598 `
  --capture C:\Pfad\zum\ttyHSL2-from-app.bin
```

Der Vergleich sucht jedes erzeugte Requestframe bytegenau und in Reihenfolge im Rohmitschnitt. Andere Startup-/RS485-Frames zwischen den OTA-Frames sind erlaubt.

Bestätigte V3.3-Referenz:

```text
Größe:  287598
MD5:    CEB6A4BF386FF644E23E410023E74673
SHA256: 6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
C5A8-Blöcke: 1712
letzter Block: 150 reale Bytes + 18 × FF
final simuliertes ACK: ackB=2
```

Die erzeugten Requests wurden gegen einen Originalmitschnitt in Reihenfolge und bytegenau abgeglichen.

## 4. TCP-/Board-Simulation

Ein echter TCP-End-to-End-Test ohne Hardware kann gegen den flashlosen Boardsimulator durchgeführt werden:

[`devtools/phnix_ota_board_simulator.py`](../../devtools/phnix_ota_board_simulator.py)

Der Simulator bindet ausschließlich an Loopback, validiert die Requests, rekonstruiert die Firmware und quittiert den letzten Block mit `ackB=2`.

Er besitzt keinen Flash- oder Cloudcode.

## 5. Gesperrter Live-Modus des direkten Senders

Der Live-Modus dieses Laborwerkzeugs bleibt separat abgesichert. Ohne die vollständige Freigabephrase aus `plan` beendet sich das Programm, bevor Socket oder COM-Port geöffnet werden.

Ser2net-Beispiel:

```powershell
python devtools/phnix_ota_sender.py send `
  --firmware C:\Pfad\zur\phnixIot_device_OTA `
  --software-code 82400644 --version V3.4 --ssid 0063 `
  --expected-md5 <MD5-DER-V3.4> --expected-size <GROESSE> `
  --tcp <HOST>:<PORT> `
  --stop-after data `
  --log ota-v34.jsonl `
  --confirm-live-transfer PHNIX-LIVE-TRANSFER-<SHA256-DER-V3.4>
```

USB-RS485-Beispiel:

```powershell
python devtools/phnix_ota_sender.py send `
  --firmware C:\Pfad\zur\phnixIot_device_OTA `
  --software-code 82400644 --version V3.4 --ssid 0063 `
  --expected-md5 <MD5-DER-V3.4> --expected-size <GROESSE> `
  --serial COM5 --baudrate 9600 `
  --stop-after data `
  --log ota-v34.jsonl `
  --confirm-live-transfer PHNIX-LIVE-TRANSFER-<SHA256-DER-V3.4>
```

Der Transport verwendet 9600 Baud, 8N1. Jede gesendete und empfangene Nachricht wird als JSONL protokolliert.

Ohne `--stop-after data` endet der Live-Modus standardmäßig bereits nach C350/C357 und C36E Status 2 und sendet keinen C5A8-Firmwareblock.

## Bedingungen für direkte Hardwaretests

- LTE-Modem oder andere Busmaster dürfen nicht gleichzeitig senden;
- Softwarecode, Boardvariante, Größe und Hash müssen bestätigt sein;
- stabile Versorgung;
- passiver Logger;
- funktionierender Recoveryweg;
- direkte C5A8-Datenphase nur mit eigener bewusster Freigabe;
- Abschluss nach Status 3/5 nicht mit dem normalen Originaldienstpfad verwechseln.

## Automatische Tests

```powershell
python -m unittest tests.test_phnix_ota_sender -v
```

Die Tests prüfen unter anderem bekannte V3.3-Frames, CRC, Metadaten, Fragmentierung, Blockrekonstruktion, Final-Padding, ACK-Art und simulierte Transportläufe.

## Verhältnis zum Windows-Endanwenderprogramm

Der **FoxAir Updater Windows v0.3.9** ist kein GUI-Frontend für den direkten Sender aus diesem Dokument.

Die Endanwenderanwendung arbeitet über ADB mit dem originalen `phnixIot4G`-Dienst und dem gemeinsamen `phnix_local_ota_controller.py`.

Sie bietet unter anderem:

1. lokale oder Remote-ADB-Verbindung;
2. read-only LTE-Backup/Firmware-Download;
3. Originalstatus und Dry-Run;
4. Manifest-Full/Show und automatische Manifest-Erzeugung;
5. vollständigen OTA-Aufruf mit Full-Abgleich und Cache-Sicherung;
6. Status/Recovery;
7. Fortschritts- und Abschlussphasen bis Status 5 / Board-Step 12;
8. optionale MQTT-Isolierung unter **Erweitert → MQTT bei Update aus**;
9. sichtbares Ereignisprotokoll und Export.

Der vollständige V3.3→V3.4-Pfad wurde mit diesem Originaldienst-/ADB-Weg erfolgreich live bestätigt.

Download und weitere Informationen:

- [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md)
- [`../RELEASE_NOTES_WINDOWS_v0.3.9.md`](../RELEASE_NOTES_WINDOWS_v0.3.9.md)
- [`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)

`phnix_ota_sender.py` bleibt dagegen ein separates Laborwerkzeug für Offline-Simulation und kontrollierte direkte RS485-Protokolltests.