# Mainboard-Firmware V3.3 – Unit 0x01 Inverter-/Leistungsboard-Protokoll

Stand: 8. September 2026

Diese Datei dokumentiert den internen Modbus-Dialog zwischen dem PHNIX-/FoxAir-Regelmainboard V3.3 und **Unit `0x01`**, dem Verdichter-/Inverter-/Leistungsboard. Ein klar markierter V3.4-Nachtrag schließt mehrere früher offene TX-Felder und dokumentiert Versionsunterschiede der internen RAM-Adressen.

```text
Mainboard-Regelung
    ↓
TX-Register 1999…2014
    ↓
Unit 0x01
    ↓
Inverter / Verdichter / integrierter Fan-Driver
    ↓
RX-Register 2099…2149
    ↓
Mainboard-Runtime
    ↓
öffentliche Register / Fehlerwörter / Schutzlogik
```

Untersuchtes V3.3-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Größe:        287598 Byte
MD5:          CEB6A4BF386FF644E23E410023E74673
SHA-256:      6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:   0x08050000
```

V3.4-Nachtrag basiert auf:

```text
Softwarecode: 82400644
Firmware:     V3.4 / 0034
Größe:        289806 Byte
SHA-256:      97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890
Imagebasis:   0x08080000
```

Bewertung:

- **bestätigt** – direkt im jeweils genannten Binary bzw. zusätzlich im realen Mitschnitt geschlossen
- **stark bestätigt** – Binarydatenfluss plus passende PHNIX-/CC32-Protokolltabelle
- **offen** – transportiert, aber semantisch noch nicht vollständig ausgewertet

---

# 1. Kurzfazit

Für die untersuchte FoxAir gilt mit aktivem H33:

```text
Mainboard → Unit 0x01
FC10, Start 1999, 16 Wörter

Unit 0x01 → Mainboard
FC10 ACK

Mainboard → Unit 0x01
FC03, Start 2099, 51 Wörter

Unit 0x01 → Mainboard
FC03, 51 Wörter
```

H33 lautet offiziell:

```text
Fan Motor Driver and Comp. Driver Integrated
```

Damit trägt derselbe Unit-1-Dialog sowohl Verdichter- als auch Fan-Driver-Daten.

Wesentliche geschlossene Punkte:

1. **Remote 1999** = Verdichter-Sollfrequenz.
2. **Remote 2000** = Run-/Driver-Mode-Wort `0/1/3`.
3. **Remote 2002** = **MAIN:1343 / A39 Max. Current Value**; V3.4 schließt den früher offenen Namen.
4. **Remote 2003** = aus C04 „Compressor Model Selection“ abgeleiteter Driverprofilcode; real `2119` entspricht `C04=13`.
5. **Remote 2006/2007** = Fan-Driver-Selektoren aus F01.
6. **Remote 2008/2009** = Fan-Sollwerte 1/2.
7. **Remote 2100** = Driver-Fehlerwort 1 → MAIN:2081.
8. **Remote 2109** = Driver-Fehlerwort 2 → MAIN:2082.
9. **MAIN:2081 Bit15** wird lokal bei Unit-1-Kommunikationsausfall erzeugt.
10. **Remote 2110** = IPM-/Driver-Temperatur in `°C + 55` → MAIN:2044.
11. V3.3 konsumiert nur einen Teil des 51-Wort-RX-Frames; viele Felder sind Reserve/andere Driverrevisionen.

---

# 2. Kommunikationsrahmen

Interner V3.3-Bus:

```text
USART3
4800 Baud
8N1
PB10 TX
PB11 RX
PE6 RS485 DE/RE
```

Scheduler:

```text
State 5: FC10 1999, 5 oder 16 Wörter
State 6: FC03 2099, 22 oder 51 Wörter
```

H33 bestimmt die Länge:

```text
H33 = 0  → TX 5 / RX 22
H33 != 0 → TX 16 / RX 51
```

Der reale Mitschnitt zeigt die lange 16/51-Wort-Variante.

V3.4 bestätigt dieselbe Remote-Registerstruktur und dieselben H33-Paketlängen. Die Codeadressen des Schedulers sind versionsbedingt verschoben.

---

# 3. TX-Puffer V3.3

Der V3.3-Mainboard-TX-Puffer beginnt bei:

```text
0x2001232C
```

Remote-Register und Pufferoffset:

```text
1999 = +0x00
2000 = +0x02
2001 = +0x04
2002 = +0x06
2003 = +0x08
2004 = +0x0A
2005 = +0x0C
2006 = +0x0E
2007 = +0x10
2008 = +0x12
2009 = +0x14
2010 = +0x16
2011 = +0x18
2012 = +0x1A
2013 = +0x1C
2014 = +0x1E
```

Der V3.3-Aufbau liegt hauptsächlich um:

```text
0x08064D50 … 0x08064E6E
```

---

# 4. TX-Tabelle 1999–2014

| Remote-Reg. | Quelle | Funktion | Status |
|---:|---|---|---|
| **1999** | `0x20016AA4+0x08` | Verdichter-Sollfrequenz | **bestätigt V3.3/V3.4** |
| **2000** | Sollfrequenz + Driver-Mode-Selektor | Run-/Driver-Mode `0/1/3` | **bestätigt V3.3** |
| **2001** | konstant `0` | Reserve / nicht benutzt | **bestätigt V3.3** |
| **2002** | `0x200162D8+0x5C` | **MAIN:1343 / A39 Max. Current Value** | **Semantik V3.4 geschlossen** |
| **2003** | C04 + Kodierung | Kompressor-/Driver-Modellprofil | **bestätigt V3.3/V3.4** |
| 2004 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2005 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| **2006** | MAIN:1059/F01 | Fan-Driver-Selektor 1 | bestätigt bei H33 |
| **2007** | MAIN:1059/F01 | Fan-Driver-Selektor 2 | bestätigt bei H33 |
| **2008** | Fan-Sollkanal 1 | Lüfter-Sollwert 1 | **bestätigt** |
| **2009** | Fan-Sollkanal 2 | Lüfter-Sollwert 2 | **bestätigt** |
| **2010** | konstant `0` | Reserve | bestätigt |
| 2011 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2012 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2013 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2014 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |

Bei H33 werden 16 Wörter transportiert, aber nicht alle 16 sind aktive Befehle.

Realer Stillstandsmitschnitt:

```text
1999=0
2000=0
2001=0
2002=0
2003=2119
2004=0
2005=0
2006=1
2007=1
2008=0
2009=0
2010=0
2011=0
2012=0
2013=0
2014=0
```

---

# 5. Remote 1999 – Verdichter-Sollfrequenz

```text
0x20016AA4+0x08
→ MAIN:2071 / Target Compressor Frequency
→ INV1:TX:1999
```

Damit gilt:

```text
MAIN:2071 == 0 / INV1:1999 == 0
→ Mainboard fordert keinen Verdichterlauf an.
```

**Bewertung: bestätigt.**

---

# 6. Remote 2000 – Run-/Driver-Mode

V3.3 bildet:

```c
if (target_hz == 0)
    unit1_2000 = 0;
else if (driver_mode_selector_20016FBA == 0)
    unit1_2000 = 1;
else
    unit1_2000 = 3;
```

| Wert | sichere Aussage |
|---:|---|
| `0` | Stop / keine Frequenzanforderung |
| `1` | Run, Driver-Modus A |
| `3` | Run, Driver-Modus B |

Der Selektor `0x20016FBA` hängt unter anderem von H34/ERP-Testmodus, einem dynamischen Zustand, C06 und Inverter-Telemetrie ab. Ein Sonderpfad existiert bei `C06==13`.

Die genaue Unit-1-interne Bedeutung von Run-Modus 1 gegenüber 3 bleibt offen.

---

# 7. Remote 2002 – A39 / Max. Current Value

Der früher nur strukturell bekannte Pfad lautet:

```text
MAIN:1343
    ↓
0x200162D8+0x5C
    ↓
INV1:TX:2002
```

Der aktuelle FoxAir-Control-/PHNIX-Registerkatalog benennt MAIN:1343 als:

```text
A39 = Max. Current Value / Maximaler Stromwert
Typ  = AMP_X2
Unit = A
```

V3.4 bestätigt die komplette Kette direkt im Scheduler:

```text
MAIN:1343 / A39
→ 0x200162D8+0x5C
→ Remote 2002
```

Damit ist der frühere Status „Semantik offen“ überholt.

Für die Bedien-/Katalogdarstellung gilt:

```text
Ampere = RAW / 2
```

**Nicht geschlossen** ist die Empfänger-Sondersemantik eines Werts `0` auf dem Inverterboard (z. B. Driverdefault/kein externes Limit/andere Sonderbedeutung).

**Bewertung: Datenfluss und Mainboardsemantik bestätigt V3.4.**

---

# 8. Remote 2003 – C04 Kompressor-/Driver-Modellcode

Quelle:

```text
MAIN:1221 / C04
Live: 0x20016B20+0x06
Range: 0…99
```

Bildung:

```c
if (C04 != 0)
    unit1_2003 = C04 + 0x083A;   // +2106
else
    unit1_2003 = 0;
```

Realer Mitschnitt:

```text
Unit1 2003 = 2119
→ C04 = 13
```

V3.4 bestätigt denselben Pfad. Der vollständige Mainboard-Xref-Audit findet **keine lokale C04→Motordaten-/Verdichtertabelle**. Aus Sicht des Mainboards ist C04 daher ein weitergereichter **Driver-/Kompressormodell-Selektor**.

Der zulässige Bereich 0…99 beweist nicht 100 physische Verdichtermodelle. Die eigentliche Profilzuordnung sitzt sehr wahrscheinlich auf der Unit-1-Seite.

Kompatible Serviceunterlagen nennen einen falschen C04-Modellcode als möglichen Auslöser von IPM-/Compressor-Drive-Startfehlern.

**Bewertung: Transport/Transformation bestätigt; konkrete C04→Verdichtertabelle offen.**

---

# 9. Remote 2006/2007 – Fan-Driver-Selektoren / F01

Nur im H33-erweiterten Pfad.

Quelle:

```text
MAIN:1059 / F01
Live: 0x20016A04+0x00
```

V3.3/V3.4-Bildung:

```text
F01 = 3 / DC Fan Motor          → 2006=1, 2007=1
F01 = 4 / DC Fan External Drive→ 2006=2, 2007=2
sonst                          → 2006=1, 2007=1 im betrachteten Paketpfad
```

Damit ist F01 ein echter Hardware-/Driverselektor. Die Unit-1-interne Bedeutung der Selectorwerte 1/2 ist noch offen.

---

# 10. Remote 2008/2009 – Fan-Sollwerte

V3.3:

```text
2008 ← 0x20016F0A
2009 ← 0x20016F0C
```

V3.4 im entsprechenden Schedulerpfad:

```text
2008 ← 0x20016F18
2009 ← 0x20016F1A
```

Die **internen RAM-Adressen** haben sich damit zwischen V3.3 und V3.4 verschoben; die Remote-Register 2008/2009 und ihre Semantik bleiben erhalten.

Der H33-Frame enthält damit gleichzeitig:

```text
Kompressor-Sollwert
+
Compressor Run/Mode
+
A39 Maximalstrom
+
C04 Kompressormodellprofil
+
Fan-Driver-Konfiguration
+
Fan-Sollwerte 1/2
```

---

# 11. RX-Puffer und Parser

V3.3-Kommunikationspuffer:

```text
0x200112CC
```

V3.3-Unit-1-Parser ungefähr ab:

```text
0x08065C7C
```

Zentrale Runtime:

```text
0x200168C4 = Inverter/Verdichter
0x2001691C = Fan-Runtime
```

Jede gültige Unit-1-Antwort setzt den Kommunikationswatchdog `0x20016F9E` auf `0` zurück.

---

# 12. RX-Tabelle 2099–2149

Die Tabelle unterscheidet bewusst zwischen **transportiert** und **vom V3.3-Mainboard tatsächlich konsumiert**.

| Remote | V3.3-Verwendung | Mainboard-Ausgabe / Bedeutung | Status |
|---:|---|---|---|
| **2099** | → `inv+0x00` | → MAIN:2080, Herstellerprotokoll „Reserved“ | benutzt, Semantik offen |
| **2100** | → `inv+0x02` | Driver Fault Word 1 → MAIN:2081 | **bestätigt** |
| **2101** | → `inv+0x04` | intern gespeichert | benutzt, offen |
| **2102** | Low-Byte → `inv+0x06` | Kompressor-Istfrequenz → MAIN:2072 | **bestätigt** |
| **2103** | → `inv+0x08` | Max. Frequenz vom Driver → MAIN:2073 | **bestätigt** |
| **2104** | → `inv+0x0A` | T33 IPM High Fault Temp. → MAIN:2061 | **stark bestätigt** |
| **2105** | → `inv+0x0C` | T34 AC Input Voltage → MAIN:2062 | **stark bestätigt** |
| **2106** | → `inv+0x0E` | T35 AC Input Current → MAIN:2057 | **stark bestätigt** |
| **2107** | → `inv+0x10` | T36 Compressor Phase Current → MAIN:2042 | **stark bestätigt** |
| **2108** | → `inv+0x12` | T37 DC Power Bus Voltage → MAIN:2043 | **stark bestätigt** |
| **2109** | → `inv+0x14` | Driver Fault Word 2 → MAIN:2082 | **bestätigt** |
| **2110** | Low-Byte → `inv+0x16` | T38 IPM Temp. → MAIN:2044 | **bestätigt** |
| **2111** | Low-Byte → `inv+0x17` | internes Diagnosebyte | benutzt, offen |
| 2112 | nicht konsumiert | – | ignoriert |
| **2113** | → `inv+0x1E` | High-Byte → MAIN:2026, Low-Byte → MAIN:2027 | benutzt, offen |
| 2114–2117 | nicht konsumiert | – | ignoriert |
| **2118** | → `inv+0x20` | → MAIN:2028 | benutzt, offen |
| 2119–2122 | nicht konsumiert | – | ignoriert |
| **2123** | nur F01/config4 → `inv+0x28` | External Fan Driver Current → MAIN:2132 | bedingt benutzt |
| 2124–2129 | nicht konsumiert | – | ignoriert |
| **2130** | → `inv+0x18`, `fan+0x0C` | Fan 1 Istwert → MAIN:2074 | **bestätigt** |
| 2131–2132 | nicht konsumiert | – | ignoriert |
| **2133** | nur config4, High-Byte → `inv+0x2A` | Fan-Driver-Telemetrie | bedingt benutzt |
| 2134 | nicht konsumiert | – | ignoriert |
| **2135** | config4, Low-Byte → `inv+0x26` | External Fan Driver IPM Temp. → MAIN:2130 | bedingt benutzt |
| **2136** | → `fan+0x2A`; config4 zusätzlich `inv+0x24` | External Fan Driver Power → MAIN:2131 | benutzt |
| 2137–2141 | nicht konsumiert | – | ignoriert |
| **2142** | → `inv+0x1A`, `fan+0x0E` | Fan 2 Istwert → MAIN:2075 | **bestätigt** |
| 2143–2149 | nicht konsumiert | – | ignoriert |

Ein unbekanntes Wort im 51-Wort-Frame ist daher nicht automatisch ein unbekannter Mainboard-Regelparameter.

---

# 13. Reale Unit-1-Antwort im Stillstand

Beobachtet ungefähr:

```text
2099 = 0
2100 = 0
2101 = 0
2102 = 0
2103 = 0
2104 = 0
2105 = 228…230
2106 = 2
2107 = 0
2108 = 313…315
2109 = 0
2110 = 86
2111 = 0
2112 = 0
2113 = 3072 = 0x0C00
2114…2117 = 0
2118 = 14
2119…2149 = 0
```

Physikalische Plausibilisierung:

```text
2102 = 0       → Verdichter steht
2105 ≈ 229     → ~229 V AC-Eingang
2108 ≈ 313     → ~313 V DC-Zwischenkreis
2110 = 86      → 86 - 55 = 31 °C IPM-Temperatur
2113 = 0x0C00  → 2026=12, 2027=0
2118 = 14      → 2028=14
```

---

# 14. Temperaturkodierung

Für Remote 2110:

```text
T_IPM_public = (raw - 55) × 10
```

Beispiel:

```text
raw 86
→ 31 °C
→ MAIN:2044 = 310
```

Remote 2104 läuft über dasselbe Offsetprinzip in MAIN:2061; Rohwert 0 ergibt den bekannten Sentinel `-55,0 °C`.

---

# 15. Öffentliche Inverterwerte – Provenance

| MAIN | PHNIX-Name | Unit-1-Quelle |
|---:|---|---:|
| 2042 | T36 Phase Current of Compressor | 2107 |
| 2043 | T37 DC Power Bus Voltage | 2108 |
| 2044 | T38 IPM Temp. | 2110 |
| **2057** | **T35 AC Input Current** | **2106** |
| 2061 | T33 IPM High Fault Temp. | 2104 |
| **2062** | **T34 AC Input Voltage** | **2105** |
| 2072 | T31 Operation Frequency of Compressor | 2102 |
| 2073 | T32 Max. Frequency from Comp. Driver | 2103 |
| 2074 | T27 Speed of Fan Motor 1 | 2130 |
| 2075 | T28 Speed of Fan Motor 2 | 2142 |
| 2080 | offiziell Reserved | 2099 |
| **2081** | **Failure 7 / Driver Fault Word 1** | **2100 + lokales Bit15** |
| **2082** | **Failure 8 / Driver Fault Word 2** | **2109** |

Wichtig:

```text
2057 = AC Input Current
2062 = AC Input Voltage
```

---

# 16. Remote 2100 → MAIN:2081 – Driver Fault Word 1

Datenfluss:

```text
Unit1 2100
    ↓
0x200168C4+0x02
    ↓
Fehlerfilter
    ↓
0x20015E38
    ↓
öffentlicher Fehlerbuilder
    ↓
MAIN:2081
```

V3.3 führt die Bits:

```text
0, 1, 2, 5, 7, 8, 9, 10
```

jeweils durch einen generischen 3-Auswertungen-Filter.

Die Bits:

```text
3,4,6,11,12,13,14
```

bleiben im normalisierten Fehlerwort roh erhalten. Remote-Bit15 wird nicht übernommen; das Mainboard erzeugt Bit15 selbst aus dem Kommunikationswatchdog.

---

# 17. MAIN:2081-Bitbelegung

| Bit | Bedeutung | Datenpfad |
|---:|---|---|
| 0 | IPM over-current / IPM module fault | Unit1 2100, 3er-Filter |
| 1 | Compressor drive/start failure | Unit1 2100, 3er-Filter |
| 2 | Compressor over-current | Unit1 2100, 3er-Filter |
| 3 | Input voltage phase loss | roh |
| 4 | IPM current sampling failure | roh |
| 5 | Drive-board device over-temperature | 3er-Filter |
| 6 | Pre-charge failure | roh + Startup-Maske |
| 7 | DC-bus over-voltage | 3er-Filter |
| 8 | DC-bus under-voltage | 3er-Filter + Startup-Maske |
| 9 | AC input under-voltage | 3er-Filter + Startup-Maske |
| 10 | AC input over-current shutdown | 3er-Filter |
| 11 | Input-voltage sampling failure | roh |
| 12 | DSP ↔ PFC communication failure | roh |
| 13 | Drive-board temperature sensing failure | roh |
| 14 | DSP ↔ communication-board failure | roh |
| **15** | **Mainboard ↔ Unit1 communication failure** | **lokal erzeugt** |

Bei Bit0/Bit1 unterscheiden sich kompatible Handbücher sprachlich leicht; die technische Fehlerfamilie und Bitposition sind konsistent.

---

# 18. Startup-Unterdrückung für 2081 Bits 6/8/9

Startup-Zähler:

```text
0x20016F66
```

Bis `0x168 = 360` löscht V3.3 aus dem veröffentlichten 2081-Wort:

```text
Maske 0x0340
→ Bits 6, 8, 9
```

Damit werden Precharge/DC-Unterspannung/AC-Unterspannung während der ersten 360 Builder-Auswertungen unterdrückt. Es wird nicht behauptet, dass 360 direkt Sekunden bedeutet.

---

# 19. Remote 2109 → MAIN:2082 – Driver Fault Word 2

```text
Unit1 2109
→ 0x200168C4+0x14
→ 0x20015E38+2
→ MAIN:2082
```

Nur Bit0 wird von V3.3 explizit durch den 3-Auswertungen-Filter geführt; übrige Bits bleiben roh.

Kompatible Driverfamilie:

| Bit | Bedeutung |
|---:|---|
| 0 | IPM module overheat shutdown |
| 1 | Compressor phase loss |
| 2 | Reserved |
| 3 | Input current sampling failure |
| 4 | Reserved |
| 5 | Reserved |
| 6 | EEPROM failure |
| 7 | AC input over-voltage protection |
| 8–14 | Reserved |
| 15 | Compressor overspeed protection |

Reservebits werden nicht spekulativ auf spätere Driverrevisionen übertragen.

---

# 20. Unit-1-Kommunikationswatchdog

Counter:

```text
0x20016F9E
```

Sinngemäß:

```c
if (counter < 250)
    counter++;

if (counter >= 240) {
    inverter.comm_fault = 1;
    inverter.actual_hz  = 0;
} else {
    inverter.comm_fault = 0;
}
```

Jede gültige Unit-1-Antwort setzt den Counter auf 0.

Öffentliche Folge:

```text
keine gültige Unit1-Antwort
→ Watchdog >= 240
→ comm_fault = 1
→ Istfrequenz = 0
→ MAIN:2072 = 0
→ MAIN:2081 Bit15 = 1
```

Damit bedeutet MAIN:2081 Bit15 einen Kommunikationsausfall zum Leistungsboard, nicht einen vom Inverter selbst gemeldeten Motorfehler.

---

# 21. Diagnose: Warum startet der Verdichter nicht?

## Fall A – Mainboard fordert keinen Start

```text
2071 = 0
Unit1 1999 = 0
Unit1 2000 = 0
```

Ursache liegt vor dem Inverterdialog, z. B. Regelung, Limits, Schutz, Betriebsart oder Freigaben.

## Fall B – Startbefehl vorhanden, Unit1 antwortet nicht

```text
2071 > 0
Unit1 1999 > 0
Unit1 2000 = 1 oder 3
keine gültige Unit1-Antwort
```

Nach Watchdogschwelle:

```text
2081 Bit15 = 1
2072 = 0
```

→ RS485-/Versorgungs-/Leistungsboard-Kommunikationsfehler wahrscheinlich.

## Fall C – Unit1 antwortet und meldet Driverfehler

```text
Unit1 FC03 gesund
2081 != 0 oder 2082 != 0
```

Dann nennt das Driverboard die Fehlerfamilie selbst.

## Fall D – Kommunikation gesund, keine Fehler, aber 2072 bleibt 0

```text
2071 > 0
Unit1 1999 > 0
Unit1 2000 = 1/3
Kommunikation gesund
2081 = 0
2082 = 0
2072 = 0
```

Besonders interessant:

```text
Unit1 2099 / MAIN:2080
Unit1 2101
Unit1 2111
Unit1 2113 / MAIN:2026/2027
Unit1 2118 / MAIN:2028
Unit1 2000 Run-Mode
Unit1 2002 / A39 Max Current Value
Unit1 2003 / C04 Driverprofil
```

## Fall E – 2072 > 0

Dann meldet Unit1 reale Verdichterfrequenz; MAIN:2019 Bit0 wird daraus ebenfalls aktiv.

---

# 22. C04 ist für Startfehler besonders relevant

Kompatible PHNIX-Serviceunterlagen nennen bei IPM-/Compressor-Drive-Fehlern einen falschen C04 Compressor Model Code als Diagnosepunkt.

```text
C04
 ↓
INV1:TX:2003
 ↓
Driverboard
```

Für den beobachteten Profilsatz:

```text
C04 = 13
Unit1 2003 = 2119
```

Bei Austausch des Inverterboards oder Parameteränderungen ist C04 daher kritisch.

---

# 23. MAIN:2026–2028 – versteckte Inverterdiagnose

Kompatible öffentliche Tabellen führen 2026–2028 als „Reserved“, V3.3 benutzt sie jedoch:

```text
Unit1 2113 High-Byte → MAIN:2026
Unit1 2113 Low-Byte  → MAIN:2027
Unit1 2118           → MAIN:2028
```

Realer Mitschnitt:

```text
2113 = 0x0C00 → 2026=12, 2027=0
2118 = 14     → 2028=14
```

Herstellersemantik offen; für Start-/Störtests sehr interessant.

---

# 24. Unit1 2099 / MAIN:2080

```text
Unit1 2099
→ 0x200168C4+0x00
→ MAIN:2080
```

Kompatible Protokolle führen MAIN:2080 als Reserved.

Arbeitsklassifikation:

```text
2099 = versteckter Driverstatus / Diagnosewort
```

Exakte Bedeutung bleibt für dynamische Mitschnitte offen.

---

# 25. Vom V3.3-Parser nicht konsumierte 51-Wort-Felder

Aktuell nicht konsumiert:

```text
2112
2114–2117
2119–2122
2124–2129
2131–2132
2134
2137–2141
2143–2149
```

Diese Felder können auf dem Driverboard Bedeutungen haben, besitzen aber keinen nachgewiesenen Consumer in V3.3.

---

# 26. Empfohlener realer Start-Test

Mindestens loggen:

```text
TX:
1999 2000 2002 2003 2006 2007 2008 2009

RX:
2099 2100 2101 2102 2103 2104 2105 2106
2107 2108 2109 2110 2111 2113 2118 2123
2130 2133 2135 2136 2142

MAIN:
2026 2027 2028 2042 2043 2044 2057 2061
2062 2071 2072 2073 2080 2081 2082
```

Übergänge:

```text
vor Start
→ Startanforderung
→ Driver-Precharge
→ erste tatsächliche Frequenz
→ Hochlauf
→ stationärer Betrieb
→ Stop
```

---

# 27. Confidence-Matrix

## Direkt bestätigt

- Unit1 Adresse `0x01`
- FC10 1999 / FC03 2099
- H33 5/22 vs. 16/51
- komplette TX-Wortpositionen
- 1999 Sollfrequenz
- 2000 Wertebildung `0/1/3`
- **2002 ↔ MAIN:1343 / A39 Max Current Value – Semantik durch V3.4 geschlossen**
- 2003 ↔ C04 und `+2106`
- **2006/2007 ↔ MAIN:1059/F01 Fan-Driver-Selektion**
- 2008/2009 Fan-Sollwerte
- V3.4 interner Fan-Sollkanalversatz auf `0x20016F18/1A`
- gesamte RX-Offsetzuordnung
- 2102 Istfrequenz
- 2103 Maxfrequenz
- 2105/2106/2107/2108 elektrische Telemetrie
- 2110 IPM-Temperaturkodierung
- 2100 → 2081
- 2109 → 2082
- 3-Auswertungen-Filter ausgewählter Bits
- Startup-Maske 2081 Bits 6/8/9
- Unit1-Watchdog 240 Auswertungen
- lokales 2081 Bit15
- 2130/2142 Fan-Istwerte
- 2135/2136/2123 Fan-Driver-Telemetrie bei F01/config4

## Stark bestätigt durch kompatible PHNIX-/CC32-Protokolle

- T35 2057 = AC Input Current
- T33 2061 = IPM High Fault Temp.
- T34 2062 = AC Input Voltage
- 2081/2082 Driverfehler-Bitnamen
- C04 = Compressor Model Selection

## Noch offen

- exakte Driversemantik Run Mode 1 vs. 3
- Empfänger-Sondersemantik von A39=0
- konkrete C04→Verdichter-/Motortyp-Tabelle auf Unit1
- Remote 2099 / MAIN:2080
- Remote 2101
- Remote 2111
- Remote 2113 → MAIN:2026/2027
- Remote 2118 → MAIN:2028
- Bedeutung nicht konsumierter 51-Wort-Felder auf anderen Driverrevisionen

Der frühere Punkt **„Herstellername MAIN:1343 / Unit1:2002 offen“ ist geschlossen**.

---

# 28. Externe Vergleichsquellen

Die Bit-/Statusnamen wurden nur dort aus kompatiblen PHNIX-/CC32-Unterlagen übernommen, wo der Binarydatenfluss bereits eindeutig geschlossen war.

- Cooper & Hunter / PHNIX-kompatible Registertabelle, 2071–2082 einschließlich Failure 7/8:
  - https://device.report/m/cd6a7721627b82d4492897f0e9a73b9b36deaa97670dfa189e9cef108bae99dd
- SpacePak/Solstice CC32 WiFi Module Manual, Protokoll V2.1:
  - https://manuals.plus/m/72d22b68c4ae789ffbf1ed545b99cd01d3e66f24dd97bec40a6f524255f315ad_optim.pdf
- PHNIX-kompatibles Service Manual mit C04-Modellcode als Diagnosepunkt:
  - https://manuals.plus/m/5cef04381057d3d628fc04b39ec9e7e7b24238e81bf5c744fb8b38c35fd18f73

---

# 29. Verwandte Dokumente

- [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) – A26-Maschinenprofile, C04, A39, Fan-Hardware, MAIN:1422
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md)
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md)

---

# 30. Endgültiges Arbeitsmodell

```text
MAINBOARD

Regelalgorithmus
    ↓
MAIN:2071 / target Hz
    ↓
INV1:1999 target Hz
INV1:2000 Run/Mode
INV1:2002 A39 Max Current Value
INV1:2003 C04 Driver-/Compressor-Model Profile
INV1:2006/2007 F01 Fan-Driver Selector
INV1:2008/2009 Fan Target 1/2
    ↓
──────────────── RS485 ────────────────
    ↓
UNIT 0x01 LEISTUNGS-/INVERTERBOARD
    ↓
Verdichter + bei H33 integrierte Fan-Driver
    ↓
INV1:2099…2149
    ↓
──────────────── RS485 ────────────────
    ↓
2100/2109 Fehler
2102 Istfrequenz
2105 AC-Spannung
2106 AC-Strom
2107 Phasenstrom
2108 DC-Bus
2110 IPM-Temperatur
2130/2142 Fan-Istwerte
    ↓
Mainboard Runtime
    ↓
2042/2043/2044/2057/2061/2062
2072/2073/2074/2075
2080/2081/2082
2026/2027/2028 hidden diagnostics
```

Damit ist Unit `0x01` auf Mainboardseite bis auf bewusst offen gelassene Driver-interne Status-/Profilfelder weitgehend kartiert. V3.4 schließt insbesondere den früher offenen `INV1:TX:2002`-Pfad als **A39 / Max Current Value** und bestätigt C04/F01 sowie die versionsabhängigen internen Fan-Solladressen.
