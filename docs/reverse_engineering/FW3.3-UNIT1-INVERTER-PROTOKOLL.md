# Mainboard-Firmware V3.3 – Unit 0x01 Inverter-/Leistungsboard-Protokoll

Stand: 24. August 2026

Diese Datei dokumentiert den internen Modbus-Dialog zwischen dem PHNIX-/FoxAir-Regelmainboard V3.3 und **Unit `0x01`**, dem Verdichter-/Inverter-/Leistungsboard. Ziel ist nicht nur ein Registerdump, sondern eine vollständige Provenance:

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

Untersuchtes Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Größe:        287598 Byte
MD5:          CEB6A4BF386FF644E23E410023E74673
SHA-256:      6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:   0x08050000
```

Bewertung:

- **bestätigt** – direkt im Binary bzw. zusätzlich im realen Mitschnitt geschlossen
- **stark bestätigt** – Binarydatenfluss plus passende PHNIX-/CC32-Protokolltabelle
- **offen** – transportiert, aber von V3.3 nicht semantisch ausgewertet

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

Die wichtigsten neuen Ergebnisse:

1. **Remote 1999** ist die Verdichter-Sollfrequenz.
2. **Remote 2000** ist ein Run-/Driver-Mode-Wort `0/1/3`.
3. **Remote 2002** spiegelt Mainboard-Register **1343**; dessen Herstellername bleibt offen.
4. **Remote 2003** ist aus C04 „Model Selection“ abgeleitet; real `2119` bedeutet bei V3.3 `C04=13`.
5. **Remote 2100** ist Driver-Fehlerwort 1 und wird zu öffentlichem **2081**.
6. **Remote 2109** ist Driver-Fehlerwort 2 und wird zu öffentlichem **2082**.
7. **2081 Bit15** stammt nicht aus Remote 2100, sondern wird lokal bei Unit-1-Kommunikationsausfall erzeugt.
8. Der Mainboardcode entprellt ausgewählte Driverfehler über drei Auswertungen.
9. **Remote 2110** ist die reale IPM-/Driver-Temperatur in `°C + 55` und wird zu Mainboard **2044**.
10. Die V3.3 konsumiert nur einen Teil der 51 Remote-Wörter; viele sind echte Reserve-/andere Driver-Revision-Felder.

---

# 2. Kommunikationsrahmen

Der interne Scheduler benutzt:

```text
USART3
4800 Baud
8N1
PB10 TX
PB11 RX
PE6 RS485 DE/RE
```

Unit-1-Schedulerzustände:

```text
State 5: FC10 1999, 5 oder 16 Wörter
State 6: FC03 2099, 22 oder 51 Wörter
```

Die Länge wird durch H33 bestimmt:

```text
H33 = 0  → TX 5 / RX 22
H33 != 0 → TX 16 / RX 51
```

Der reale Mitschnitt zeigt die lange 16/51-Wort-Variante.

---

# 3. TX-Puffer

Der Mainboard-TX-Puffer beginnt bei:

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

Der Aufbau liegt hauptsächlich im Schedulerbereich um:

```text
0x08064D50 … 0x08064E6E
```

---

# 4. Vollständige TX-Tabelle 1999–2014

| Remote-Reg. | Quelle | Funktion | V3.3 |
|---:|---|---|---|
| **1999** | `0x20016AA4+0x08` | Verdichter-Sollfrequenz | **bestätigt** |
| **2000** | Sollfrequenz + `0x20016FBA` | Run-/Driver-Mode `0/1/3` | **bestätigt** |
| **2001** | konstant `0` | Reserve / nicht benutzt | **bestätigt** |
| **2002** | `0x200162D8+0x5C` | Mainboard-Reg. 1343, Herstellername offen | **bestätigt** |
| **2003** | C04 + Kodierung | Kompressor-/Driver-Modellcode | **bestätigt** |
| 2004 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2005 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| **2006** | Fan-Konfiguration | Fan-Driver-Selektor 1 | bestätigt bei H33 |
| **2007** | Fan-Konfiguration | Fan-Driver-Selektor 2 | bestätigt bei H33 |
| **2008** | `0x20016F0A` | Lüfter-Sollwert 1 | **bestätigt** |
| **2009** | `0x20016F0C` | Lüfter-Sollwert 2 | **bestätigt** |
| **2010** | konstant `0` | Reserve | bestätigt |
| 2011 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2012 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2013 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |
| 2014 | nicht aktiv geschrieben | Reserve/Legacy | bestätigt |

Wichtig:

> Die Tatsache, dass bei H33 16 Wörter übertragen werden, bedeutet nicht, dass alle 16 Register aktive Befehle sind. V3.3 baut nur die oben markierten Felder aktiv auf.

Im realen Stillstandsmitschnitt sieht der Block aus wie:

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

Die finale Mainboard-Sollfrequenz liegt bei:

```text
0x20016AA4 + 0x08
```

und wird öffentlich als:

```text
Mainboard 2071 = Target Compressor Frequency
```

bereitgestellt.

Genau dieser Wert wird nach Unit-1-Register 1999 geschrieben:

```text
Kompressorregler
    ↓
0x20016AA4+8
    ↓
Mainboard 2071
    ↓
Unit1 1999
```

Damit ist für die Diagnose eindeutig:

```text
2071 == 0 / Unit1 1999 == 0
→ Mainboard fordert keinen Verdichterlauf an.
```

---

# 6. Remote 2000 – Run-/Driver-Mode

Die Bildung ist bytegenau:

```c
if (target_hz == 0)
    unit1_2000 = 0;
else if (driver_mode_selector_20016FBA == 0)
    unit1_2000 = 1;
else
    unit1_2000 = 3;
```

Damit:

| Wert | sichere Aussage |
|---:|---|
| `0` | Stop / keine Frequenzanforderung |
| `1` | Run, Driver-Modus A |
| `3` | Run, Driver-Modus B |

Die exakte Herstellerbezeichnung der Modi `1` und `3` wurde nicht gefunden und wird deshalb nicht erfunden.

## 6.1 Woher kommt `0x20016FBA`?

Der Writer liegt ungefähr bei:

```text
0x0808438C … 0x0808443A
```

Der Selektor hängt unter anderem von:

- H34 / ERP Testing Mode,
- dem dynamischen internen Zustand `0x20016FB7`,
- C06,
- Inverter-Telemetrie,

ab.

C06 liegt bei:

```text
0x20016B20 + 0x0A
```

und ein besonderer Pfad wird bei:

```text
C06 == 13
```

aktiv.

Die sichere funktionale Benennung lautet daher:

```text
0x20016FBA = dynamischer Compressor-Driver-Mode-Selektor
```

**Nicht geschlossen:** was Unit `0x01` intern bei Run-Modus 1 gegenüber 3 exakt anders macht.

---

# 7. Remote 2002 – Spiegel von Mainboard 1343

Quelle:

```text
0x200162D8 + 0x5C
```

Der Wert wird aus dem zentralen Parameter-/Kommunikationsbereich übernommen und zusätzlich in den öffentlichen Parameter-Mirror kopiert.

Die Mirror-Arithmetik ergibt:

```text
0x20012788 + 0x694
→ Mainboard-Register 1343
```

Somit gilt:

```text
Mainboard 1343
    ↓
0x200162D8+0x5C
    ↓
Unit1 2002
```

Die bekannte PHNIX-/CC32-Protokolltabelle benennt 1343 nicht, und auch im Repository existiert bislang kein belastbarer Name.

**Bewertung:** Mapping bestätigt, Semantik offen.

---

# 8. Remote 2003 – Kompressor-/Driver-Modellcode

Quelle ist:

```text
C04 = 0x20016B20 + 0x06
Mainboard-Register 1221
```

Offizielle C04-Bezeichnung in kompatiblen PHNIX-Unterlagen:

```text
C04 = Model Selection / Compressor model selection
Range 0…99
```

V3.3 bildet:

```c
if (C04 != 0)
    unit1_2003 = C04 + 0x083A;   // +2106
else
    unit1_2003 = 0;
```

Im realen Mitschnitt:

```text
Unit1 2003 = 2119
```

also:

```text
C04 = 2119 - 2106 = 13
```

Für die konkrete Anlage ist damit **C04 = 13** direkt aus dem internen Drivertelegramm rekonstruierbar.

Serviceunterlagen bestätigen außerdem, dass ein falscher C04-Modellcode typische Ursachen für IPM-/Compressor-Drive-Startfehler sein kann.

---

# 9. Remote 2006/2007 – Fan-Driver-Selektoren

Nur im H33-erweiterten Pfad.

Aus dem Fan-Konfigurationswert `0x20016A04[0]` bildet die Firmware:

```text
Fan config 3 → 2006=1, 2007=1
Fan config 4 → 2006=2, 2007=2
sonst        → 2006=1, 2007=1
```

Die exakte Driver-interne Bedeutung `1/2` ist offen.

---

# 10. Remote 2008/2009 – Fan-Sollwerte

```text
2008 ← 0x20016F0A
2009 ← 0x20016F0C
```

Das sind die beiden bereits vollständig rekonstruieren Lüfter-Sollkanäle.

Damit enthält der H33-Frame tatsächlich gleichzeitig:

```text
Kompressor-Sollwert
+
Compressor Run/Mode
+
Kompressormodell
+
Fan-Driver-Konfiguration
+
Fan-Sollwerte 1/2
```

---

# 11. RX-Puffer und Parser

Die Unit-1-Antwort beginnt im Kommunikationspuffer bei:

```text
0x200112CC
```

Der Unit-1-Parser liegt ungefähr ab:

```text
0x08065C7C
```

Die zentrale Inverter-Runtime ist:

```text
0x200168C4
```

Die Fan-Runtime ist:

```text
0x2001691C
```

Nach jeder gültigen Unit-1-Antwort wird außerdem der Unit-1-Kommunikationswatchdog:

```text
0x20016F9E
```

auf `0` zurückgesetzt.

---

# 12. Vollständige RX-Tabelle 2099–2149

Die Tabelle unterscheidet bewusst zwischen **transportiert** und **von V3.3 tatsächlich konsumiert**.

| Remote | V3.3-Verwendung | Mainboard-Ausgabe / Bedeutung | Status |
|---:|---|---|---|
| **2099** | → `inv+0x00` | → Mainboard 2080, Herstellerprotokoll dort „Reserved“ | benutzt, Semantik offen |
| **2100** | → `inv+0x02` | Driver Fault Word 1 → 2081 | **bestätigt** |
| **2101** | → `inv+0x04` | intern gespeichert, Bedeutung offen | benutzt |
| **2102** | Low-Byte → `inv+0x06` | Kompressor-Istfrequenz → 2072 | **bestätigt** |
| **2103** | → `inv+0x08` | Max. Frequenz vom Driver → 2073 | **bestätigt** |
| **2104** | → `inv+0x0A` | T33 IPM High Fault Temp. → 2061 | **stark bestätigt** |
| **2105** | → `inv+0x0C` | T34 AC Input Voltage → 2062 | **stark bestätigt** |
| **2106** | → `inv+0x0E` | T35 AC Input Current → 2057 | **stark bestätigt** |
| **2107** | → `inv+0x10` | T36 Compressor Phase Current → 2042 | **stark bestätigt** |
| **2108** | → `inv+0x12` | T37 DC Power Bus Voltage → 2043 | **stark bestätigt** |
| **2109** | → `inv+0x14` | Driver Fault Word 2 → 2082 | **bestätigt** |
| **2110** | Low-Byte → `inv+0x16` | T38 IPM Temp. → 2044 | **bestätigt** |
| **2111** | Low-Byte → `inv+0x17` | internes Diagnosebyte, Name offen | benutzt |
| 2112 | nicht konsumiert | – | ignoriert |
| **2113** | → `inv+0x1E` | High-Byte → 2026, Low-Byte → 2027 | benutzt, Name offen |
| 2114 | nicht konsumiert | – | ignoriert |
| 2115 | nicht konsumiert | – | ignoriert |
| 2116 | nicht konsumiert | – | ignoriert |
| 2117 | nicht konsumiert | – | ignoriert |
| **2118** | → `inv+0x20` | → Mainboard 2028 | benutzt, Name offen |
| 2119 | nicht konsumiert | – | ignoriert |
| 2120 | nicht konsumiert | – | ignoriert |
| 2121 | nicht konsumiert | – | ignoriert |
| 2122 | nicht konsumiert | – | ignoriert |
| **2123** | nur Fan config 4 → `inv+0x28` | External Fan Driver Current → public 2132 | bedingt benutzt |
| 2124 | nicht konsumiert | – | ignoriert |
| 2125 | nicht konsumiert | – | ignoriert |
| 2126 | nicht konsumiert | – | ignoriert |
| 2127 | nicht konsumiert | – | ignoriert |
| 2128 | nicht konsumiert | – | ignoriert |
| 2129 | nicht konsumiert | – | ignoriert |
| **2130** | → `inv+0x18`, `fan+0x0C` | Fan 1 Istwert → public 2074 | **bestätigt** |
| 2131 | nicht konsumiert | – | ignoriert |
| 2132 | nicht konsumiert | – | ignoriert |
| **2133** | nur Fan config 4, High-Byte → `inv+0x2A` | Teil der Fan-Driver-Telemetrie | bedingt benutzt |
| 2134 | nicht konsumiert | – | ignoriert |
| **2135** | nur Fan config 4, Low-Byte → `inv+0x26` | External Fan Driver IPM Temp. → public 2130 | bedingt benutzt |
| **2136** | → `fan+0x2A`; bei config4 zusätzlich `inv+0x24` | External Fan Driver Power → public 2131 | benutzt |
| 2137 | nicht konsumiert | – | ignoriert |
| 2138 | nicht konsumiert | – | ignoriert |
| 2139 | nicht konsumiert | – | ignoriert |
| 2140 | nicht konsumiert | – | ignoriert |
| 2141 | nicht konsumiert | – | ignoriert |
| **2142** | → `inv+0x1A`, `fan+0x0E` | Fan 2 Istwert → public 2075 | **bestätigt** |
| 2143 | nicht konsumiert | – | ignoriert |
| 2144 | nicht konsumiert | – | ignoriert |
| 2145 | nicht konsumiert | – | ignoriert |
| 2146 | nicht konsumiert | – | ignoriert |
| 2147 | nicht konsumiert | – | ignoriert |
| 2148 | nicht konsumiert | – | ignoriert |
| 2149 | nicht konsumiert | – | ignoriert |

Damit ist wichtig:

> Ein unbekanntes Wort im 51-Wort-Frame ist nicht automatisch ein unbekannter V3.3-Regelparameter. Viele Wörter werden zwar übertragen, von dieser Mainboardversion aber überhaupt nicht gelesen.

---

# 13. Reale Unit-1-Antwort im Stillstand

Im vorhandenen Mitschnitt erscheinen wiederholt ungefähr:

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

Das validiert mehrere Zuordnungen direkt physikalisch:

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

Für Remote 2110 wird im Mainboard gerechnet:

```text
T_IPM_public = (raw - 55) × 10
```

Damit:

```text
raw 86
→ 31 °C
→ public 2044 = 310
```

Das stimmt exakt mit dem beobachteten Hauptstatus überein.

Remote 2104 läuft über dasselbe Offsetprinzip in den öffentlichen T33-Wert 2061. Ein Rohwert 0 führt dort zur bekannten Sentinelanzeige:

```text
-55.0 °C
```

---

# 15. Öffentliche Inverterwerte – korrigierte Provenance

| Mainboard-Reg. | PHNIX-Name | Unit-1-Quelle |
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

Damit ist eine alte lokale Monitorbezeichnung zu korrigieren:

```text
2057 ≠ AC Input Voltage
2057 = AC Input Current
2062 = AC Input Voltage
```

---

# 16. Remote 2100 → Mainboard 2081: Driver Fault Word 1

Der Datenfluss ist geschlossen:

```text
Unit1 2100
    ↓
0x200168C4+0x02
    ↓
Fehlerfilter 0x080882E2ff
    ↓
0x20015E38
    ↓
öffentlicher Fehlerbuilder
    ↓
Mainboard 2081
```

## 16.1 Welche Bits werden entprellt?

V3.3 führt folgende Bits einzeln durch den generischen Fehlerfilter `0x08088208`:

```text
0
1
2
5
7
8
9
10
```

Der Filter wird jeweils mit:

```text
r2 = 3
r3 = 0
```

aufgerufen.

Damit müssen diese Zustände über **drei aufeinanderfolgende Auswertungen** qualifizieren, bevor der gefilterte Fehlerzustand übernommen wird.

Es wird bewusst nicht „3 Sekunden“ behauptet; hier ist nur die Anzahl der Auswertungen bytegenau bewiesen.

Die Bits:

```text
3, 4, 6, 11, 12, 13, 14
```

bleiben im normalisierten Fehlerwort roh erhalten.

Remote-Bit 15 wird später nicht übernommen; siehe Kommunikationswatchdog.

---

# 17. 2081-Bitbelegung

Eine zur PHNIX-/CC32-Registerfamilie passende öffentliche Protokolltabelle beschreibt **exakt Mainboard-Register 2081** mit folgender Belegung. Da das Binary bestätigt, dass dieses Wort aus Unit1-2100 aufgebaut wird, ist die Zuordnung sehr stark.

| Bit | Bedeutung | Binarypfad |
|---:|---|---|
| 0 | IPM over-current / IPM module fault | aus Unit1 2100, 3er-Filter |
| 1 | Compressor drive/start failure | aus Unit1 2100, 3er-Filter |
| 2 | Compressor over-current | aus Unit1 2100, 3er-Filter |
| 3 | Input voltage phase loss | roh aus Unit1 2100 |
| 4 | IPM current sampling failure | roh |
| 5 | Drive-board device over-temperature | 3er-Filter |
| 6 | Pre-charge failure | roh, zusätzlich Startup-Maske |
| 7 | DC-bus over-voltage | 3er-Filter |
| 8 | DC-bus under-voltage | 3er-Filter + Startup-Maske |
| 9 | AC input under-voltage | 3er-Filter + Startup-Maske |
| 10 | AC input over-current shutdown | 3er-Filter |
| 11 | Input-voltage sampling failure | roh |
| 12 | DSP ↔ PFC communication failure | roh |
| 13 | Drive-board temperature sensing failure | roh |
| 14 | DSP ↔ communication-board failure | roh |
| **15** | **Mainboard ↔ Unit1 communication failure** | **lokal erzeugt, nicht aus Unit1 Bit15** |

Hinweis zur Übersetzung:

Bei Bit0/Bit1 unterscheiden sich kompatible Handbücher sprachlich leicht zwischen „IPM overheat/over-current“ und „compressor drive/start failure“. Die technische Fehlerfamilie und Bitposition sind jedoch konsistent. Für genaue Servicecodes ist die jeweilige Driverrevision zu beachten.

---

# 18. Startup-Unterdrückung für 2081 Bits 6/8/9

Der öffentliche Fehlerbuilder besitzt einen Startup-Zähler bei:

```text
0x20016F66
```

Bis zum Wert:

```text
0x168 = 360
```

löscht V3.3 aus dem zu veröffentlichenden 2081-Wort die Maske:

```text
0x0340
```

also:

```text
Bit 6  Pre-charge failure
Bit 8  DC bus under-voltage
Bit 9  AC input under-voltage
```

Diese drei Fehler werden damit während der ersten **360 Builder-Auswertungen** unterdrückt.

Das verhindert erwartbare Einschalt-/Zwischenkreiszustände als sofort sichtbare Fehler.

**Nicht behauptet:** dass 360 direkt Sekunden bedeutet.

---

# 19. Remote 2109 → Mainboard 2082: Driver Fault Word 2

Datenfluss:

```text
Unit1 2109
    ↓
0x200168C4+0x14
    ↓
0x20015E38+2
    ↓
Mainboard 2082
```

Nur **Bit0** wird von V3.3 explizit über den 3-Auswertungen-Filter geführt. Die übrigen Bits des Wortes bleiben roh erhalten.

Eine kompatible CC32-Protokolltabelle benennt 2082:

| Bit | Bedeutung in dieser Driverfamilie |
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

Da verschiedene Inverterrevisionen einige „Reserved“-Bits später anders belegen können, werden nur die oben dokumentierten Family-Namen übernommen und nicht auf unbestätigte V3.3-Zustände extrapoliert.

---

# 20. Unit-1-Kommunikationswatchdog

Der direkte Watchdog liegt ungefähr bei:

```text
0x0805DAE4 … 0x0805DB24
```

Counter:

```text
0x20016F9E
```

Logik:

```c
if (counter < 250)
    counter++;

if (counter >= 240) {
    inverter.comm_fault = 1;  // 0x200168C4+0x22
    inverter.actual_hz  = 0;  // 0x200168C4+0x06
} else {
    inverter.comm_fault = 0;
}
```

Jede gültige Unit-1-Antwort setzt:

```text
0x20016F9E = 0
```

zurück.

Der öffentliche Fehlerbuilder verwendet anschließend:

```text
0x200168C4 + 0x22
```

für:

```text
2081 Bit15
```

Damit ist die gesamte Kette bestätigt:

```text
keine gültige Unit1-Antwort
      ↓
Watchdog 0x20016F9E steigt
      ↓
>= 240 Auswertungen
      ↓
comm_fault = 1
actual_hz = 0
      ↓
2072 = 0
2081 Bit15 = 1
```

Das ist eine sehr wertvolle Diagnosemöglichkeit:

> **2081 Bit15 bedeutet in V3.3 tatsächlich Kommunikationsausfall zum Verdichter-/Leistungsboard und nicht einen vom Inverter selbst gemeldeten Motorfehler.**

---

# 21. Diagnose: Warum startet der Verdichter nicht?

Mit dem jetzt geschlossenen Datenfluss kann man Fälle sauber auseinanderhalten.

## Fall A – Mainboard fordert gar keinen Start

```text
2071 = 0
Unit1 1999 = 0
Unit1 2000 = 0
```

Dann liegt die Ursache **vor** dem Inverterdialog:

- normale Regelung fordert keinen Verdichter,
- Mindest-/Maximalgrenzen,
- Schutz-/Sperrzustand,
- Abtau-/Betriebsartenlogik,
- externe Freigaben usw.

Das Leistungsboard „verweigert“ hier nichts; es bekommt schlicht keinen Startbefehl.

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

→ **RS485-/Versorgungs-/Leistungsboard-Kommunikationsfehler.**

Zu prüfen:

- Unit-1-Boardversorgung,
- USART3/RS485 A/B,
- Transceiver,
- Steckverbindungen,
- Driverboard MCU.

## Fall C – Unit1 antwortet, meldet aber Driverfehler

```text
Unit1 FC03 läuft sauber
2081 != 0 oder 2082 != 0
```

Dann ist das Driverboard erreichbar und nennt selbst die Ursache.

Beispiele:

```text
2081 bit1 → Compressor drive/start failure
2081 bit2 → Compressor over-current
2081 bit5 → Driver-board over-temperature
2081 bit6 → Pre-charge failure
2081 bit7 → DC-bus over-voltage
2081 bit8 → DC-bus under-voltage
2081 bit9 → AC input under-voltage
2082 bit0 → IPM overheat shutdown
2082 bit1 → compressor phase loss
2082 bit6 → EEPROM failure
2082 bit15 → compressor overspeed
```

## Fall D – Unit1 antwortet, keine Fehler, aber 2072 bleibt 0

```text
2071 > 0
Unit1 1999 > 0
Unit1 2000 = 1/3
Kommunikation gesund
2081 = 0
2082 = 0
2072 = 0
```

Dann ist das Leistungsboard erreichbar, bekommt eine Run-Anforderung, meldet aber noch keine reale Frequenz und keinen publizierten Driverfehler.

Für diesen Sonderfall sind besonders interessant:

```text
Unit1 2099  → public 2080 / hidden status
Unit1 2101  → interner Status
Unit1 2111  → internes Diagnosebyte
Unit1 2113  → public 2026/2027
Unit1 2118  → public 2028
Unit1 2000  → Mode 1/3
Unit1 2002  → Mainboard 1343
```

Diese Felder sind die nächste Ebene für einen realen „Command accepted but no start“-Mitschnitt.

## Fall E – 2072 > 0

Dann meldet Unit1 tatsächlich eine laufende Verdichterfrequenz.

Zusätzlich setzt das Mainboard:

```text
2019 Bit0 = 1
```

auf Basis von `2072 != 0`.

Damit ist der reale Verdichterlauf vom Driverboard bestätigt.

---

# 22. C04 ist für Startfehler besonders relevant

Die externe Service-Dokumentation derselben PHNIX-Driverfamilie nennt bei:

```text
IPM-/Compressor Drive Error
```

unter den ersten Prüfpunkten einen falschen **C04 Compressor Model Code**.

Das passt perfekt zum Binary:

```text
C04
 ↓
Unit1 2003
 ↓
Driverboard
```

Für die konkrete Anlage:

```text
C04 = 13
Unit1 2003 = 2119
```

Bei einem späteren Austausch des Inverterboards oder einer Parameteränderung ist deshalb die korrekte C04-Zuordnung kritisch.

---

# 23. Öffentliche „Reserved“-Register 2026–2028 sind echte Hidden-Diagnostics

Kompatible öffentliche PHNIX-/CC32-Tabellen führen:

```text
2026
2027
2028
```

als „Reserved“.

V3.3 benutzt sie aber explizit:

```text
Unit1 2113 High-Byte → 2026
Unit1 2113 Low-Byte  → 2027
Unit1 2118           → 2028
```

Im realen Mitschnitt:

```text
2113 = 0x0C00
→ 2026 = 12
→ 2027 = 0

2118 = 14
→ 2028 = 14
```

Das sind somit **versteckte Inverter-Diagnosefelder**, deren Herstellersemantik aktuell noch offen ist.

Diese Register sind für gezielte Start-/Störtests besonders interessant, weil sie sich verändern können, obwohl die offizielle Tabelle sie als Reserve bezeichnet.

---

# 24. Unit1 2099 / Mainboard 2080

Remote 2099 wird nach:

```text
0x200168C4+0x00
```

übernommen und später als:

```text
Mainboard 2080
```

veröffentlicht.

Kompatible Herstellerprotokolle führen 2080 als „Reserved“.

Damit gilt aktuell:

```text
2099 = versteckter Driverstatus / Diagnosewort
```

Die genaue Bedeutung wird erst mit einem dynamischen Start-/Stop-/Fehler-Mitschnitt festgelegt.

---

# 25. Was V3.3 aus dem 51-Wort-Frame ausdrücklich NICHT benutzt

Aktuell nicht vom V3.3-Unit1-Parser konsumiert:

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

Diese Felder können auf dem Leistungsboard durchaus eine Bedeutung haben, haben aber **keinen nachgewiesenen Consumer in dieser Mainboardversion**.

Daher werden sie nicht spekulativ benannt.

---

# 26. Empfohlener realer Start-Test

Für einen Test, bei dem der Verdichter tatsächlich startet, sollte der interne Buslogger pro Zyklus mindestens erfassen:

```text
TX:
1999
2000
2002
2003
2006
2007
2008
2009

RX:
2099
2100
2101
2102
2103
2104
2105
2106
2107
2108
2109
2110
2111
2113
2118
2123
2130
2133
2135
2136
2142

öffentliche Mainboardwerte:
2026
2027
2028
2042
2043
2044
2057
2061
2062
2071
2072
2073
2080
2081
2082
```

Besonders wertvoll sind die Übergänge:

```text
vor Start
→ Startanforderung
→ Driver-Precharge
→ erste tatsächliche Frequenz
→ Hochlauf
→ stationärer Betrieb
→ Stop
```

Damit sollten sich auch die aktuell offenen Felder 2099/2101/2111/2113/2118 empirisch klassifizieren lassen.

---

# 27. Confidence-Matrix

## Direkt bestätigt

- Unit1 Adresse `0x01`
- FC10 1999 / FC03 2099
- H33 5/22 vs. 16/51
- komplette TX-Wortpositionen
- 1999 Sollfrequenz
- 2000 Wertebildung `0/1/3`
- 2002 ↔ Mainboard 1343
- 2003 ↔ C04 und `+2106`
- 2008/2009 Fan-Sollwerte
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
- 2135/2136/2123 Fan-Driver-Telemetrie bei config4

## Stark bestätigt durch kompatible PHNIX-/CC32-Protokolle

- T35 2057 = AC Input Current
- T33 2061 = IPM High Fault Temp.
- T34 2062 = AC Input Voltage
- 2081/2082 Driverfehler-Bitnamen
- C04 = Compressor Model Selection

## Noch offen

- Herstellername Mainboard 1343 / Unit1 2002
- exakte Driversemantik Run Mode 1 vs. 3
- Remote 2099 / public 2080
- Remote 2101
- Remote 2111
- Remote 2113 → hidden 2026/2027
- Remote 2118 → hidden 2028
- Bedeutung der nicht konsumierten 51-Wort-Felder auf anderen Driverrevisionen

---

# 28. Externe Vergleichsquellen

Die Bit-/Statusnamen wurden nicht blind aus Fremdunterlagen übernommen. Sie dienen nur dort als Semantikanker, wo das V3.3-Binary den Datenfluss bereits eindeutig geschlossen hat.

Kompatible PHNIX-/CC32-Protokollfamilie:

- Cooper & Hunter / PHNIX-kompatible Registertabelle: Register 2071–2082 einschließlich Failure 7/8
  - https://device.report/m/cd6a7721627b82d4492897f0e9a73b9b36deaa97670dfa189e9cef108bae99dd
- SpacePak/Solstice CC32 WiFi Module Manual, Protokoll V2.1: T35/T33/T34 sowie vollständige 2081/2082-Bitfelder
  - https://manuals.plus/m/72d22b68c4ae789ffbf1ed545b99cd01d3e66f24dd97bec40a6f524255f315ad_optim.pdf
- PHNIX-kompatibles Service Manual mit C04-Modellcode als Diagnosepunkt bei Compressor Drive/IPM Fault
  - https://manuals.plus/m/5cef04381057d3d628fc04b39ec9e7e7b24238e81bf5c744fb8b38c35fd18f73

---

# 29. Verwandte Dokumente

- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md) – übersichtliche Kompressor-Regelkette
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) – Board-/Slave-Architektur
- [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md) – USART3/PB10/PB11/PE6 bis zur RS485-Hardware
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) – Berechnung der Fan-Sollwerte
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) – 60-Hz-Oil-Return-Anforderung vor Unit1

---

# 30. Endgültiges Arbeitsmodell

```text
MAINBOARD

Regelalgorithmus
    ↓
2071 / target Hz
    ↓
Unit1 1999
Unit1 2000 Run/Mode
Unit1 2002 hidden control
Unit1 2003 C04 model code
    ↓
──────────────── RS485 ────────────────
    ↓
UNIT 0x01 LEISTUNGS-/INVERTERBOARD
    ↓
Verdichter + bei H33 integrierte Fan-Driver
    ↓
Unit1 2099…2149
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

Damit ist Unit `0x01` auf V3.3-Seite bis auf wenige bewusst offen gelassene Herstellerstatusfelder vollständig kartiert.
