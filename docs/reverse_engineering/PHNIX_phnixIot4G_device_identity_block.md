# PHNIX `phnixIot4G` – Device-ID, EEPROM und Provisionierung

Stand: 2026-08-26

Diese Datei verbindet die Analyse des LTE-Dienstes `phnixIot4G` mit der
Mainboard-Firmware V3.3. Sie dokumentiert Herkunft, RAM- und EEPROM-Layout,
CRC-Schutz und den versteckten Schreibpfad der 12-Byte-Device-ID.

Untersuchtes Mainboardimage:

```text
Dateigröße: 287598 Byte
Imagebasis: 0x08050000
SHA-256:    6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
```

## 1. Ergebnis in Kurzform

- Die individuelle Kennung steht **nicht fest im V3.3-OTA-Image**.
- Ihre autoritative Laufzeitkopie beginnt bei `0x20016B50`.
- Beim Start wird ein CRC-geschützter Datensatz aus einem externen,
  24C16-kompatiblen I²C-EEPROM geladen.
- Primärer vollständiger Datensatz: EEPROM `0x03B8`.
- Boot-Fallback: EEPROM `0x03A0`.
- Die ersten sechs Wörter bilden die 12-Byte-Device-ID; zwei weitere Wörter
  werden als reservierter Paketkopf mitgeführt.
- Die vier Bytes bei Datensatzoffset `+0x10..+0x13` sind in V3.3 vollständig
  rekonstruiert: CRC-geschützte, aber semantisch ungenutzte Reservebytes.
- Ein verstecktes Warmlink-FC10-Kommando ab Register 7001 kann die acht
  Paketkopfwörter ändern; die Änderung wird anschließend im EEPROM
  persistiert.
- Die öffentlichen Register 2001–2008 und die Diagnosekopie 6001–6008 sind
  nur Lesespiegel und kein Schreibweg zur autoritativen Identität.

## 2. Öffentlicher Block ab Register 2001 / `0x07D1`

Die LTE-DTU enthält den festen Modbus-RTU-Read:

```text
63 03 07 D1 00 5A 9C FE
```

Er fordert von Slave `0x63` 90 Register ab `0x07D1` an. Bei der Antwort
`63 03 B4 ...` kopiert `uart485_get_productKey()` nur die ersten zwölf
Datenbytes in den globalen `deviceID`-Puffer:

```c
memcpy(aliMqtt_get_deviceID_buf(), &frame[3], 12);
```

Ein zweiter LTE-Empfangspfad akzeptiert `63 10 07 D1 ...` und kopiert dieselben
zwölf Bytes ab Frameoffset 7. Die folgenden 168 Bytes der 90-Register-Antwort
werden in diesem LTE-Pfad nicht semantisch ausgewertet.

Die Mainboard-Firmware baut Register 2001–2008 vollständig aus den acht
Wörtern bei `0x20016B50 + 0x00..0x0E` auf. Danach folgen die festen Kopfwerte:

```text
2009 = 0x0210
2010 = 0x07D1
```

Der gleiche Acht-Wort-Kopf wird auch in weitere 90-Register-Pakete kopiert.

## 3. Zusammensetzung der 12-Byte-ID

Die Firmware behandelt die ersten sechs Wörter als **opaque 12-Byte-Kennung**.
Sie prüft weder das Präfix `WF` noch Dezimalziffern oder ein Datumsformat.

Das folgende synthetische Beispiel ist kein Wert eines realen Geräts:

```text
WF2403150123
```

| Register | Wort | Big-Endian-ASCII |
|---:|---:|---|
| 2001 | `0x5746` | `WF` |
| 2002 | `0x3234` | `24` |
| 2003 | `0x3033` | `03` |
| 2004 | `0x3135` | `15` |
| 2005 | `0x3031` | `01` |
| 2006 | `0x3233` | `23` |

Die empirisch plausible Lesart ist:

```text
WF + YYMMDD + laufende Nummer
WF + 240315 + 0123
```

Diese Formatbedeutung ist **nicht durch die Firmware bestätigt** und muss durch
den Vergleich mehrerer Geräte abgesichert werden.

Im EEPROM liegen die 16-Bit-Wörter little-endian. Für das Beispiel lauten die
ersten zwölf physischen Bytes daher:

```text
46 57 34 32 33 30 35 31 31 30 33 32
```

## 4. Autoritative RAM-Struktur

Die V3.3-Anwendung reserviert bei `0x20016B50` 24 Byte:

| RAM-Offset | Länge | Bedeutung in V3.3 |
|---:|---:|---|
| `+0x00..+0x0B` | 12 | sechs Wörter Device-ID |
| `+0x0C..+0x0F` | 4 | zwei reservierte Paketkopfwörter |
| `+0x10..+0x13` | 4 | CRC-geschützte Reservebytes, ohne semantischen Leser/Writer |
| `+0x14..+0x15` | 2 | Modbus-CRC16 über `+0x00..+0x13`, little-endian gespeichert |
| `+0x16..+0x17` | 2 | RAM-Alignment/Padding; nicht Teil der Bootprüfung |

Die nächsten Strukturen beginnen bei `0x20016B68`. Die 24-Byte-Grenze ist
damit statisch eindeutig.

### Rekonstruktion der bisher unbekannten vier Bytes

Für `+0x10..+0x13` wurden alle direkten Referenzen auf die Struktur geprüft:

- kein Paket- oder Statusbuilder liest diese Bytes semantisch;
- kein eigener Anwendungswriter weist ihnen Werte zu;
- der 7001-Provisionierungspfad verändert sie nicht;
- sie werden nur im CRC20, im Schattenvergleich und beim Persistieren
  mitgeführt;
- wenn beide EEPROM-Datensätze ungültig sind, werden sie zusammen mit den
  übrigen 20 Nutzbytes auf null gesetzt.

Damit sind sie für **V3.3** als CRC-geschützte Reserve-/Forward-Compatibility-
Bytes klassifiziert. Das beweist nicht, dass ein Bootloader oder eine andere
Firmwareversion ihnen niemals eine Bedeutung gibt.

## 5. Externes EEPROM und Boot-Ladevorgang

Die Routinen um `0x08050C08` (Write) und `0x08050C5E` (Read) bit-bangen ein
externes I²C-EEPROM. Sie senden die Geräteadressen `0xA0`/`0xA1` und kodieren
obere Adressbits in der Slave-Adresse. Das entspricht einem
**24C16-kompatiblen EEPROM mit 2 KiB**; in 7-Bit-Schreibweise ist die
Basisadresse `0x50`.

Der Bootpfad um `0x08051106` arbeitet so:

1. 22 Byte ab EEPROM `0x03B8` lesen.
2. CRC16 über die ersten 20 Byte berechnen.
3. Mit den little-endian gespeicherten Bytes 20/21 vergleichen.
4. Bei ungültigem Datensatz 22 Byte ab `0x03A0` lesen und gleich prüfen.
5. Sind beide ungültig, die 20 Nutzbytes im RAM nullen und eine spätere
   Neupersistierung anstoßen.

| EEPROM-Bereich | Bootrolle | Laufzeitverhalten |
|---:|---|---|
| `0x03A0` | Fallback-/Factory-Slot | Laufzeitwriter aktualisiert nur die ersten 16 Byte |
| `0x03B8` | primärer, vollständiger Datensatz | Laufzeitwriter aktualisiert Nutzdaten und CRC vollständig |

Die Slots sind daher **keine symmetrischen redundanten Kopien**.

## 6. Persistenz und asymmetrischer Schreibplan

Der Änderungsdetektor vergleicht die ersten 20 Byte der Struktur gegen den
Schatten bei `0x20016B98`. Bei einer Abweichung setzt er einen Countdown von 40
und aktualisiert den Schatten. Der generische Persistenzworker berechnet die
CRC neu und schreibt in 8-Byte-Blöcken:

| Schritt | EEPROM-Ziel | RAM-Quelle | Länge |
|---:|---:|---:|---:|
| 0 | `0x03A0` | `+0x00` | 8 |
| 1 | `0x03A8` | `+0x08` | 8 |
| 2 | `0x03B8` | `+0x00` | 8 |
| 3 | `0x03C0` | `+0x08` | 8 |
| 4 | `0x03C8` | `+0x10` | 8 |

Der letzte Schritt schreibt die vier Reservebytes, die zweibyte CRC und zwei
RAM-Paddingbytes bis `0x03CF`. Beim nächsten Boot werden aus `0x03B8` nur die
22 relevanten Bytes gelesen; die beiden Paddingbytes werden ignoriert.

Folge der Asymmetrie: Nach einer Laufzeitänderung enthält `0x03A0` zwar die
ersten 16 neuen Bytes, erhält in diesem Pfad aber weder Reservebytes noch eine
passende neue CRC. Warum der Hersteller den Fallback so behandelt, ist aus
V3.3 nicht ersichtlich.

## 7. Versteckter schreibbarer Provisionierungspfad

Der separate Warmlink-/LTE-Dispatcher auf USART1, Slave `0x63`, akzeptiert für
diese Funktion exakt ein FC10-Telegramm ab **Rohregister 7001** mit **10
Wörtern**:

| Register | Erforderlicher/Inhalt |
|---:|---|
| 7001 | Marker `0x00AA` |
| 7002 | Marker `0x005A` |
| 7003–7008 | sechs neue Device-ID-Wörter |
| 7009–7010 | zwei reservierte Paketkopfwörter |

Der Dispatcher prüft Function Code, Start, Menge, Bytecount und beide Marker.
Der Applypfad kopiert danach die Wörter 7003–7010 nach
`0x20016B50 + 0x00..0x0E`. Die vier Reservebytes `+0x10..+0x13` bleiben
erhalten. Der Änderungsdetektor stößt anschließend die EEPROM-Persistierung an.

Dieser Pfad ist hochriskant: Er ändert eine geräteindividuelle, cloudnahe
Kennung und besitzt lediglich zwei konstante Marker, keine kryptographische
Authentifizierung. Er sollte in Werkzeugen nicht als generisches Schreibfenster
angeboten werden.

## 8. Was ist tatsächlich schreibbar?

| Zugriff | Ergebnis |
|---|---|
| Warmlink `0x63`, FC10, 7001, exakt 10 Wörter | autoritativer, persistenter Provisionierungspfad |
| Register 2001–2008 | öffentlicher Read-/Statusspiegel; kein normaler Schreibpfad |
| DIAG 6001–6008 | direkter Engineering-Readspiegel; read-only |
| andere Paketköpfe per generischem FC10 | höchstens Spiegeländerung; nicht autoritativ/persistent belegt |
| normales OTA-Anwendungsimage | enthält/überschreibt diesen EEPROM-Datensatz nicht |

## 9. Bedeutung für OTA und Mainboardwechsel

Der Device-ID-Datensatz liegt vor den bekannten OTA-Statusbereichen ab
`0x03D8` und außerhalb des Anwendungsimages. Ein normales V3.3-OTA transportiert
daher keine individuelle Device-ID und überschreibt sie nicht.

Bei einem Mainboardwechsel wandert die Identität mit dem EEPROM des Boards:
Ein Ersatzboard liefert grundsätzlich seinen eigenen provisionierten Wert.
ProductKey, LTE-Modem-IMEI, SIM-ICCID und Cloud-Credentials sind davon getrennte
Identitäten; die serverseitige Reaktion auf eine geänderte Board-ID ist durch
die lokale Firmwareanalyse allein nicht beweisbar.

## 10. Beweisgrad und Grenzen

### Statisch bestätigt

- RAM-Adresse und vollständiges 24-Byte-Layout;
- 20 CRC-geschützte Nutzbytes und little-endian CRC16;
- primärer EEPROM-Datensatz `0x03B8` und Fallback `0x03A0`;
- 24C16-kompatibler I²C-Zugriff;
- vollständige Klassifikation von `+0x10..+0x13` für V3.3;
- asymmetrischer 8-Byte-Schreibplan;
- 7001/10-FC10-Provisionierung mit `0x00AA`, `0x005A`;
- öffentliche und DIAG-Register sind nur Lesespiegel;
- die individuelle Kennung ist kein Literal des V3.3-OTA-Images.

### Offen

- herstellerseitige Bestätigung des Formats `WF + YYMMDD + laufende Nummer`;
- Zweck der beiden reservierten Paketkopfwörter 2007/2008;
- mögliche Bedeutung der vier Reservebytes in anderen Firmwareständen oder im
  Bootloader;
- Grund für den asymmetrischen Fallback-Schreibplan;
- serverseitige Konsequenz einer neu provisionierten Mainboard-ID;
- Bedeutung der übrigen Register des 90-Wort-Blocks jenseits des Paketkopfs.

## 11. Verwandte Dokumente

- [Identity-/ProductKey-Pfad und Mainboardwechsel](PHNIX_phnixIot4G_identity_rs485.md)
- [Warmlink-/LTE-Dispatcher Slave 0x63](FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md)
- [Service-/Engineering-Modbus-Audit](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
