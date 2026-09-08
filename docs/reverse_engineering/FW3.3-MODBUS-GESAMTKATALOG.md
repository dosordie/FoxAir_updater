# Mainboard-Firmware V3.3 – Modbus-Gesamtkatalog und Namespace-Index

Stand: 8. September 2026

Diese Datei ist der **zentrale Einstiegspunkt für alle Modbus-Register der untersuchten FoxAir-/PHNIX-Mainboard-Firmware V3.3**. Zusätzlich enthält sie klar markierte **V3.4-Nachträge**, wenn die neuere Firmware frühere offene Registersemantiken schließt oder zusätzliche Diagnose-/Limiterfunktionen bestätigt.

Sie trennt bewusst Register-Namespaces, Busrollen und Zugriffswege. Eine nackte Registernummer reicht bei dieser Anlage nicht aus – und seit den Live-Tests gilt zusätzlich: **dieselbe Registernummer kann je nach physischem/seriellen Zugriffspfad unterschiedlich erreichbar sein.**

Für die hardwarebezogenen V3.4-Erkenntnisse ist das neue Dokument [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) die autoritative Zusammenfassung.

---

# 1. Wichtigste Regel: Namespace + Slave-/Buskontext angeben

Beispiel:

```text
MAIN:2072 = öffentliche Kompressor-Istfrequenz des Regelmainboards
INV1:2102 = Remote-Register des Inverterboards, aus dem MAIN:2072 entsteht
DIAG:6040 = Engineering-/Diagnosespiegel derselben Istfrequenz
```

Daher gilt künftig in Dokumentation und Software:

```text
<Namespace>:<Register> + Bus-/Slavekontext
```

statt nur einer Zahl.

Ein aktuelles Beispiel ist `ENG:CTRL:8801`: auf dem direkten User-/Mainboard-Modbus ist es live R/W bestätigt; auf dem Warmlink-/LTE-Pfad mit Slave `0x63` ist FC03 dagegen nicht verfügbar und ein FC16-ACK beweist dort nicht, dass der echte Mainboardwert übernommen wurde.

---

# 2. Gesamte bekannte Modbus-Landschaft

| Namespace | Slave-/Buskontext | Register | Rolle | Status |
|---|---|---:|---|---|
| `MAIN:P` | direkter Mainboard/User-Slave | 1001–1540 | öffentliche Parameter | vollständig strukturell auditiert |
| `MAIN:S` | Mainboardstatus / interner Broadcast | 2001–2180 | öffentliche Laufzeit-/Statuswerte | vollständig strukturell auditiert |
| `ENG:A` | direkter Mainboard-Service/Engineeringdispatcher | 5001–5090 | Engineering-Parameter-Schatten | Rolle/RAM/RW geschlossen |
| `ENG:B` | direkter Mainboard-Service/Engineeringdispatcher | 5091–5180 | Konfig-/Synchronisationsfenster | Rolle/RAM/RW geschlossen |
| `DIAG` | direkter Mainboard-Service/Engineeringdispatcher | 6001–6090 | Live-Diagnosesnapshot | Rolle/RAM/RW geschlossen; V3.4 schließt zusätzlich 6022/6023 |
| `ENG:CTRL` | direkter Mainboard-Service/Engineeringdispatcher | 8801–8820 | Engineering-Control | **8801 live funktional geschlossen; Rest klassifiziert offen** |
| `SPECIAL` | Mainboard-Service | 60000 | Modbus-Adresse auf 1 zurücksetzen | geschlossen |
| `SPECIAL` | Mainboard-Service | 60010 | UID-gebundene Adress-Provisionierung | geschlossen |
| `INV1:TX` | interner USART3-Bus, Unit 0x01 | 1999–2014 | Verdichter-/Fan-Solltelegramm | weitgehend geschlossen; 2002=A39, 2003=C04-Profil |
| `INV1:RX` | interner USART3-Bus, Unit 0x01 | 2099–2149 | Inverter-/Fan-Telemetrie | zentrale Felder/Fehler geschlossen |
| `FAN4` | interner USART3-Bus, Unit 0x04 | 1011–1024 | separater Fan-Driver | strukturell geschlossen |
| `HMI3` | interner USART3-Bus, Unit 0x03 | 3001–3021 | DWIN/Wire-Controller | Teilnehmer/Rolle bestätigt |
| `HMI2` | interner USART3-Bus, Unit 0x02 | 3001–3021 | optionaler zweiter HMI-Kanal | Rolle sehr wahrscheinlich |
| `HYD5` | interner USART3-Bus, Unit 0x05 | 1001ff/2000ff | Hydraulik-/Erweiterungsmodul | Busrolle geschlossen, Einzelregister offen |
| `HYD61` | interner USART3-Bus, Unit 0x61 | 1001ff/2001ff | alternative H30-Modulvariante | Busrolle geschlossen |
| `WARMLINK63` | Warmlink-/LTE-RS485, Slave 0x63 | ausgewählte MAIN-/Serviceadressen | gefilterter Service-/Gatewayzugriff | **live als eigener Zugriffspfad bestätigt** |
| `OTA63` | Warmlink-/Servicepfad, Slave 0x63 | `0xCxxx` | OTA/IAP-Protokoll | separat dokumentiert |

Wichtig: `WARMLINK63` und der direkte User-/Mainboard-Modbus dürfen nicht als identische R/W-Oberfläche behandelt werden.

---

# 3. MAIN:P – öffentliche Parameter 1001–1540

Vollständiger V3.3-Audit:

[`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)

Kernpunkte:

```text
FC03: 1001–1540 lesbar
FC06: normale Parameter schreibbar, Paketköpfe geschützt
FC10: 1001–1540 technisch komplett schreibbar
```

Zentraler Modbusspiegel:

```text
0x20012788
```

Die Register werden blockweise in separate Live-Strukturen für H/A/F/D/E/R/Z/C/P/SG/Timer usw. synchronisiert.

## Paketkopfblöcke

```text
1001–1010
1091–1100
1181–1190
1271–1280
1361–1370
1451–1460
```

Softwarepolicy: **read-only**, obwohl FC10 technisch schreiben kann.

## Ende des normalen V3.3-Bereichs

```text
1540
```

`1541–1550` gehört nicht in den normalen V3.3-MAIN-Parameterdispatcher.

## SG-Ready-Quelle MAIN:1334

V3.3 besitzt zusätzlich zum bisher dokumentierten 0/1/2-Schema:

```text
1334 = 3
```

Dieser Wert aktiviert den virtuellen SG-Ready-Pfad über `ENG:CTRL:8801`.

Die Funktion ist inzwischen **Binary + live bestätigt**.

## V3.4-Nachtrag: zentrale Hardware-/Maschinenparameter

V3.4 bestätigt, dass die physische Maschinen-/Leistungsklasse nicht durch ein einzelnes „7/9/12-kW“-Register ausgewählt wird. Besonders relevant sind:

| MAIN:P | Code | Funktion | V3.4-Wirkung |
|---:|---|---|---|
| **1019** | H33 | Fan-/Compressor-Driver integriert | bestimmt Unit-1-Paketlängen 5/22 bzw. 16/51 Wörter |
| **1054** | A26 | Kältemittel-/Maschinenprofil | Parität R32/R290; voller Wert 0..7 wählt T04×T02-Referenzkennfeld |
| **1059** | F01 | Lüftermotortyp | DC-Fan-Driver-Selektion, Werte 3/4 aktiv verwendet |
| **1074** | F10 | Lüfteranzahl | Einzel-/Doppellüfter; zweiter Sollkanal |
| **1081/1083** | F18/F19 | minimale Fan-Drehzahl Kühlen/Heizen | Fan-Kennlinienuntergrenzen |
| **1089** | F23 | Nenn-Drehzahl DC/AC-Fan | Fan-Hardwarereferenz |
| **1103/1104** | F25/F26 | maximale Fan-Drehzahl Kühlen/Heizen | Fan-Kennlinienobergrenzen |
| **1220** | C03 | maximale Kompressorfrequenz | absolute obere Grundgrenze |
| **1221** | C04 | Kompressormodell | `INV1:TX:2003 = 0` oder `C04 + 0x083A`; keine lokale C04-Modelltabelle gefunden |
| **1343** | A39 | Max. Current Value | **direkt nach INV1:TX:2002** |
| **1344** | A40 | Rated Water Flow | hydraulische Nenn-/Maschinengröße |
| **1422** | – | relatives Verdichterlimit im SG-/Zusatzheizungs-Pfad | Default 70 %, **kein statischer Hardwareparameter** |

Details: [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md).

## Sensor-/Messwert-Offsets

V3.3 besitzt sieben bestätigte öffentliche additive Kalibrierparameter:

| MAIN:P | Messwert | Typ / Skalierung |
|---:|---|---|
| **1022** | Wasserdurchfluss | signed16, `0,01 m³/h` pro raw |
| **1212** | T01 Einlasswassertemperatur | signed8, `0,1 K` pro raw |
| **1213** | T02 Auslasswassertemperatur | signed8, `0,1 K` pro raw |
| **1214** | T08 Warmwasserspeicher | signed8, `0,1 K` pro raw |
| **1353** | Zone-1-Raumtemperatur | signed8, `0,1 K` pro raw |
| **1354** | Zone-2-Raumtemperatur | signed8, `0,1 K` pro raw |
| **1355** | T04 Außentemperatur | signed8, `0,1 K` pro raw |

Die sechs Temperaturwerte werden als signed Offset auf den jeweiligen Sensorwert addiert. `1022` wird als signed Durchflusskorrektur auf einen bereits gültigen Basisdurchfluss angewendet.

Details und Live-RAM-Adressen:

[`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)

## MAIN:1463 – Auswahl optionaler zweiter Außentemperaturfühler

`MAIN:1463` ist ein Quellenselektor für den aufbereiteten Außentemperaturpfad.

```text
1463 != 1
→ lokaler T04

1463 == 1 und zweiter AT-Sensor gültig
→ zweiter lokaler Außentemperatur-Thermistor

1463 == 1 und zweiter AT-Sensor ungültig
→ Fallback auf lokalen T04
```

Live-RAM:

```text
MAIN:1463 -> 0x20016278+0x55
```

Der zweite Sensor liegt bei:

```text
Temperatur   0x20015FA8+0x8A
Sensorstatus 0x20015FA8+0x8E
```

`1463` wirkt auf `MAIN:2048`, nicht auf den direkten lokalen T04-Wert `MAIN:2136`. Bei `1463=1` wird der direkte alternative Sensorwert zusätzlich als `MAIN:2033` veröffentlicht.

---

# 4. MAIN:S – öffentliche Statusregister 2001–2180

Vollständiger Audit:

[`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)

Besonders wichtige geschlossene Register:

| MAIN | Bedeutung |
|---:|---|
| 2019 Bit0 | tatsächlicher Verdichterlauf aus Inverter-Istfrequenz |
| 2019 Bit2 | mindestens ein Lüfter meldet tatsächliche Aktivität |
| **2032** | **Verdichter-Betriebsstunden; einzelner uint16-Stundenzähler** |
| **2033** | **direkter optionaler zweiter lokaler Außentemperaturfühler; bei MAIN:1463=1, raw/10 °C** |
| 2042 | Kompressor-Phasenstrom |
| 2043 | DC-Bus-Spannung |
| 2044 | IPM-Temperatur |
| 2045 | T01 Einlasswasser |
| 2046 | T02 Auslasswasser |
| **2048** | **ausgewählte und zeitlich aufbereitete wirksame Außentemperatur; Quelle über MAIN:1463** |
| 2049 | T03 Verdampfertemperatur |
| 2054 | elektrische Gesamtleistung, raw/10 kW |
| 2057 | T35 AC Input Current |
| 2059 | thermische Gesamtleistung, raw/10 kW |
| 2060 | Gesamt-COP, raw/100 |
| 2062 | T34 AC Input Voltage |
| 2071 | Kompressor-Sollfrequenz |
| 2072 | Kompressor-Istfrequenz |
| 2073 | Inverter-Maximalfrequenz |
| 2074/2075 | Lüfter-Istwerte |
| 2076 | Lüfter-Sollwert 1 / veröffentlichter Hauptsollwert |
| 2080 | Inverter-/Driver-Status aus INV1:2099 |
| 2081 | Inverter-/Driver Fault Word 1 |
| 2082 | Inverter-/Driver Fault Word 2 |
| **2133** | **tatsächlich aktiver SG-Ready-Modus 0..4** |
| **2136** | **direkter lokaler T04-Außentemperaturwert; korrigiert über MAIN:1355** |
| 2137 | reine WP-/Inverter-Eingangsleistung vor Zusatzanteil |
| 2138 | reine thermische WP-Leistung vor Zusatzanteil |
| **2139 Bit1/3/4/5/6** | bekannte Frequenzbegrenzungs-/Schutzzustände |
| **2139 Bit8** | **V3.4: SG-/Zusatzheizungs-Koordination, relatives Verdichterlimit über MAIN:1422 aktiv** |
| 2146 | Capability-/Statusbitfeld |
| **2160** | **Zone-1-Raumtemperatur; Offset MAIN:1353** |
| 2161 | Zone-2-Mischwassertemperatur |
| **2162** | **Zone-2-Raumtemperatur; Offset MAIN:1354** |
| 2163 | Mischventil-/Mischkreiswert 0…100 % |
| 2164 | Zone-1-Auslauftemperatur nach AT-Kompensation |
| 2165 | Zone-2-Auslauftemperatur nach AT-Kompensation |

Details zu `MAIN:2139`: [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md).

### MAIN:2032 / 2033 sind kein 32-Bit-Paar

```text
0x20016E88+0x00 = laufende Sekunden innerhalb der Stunde
0x20016E88+0x02 = Verdichter-Betriebsstunden → MAIN:2032
```

`2033` stammt aus dem separaten optionalen Außentemperatursensorpfad.

### Außentemperatur: 2033, 2048 und 2136 haben unterschiedliche Rollen

```text
MAIN:2136 = direkter lokaler Standard-T04 inkl. MAIN:1355 Offset
MAIN:2033 = direkter zweiter lokaler AT-Sensor bei MAIN:1463=1
MAIN:2048 = ausgewählte + gültigkeitsgeprüfte + zeitlich aufbereitete wirksame Außentemperatur
```

V3.3 baut und broadcastet tatsächlich bis **2180**.

---

# 5. ENG:A – 5001–5090

Details:

[`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)

Rolle:

```text
Engineering parameter shadow / service profile
```

RAM:

```text
5001 → 0x20015158
```

Der Block wird normal aus aktiven Liveparametern aufgebaut und kann in einem speziellen Apply-Zustand wieder in die Liveparameter zurückgeschrieben werden.

Damit ist er **zustandsändernd und sicherheitsrelevant**.

---

# 6. ENG:B – 5091–5180

RAM:

```text
5091 → 0x2001520C
```

Rolle:

```text
90-word engineering/config synchronization window
```

Bei gesetztem Requestflag wird der komplette Block per:

```text
Unit 0x63
FC10
Start 5091
Qty 90
```

weitergeleitet.

Nicht als normales User-Parameterfenster behandeln.

---

# 7. DIAG – 6001–6090

RAM:

```text
6001 → 0x200152C0
```

Direkter Mainboard-/Engineeringdispatcher:

```text
FC03 = ja
FC06 = nein
FC10 = nein
```

Rolle:

```text
live engineering diagnostic snapshot
```

Besonders nützliche bestätigte Werte:

```text
6016 = T01 Einlasswasser
6017 = T02 Auslasswasser
6019 = T04 Außentemperatur
6040 = Kompressor-Istfrequenz
6044 = Lüfter-Istwert 1
6045 = Lüfter-Istwert 2
6073ff = Low-Level-I/O-Bitfelder
6088 = Service-/Handshake-Statuswort
```

## V3.4-Nachtrag DIAG:6022/6023

V3.4 schließt zwei zusätzliche Werte im Diagnosesnapshot:

```text
DIAG:6022 = Kompressor-Istfrequenz im Maschinenprofil-Diagnosepfad
DIAG:6023 = relative Verdichterlast in %
```

Sinngemäß:

```text
DIAG:6023 ≈ MAIN:2072 / F_ref(A26,T04,T02) × 100
```

`DIAG:6023` selbst besitzt keinen nachgewiesenen internen Rückverbrauch und ist damit ein Diagnose-/Anzeigewert. Die zugrunde liegende `F_ref`-Referenzfrequenz wird jedoch für echte relative Verdichterlimits verwendet.

Details: [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md).

---

# 8. ENG:CTRL – 8801–8820

RAM:

```text
8801 → 0x20016970
```

## 8.1 8801 – virtueller SG-Ready-Zustand

Voraussetzung:

```text
MAIN:1334 == 3
```

Mapping:

```text
8801=1 → SG contacts (1,0) → Mode 1
8801=2 → SG contacts (0,0) → Mode 2
8801=3 → SG contacts (0,1) → Mode 3
8801=4 → SG contacts (1,1) → Mode 4
```

Über den direkten User-/Mainboard-Modbus ist 8801 live R/W und funktional bestätigt.

## 8.2 Fester 10-Minuten-Hold

Nach jeder tatsächlich akzeptierten SG-Modusänderung:

```text
Runtime 0x2001696C = 1200 Zyklen
1200 × 0,5 s = 10 min
```

Während des Holds kann 8801 bereits geändert werden, `MAIN:2133` bleibt jedoch auf dem zuletzt akzeptierten Modus.

## 8.3 Änderung von 1334 resettiert den Hold

Binary + live bestätigt.

## 8.4 8802–8820

R/W-Adresse im direkten Dispatcher bestätigt, direkte Laufzeitsemantik nicht geschlossen.

Softwarepolicy: **nicht generisch beschreibbar machen**.

---

# 9. Warmlink-/LTE-0x63 versus direkter User-Modbus

Auf dem Warmlink-/LTE-Bus mit Slave `0x63`:

```text
1334 lesen/schreiben -> funktioniert
2133 lesen           -> funktioniert
8801 FC03            -> Timeout
8801 FC16            -> formal korrekter ACK beobachtet, kein sicherer Cross-Bus-Apply
```

Daraus folgt:

> Die FC03/FC06/FC10-Rechte des direkten Engineeringdispatchers dürfen nicht pauschal auf den Warmlink-/LTE-0x63-Pfad übertragen werden.

---

# 10. SPECIAL – 60000 / 60010

## 60000

```text
FC06 60000
→ MAIN:1024 = 1
```

Reset der Modbus-Unit-Adresse auf 1.

## 60010

```text
FC03 60010
→ 96-Bit STM32 UID lesen

FC10 60010
→ UID-Prüfung
→ neue MAIN:1024 Unit Address übernehmen
```

UID-Quelle:

```text
0x1FFFF7E8
0x1FFFF7EC
0x1FFFF7F0
```

---

# 11. INV1 – Unit 0x01 Leistungs-/Inverterboard

Interner Bus V3.3:

```text
USART3
4800 8N1
PB10 TX
PB11 RX
PE6 DE/RE
```

H33 entscheidet:

```text
H33=0 → 5 TX-Wörter / 22 RX-Wörter
H33=1 → 16 TX-Wörter / 51 RX-Wörter
```

Reale Anlage: H33-integrierte Variante.

## TX 1999–2014

```text
1999 = Kompressor-Sollfrequenz
2000 = Run-/Mode-Wort
2002 = MAIN:1343 / A39 Max Current Value
2003 = C04-Driver-/Kompressormodellcode:
       0 bei C04=0, sonst C04 + 0x083A
2006/2007 = Fan-Driver-Selektoren bei H33
2008 = Lüfter-Soll 1
2009 = Lüfter-Soll 2
```

V3.4 bestätigt ausdrücklich:

```text
MAIN:1343 / A39
→ 0x200162D8+0x5C
→ INV1:TX:2002
```

und findet keine lokale Mainboardtabelle, die C04 selbst in konkrete Motordaten übersetzt. C04 ist aus Mainboardsicht ein weitergereichter Driverprofil-Selektor.

## RX 2099–2149

```text
2100 → MAIN:2081 Driver Fault Word 1
2102 → MAIN:2072 Kompressor-Istfrequenz
2103 → MAIN:2073 Maximalfrequenz
2105 → MAIN:2062 AC Input Voltage
2106 → MAIN:2057 AC Input Current
2107 → MAIN:2042 Compressor Phase Current
2108 → MAIN:2043 DC Bus Voltage
2109 → MAIN:2082 Driver Fault Word 2
2110 → MAIN:2044 IPM Temperature
```

Details:

[`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)

---

# 12. FAN4 – Unit 0x04 separater Fan-Driver

```text
FC03 1011–1024
14 Wörter
```

Bestätigt unter anderem:

```text
1017 → MAIN:2074 Fan actual 1
1018 → MAIN:2075 Fan actual 2
```

Der Pfad unterstützt Hardwarevarianten mit separatem Fan-Motor-Driver. In der untersuchten Anlage läuft der integrierte H33-Pfad über Unit 0x01.

---

# 13. HMI / Hydraulikmodule

## Unit 0x03

```text
FC03 3001–3021
```

Aktives DWIN-/Wire-Controller-HMI.

## Unit 0x02

Gleiche HMI-Abfrage, optionaler/zweiter HMI-Kanal.

## Unit 0x05 / 0x61

H30-gesteuerter Hydraulik-/Erweiterungsmodulpfad:

```text
H30 != 3 → Unit 0x05
H30 == 3 → Unit 0x61
```

---

# 14. OTA63 – Service-/OTA-Namespace

Der reverse-engineerte OTA-Pfad verwendet im Service-/Warmlinkkontext Register im `0xCxxx`-Bereich, unter anderem:

```text
0xC350
0xC357
0xC36C
0xC36E
0xC371
0xC378
0xC544
0xC5A8
```

Dieser Namespace gehört **nicht** in die normalen 1xxx/2xxx/5xxx/6xxx/8xxx-Registertabellen.

---

# 15. Rechteübersicht des direkten Mainboard-Dispatchers

| Namespace | Start | Ende | FC03 | FC06 | FC10 |
|---|---:|---:|---|---|---|
| MAIN:P | 1001 | 1540 | ja | ja* | ja |
| MAIN:S | 2001 | 2180 | Status/read bzw. interner Broadcast | nein als normale Userparameter | – |
| ENG:A | 5001 | 5090 | ja | ja | ja |
| ENG:B | 5091 | 5180 | ja | nein | ja |
| DIAG | 6001 | 6090 | ja | nein | nein |
| ENG:CTRL | 8801 | 8820 | ja | ja | ja |
| SPECIAL | 60000 | 60000 | nein | Sonderfunktion | nein |
| SPECIAL | 60010 | 60010 | Sonderfunktion | nein | Sonderfunktion |

\* FC06 schützt Paketköpfe.

**Diese Tabelle beschreibt den direkten Mainboard-/Engineeringdispatcher. Sie ist keine Garantie für identische Rechte über `WARMLINK63`.**

---

# 16. Stand der Architektur

Für V3.3 sind die Modbusbereiche, Dispatcherrechte, zentralen RAM-Spiegel, Boardbusrollen und wesentlichen Status-/Engineeringpfade strukturell geschlossen.

Der V3.4-Hardwareaudit ergänzt insbesondere:

- **INV1:TX:2002 = MAIN:1343 / A39 Max Current Value**
- **C04 wird als Driverprofil über INV1:TX:2003 weitergereicht; keine lokale Mainboard-Modelltabelle gefunden**
- **A26 = Kältemittel + Maschinenprofil; voller Wert 0..7 wählt ein T04×T02-Referenzfrequenzkennfeld**
- **F01/F10 sind echte Hardwarepfade für Fan-Driver-Typ und Lüfteranzahl**
- **DIAG:6023 = relative Verdichterlast gegen die A26/T04/T02-Referenzfrequenz**
- **MAIN:1422 = relatives Verdichterlimit im SG-/Zusatzheizungs-Koordinationspfad, Default 70 %**
- **MAIN:2139 Bit8 = Aktivstatus dieses relativen Limitpfads**

Diese Punkte ändern die Namespace-Architektur nicht, schließen aber mehrere zuvor offene fachliche Registersemantiken.

---

# 17. Dokumentationshierarchie

1. **Diese Datei** – Gesamtindex / Namespace-Modell
2. [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) – **Hardware-/Maschinenprofile, A26, C04, A39, Fan-Konfiguration, MAIN:1422**
3. [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
4. [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
5. [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
6. [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
7. [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
8. [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md)
9. [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
10. [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
11. [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md)
12. [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
13. [`FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md`](FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md)
14. [`FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md`](FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md)
