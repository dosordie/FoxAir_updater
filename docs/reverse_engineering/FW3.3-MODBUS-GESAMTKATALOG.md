# Mainboard-Firmware V3.3 – Modbus-Gesamtkatalog und Namespace-Index

Stand: 24. August 2026

Diese Datei ist der **zentrale Einstiegspunkt für alle Modbus-Register der untersuchten FoxAir-/PHNIX-Mainboard-Firmware V3.3**.

Sie trennt bewusst Register-Namespaces, Busrollen und Zugriffswege. Eine nackte Registernummer reicht bei dieser Anlage nicht aus – und seit den Live-Tests gilt zusätzlich: **dieselbe Registernummer kann je nach physischem/seriellen Zugriffspfad unterschiedlich erreichbar sein.**

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
| `DIAG` | direkter Mainboard-Service/Engineeringdispatcher | 6001–6090 | Live-Diagnosesnapshot | Rolle/RAM/RW geschlossen |
| `ENG:CTRL` | direkter Mainboard-Service/Engineeringdispatcher | 8801–8820 | Engineering-Control | **8801 live funktional geschlossen; Rest klassifiziert offen** |
| `SPECIAL` | Mainboard-Service | 60000 | Modbus-Adresse auf 1 zurücksetzen | geschlossen |
| `SPECIAL` | Mainboard-Service | 60010 | UID-gebundene Adress-Provisionierung | geschlossen |
| `INV1:TX` | interner USART3-Bus, Unit 0x01 | 1999–2014 | Verdichter-/Fan-Solltelegramm | weitgehend geschlossen |
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

Vollständiger Audit:

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

---

# 4. MAIN:S – öffentliche Statusregister 2001–2180

Vollständiger Audit:

[`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)

Besonders wichtige geschlossene Register:

| MAIN | Bedeutung |
|---:|---|
| 2019 Bit0 | tatsächlicher Verdichterlauf aus Inverter-Istfrequenz |
| 2019 Bit2 | mindestens ein Lüfter meldet tatsächliche Aktivität |
| 2042 | Kompressor-Phasenstrom |
| 2043 | DC-Bus-Spannung |
| 2044 | IPM-Temperatur |
| 2045 | T01 Einlasswasser |
| 2046 | T02 Auslasswasser |
| 2048 | T04 Außentemperatur |
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
| 2136 | zweiter T04-/Außentemperaturpfad |
| 2137 | reine WP-/Inverter-Eingangsleistung vor Zusatzanteil |
| 2138 | reine thermische WP-Leistung vor Zusatzanteil |
| 2146 | Capability-/Statusbitfeld |

V3.3 baut und broadcastet tatsächlich bis **2180**.

Bei der untersuchten Anlage ist `2133` insbesondere bei eingeschalteter/aktiver WP als Live-Rückmeldung des SG-Modus relevant. Beim Umschalten greift zusätzlich der unten dokumentierte 10-Minuten-Hold.

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

in einer separaten Kommunikationsinstanz weitergeleitet.

Nicht als normales User-Parameterfenster behandeln.

Die Zahl `0x63` allein beweist dabei nicht, dass dieser interne Forwardingpfad exakt dieselbe Semantik wie jede manuelle Warmlink-/LTE-Anfrage besitzt.

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

Dieser Bereich ist für zukünftige Diagnosefunktionen in `FoxAir_Control` besonders interessant, weil er read-only ist und zusätzliche interne Zustände bereitstellt.

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

Damit besitzt MAIN:1334 den in der bisherigen Software fehlenden vierten Auswahlwert:

```text
3 = virtueller/Modbus SG-Ready-Eingang
```

### Live bestätigt

Über den direkten User-/Mainboard-Modbus:

```text
8801 initial 0
FC03 lesen -> funktioniert
0..4 schreiben -> funktioniert
Rücklesen -> funktioniert
Wert bleibt stehen
```

Die SG-Wirkung ist ebenfalls praktisch bestätigt. Unter anderem:

```text
8801=1 -> Mode 1 / Schlafmodus, WP startet nicht
8801=4 -> Mode 4 / High Power, WP startet
```

Die virtuelle SG-Steuerung ist damit praktisch geschlossen.

## 8.2 Fester 10-Minuten-Hold

Nach jeder tatsächlich akzeptierten SG-Modusänderung setzt V3.3:

```text
Runtime 0x2001696C = 0x04B0 = 1200 Zyklen
```

Die SG-Routine läuft alle ca. `0,5 s`:

```text
1200 × 0,5 s = 600 s = 10 min
```

Während des Holds:

```text
8801 kann sofort geändert werden
8801 ist sofort rücklesbar
2133 bleibt zunächst auf dem zuletzt akzeptierten Mode
```

Nach Ablauf wird der dann aktuell anliegende gewünschte SG-Zustand übernommen.

## 8.3 Änderung von 1334 resettiert den Hold

Ändert sich `MAIN:1334`, setzt V3.3 den Hold-Timer und interne Übergangszustände zurück.

Dies wurde **nicht nur im Binary rekonstruiert, sondern am 24.08.2026 live am Gerät bestätigt**.

Damit kann ein Quellenwechsel für kontrollierte Tests eine sofortige neue Modeannahme ermöglichen. Für normale Automatisierung sollte dieser Mechanismus nicht zum künstlich schnellen Umschalten missbraucht werden.

## 8.4 8802–8820

R/W-Adresse im direkten Dispatcher bestätigt, direkte V3.3-Laufzeitsemantik nicht geschlossen.

Softwarepolicy: **nicht generisch beschreibbar machen**.

---

# 9. Warmlink-/LTE-0x63 versus direkter User-Modbus

Die Live-Tests zeigen eine wichtige Zugriffspfad-Asymmetrie.

Auf dem Warmlink-/LTE-Bus mit Slave `0x63`:

```text
1334 lesen       -> funktioniert
1334 schreiben   -> funktioniert
2133 lesen       -> funktioniert
8801 FC03        -> Timeout / keine Antwort
8801 FC16        -> formal korrekter ACK beobachtet
```

Der FC16-ACK auf `8801` konnte im Cross-Bus-Gegencheck **nicht als tatsächliche Änderung des direkten User-Modbus-Registers 8801 bestätigt werden**.

Daraus folgt:

> Die FC03/FC06/FC10-Rechte des direkten Engineeringdispatchers dürfen nicht pauschal auf den Warmlink-/LTE-0x63-Pfad übertragen werden.

`WARMLINK63` ist daher als gefilterter Service-/Gatewayzugang separat zu behandeln.

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
→ 12 UID-Bytes müssen exakt zurückgesendet werden
→ danach neue MAIN:1024 Unit Address übernehmen
```

UID-Quelle:

```text
0x1FFFF7E8
0x1FFFF7EC
0x1FFFF7F0
```

Dies ist ein Provisionierungsmechanismus, keine starke Authentifizierung.

---

# 11. INV1 – Unit 0x01 Leistungs-/Inverterboard

Interner Bus:

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
2002 = MAIN:1343 / Max Current Value transportiert
2003 = Compressor Model/Driver Code aus C04
2008 = Lüfter-Soll 1
2009 = Lüfter-Soll 2
```

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
FC03
1011–1024
14 Wörter
```

Bestätigt unter anderem:

```text
1017 → MAIN:2074 Fan actual 1
1018 → MAIN:2075 Fan actual 2
```

Der Pfad unterstützt Hardwarevarianten mit separatem Fan-Motor-Driver. In der untersuchten Anlage läuft der integrierte H33-Pfad über Unit 0x01; Unit 0x04 wurde im Mitschnitt gepollt, antwortete dort aber nicht.

---

# 13. HMI / Hydraulikmodule

## Unit 0x03

```text
FC03 3001–3021
```

Aktives DWIN-/Wire-Controller-HMI. Reale Antwort enthält u.a. Softwarecode/-version.

## Unit 0x02

Gleiche HMI-Abfrage, optionaler/zweiter HMI-Kanal.

## Unit 0x05 / 0x61

H30-gesteuerter Hydraulik-/Erweiterungsmodulpfad:

```text
H30 != 3 → Unit 0x05
H30 == 3 → Unit 0x61
```

Die Busarchitektur ist geschlossen; die vollständige Einzelregistersemantik dieser Remote-Module ist für den Mainboard-Modbuskatalog nicht erforderlich.

---

# 14. OTA63 – Service-/OTA-Namespace

Der reverse-engineerte OTA-Pfad verwendet auf dem Service-/Warmlinkkontext Register im `0xCxxx`-Bereich, unter anderem:

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

Dass derselbe Slavekontext `0x63` zusätzlich ausgewählte normale Mainboardregister transportieren kann, bedeutet nicht, dass alle direkten Mainboard-Dispatcherrechte dort verfügbar sind; `8801` ist der konkrete Gegenbeweis.

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

# 16. Was bedeutet „Modbus-Thema abgeschlossen“?

Nach den Audits und Live-Tests sind für V3.3 geschlossen:

- öffentliche Parameteradressierung
- öffentliche Statusadressierung
- FC03/FC06/FC10-Rechte des direkten Mainboarddispatchers
- Paketkopf-Ausnahmen
- zentrale RAM-Spiegel
- wichtige Live-Strukturen
- interne Boardbus-Adressen
- Inverter-/Fan-Transport
- Service-/Engineering-Fenster
- Diagnosefenster
- **SG-Ready-Engineeringsteuerung über 8801, einschließlich 10-Minuten-Hold**
- **Reset des SG-Holds bei Änderung von 1334 – Binary + live bestätigt**
- **Zugriffspfad-Unterschied direkter User-Modbus versus Warmlink/LTE 0x63**
- Unit-Address-Provisionierung
- OTA-Namespace-Abgrenzung

Es bleiben einzelne fachliche Namen proprietärer/undokumentierter Rohfelder offen. Diese sind aber keine unbekannten Modbusbereiche mehr, sondern eindeutig als RAW mit Namespace, RAM-Quelle und Funktionengruppe klassifiziert.

Damit ist die **Modbus-Architektur der Mainboard-Firmware V3.3 als abgeschlossen zu betrachten**.

---

# 17. Dokumentationshierarchie

1. **Diese Datei** – Gesamtindex / Namespace-Modell
2. [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
3. [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
4. [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
5. [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
6. [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
7. [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md)
8. [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
9. [`FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md`](FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md)
10. [`FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md`](FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md)