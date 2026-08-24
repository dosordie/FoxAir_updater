# Mainboard-Firmware V3.3 – interner Modbus, Boardadressen und Servicepfade

Stand: 24. August 2026

Diese Datei dokumentiert die interne Modbus-Kommunikationsarchitektur der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3` und trennt ausdrücklich drei unterschiedliche Rollen:

1. **interner Boardbus** – Mainboard als Modbus-Master,
2. **direkter Mainboard-/User-Modbus** – Mainboard als Slave mit öffentlichem und Engineeringdispatcher,
3. **Warmlink-/LTE-Servicepfad `0x63`** – separater, gefilterter Slave-/Gatewaypfad einschließlich OTA.

Die Analyse verbindet V3.3-Binary, rekonstruierte State-Machines und reale Bus-/Funktionstests.

Untersuchtes Binary:

```text
Größe:       287598 Byte
MD5:         CEB6A4BF386FF644E23E410023E74673
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:  0x08050000
```

Bewertung:

- **bestätigt** – direkt im Binary bzw. Busverkehr geschlossen
- **live bestätigt** – zusätzlich am realen Gerät funktional verifiziert
- **sehr wahrscheinlich** – Datenfluss geschlossen, physische Herstellerbezeichnung noch offen
- **offen** – Einzelbedeutung noch nicht belastbar benannt

---

# 1. Gesamtarchitektur

```text
                         FoxAir Mainboard V3.3
                                  │
                 ┌────────────────┼─────────────────┐
                 │                │                 │
       interner Boardbus      User-Modbus      Warmlink/LTE
       USART3 / 4800 8N1      Slavepfad         USART1 / 9600
       Mainboard = Master      Mainboard=Slave    Slave 0x63
                 │                │                 │
   ┌─────────────┼───────┐        │         gefilterter Zugriff
   │             │       │        │         + Service/OTA 0xCxxx
 0x01        0x02/0x03   0x04     │
 Inverter      HMI       Fan      │
   │                              │
 0x05 / 0x61 Hydraulik           │
                                  │
                         MAIN:P 1001–1540
                         MAIN:S 2001–2180
                         ENG:A 5001–5090
                         ENG:B 5091–5180
                         DIAG 6001–6090
                         ENG:CTRL 8801–8820
                         SPECIAL 60000/60010
```

Wichtig:

> Die direkten Dispatcherrechte des User-/Mainboard-Modbus dürfen **nicht** automatisch auf den Warmlink-/LTE-Slave `0x63` übertragen werden. Der Live-Test von `8801` beweist eine registerabhängige Filterung des 0x63-Pfads.

---

# 2. Physische UART-Trennung – bestätigt

Der interne Boardring läuft über:

```text
USART3 = 0x40004800
Baud    = 4800
Format  = 8N1
TX      = PB10
RX      = PB11
DE/RE   = PE6
```

Der Warmlink-/Servicepfad läuft separat über:

```text
USART1 = 0x40013800
Baud    = 9600
Format  = 8N1
TX      = PA9
RX      = PA10
Slavekontext = 0x63
```

Damit ist die früher offene Frage, ob interner Boardring und Servicepfad auf derselben UART liegen, **geschlossen: sie sind hardwareseitig getrennt**.

Details: [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md).

---

# 3. Zentraler Modbus-Master-Builder des internen Rings

Funktion:

```text
0x080695F0
```

Argumente:

```text
r0 = Slave-Adresse
r1 = Function Code
r2 = Datenpuffer
r3 = Startregister
Stack = Anzahl Register/Wörter
```

CRC:

```text
0x0805094E
```

Der Builder gehört zum **internen USART3-Masterring** und ist nicht mit dem externen Mainboard-Slavedispatcher zu verwechseln.

---

# 4. Zyklischer interner Scheduler

State-Machine:

```text
0x08064C40 … 0x08064FC6
State: 0x20016FCE
```

| State | Slave | FC | Start | Qty | Rolle |
|---:|---:|---:|---:|---:|---|
| 0 | `0x03` | 03 | 3001 | 21 | HMI/Display lesen |
| 1 | `0x02` | 03 | 3001 | 21 | optionalen zweiten HMI-Kanal lesen |
| 2 | `0x00` | 10 | 2001 | 90 | MAIN-Status 2001–2090 broadcasten |
| 3 | `0x00` | 10 | 2091 | 90 | MAIN-Status 2091–2180 broadcasten |
| 4 | `0x04` | 03 | 1011 | 14 | separaten Fan-Driver lesen |
| 5 | `0x01` | 10 | 1999 | 5 oder 16 | Inverter/Fan-Sollwerte schreiben |
| 6 | `0x01` | 03 | 2099 | 22 oder 51 | Inverter/Fan-Telemetrie lesen |
| 7 | `0x05` | 03 | 2000 | 90 | Hydraulikmodul lesen |
| 7 alt. | `0x61` | 03 | 2001 | 90 | H30==3 alternative Variante |
| 8 | `0x05` | 10 | 1001 | 90 | Hydraulikmodul schreiben |
| 8 alt. | `0x61` | 10 | 1001 | 90 | H30==3 alternative Variante |
| 9 | – | – | – | – | Zyklusabschluss |

**Bewertung: bestätigt.**

---

# 5. Unit 0x01 – Verdichter-/Leistungs-/Inverterboard

Mainboard schreibt:

```text
Slave 0x01
FC10
Start 1999
```

und liest:

```text
Slave 0x01
FC03
Start 2099
```

Der Teilnehmer ist im realen Mitschnitt aktiv und antwortet.

## H33-Weiche

```text
Register 1019 = H33
H33 = Fan Motor Driver and Comp. Driver Integrated
```

### H33=0

```text
FC10 1999 qty5
FC03 2099 qty22
```

### H33!=0

```text
FC10 1999 qty16
FC03 2099 qty51
```

Die reale Anlage benutzt den 16/51-Wort-Pfad. Damit sind Verdichterdriver und Fan-Driver kommunikativ in Unit 0x01 integriert.

---

# 6. Unit-0x01-Sollwerte 1999–2014

Sendepuffer:

```text
0x2001232C
```

Wichtige Felder:

| INV1 | Quelle | Funktion |
|---:|---|---|
| 1999 | `0x20016AA4+0x08` | Kompressor-Sollfrequenz = MAIN:2071 |
| 2000 | Sollfrequenz + Modus | Run-/Mode-Wort 0/1/3 |
| 2001 | 0 | Reserve/noch offen |
| **2002** | `0x200162D8+0x5C` = MAIN:1343/A39 | **Maximalstrom-/Current-Limit-Vorgabe** |
| 2003 | C04 + Drivercode | Kompressor-/Driver-Modellcode |
| 2006/2007 | Fan-Konfiguration | Fan-Driver-Selektoren |
| 2008 | `0x20016F0A` | Lüfter-Sollwert 1 |
| 2009 | `0x20016F0C` | Lüfter-Sollwert 2 |
| 2010 | 0 | noch offen |

Die frühere Klassifikation von INV1:2002 als lediglich „offen“ ist damit überholt.

---

# 7. Unit-0x01-Rückmeldungen 2099–2149

RX-Livestruktur:

```text
0x200168C4
```

Wichtige Zuordnungen:

| INV1 | MAIN | Bedeutung |
|---:|---:|---|
| 2099 | 2080 | Inverter-/Driver-Statuswort, Bitsemantik offen |
| 2100 | 2081 | Driver Fault Word 1 |
| 2102 | 2072 | Kompressor-Istfrequenz |
| 2103 | 2073 | maximale Driverfrequenz |
| 2104 | 2061 | T33 / Driver-Temperaturgrenze |
| 2105 | 2062 | AC Input Voltage |
| 2106 | 2057 | T35 AC Input Current |
| 2107 | 2042 | Kompressor-Phasenstrom |
| 2108 | 2043 | DC-Bus-Spannung |
| 2109 | 2082 | Driver Fault Word 2 |
| 2110 | 2044 | IPM-Temperatur, konvertiert |
| 2113 high/low | 2026/2027 | Diagnosebytes |
| 2118 | 2028 | Diagnosewert |

Bei H33 aktiv stammen zusätzliche Fan-Rückmeldungen ebenfalls aus diesem 51-Wort-Block.

---

# 8. H33-erweiterte Fan-Kanäle über Unit 0x01

Bestätigt:

```text
INV1:2130 → 0x2001691C+0x0C → MAIN:2074 Fan actual 1
INV1:2142 → 0x2001691C+0x0E → MAIN:2075 Fan actual 2
```

Gesamtring:

```text
Mainboard-Fanregler
   ↓
0x20016F0A / 0x20016F0C
   ↓
INV1:2008 / 2009
   ↓
integrierter Fan-Driver
   ↓
INV1:2130 / 2142
   ↓
MAIN:2074 / 2075
```

---

# 9. Unit 0x04 – separater Fan-Driver-Pfad

Anfrage:

```text
Slave 0x04
FC03
Start 1011
Qty 14
```

Bestätigte Übernahmen:

```text
1017 → MAIN:2074 Fan actual 1
1018 → MAIN:2075 Fan actual 2
```

Weitere 1011–1024-Werte füllen die Fan-Driver-Livestruktur `0x2001691C`.

Im untersuchten Mitschnitt wird 0x04 gepollt, antwortet aber nicht; die reale Anlage arbeitet über den H33-integrierten Unit-0x01-Pfad.

---

# 10. Unit 0x03 / 0x02 – HMI

## Unit 0x03

```text
FC03 3001 qty21
```

Reale Antwort bestätigt u. a.:

```text
3012 = 463
3013 = 17 = V1.7
```

Damit aktiver DWIN-/Wire-Controller.

## Unit 0x02

Gleiche 3001/21-Abfrage und gleicher Kommunikationsklassenpfad; physisch sehr wahrscheinlich optionaler zweiter HMI-/Controllerkanal. Im untersuchten Mitschnitt ohne gültige Antwort.

---

# 11. Broadcast Unit 0x00

Das Mainboard veröffentlicht intern:

```text
FC10 Broadcast 2001–2090 qty90
FC10 Broadcast 2091–2180 qty90
```

Damit erhalten HMI/Controller/weitere Teilnehmer den kompletten öffentlichen Statusblock.

---

# 12. Unit 0x05 / 0x61 – Hydraulikmodule

Auswahlparameter:

```text
MAIN:1036 = H30 = Enable Hydraulic Module
```

### H30 != 3

```text
Unit 0x05
RX: FC03 2000–2089
TX: FC10 1001–1090
```

### H30 == 3

```text
Unit 0x61
RX: FC03 2001–2090
TX: FC10 1001–1090
```

Die funktionale Rolle ist bestätigt; genaue physische Modulrevisionen bleiben offen.

---

# 13. Direkter Mainboard-/User-Modbus

Der direkte Mainboard-Slavedispatcher ist vom internen Masterring getrennt.

V3.3-Bereiche:

```text
MAIN:P     1001–1540
MAIN:S     2001–2180
ENG:A      5001–5090
ENG:B      5091–5180
DIAG       6001–6090
ENG:CTRL   8801–8820
SPECIAL    60000 / 60010
```

Für den **direkten Dispatcher** sind unter anderem bestätigt:

```text
ENG:CTRL 8801–8820
FC03 yes
FC06 yes
FC10 yes
```

Diese Rechte gelten nicht automatisch für andere Proxy-/Gatewaypfade.

Details:

- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)

---

# 14. ENG:CTRL:8801 – virtueller SG-Ready-Zustand

Ein besonders wichtiger live validierter Engineeringbefehl ist:

```text
ENG:CTRL:8801
RAM 0x20016970
```

Wenn:

```text
MAIN:1334 = 3
```

wertet V3.3 `8801` als virtuelle SG-Kontakte aus:

```text
8801=1 → (1,0) → SG Mode 1
8801=2 → (0,0) → SG Mode 2
8801=3 → (0,1) → SG Mode 3
8801=4 → (1,1) → SG Mode 4
```

Am realen direkten User-Modbus bestätigt:

```text
8801 lesen            ✓
0..4 schreiben        ✓
Rücklesen             ✓
SG-Wirkung            ✓
```

Unter anderem:

```text
8801=1 → Schlafmodus; WP startet nicht
8801=4 → High-Power-Modus; WP startet
```

## 10-Minuten-Hold

Nach jeder akzeptierten SG-Modusänderung:

```text
0x2001696C = 1200
1200 × 0,5 s = 10 Minuten
```

Währenddessen kann 8801 bereits einen neuen Wert enthalten; MAIN:2133 bleibt noch auf dem vorherigen effektiven Modus.

## Hold-Reset durch MAIN:1334

Eine Änderung der SG-Quellenauswahl `MAIN:1334` setzt den 10-Minuten-Hold zurück.

**Dieser Punkt ist Binary + live am realen Gerät bestätigt.**

Details: [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md).

---

# 15. Warmlink-/LTE-Servicepfad – Slave 0x63

Der Warmlink-/LTE-Bus ist ein separater serieller Kanal auf USART1/9600.

Rollenrichtung:

```text
Warmlink/LTE bzw. externer Master
        ↓
Mainboard-Service-/Gatewaypfad Slave 0x63
```

Dieser Pfad trägt sowohl Service-/OTA-Kommunikation als auch ausgewählte normale Mainboardzugriffe.

Live bestätigt:

```text
0x63: MAIN:1334 lesen       ✓
0x63: MAIN:1334 schreiben   ✓
0x63: MAIN:2133 lesen       ✓
```

Für `8801` zeigt sich jedoch eine klare Asymmetrie:

```text
0x63 FC03 8801  → Timeout / keine Antwort
0x63 FC16 8801  → formal passender ACK
```

Der Cross-Bus-Gegencheck konnte **keine tatsächliche Änderung des echten User-Modbus-Registers 8801** durch diesen LTE-FC16-ACK bestätigen.

Daraus folgt:

> `0x63` ist kein transparenter 1:1-Proxy auf den direkten Mainboarddispatcher. Er besitzt register-/funktionsabhängige Filter- oder Gatewaylogik.

Die frühere Annahme, alle direkten Engineeringrechte seien über `0x63` identisch verfügbar, ist damit widerlegt.

---

# 16. Service-/Engineeringbereiche

Die früher noch offenen Bereiche sind inzwischen strukturell geschlossen:

```text
ENG:A    5001–5090  Engineering-Parameter-Schatten / Apply-Profil
ENG:B    5091–5180  90-Wort-Konfig-/Synchronisationsfenster
DIAG     6001–6090  read-only Engineering-Diagnosesnapshot
ENG:CTRL 8801–8820  Engineering-Control; 8801 funktional geschlossen
SPECIAL  60000      MAIN:1024 / Unit Address auf 1 zurücksetzen
SPECIAL  60010      STM32-UID-gebundene Unit-Address-Provisionierung
```

Die alte Bezeichnung eines allgemeinen Servicefensters `8001–8090` für diesen V3.3-Mainboarddispatcher ist zu verwerfen; der bestätigte Engineering-Control-Bereich ist `8801–8820`.

---

# 17. OTA-/Service-Namespace auf 0x63

Zusätzlich zu ausgewählten normalen/Servicezugriffen nutzt der Warmlink-/0x63-Pfad einen separaten `0xCxxx`-Namespace für OTA/IAP, unter anderem:

```text
0xC350 server/version
0xC357 OTA metadata
0xC36C cancel
0xC36E allow upgrade
0xC371 block ACK/progress
0xC378 rollback/init
0xC544 hardware/software info
0xC5A8 firmware block
```

Dieser OTA-Namespace darf nicht mit `MAIN:P`, `MAIN:S` oder `ENG:CTRL` zusammengelegt werden.

---

# 18. Beobachtete Teilnehmer der realen internen Anlage

| Adresse | Rolle | Anfrage | Antwort | Status |
|---:|---|---|---|---|
| `0x00` | Status-Broadcast | ja | keine vorgesehen | aktiv |
| `0x01` | Verdichter-/integriertes Antriebsboard | ja | **ja** | **aktiv** |
| `0x02` | optionaler HMI-Kanal | ja | nein | nicht antwortend |
| `0x03` | DWIN-/Wire-Controller | ja | **ja** | **aktiv** |
| `0x04` | separater Fan-Driver | ja | nein | nicht antwortend im Mitschnitt |
| `0x05` | Hydraulikpfad | ja | nicht belegt | H30-Pfad gewählt |
| `0x61` | alternative H30-Variante | nein | nein | nicht gewählt |

`0x63` gehört **nicht** in diese Tabelle des USART3-Masterzyklus; es ist der separate USART1-Service-/Warmlink-Slavepfad.

---

# 19. Diagnosemöglichkeiten

Ein passiver Mitschnitt des internen USART3-Rings kann die Boards separat überwachen.

## Unit 0x01 bei H33=1

```text
01 10 07 CF 00 10 ...   FC10 qty16
01 10 07 CF 00 10 ...   ACK
01 03 08 33 00 33 ...   FC03 qty51
01 03 66 ...             Antwort
```

## Unit 0x03

```text
03 03 0B B9 00 15 ...
03 03 2A ...
```

## Unit 0x04

```text
04 03 03 F3 00 0E ...
```

Der separate Warmlink-/LTE-Bus muss mit 9600 8N1 und eigenem Slave-/Registerkontext analysiert werden.

---

# 20. Noch offene Punkte

Die Architektur selbst ist weitgehend geschlossen. Offen bleiben vor allem Einzelbenennungen:

1. physische Board-P/N von Unit 0x01,
2. konkrete Unit-0x04-Fan-Driver-Platine und vollständige Register 1011–1024,
3. genaue Hydraulikmodulrevisionen 0x05/0x61,
4. genaue zweite HMI-Variante 0x02,
5. einzelne Unit-0x01 Run-/Mode-/Diagnosebits,
6. vollständige Filter-/Whitelistregeln des Warmlink-/LTE-0x63-Gatewaypfads.

Nicht mehr offen sind:

- interner UART/RS485-Pfad,
- physische Trennung USART3 vs USART1,
- öffentliche/Engineeringbereiche des direkten Dispatchers,
- Funktion von 60000/60010,
- Funktion von 8801,
- 10-Minuten-SG-Hold,
- Reset dieses Holds durch Änderung von 1334.

---

# 21. Verwandte Analysen

- [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)

---

# 22. Arbeitsmodell

Für jede künftige Registeranalyse ist die vollständige Kette anzugeben:

```text
Regelalgorithmus
   ↓
interne Soll-/Istvariable
   ↓
Busrolle / physischer UART
   ↓
Slave + FC + Remote-/Mainboardregister
   ↓
Producer/Consumer
   ↓
öffentliche Rückmeldung / Schutzlogik
```

Zusätzlich gilt seit den 8801-Live-Tests:

> **Ein bestätigtes Register im direkten Mainboarddispatcher ist nicht automatisch über jeden Gateway-/Servicepfad mit denselben Function Codes verfügbar.**

Damit ist die interne Boardarchitektur und ihre Abgrenzung zum User- und Warmlink-/LTE-Modbus für V3.3 strukturell abgeschlossen.