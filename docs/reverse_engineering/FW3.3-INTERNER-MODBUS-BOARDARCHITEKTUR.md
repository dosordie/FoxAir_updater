# Mainboard-Firmware V3.3 – interner Modbus, Boardadressen und Servicepfade

Stand: 24. August 2026

Diese Datei dokumentiert die interne Modbus-Kommunikationsarchitektur der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3` und trennt ausdrücklich drei unterschiedliche Rollen:

1. **interner Boardbus** – Mainboard als Modbus-Master,
2. **direkter Mainboard-/User-Modbus** – Mainboard als Slave mit öffentlichem und Engineeringdispatcher,
3. **Warmlink-/LTE-Servicepfad `0x63`** – separater Slave-/Gatewaydispatcher einschließlich eigener Servicefenster und OTA.

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
       USART3 / 4800 8N1      Mainboard-Slave   USART1 / 9600
       Mainboard = Master      direkter Dispatcher Slave 0x63
                 │                │                 │
   ┌─────────────┼───────┐        │         eigener 0x63-Dispatcher
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

> Direkter User-/Mainboarddispatcher und Warmlink-`0x63`-Dispatcher besitzen **nicht dieselben Registerbereiche**. Das erklärt insbesondere, warum `8801` am User-Modbus funktioniert, auf dem LTE-/0x63-Pfad aber nicht lesbar ist.

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

Der Builder gehört zum **internen USART3-Masterring** und ist nicht mit den externen Mainboard-Slavedispatchern zu verwechseln.

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

Bestätigt:

```text
1017 → MAIN:2074 Fan actual 1
1018 → MAIN:2075 Fan actual 2
```

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

## Unit 0x02

Gleiche 3001/21-Abfrage; sehr wahrscheinlich optionaler zweiter HMI-/Controllerkanal. Im untersuchten Mitschnitt ohne gültige Antwort.

---

# 11. Broadcast Unit 0x00

Das Mainboard veröffentlicht intern:

```text
FC10 Broadcast 2001–2090 qty90
FC10 Broadcast 2091–2180 qty90
```

---

# 12. Unit 0x05 / 0x61 – Hydraulikmodule

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

---

# 13. Direkter Mainboard-/User-Modbus

Der direkte Mainboard-Slavedispatcher ist vom internen Masterring und vom Warmlink-0x63-Dispatcher zu trennen.

Bestätigte Bereiche:

```text
MAIN:P     1001–1540
MAIN:S     2001–2180
ENG:A      5001–5090
ENG:B      5091–5180
DIAG       6001–6090
ENG:CTRL   8801–8820
SPECIAL    60000 / 60010
```

Für den direkten Dispatcher:

```text
ENG:CTRL 8801–8820
FC03 yes
FC06 yes
FC10 yes
```

Details:

- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)

---

# 14. ENG:CTRL:8801 – virtueller SG-Ready-Zustand

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

Am direkten User-Modbus live bestätigt:

```text
8801 lesen       ✓
0..4 schreiben   ✓
Rücklesen        ✓
SG-Wirkung       ✓
```

Unter anderem:

```text
8801=1 → Schlafmodus; WP startet nicht
8801=4 → High-Power-Modus; WP startet
```

## 10-Minuten-Hold

```text
0x2001696C = 1200
1200 × 0,5 s = 10 Minuten
```

Währenddessen kann 8801 bereits einen neuen Wert enthalten; MAIN:2133 bleibt noch auf dem vorherigen effektiven Modus.

## Hold-Reset durch MAIN:1334

Eine Änderung der SG-Quellenauswahl `MAIN:1334` setzt den 10-Minuten-Hold zurück.

**Binary + live bestätigt.**

Details: [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md).

---

# 15. Warmlink-/LTE-Dispatcher – Slave 0x63

Der Warmlink-/LTE-Pfad besitzt eine eigene große Dispatcherfunktion ungefähr bei:

```text
0x08067548
```

Sie akzeptiert Slave:

```text
0x63
```

und teilweise Broadcast `0x00`.

Dieser Dispatcher ist **nicht identisch** mit dem direkten User-/Engineeringdispatcher.

## 15.1 FC03-Bereiche

Statisch bestätigt:

```text
1001–1540
2001–2180
8001–8090
```

jeweils mit maximal 90 Wörtern pro normalem Bereich, zusätzlich mehrere Spezialreads.

Das erklärt die Livebeobachtung exakt:

```text
0x63:1334 lesen → funktioniert, weil 1334 ∈ 1001–1540
0x63:2133 lesen → funktioniert, weil 2133 ∈ 2001–2180
0x63:8801 lesen → keine Antwort, weil 8801 in diesem FC03-Dispatcher nicht enthalten ist
```

## 15.2 FC06-Bereiche

Statisch bestätigt:

```text
1001–1540
8001–8090
```

mit eigener Parameterprüfung/Sonderlogik.

## 15.3 FC10-Bereiche

Statisch bestätigt sind mindestens:

```text
1001–1540
5091–5180
7001–7090
7091–7180
8001–8090
```

sowie die speziellen OTA-/Serviceadressen im `0xCxxx`-Bereich.

**8801–8820 ist auch im normalen FC10-Bereich dieses `0x63`-Dispatchers nicht enthalten.**

Damit fällt eine FC10-Anfrage auf `8801` in diesem rekonstruierten Handler durch, ohne dass `ENG:CTRL:8801` geschrieben wird.

## 15.4 Einordnung des beobachteten FC16-ACKs auf 8801

Im realen Warmlink-Test wurde auf eine injizierte FC16-Anfrage `0x63 / 8801 / Wert 2` ein formal passender ACK gesehen.

Der statische V3.3-`0x63`-Dispatcher verarbeitet `8801` jedoch weder in seinem normalen FC03- noch FC10-Bereich. Gleichzeitig änderte sich beim Cross-Bus-Gegencheck das echte User-Modbus-Register `8801` nicht nachweisbar.

Daher gilt jetzt präziser:

> Der beobachtete ACK kann **nicht als Beweis für einen Mainboard-Apply auf ENG:CTRL:8801** gewertet werden. Seine genaue Quelle – z. B. weiterer Proxy-/Gatewaypfad oder ein anderes Busverhalten – ist separat zu klären.

Die funktionale SG-Steuerung über `8801` ist über den direkten User-Modbus bestätigt, nicht über Warmlink-0x63.

---

# 16. Warmlink-spezifisches internes Fenster 8001–8090

Der bereits früher gefundene Block `8001–8090` bleibt gültig, ist aber jetzt korrekt einzuordnen:

> Er gehört **zum separaten Warmlink-/Service-Dispatcher `0x63`**, nicht zum direkten `ENG:CTRL:8801–8820`-Fenster.

Backing-Struktur:

```text
0x20015EF0
```

Bekannte Spiegelungen in öffentliche V3.3-Statusfelder:

```text
2151 ← Teil/Status aus 8001-Pfad
2153 ← 8002
2156 ← 8003
2154 ← 8004
2155 ← 8005
2157 ← 8007
2158 ← 8008
```

Internes 8006 besitzt eine Änderungserkennung mit einem 150-Zyklen-Timer.

Die genaue fachliche Rolle dieses Subsystems bleibt offen; Existenz, 0x63-Zugehörigkeit und RAM-Fenster sind bestätigt.

Damit existieren **zwei verschiedene 8xxx-Namespaces**:

```text
8001–8090 → Warmlink-/0x63-spezifisches internes Servicefenster
8801–8820 → direkter Mainboard-Engineering-Control-Bereich
             8801 = virtueller SG-Ready-Zustand
```

Diese dürfen nicht zusammengeführt werden.

---

# 17. Weitere Warmlink-FC10-Servicefenster

Der `0x63`-FC10-Dispatcher kennt zusätzlich:

```text
5091–5180
7001–7090
7091–7180
```

`5091–5180` ist als 90-Wort-Konfigurations-/Synchronisationsfenster bereits aus dem Engineeringaudit bekannt.

Die beiden 7xxx-Fenster sind als eigenständige Warmlink-/Service-Transferbereiche strukturell bestätigt; ihre vollständige fachliche Einzelbedeutung ist noch nicht geschlossen und sollte nicht als normaler User-Parameterbereich angeboten werden.

---

# 18. OTA-/Service-Namespace auf 0x63

Zusätzlich nutzt der `0x63`-Dispatcher spezielle `0xCxxx`-Adressen, unter anderem:

```text
0xC350
0xC357
0xC36A / weitere Status-/Steueradressen
0xC36C/0xC36E im OTA-Gesamtpfad
0xC371 ff.
0xC378 ff.
0xC544 Hardware-/Softwareinformation
0xC5A8 Firmwareblock
```

Die exakte OTA-Tabelle ist in den OTA-Dokumenten maßgeblich; wichtig für diese Architekturdatei ist die Namespace-Trennung.

---

# 19. Beobachtete Teilnehmer der realen internen Anlage

| Adresse | Rolle | Anfrage | Antwort | Status |
|---:|---|---|---|---|
| `0x00` | Status-Broadcast | ja | keine vorgesehen | aktiv |
| `0x01` | Verdichter-/integriertes Antriebsboard | ja | **ja** | **aktiv** |
| `0x02` | optionaler HMI-Kanal | ja | nein | nicht antwortend |
| `0x03` | DWIN-/Wire-Controller | ja | **ja** | **aktiv** |
| `0x04` | separater Fan-Driver | ja | nein | nicht antwortend im Mitschnitt |
| `0x05` | Hydraulikpfad | ja | nicht belegt | H30-Pfad gewählt |
| `0x61` | alternative H30-Variante | nein | nein | nicht gewählt |

`0x63` gehört **nicht** in diesen USART3-Masterzyklus; es ist der separate USART1-Warmlink-/Service-Slavepfad.

---

# 20. Diagnosemöglichkeiten

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

Der separate Warmlink-/LTE-Bus muss mit 9600 8N1 und eigenem `0x63`-Registerkontext analysiert werden.

---

# 21. Noch offene Punkte

Offen bleiben vor allem Einzelbenennungen:

1. physische Board-P/N von Unit 0x01,
2. konkrete Unit-0x04-Fan-Driver-Platine,
3. genaue Hydraulikmodulrevisionen 0x05/0x61,
4. genaue zweite HMI-Variante 0x02,
5. einzelne Unit-0x01 Run-/Mode-/Diagnosebits,
6. vollständige Semantik von Warmlink `8001–8090`,
7. vollständige Semantik der Warmlink-FC10-Fenster `7001–7180`,
8. genaue Quelle des im Realtest gesehenen FC16-ACKs auf nicht unterstütztes `0x63:8801`.

Nicht mehr offen sind:

- interner UART/RS485-Pfad,
- physische Trennung USART3 vs USART1,
- direkte Mainboard-/Engineeringbereiche,
- Funktion von 60000/60010 im direkten Dispatcher,
- Funktion von 8801,
- 10-Minuten-SG-Hold,
- Reset dieses Holds durch Änderung von 1334,
- Grund, warum `0x63` FC03 auf 8801 nicht antwortet.

---

# 22. Verwandte Analysen

- [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)

---

# 23. Arbeitsmodell

Für jede künftige Registeranalyse ist die vollständige Kette anzugeben:

```text
Regelalgorithmus
   ↓
interne Soll-/Istvariable
   ↓
Busrolle / physischer UART
   ↓
Dispatcher
   ↓
Slave + FC + Remote-/Mainboardregister
   ↓
Producer/Consumer
   ↓
öffentliche Rückmeldung / Schutzlogik
```

Zusätzlich gilt seit den 8801-Live-Tests:

> **Gleiche oder ähnliche Registerzahlen in verschiedenen Dispatchern sind eigenständige Namespaces. Ein bestätigtes Register im direkten Mainboarddispatcher ist nicht automatisch auf Warmlink-0x63 verfügbar.**

Damit ist die interne Boardarchitektur und ihre Abgrenzung zum User- und Warmlink-/LTE-Modbus für V3.3 deutlich präziser geschlossen.