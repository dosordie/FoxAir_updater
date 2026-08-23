# PHNIX-Logger: Registerbenennung und OTA-Beobachtung

Stand: 2026-08-23

## Zweck

Diese Datei ist die Übergabe für die spätere Anpassung eines passiven
RS485-Loggers. Sie beschreibt:

- wie der Bereich 200 bis 215 zu benennen und auszuwerten ist;
- welche PHNIX-Sonderregister nicht wie gewöhnliche Warmlink-Register
  behandelt werden dürfen;
- welche Frames ein Logger während eines Mainboard-Firmwaretransfers erkennen,
  korrelieren und sicherheitsrelevant melden muss.

Der Logger bleibt passiv. Aus dieser Datei folgt keine Freigabe zum Senden.

## 1. Grundregel: Adresse nur aus dem Frameheader lesen

Bei einem FC10-Datenframe ist die Startadresse ausschließlich:

```text
Byte 0      Slave
Byte 1      Funktion
Byte 2..3   Startadresse, big-endian
Byte 4..5   Quantity
Byte 6      ByteCount
Byte 7..    Nutzdaten
letzte 2    Modbus-CRC, low byte zuerst
```

Ein Datenwort `00 C8` innerhalb des Payloads ist **nicht automatisch Register
200**. Nur `frame[2:4] == 00 C8` bezeichnet die Startadresse `0x00C8`.

PHNIX nutzt FC10 auf diesem Bus auch für Mainboard-zu-DTU-Datenmeldungen. Ein
Logger sollte ein vollständiges Paket deshalb zunächst neutral als
`FC10 data frame` bezeichnen. `Write`, `Request`, `Response`, `DTU→Board` und
`Board→DTU` dürfen erst aus Busanschluss/Richtung oder dem bekannten
Sonderregister abgeleitet werden.

## 2. Register 200 bis 215: ProductKey

```text
Start dezimal:   200
Start hex:       0x00C8
Ende dezimal:    215
Ende hex:        0x00D7
Anzahl:          16 Register
Nutzdaten:       32 Byte
Bedeutung:       PHNIX/Aliyun ProductKey
Erwartete Form:  63 10 00 C8 00 10 20 <32 Byte> <CRC_LO CRC_HI>
Richtung:        Mainboard → LTE/DTU
```

Empfohlene Loggernamen:

| Dezimal | Hex | Name |
|---:|---:|---|
| 200 | `0x00C8` | `PHNIX_PRODUCT_KEY_WORD_00` |
| 201 | `0x00C9` | `PHNIX_PRODUCT_KEY_WORD_01` |
| 202 | `0x00CA` | `PHNIX_PRODUCT_KEY_WORD_02` |
| 203 | `0x00CB` | `PHNIX_PRODUCT_KEY_WORD_03` |
| 204 | `0x00CC` | `PHNIX_PRODUCT_KEY_WORD_04` |
| 205 | `0x00CD` | `PHNIX_PRODUCT_KEY_WORD_05` |
| 206 | `0x00CE` | `PHNIX_PRODUCT_KEY_WORD_06` |
| 207 | `0x00CF` | `PHNIX_PRODUCT_KEY_WORD_07` |
| 208 | `0x00D0` | `PHNIX_PRODUCT_KEY_WORD_08` |
| 209 | `0x00D1` | `PHNIX_PRODUCT_KEY_WORD_09` |
| 210 | `0x00D2` | `PHNIX_PRODUCT_KEY_WORD_10` |
| 211 | `0x00D3` | `PHNIX_PRODUCT_KEY_WORD_11` |
| 212 | `0x00D4` | `PHNIX_PRODUCT_KEY_WORD_12` |
| 213 | `0x00D5` | `PHNIX_PRODUCT_KEY_WORD_13` |
| 214 | `0x00D6` | `PHNIX_PRODUCT_KEY_WORD_14` |
| 215 | `0x00D7` | `PHNIX_PRODUCT_KEY_WORD_15` |

### Auswertung

Die 32 Nutzbytes werden in Busreihenfolge zusammengesetzt, nicht als 16
numerische Messwerte interpretiert. Für eine Diagnoseansicht kann zusätzlich
eine ASCII-Darstellung bis zum ersten Nullbyte erzeugt werden.

Der ProductKey ist eine Geräte-/Cloudkennung. Standardausgabe und öffentliche
Logs müssen ihn maskieren, zum Beispiel:

```text
ProductKey: a5cV…C8x (32 raw bytes, CRC valid)
```

Vollständige ProductKeys, DeviceNames, DeviceSecrets, IMEI und signierte URLs
gehören nicht in öffentliche Mitschnitte.

### Beobachtung im Live-Mitschnitt

Im Mitschnitt vom 23.08.2026 wurde der Bereich eindeutig gesehen:

```text
18:04:34  63 10 00 C8 00 10 20 ...
```

Das folgte auf den regulären Neustart des Originaldienstes und gehört zum
Provisionierungs-/Startupverkehr, nicht zum Firmwaredatenstrom.

## 3. Normaler Startup- und Geräteinfoverkehr

Diese Bereiche dürfen nicht als OTA-Datenblöcke fehlklassifiziert werden:

| Register/Bereich | Dezimal | Form | Bedeutung |
|---:|---:|---|---|
| `0x0004` | 4 | FC03 Read 1 | Trigger eines vollständigen Geräteinfozyklus bis C544 |
| `0x0006` | 6 | FC03 Read 1 | UART-/485-Status- und Startup-Handshake |
| `0x00C8–0x00D7` | 200–215 | FC10, 16 Register/32 Byte | ProductKey |
| `0x01F4` | 500 | FC03 Read | lokaler DTU-Info-/Errorstatus |
| `0x03E9` | 1001 | FC10/FC03, 90 Register | Warmlink-Geräteinfoblock 1 |
| `0x0443` | 1091 | 90 Register | Warmlink-Geräteinfoblock 2 |
| `0x049D` | 1181 | 90 Register | Warmlink-Geräteinfoblock 3 |
| `0x04F7` | 1271 | 90 Register | Warmlink-Geräteinfoblock 4 |
| `0x0551` | 1361 | 90 Register | Warmlink-Geräteinfoblock 5 |
| `0x05AB` | 1451 | 90 Register | Warmlink-Geräteinfoblock 6 |
| `0x07D1` | 2001 | 90 Register | Device-ID-/Geräteinfobereich; erste 12 Datenbytes Device-ID |
| `0x082B` | 2091 | 90 Register | weiterer Warmlink-Geräteinfoblock |

Ein einzelner Read von `0x0004` kann die acht 90-Register-Blöcke und später
`C544` auslösen. Das ist normaler Identifikationsverkehr und allein kein
OTA-Start.

## 4. PHNIX-OTA-Sonderregister

| Register | Dezimal | Erwartete Richtung | Quantity/Nutzdaten | Loggername und Bedeutung |
|---:|---:|---|---|---|
| `0xC350` | 50000 | DTU → Board | 7 Reg./14 Byte | `OTA_OFFER`: SSID, Softwarecode, interne Version |
| `0xC357` | 50007 | DTU → Board | 19 Reg./38 Byte | `OTA_FILE_INFO`: SSID, Dateigröße, MD5 |
| `0xC36A` | 50026 | DTU → Board | 2 Reg./4 Byte | `OTA_CANCEL_REQUEST`: SSID, Status |
| `0xC36C` | 50028 | Board → DTU | 2 Reg./4 Byte | `OTA_CANCEL_RESPONSE`: SSID, Status |
| `0xC36E` | 50030 | Board → DTU | real 2 Reg./4 Byte | `OTA_BOARD_STATUS`: SSID, OTA-Status |
| `0xC371` | 50033 | Board → DTU | 4 Reg./8 Byte | `OTA_BLOCK_ACK`: SSID, ackA, ackB, Blocknummer |
| `0xC375` | 50037 | DTU → Board | 2 Reg./4 Byte | `OTA_ROLLBACK_REQUEST` |
| `0xC378` | 50040 | Board → DTU | 2 Reg./4 Byte | `OTA_ROLLBACK_RESPONSE` |
| `0xC37B` | 50043 | DTU → Board | 2 Reg./4 Byte | `OTA_STATUS_ACK`, unter anderem Status 7 für C544 |
| `0xC544` | 50500 | Board → DTU | 13 Reg./26 Byte | `BOARD_VERSION_INFO` |
| `0xC5A8` | 50600 | DTU → Board | PHNIX-Sonderlayout | `OTA_FIRMWARE_BLOCK`: SSID, Blockzahlen, Firmwaredaten |

Die Dezimalzahl ist nur eine alternative Anzeige. Im Rohframe stehen die zwei
big-endian Adressbytes, beispielsweise `C3 6A` für `0xC36A`.

## 5. Wichtige Payloads

### C350 – Firmwareangebot

```text
63 10 C3 50 00 07 0E
SSID_BE16
softwareCode ASCII[8]
version485 ASCII[4]
CRC_LO CRC_HI
```

Für Mainboard-V3.3 ist die interne Version `0033`, nicht `V3.3`. `0033` ist
hier Inhalt des Versionsfeldes; der gleich aussehende Cloud-Code `0033` ist
eine andere Protokollebene.

### C357 – Dateimetadaten

```text
63 10 C3 57 00 13 26
SSID_BE16
fileSize_BE32
MD5 als 32 lowercase ASCII-Zeichen
CRC_LO CRC_HI
```

Der Logger muss Dateigröße und MD5 einmal pro OTA-Lauf festhalten und bei jeder
Wiederholung auf Gleichheit prüfen. Änderungen im selben Lauf sind ein harter
Alarm.

### C36E – Status des Mainboards

Das echte V3.3-Wireformat enthält vier Nutzbytes:

```text
SSID_BE16
status_BE16
```

Eine früher im Labor verwendete 6-Byte-Variante mit zusätzlicher Blockgröße war
nur handler-kompatibel synthetisch. Der Logger darf sie nicht als behauptetes
Originalformat voraussetzen.

Besonders relevant:

```text
Status 1  Angebot akzeptiert / C357 folgt
Status 2  Metadaten akzeptiert / Datenphase kann beginnen
Status 3  Datenphase abgeschlossen, weitere Abschlusslogik
Status 4  Fehler nach Datenphase
Status 5  Commit/Promotionstatus
Status 6  Upgradefehler
Status 7  Versions-/C544-bezogener Status
```

Die genaue Ablaufwirkung ist kontextabhängig. Der Logger soll immer vorheriges
Frame, SSID und aktuellen OTA-Lauf mit ausgeben.

### C36A/C36C – Cancel

```text
C36A: SSID_BE16, status_BE16
C36C: SSID_BE16, status_BE16
```

Der erfolgreiche Live-Test zeigte intern:

```text
board_ota_step 12 -> 7 -> 12
cancel_pending   0 -> 1 -> 0
```

Im parallelen Loggerausschnitt waren `C36A/C36C` nicht enthalten. Ein Logger
darf das Ausbleiben eines sichtbaren Frames daher nicht als Gegenbeweis zur
internen Zustandsbeobachtung interpretieren. Für kommende Läufe müssen
`C3 6A` und `C3 6C` ausdrücklich roh gesucht und mit CRC protokolliert werden.

### C371 – Firmwareblock-ACK

```text
SSID_BE16
ackA_BE16
ackB_BE16
ackBlock_BE16
```

Akzeptierter Normalfall:

```text
ackA == 1
ackBlock == erwartete aktuelle Blocknummer
ackB == 1  -> Offset um Blockgröße erhöhen
ackB == 2  -> finaler Block; Offset exakt auf fileSize setzen
```

Falsche, übersprungene oder rückwärts laufende Blocknummern sowie unbekannte
ACK-Werte müssen als OTA-Fehler hervorgehoben werden.

### C5A8 – Firmwareblock

Bei der bestätigten Defaultblockgröße 168:

```text
63 10 C5 A8 00 57 A8
SSID_BE16
totalBlocks_BE16
currentBlock_BE16
168 Firmwarebytes
CRC_LO CRC_HI
```

PHNIX verwendet hier ein Sonderlayout: `Quantity=0x0057` und
`ByteCount=0xA8`. Ein strikt generischer Modbus-Parser würde wegen
`Quantity*2 != ByteCount` ablehnen. Für `0xC5A8` muss die Framelänge anhand des
ByteCount-Feldes bestimmt und anschließend die CRC geprüft werden.

Für die bekannte Datei mit 287598 Byte und Blockgröße 168 gilt:

```text
1712 Blöcke
Block 1..1711: je 168 reale Firmwarebytes
Block 1712:   150 reale Bytes + 18 × FF Padding
finales C371: ackB=2, ackBlock=1712
```

Der Logger sollte niemals die Paddingbytes in den rekonstruierten Dateihash
einbeziehen. Rekonstruiert werden höchstens `fileSize` Bytes aus C357.

## 6. Erwartete Transferfolge

```text
C350 Angebot
 -> C350-Bestätigung und C36E Status 1
C357 Dateigröße/MD5
 -> C357-Bestätigung und C36E Status 2
C5A8 Block N
 -> C371 ackA=1, ackB=1, ackBlock=N
... Wiederholung ...
C5A8 letzter Block
 -> C371 ackA=1, ackB=2, ackBlock=letzter Block
C36E Status 3/4
 -> C37B passender Status-ACK
C36E Status 5/6 beziehungsweise weiterer Handoff-/Recoverypfad
```

Retries sind zulässig, müssen aber als Wiederholung desselben semantischen
Frames erkannt werden. Ein Retry darf nicht doppelt in den rekonstruierten
Firmwarestrom aufgenommen werden.

`C544 -> C37B Status 7` kann auch beim Geräteinfozyklus auftreten und ist nicht
automatisch Beweis für einen laufenden Firmwaretransfer. Im Mitschnitt vom
23.08.2026 wurde genau dieses Paar gesehen:

```text
C544 Boardversion
C37B mit SSID 0x0063 und Status 7
```

## 7. Logger-Zustandsmodell

Pro SSID sollte ein eigener Laufzustand geführt werden:

```text
idle
offer_seen
offer_accepted
metadata_seen
metadata_accepted
data_active
last_block_acked
promotion_or_commit
terminal_success
terminal_failure
cancel_pending
cancelled
```

Mindestens zu speichern:

- SSID;
- Softwarecode und interne Version aus C350;
- Dateigröße und MD5 aus C357;
- ausgehandelte/benutzte Blockgröße;
- totalBlocks;
- letzte gesendete und letzte bestätigte Blocknummer;
- aus Blocknummer und Dateigröße berechneter bestätigter Byteoffset;
- Anzahl und Ursache von Retries;
- letzter C36E-Status;
- Cancel-/Rollbackzustand;
- CRC-Fehler, Framinglücken und Zeitstempel.

## 8. Harte Warnungen und Stopmarker

Der Logger soll mindestens folgende Ereignisse rot beziehungsweise als
`OTA_CRITICAL` markieren:

- erstes `C5A8`: ab hier schreibt das Mainboard in den Staging-Flash;
- C5A8 ohne zuvor passendes C350, C357 und C36E Status 2;
- C350/C357-Metadaten ändern sich innerhalb desselben Laufs;
- CRC-Fehler in einem OTA-Frame;
- Blocknummer 0, Sprung, Rücklauf oder falsches C371-ACK;
- `ackB=2` vor dem rechnerisch letzten Block;
- mehr rekonstruierte Daten als C357-fileSize;
- C36E Status 4 oder 6;
- C36A ohne passende C36C-Status-1-Bestätigung;
- C5A8 nach bestätigtem Cancel;
- gleichzeitige widersprüchliche OTA-Frames von zwei Sendern;
- Strom-/Busunterbrechung ab erstem C5A8 bis bestätigtem Terminalzustand.

Ein sichtbares `C36A` allein ist kein sicherer Ausstieg. Erforderlich sind
mindestens passende SSID, `C36C status 1` und das Ende weiterer C5A8-Frames.
Beim Originaldienst soll zusätzlich dessen interner Terminalzustand geprüft
werden.

## 9. Was für die Firmwareübertragung außerhalb des Loggers zu beachten ist

Der passive Logger verbessert Nachweis und Diagnose, ersetzt aber keine
Transferguards:

1. Firmwaredatei vorab gegen erwartete Größe und MD5 prüfen.
2. Imagebasis und Vector Table prüfen; die bekannte V3.3 ist für
   `0x08050000` gelinkt.
3. OTA_INFO vor dem Start CRC-validieren; Offset und Länge müssen zum geplanten
   Neu-/Resume-Lauf passen.
4. Cloud während eines lokalen Transfers kontrolliert isolieren, damit kein
   zweites `0033`, Cancel oder Metadatenwechsel eingreift.
5. Nur einen aktiven Sender auf dem RS485-Bus zulassen. Das zweite LTE-Modem
   kann sonst Frames dazwischen senden; deshalb Sendepause und Kollisionscheck.
6. Stabile Versorgung ab erstem C5A8 sicherstellen.
7. C350/C357-Handshake als eigene Freigabestufe ohne C5A8 testen.
8. Erst danach die Flash-schreibende C5A8-Stufe separat freigeben.
9. Finalen C371-ACK und die nachfolgenden C36E/C37B-/Commitzustände vollständig
   beobachten; ein kompletter Datentransport ist noch kein bewiesener Boot.
10. Power-Loss-Recovery, residenter Loader bei `0x08000000` und der genaue
    Promotion-/Fallbackpfad bleiben die wesentlichen Restrisiken eines echten
    Updates.

## 10. Parseranforderungen

- fragmentierte Eingänge puffern, bis das vollständige Frame vorliegt;
- mehrere Frames in einem Read einzeln extrahieren;
- CRC vor semantischer Auswertung prüfen;
- FC03-Request/Response, FC10-Kurz-ACK und FC10-Datenframe unterscheiden;
- für C5A8 die PHNIX-Ausnahme `Quantity*2 != ByteCount` unterstützen;
- bei ungültigem Präfix byteweise resynchronisieren, nicht pauschal große
  Puffer verwerfen;
- verworfene Bytes mit Zeitstempel und Hexdump erhalten;
- OTA-Sonderregister vor der normalen Warmlink-Registertabelle dispatchen;
- sensible Identifikationsdaten standardmäßig maskieren;
- Rohframe, dekodierte Felder, Richtung, CRC-Status und Laufzustand gemeinsam
  protokollieren.

Der vorliegende Mitschnitt zeigt, warum das wichtig ist: vollständige
189-Byte-Geräteinfoblöcke wurden korrekt zusammengesetzt, einzelne 32-Byte-
Identifikationsantworten aber als Restbuffer verworfen. Für einen OTA-Lauf darf
ein vergleichbarer Parserverlust bei C36A/C36C oder C371 nicht unbemerkt
bleiben.

## Zugehörige Detaildokumente

- [`PHNIX_phnixIot4G_uart_provisioning.md`](PHNIX_phnixIot4G_uart_provisioning.md)
- [`PHNIX_phnixIot4G_ota_rs485_frames.md`](PHNIX_phnixIot4G_ota_rs485_frames.md)
- [`PHNIX_phnixIot4G_ota_cancel_rollback_restart.md`](PHNIX_phnixIot4G_ota_cancel_rollback_restart.md)
- [`PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md`](PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md)
- [`PHNIX_CANCEL_PROBE_LIVE_RESULT.md`](PHNIX_CANCEL_PROBE_LIVE_RESULT.md)
- [`FW3.3-OTA-PROMOTION-RECOVERY.md`](FW3.3-OTA-PROMOTION-RECOVERY.md)

