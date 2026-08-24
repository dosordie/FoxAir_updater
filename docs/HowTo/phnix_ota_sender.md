# Kontrollierter PHNIX-Mainboard-OTA-Sender

> [!NOTE]
> Für Endanwender existiert inzwischen eine separate **FoxAir-Updater-Windows-GUI** als Portable-ZIP und Setup-EXE unter [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases).
>
> Diese GUI verwendet den rekonstruierten Originaldienst-/ADB-OTA-Pfad und ist **nicht** identisch mit dem hier beschriebenen direkten RS485-Sender. Unter Windows sind ADB-Verbindung, Originalstatus und Backup real getestet; ein echter Firmware-Versionswechsel ist weiterhin nicht live bestätigt.

Für passive Buslogger und die vollständige Benennung der Startup-/OTA-Register
siehe
[`PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md).

Stand: 24. August 2026

[`devtools/phnix_ota_sender.py`](../../devtools/phnix_ota_sender.py) bildet die
LTE→Mainboard-Seite des rekonstruierten PHNIX-OTA-Protokolls nach. Das Werkzeug
kontaktiert weder PHNIX-Cloud noch MQTT oder HTTP. Es kann einen Transfer offline
planen und simulieren sowie – erst nach einer starken manuellen Freigabe – über
ser2net oder einen lokalen USB-RS485-Adapter senden.

## Sicherheitsgrenze der ersten Version

Der Sender implementiert:

```text
C350  Softwarecode und interne Version
C357  Dateigröße und MD5
C36E  Status 1/2 empfangen
C5A8  Firmwareblöcke senden
C371  Blockbestätigungen prüfen
```

Er stoppt nach dem finalen C371 mit `ackB=2`. Er sendet ausdrücklich **kein**
C37B als Antwort auf C36E/status 3 oder status 5. Der spätere
Commit-/Handoff-/Bootloaderabschluss ist damit noch nicht Teil dieses Werkzeugs.

Wichtig: Schon der erste C5A8-Block wird vom echten Mainboard in den
OTA-Stagingbereich geschrieben. Ein Abbruch vor status 5 bedeutet nicht, dass
bis dahin kein Flash verändert wurde.

## Voraussetzungen

- Python 3.10 oder neuer
- für USB-RS485 zusätzlich `pyserial` (`requirements.txt` enthält es bereits)
- Firmwaredatei, erwartete Größe und erwarteter MD5
- achtstelliger Softwarecode
- Zielversion und OTA-SSID

Die Firmwaredatei wird nicht ins Repository eingecheckt.

## 1. Reine Planung – garantiert ohne Verbindung

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

`plan` öffnet weder Socket noch COM-Port. Es prüft Datei und Metadaten und gibt
unter anderem C350, C357, ersten/letzten C5A8-Frame, Blockzahl, Final-Padding und
den SHA-256 des gesamten erzeugten Bytestroms aus.

`V3.4` wird für C350 automatisch in die originale interne Schreibweise `0034`
umgewandelt.

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

- erzeugt jedes C5A8-Frame,
- prüft jeden Modbus-CRC,
- rekonstruiert die Firmware aus den Frames,
- prüft Blocknummern und `0xFF`-Padding,
- simuliert C371 mit `ackB=1` und am letzten Block `ackB=2`,
- vergleicht die Rekonstruktion bytegenau mit der Quelldatei.

Auch dieser Modus besitzt keinen Transportcodepfad.

## 3. Vergleich mit einem Originalmitschnitt

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

Der Vergleich sucht jedes erzeugte Requestframe bytegenau und in Reihenfolge im
Rohmitschnitt. Andere Startup-/RS485-Frames zwischen den OTA-Frames sind erlaubt.

## 4. Gesperrter Live-Modus

Der Live-Modus ist für einen späteren, separat freizugebenden Laborschritt
vorbereitet. Ohne die vollständige Freigabephrase aus `plan` beendet sich das
Programm, **bevor** ein Socket oder COM-Port geöffnet wird.

Ser2net:

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

USB-RS485:

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

Der Transport verwendet 9600 Baud, 8N1. Jede gesendete und empfangene Nachricht
wird als JSONL mit Zeitstempel und Rohbytes protokolliert.

Ohne `--stop-after data` endet der Live-Modus standardmäßig bereits nach
C350/C357 und C36E/status 2 und sendet keinen C5A8-Firmwareblock. Die Datenphase
muss damit zusätzlich zur Hash-Freigabe ausdrücklich gewählt werden.

### Bedingungen vor einem späteren echten Lauf

- LTE-Modem oder andere Busmaster dürfen nicht gleichzeitig senden.
- Softwarecode, Boardvariante, Größe und Hash der V3.4 müssen vorher bestätigt sein.
- Flash-/Loaderbackup und funktionierender Hardware-Recoveryweg müssen existieren.
- stabile Versorgung; keine Wärmepumpenabschaltung während der Datenphase.
- zunächst eigener freigegebener C350/C357-Handshaketest ohne C5A8-Datenphase.
- Abschluss ab C36E/status 3 bleibt bis zur Loaderanalyse gesondert gesperrt.

## Validierung mit V3.3 und originalem `phnixIot4G`

Verwendete echte Referenzdatei:

```text
Größe:  287598
MD5:    CEB6A4BF386FF644E23E410023E74673
SHA256: 6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
```

Ergebnisse:

```text
interne Simulation:     erfolgreich
rekonstruierte Bytes:   287598, bytegleich
C5A8-Blöcke:            1712
letzter Block:          150 reale Bytes + 18 × FF
final simuliertes ACK:  ackB=2

VM-Originalmitschnitt:  313382 Byte
verglichene Requests:   1714
                       (C350 + C357 + 1712 × C5A8)
Ergebnis:               alle bytegenau und in Originalreihenfolge gefunden
erstes Match:           Offset 16
letztes Match:          Offset 313199
Ende letztes Frame:     Offset 313382
```

Danach wurde der vollständige Sender zusätzlich innerhalb der Test-VM über
einen echten TCP-Loopback-Socket gegen den flashlosen Boardsimulator ausgeführt:

```text
Sender-Rückgabecode:       0
Simulator-Rückgabecode:    0
protokollierte Ereignisse: 3431
empfangene Blöcke:         1712
rekonstruierte Bytes:      287598
MD5/SHA256:                exakt wie Referenzdatei
finales ACK:               ackB=2
C37B erzeugt:              nein
```

Ein separater Sperrtest mit falscher Freigabephrase endete mit Rückgabecode 3,
bevor der Testsocket geöffnet und bevor eine Logdatei angelegt wurde.

Das Originalprogramm lief dabei in der vorhandenen QEMU-Laborumgebung mit
Loopback-only-Netzwerknamespace ohne IPv4-/IPv6-Defaultroute und ausschließlich
lokalen QMI-, MQTT-, HTTP- und RS485-Ersatzdiensten. Die reale Wärmepumpe, der
reale ser2net-Endpunkt und die PHNIX-Cloud wurden für diese Entwicklung nicht
kontaktiert.

## Automatische Tests

```powershell
python -m unittest tests.test_phnix_ota_sender -v
```

Die Tests prüfen unter anderem bekannte V3.3-Frames, CRC, Metadaten, Fragmentierung
von TCP-/Serial-Eingängen, Blockrekonstruktion, Final-Padding, ACK-Art und einen
vollständigen simulierten Transportlauf ohne C37B-Ausgabe.

Für einen echten TCP-End-to-End-Test ohne Hardware existiert zusätzlich
[`devtools/phnix_ota_board_simulator.py`](../../devtools/phnix_ota_board_simulator.py).
Er bindet ausschließlich an Loopback, validiert alle Requests gegen die lokale
Firmwaredatei, rekonstruiert diese und quittiert den letzten Block mit `ackB=2`.
Er besitzt keinen Flash- oder Cloudcode.

## Windows-Endanwenderprogramm existiert inzwischen

Der frühere Plan einer späteren PySide6-Oberfläche wurde inzwischen als **FoxAir Updater Windows** umgesetzt. Diese Anwendung ist jedoch bewusst **kein GUI-Frontend für den direkten RS485-Sender aus diesem Dokument**.

Die Windows-Endanwenderanwendung arbeitet über ADB mit dem originalen `phnixIot4G`-Dienst und verwendet den gemeinsamen `phnix_local_ota_controller.py` unverändert als Controller-Core. Sie bietet unter anderem:

1. lokale oder Remote-ADB-Verbindung;
2. read-only LTE-Backup/Firmware-Download;
3. Originalstatus und Dry-Run;
4. Manifest-Full/Show und automatische Manifest-Erzeugung;
5. experimentellen vollständigen OTA-Aufruf mit zusätzlichem Full-Abgleich und LTE-Cache-Sicherung;
6. Restore und Gleichversionstest;
7. sichtbares Ereignisprotokoll mit Export.

Download und weitere Informationen:

- [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md)
- [`firmware_backup_lte.md`](firmware_backup_lte.md)

Der hier dokumentierte `phnix_ota_sender.py` bleibt dagegen ein separates Laborwerkzeug für Offline-Simulation und kontrollierte direkte RS485-Protokolltests.
