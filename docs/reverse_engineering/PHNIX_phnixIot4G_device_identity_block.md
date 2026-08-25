# PHNIX `phnixIot4G` – Device-ID-/Provisioningblock `0x07D1`

Stand: 2026-08-26

Diese Datei ergänzt die statische Analyse der frühen RS485-/Provisioningphase.

## 1. Fest eingebauter Read-Request

Im Binary liegt bei `.rodata`:

```text
63 03 07 D1 00 5A 9C FE
```

Dekodiert als Modbus-RTU:

```text
Slave      0x63
Function   0x03
Start      0x07D1
Quantity   0x005A = 90 Register
CRC        0xFE9C / Wire bytes 9C FE
```

Damit fordert die DTU **90 Register = 180 Datenbytes** ab `0x07D1` an.

## 2. Erwartete Standardantwort

`uart485_get_productKey()` erkennt explizit:

```text
byte 0 == 0x63
byte 1 == 0x03
byte 2 == 0xB4   // 180 Datenbytes
```

Bei passender Antwort kopiert die Firmware:

```c
memcpy(aliMqtt_get_deviceID_buf(), &frame[3], 12);
```

und verwendet damit **nur die ersten 12 Bytes der 180-Byte-Nutzlast** als Device-ID.

Danach verlässt dieser Pfad die Funktion erfolgreich. Für die verbleibenden **168 Bytes** existiert in diesem Antwortzweig keine weitere Auswertung.

## 3. Liveinhalt der zwölf Device-ID-Bytes

Im realen 90-Register-Block ab `2001 / 0x07D1` wurden in den ersten sechs
Registern folgende Werte gelesen:

| Register | Dezimal | Hex | Big-Endian-ASCII |
|---:|---:|---:|---|
| 2001 | 22342 | `0x5746` | `WF` |
| 2002 | 12850 | `0x3232` | `22` |
| 2003 | 12592 | `0x3130` | `10` |
| 2004 | 12853 | `0x3235` | `25` |
| 2005 | 12340 | `0x3034` | `04` |
| 2006 | 14133 | `0x3735` | `75` |

Zusammengesetzt ergibt das exakt:

```text
WF2210250475
```

FoxAir Control bezeichnet diese Kennung seit der späteren Mappingkorrektur als
**WiFi Barcode / Kommunikationsmodul-ID** und ausdrücklich nicht als
Geräte-Serial-No. des Wärmepumpen-Typenschilds. Die derzeit plausibelste, aber
nicht herstellerseitig bestätigte Formatauslegung ist:

```text
WF + YYMMDD + laufende Nummer
WF + 221025 + 0475
     2022-10-25
```

Die gleiche Kennung steht als Paketkopf in mehreren 90-Register-Blöcken. Für
die LTE-DTU ist speziell die Kopie ab `0x07D1` relevant, weil genau deren erste
zwölf Bytes in den internen `deviceID`-Puffer kopiert werden.

### Liegt `WF2210250475` fest im V3.3-OTA-Image?

Im untersuchten 287598-Byte-Mainboardimage mit SHA-256
`6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A`
wurde die Kennung nicht gefunden:

- nicht als zusammenhängender ASCII-String `WF2210250475`;
- nicht als Folge der sechs Big-Endian-Registerworte;
- nicht als Folge derselben sechs Little-Endian-16-Bit-Worte;
- selbst das erste Wort `0x5746` kommt im Image in keiner Byteordnung als
  16-Bit-Literal vor.

Damit ist die Kennung **nicht als direkter Datenstring oder Worttabelle im
V3.3-Anwendungsimage enthalten**. Am wahrscheinlichsten stammt sie aus einem
separat provisionierten nichtflüchtigen Produktionsbereich, beispielsweise
I²C-EEPROM, residentem Loader-/Datenflash oder einem anderen bei OTA nicht
mitgelieferten Konfigurationsbereich, und wird beim Start in den Modbusspiegel
übernommen.

Vollständig ausgeschlossen ist allein durch die Stringsuche noch nicht, dass
der Programmcode den Wert aus einzelnen Teilwerten zusammensetzt. Wegen des
datums-/laufnummerartigen Formats und des fehlenden Literals ist eine
geräteindividuelle Produktionsprovisionierung jedoch deutlich plausibler als
eine für alle V3.3-Geräte fest einkompilierte Konstante.

## 4. Konsequenz

Der Block `0x07D1..0x082A` ist wesentlich größer als die tatsächlich von `phnixIot4G` benötigte Device-ID.

Belegt aus Sicht der LTE-Firmware:

```text
0x07D1 ... erste 12 Byte / 6 Register -> Device-ID
Restliche 168 Byte / 84 Register      -> von phnixIot4G in diesem Read-Pfad ignoriert
```

Wichtig: „ignoriert“ bedeutet nur, dass **diese LTE-Firmware** die Daten nicht semantisch verwendet. Das sagt nicht aus, dass die Register auf dem Mainboard bedeutungslos sind.

Gerade deshalb ist der Restblock ein interessanter Kandidat für:

- Modell-/Hardwarekennung,
- Serien-/Produktdaten,
- Firmware-/Buildinformationen,
- Produktions-/Serviceparameter,
- weitere Boardfähigkeiten.

Diese Bedeutungen sind statisch aus `phnixIot4G` nicht belegbar, weil die Bytes nach Offset 12 nicht gelesen werden.

## 5. Zweiter Device-ID-Pfad über FC `0x10`

Neben der Standard-Read-Antwort erkennt `uart485_get_productKey()` zusätzlich ein eingehendes Write-Multiple-Registers-artiges Frame:

```text
63 10 07 D1 ...
```

Wenn die Datenlänge/der erste Nutzdatenbereich plausibel ist, kopiert die Firmware erneut:

```c
memcpy(deviceID, &frame[7], 12);
```

Damit kann dieselbe 12-Byte-Device-ID offenbar sowohl:

1. als Antwort auf den aktiven `0x03 / 0x07D1 / 90 Register`-Read kommen,
2. als aktiv vom Mainboard gesendetes `0x10 / 0x07D1`-Frame eintreffen.

Das zeigt, dass `0x07D1` im PHNIX-Protokoll ein echter Geräteidentitätsbereich ist und nicht nur ein zufälliger Startup-Read.

## 6. ProductKey-Pfad `0x00C8`

In derselben Funktion existiert ein weiterer FC10-Sonderfall:

```text
63 10 00 C8 ...
```

Nach CRC-Prüfung werden exakt **32 Byte ab Frameoffset 7** in `aliMqtt_get_product_buf()` kopiert.

Damit gilt:

```text
0x00C8 -> ProductKey / 32 Byte
0x07D1 -> Device-ID / 12 Byte relevant für LTE-DTU
```

Der ProductKey ist also nicht Bestandteil des ausgewerteten ersten 12-Byte-Bereichs von `0x07D1`, sondern besitzt einen separaten Mainboard-Pfad.

## 7. Weitere fest eingebaute Read-Requests

Direkt neben dem `0x07D1`-Request liegen im Binary:

```text
63 03 00 06 00 01 6C 49
63 03 00 04 00 01 CD 89
63 03 07 D1 00 5A 9C FE
```

Damit sind drei feste Reads bestätigt:

| Startregister | Menge | Funktion im LTE-Code |
|---:|---:|---|
| `0x0006` | 1 | früher Startup-/Handshake-Read; genaue Semantik noch offen |
| `0x0004` | 1 | `uart485_get_device_info()` / nach erfolgreicher MQTT-Initialisierung; live als Trigger für acht Geräteinfoblöcke und späteres C544 bestätigt |
| `0x07D1` | 90 | Geräteidentitätsblock; erste 12 Datenbytes = Device-ID |

## 8. Interessanter Punkt für Mainboard-RE

Für die parallele Mainboard-Firmwareanalyse ist besonders der Bereich

```text
0x07D7 .. 0x082A
```

interessant: Nach den ersten sechs Registern der 12-Byte-Device-ID bleiben 84 Register, deren Semantik aus dem LTE-Programm nicht hervorgeht.

Die beste weitere Quelle dafür ist daher nicht `phnixIot4G`, sondern:

- Mainboard-Firmware: Suche nach Registeradresse `0x07D1`, Bereichsgrenzen und 90-Register-Readhandler,
- reale passive RS485-Aufzeichnung der Antwort auf `63 03 07 D1 00 5A 9C FE`,
- Vergleich mehrerer Boards/Geräte, um konstante und variable Felder zu unterscheiden.

## 9. Beweisgrad

### Bewiesen

- Read-Request `63 03 07 D1 00 5A 9C FE` ist statisch eingebaut;
- erwartete Antwort hat `0xB4 = 180` Datenbytes;
- nur `frame[3..14]` werden als 12-Byte-Device-ID kopiert;
- die zwölf Livebytes der untersuchten Anlage dekodieren zu `WF2210250475`;
- die Kennung ist im V3.3-OTA-Image weder als ASCII-String noch als direkte
  Folge der sechs 16-Bit-Worte enthalten;
- die übrigen 168 Datenbytes werden in diesem Pfad nicht ausgewertet;
- alternativer FC10-Pfad `63 10 07 D1` kopiert ebenfalls 12 Byte Device-ID;
- FC10 `63 10 00 C8` liefert 32 Byte ProductKey.

### Offen

- exakter nichtflüchtiger Speicherort und Provisionierungsweg von
  `WF2210250475` auf dem Mainboard;
- Bestätigung des vermuteten Formats `WF + YYMMDD + laufende Nummer` durch
  Vergleich mehrerer Geräte;
- Bedeutung der restlichen 84 Register des `0x07D1`-Blocks;
- Bedeutung des einzelnen Registerwerts `0x0004` und genaue Semantik des festen Reads `0x0006` auf Mainboardseite. Die Ablaufwirkung von `0x0004` ist dagegen [dynamisch bestätigt](PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md): acht 90-Register-Blöcke und rund 49 Sekunden später C544.
