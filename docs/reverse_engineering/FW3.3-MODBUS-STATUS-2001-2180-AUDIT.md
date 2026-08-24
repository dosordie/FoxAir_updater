# Mainboard-Firmware V3.3 – Modbus-Statusregister 2001–2180: Audit gegen FoxAir_Control

Stand: 24. August 2026

Diese Datei ist **Phase 1 des vollständigen Modbus-Registeraudits** der PHNIX-/FoxAir-Mainboard-Firmware V3.3.

Verglichen werden:

1. **V3.3-Binary** `phnixIot_device_OTA` als Primärquelle für das tatsächlich implementierte Verhalten,
2. der aktuelle Software-Wissensstand aus `dosordie/FoxAir_Control/data`, insbesondere:
   - `data/foxair_phnix_registers.json`
   - `data/foxair_phnix_knowledge.json`
   - `data/foxair_phnix_display_registers.json`
3. vorhandene Reverse-Engineering-Dokumente in diesem Repository,
4. reale USART3-/Modbus-Mitschnitte der laufenden FoxAir,
5. kompatible PHNIX-/CC32-Unterlagen nur als zusätzliche Namens-/Plausibilitätsquelle.

Aktueller Vergleichsstand von `FoxAir_Control/data/foxair_phnix_registers.json`:

```text
Blob SHA: ff24c160813f12304b7b8c403be0287b49a84686
```

Untersuchtes Mainboard-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Größe:        287598 Byte
MD5:          CEB6A4BF386FF644E23E410023E74673
SHA-256:      6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:   0x08050000
```

Bewertung:

- **bestätigt** – direkt aus dem Binary geschlossen, häufig zusätzlich durch Live-Mitschnitt gestützt
- **sehr wahrscheinlich** – Datenfluss/Struktur ist geschlossen, letzte Herstellerbezeichnung fehlt
- **offen** – Register wird nachweislich verwendet, die fachliche Bedeutung ist noch nicht ausreichend geschlossen

---

# 1. Ergebnis in Kurzform

Der aktuelle Datenbestand in `FoxAir_Control/data` ist bereits sehr weit fortgeschritten. Der Audit ergibt **keinen grundlegenden Registerversatz**, sondern überwiegend gezielte Korrekturen und neue V3.3-private Erweiterungen.

Die wichtigsten Änderungen sind:

1. **2057 ist jetzt endgültig T35 / AC Input Current**, nicht mehr „Bedeutung unbestätigt“.
2. **2054, 2059 und 2060 haben jetzt bytegenau bestätigte Skalierungen** `/10`, `/10`, `/100`.
3. **2071 ist die Kompressor-Sollfrequenz**, 2072 die tatsächliche Betriebsfrequenz.
4. **2080 stammt direkt von Unit-1-Remote-Reg. 2099**.
5. **2081/2082 sind die beiden Inverter-/Driver-Fehlerwörter** von Unit `0x01`; 2081 Bit15 wird lokal als Unit-1-Kommunikationsfehler erzeugt.
6. **2019 Bit0 und Bit2 sind Ist-Rückmeldungen**, keine simplen lokalen Ausgangsbefehle.
7. **2026–2028 sind versteckte Unit-1-Diagnosefelder**, nicht bedeutungslose Register `"9"`.
8. **2117/2119/2121/2123 sind keine Reserve**, sondern High-Wörter von 32-Bit-Energiezählern.
9. **2125/2126 und 2127/2128 sind zwei weitere 32-Bit-Energiezählerpaare**; sehr wahrscheinlich Warmwasser/DHW elektrisch und thermisch.
10. **2136 ist ein zweiter T04-/Außentemperaturwert**, nicht ein unbekannter berechneter Modulwert.
11. **2137/2138 sind keine bloßen Spiegel von 2054/2059**. Sie sind die reinen WP-Leistungsgrößen vor Addition eines zusätzlichen Leistungsanteils.
12. **2140–2143 sind strukturell zwei 32-Bit-Werte**.
13. **2146 ist ein echtes Capability-/Status-Bitfeld**; der V3.3-Basiswert ist `0x002C`.
14. Der aktuelle `FoxAir_Control`-Katalog endet bei **2149**, die V3.3 baut und broadcastet aber **bis 2180**. Die Register 2151–2166 sowie 2178–2180 haben bestätigte interne Quellen.

---

# 2. Mainboard-Namespace nicht mit internen Boardregistern verwechseln

Für den Gesamtkatalog gilt ab jetzt ausdrücklich ein Namespace-Modell.

Beispiel:

```text
MAIN:2081   = öffentliches Mainboard-Fehlerwort
INV1:2100   = Remote-Reg. 2100 auf internem Inverterboard Unit 0x01
```

Die beiden Zahlenbereiche dürfen nicht allein anhand der Registernummer gleichgesetzt werden.

Ein konkretes Beispiel:

```text
INV1:2100
    ↓ RX-Parser
Mainboard-Runtime 0x200168C4
    ↓ Fehlerfilter
MAIN:2081
```

Dasselbe gilt für Fan-Drive Unit `0x04`, Display Unit `0x03` und die Hydraulikmodule.

---

# 3. Statusbuilder und Registerspiegel

Der zentrale öffentliche Statusspiegel liegt bei:

```text
0x20012788
```

Für den Hauptstatusbereich gilt:

```text
Mirror-Offset = 0x820 + 2 × (Register - 2001)
```

Der Builder liegt hauptsächlich ungefähr bei:

```text
0x0806C2xx … 0x0806CCxx
```

Er baut die beiden 90-Wort-Blöcke:

```text
2001 … 2090
2091 … 2180
```

Diese werden anschließend auf dem internen USART3-Modbus per Broadcast `0x00 / FC10` verteilt.

Der reale Mitschnitt bestätigt, dass der zweite Block tatsächlich bis **2180** übertragen wird.

---

# 4. Register 2019 – Ausgangsbitfeld: zwei wichtige Bedeutungspräzisierungen

Der aktuelle Softwarestand nennt unter anderem:

```text
Bit0 = Kompressor-Ausgang
Bit2 = Lüfter Hochgeschwindigkeitsausgang
```

Die V3.3 zeigt präziser:

## 4.1 Bit 0

Bit0 wird aus der vom Inverter zurückgemeldeten tatsächlichen Kompressorfrequenz erzeugt:

```text
0x200168C4 + 0x06 != 0
    ↓
2019 Bit0 = 1
```

Damit lautet die technisch richtige Semantik:

> **Kompressor tatsächlich laufend / Istfrequenz ungleich 0**

Es ist kein simpler Relais-/Sollbefehl.

## 4.2 Bit 2

Bit2 wird gesetzt, wenn mindestens eine tatsächliche Lüfterrückmeldung ungleich 0 ist:

```text
0x2001691C +0x0C != 0
ODER
0x2001691C +0x0E != 0
    ↓
2019 Bit2 = 1
```

Technisch richtige Semantik:

> **Mindestens ein Lüfter meldet tatsächliche Aktivität**

Es ist nicht der Lüfter-Sollwert und nicht einfach „High-Speed-Ausgang“.

**Softwareaktion:** Namen/Description präzisieren; Bitnummern bleiben unverändert.

---

# 5. Register 2026–2028 – versteckte Inverterdiagnose

Der aktuelle Softwarebestand führt:

```text
2026 = "9"
2027 = "9"
2028 = "9"
```

Die V3.3-RX-Verarbeitung von Unit `0x01` beweist:

```text
INV1:2113 High-Byte → MAIN:2026
INV1:2113 Low-Byte  → MAIN:2027
INV1:2118           → MAIN:2028
```

Damit sind diese Register keine bedeutungslose Reserve.

Empfohlene vorläufige Namen:

```text
2026 = Inverter-Diagnose 2113 High-Byte
2027 = Inverter-Diagnose 2113 Low-Byte
2028 = Inverter-Diagnose 2118
```

Die fachliche Bedeutung der Rohwerte ist noch offen.

**Bewertung: Provenance bestätigt, Semantik offen.**

---

# 6. 2042–2044 / 2057 / 2061 / 2062 – Invertertelemetrie

Die Provenance ist jetzt geschlossen:

| MAIN | Quelle Unit 0x01 | Runtime | Bedeutung |
|---:|---:|---|---|
| 2042 | 2107 | `0x200168C4+0x10` | Kompressor-Phasenstrom |
| 2043 | 2108 | `+0x12` | DC-Bus-Spannung |
| 2044 | 2110 | `+0x16` | IPM-Temperatur |
| **2057** | **2106** | `+0x0E` | **T35 AC Input Current** |
| 2061 | 2104 | `+0x0A` | T33 IPM High Fault Temp. |
| 2062 | 2105 | `+0x0C` | T34 AC Input Voltage |

Für 2044 gilt:

```text
MAIN:2044 = (INV1:2110 - 55) × 10
```

Beispiel real:

```text
INV1:2110 = 86
→ (86 - 55) × 10 = 310
→ MAIN:2044 = 31,0 °C
```

## Korrektur 2057

Aktuell in `FoxAir_Control`:

```text
Livewert 2057 (nicht T34; Bedeutung unbestätigt)
```

Neu:

```text
2057 = T35 / AC Input Current
Einheit = A
Skalierung entsprechend T35-Rohformat
```

**Bewertung: bestätigt.**

---

# 7. 2054, 2059, 2060 – Leistung und COP: Skalierung jetzt exakt

Die aktuelle Software verwendet bereits plausible Skalierungen. Die V3.3 bestätigt sie bytegenau.

## 7.1 Register 2054 – elektrische Gesamtleistung

Statusbuilder:

```text
P_total_electric = float[0x200161A4 + 0x14]
MAIN:2054 = int(P_total_electric × 10)
```

Damit:

```text
Raw 1 = 0,1 kW
Raw 10 = 1,0 kW
```

**Skalierung `/10 kW` ist bestätigt.**

## 7.2 Register 2059 – thermische Gesamtleistung / Unit Capacity

```text
Q_total = float[0x200161A4 + 0x18]
MAIN:2059 = int(Q_total × 10)
```

**Skalierung `/10 kW` ist bestätigt.**

## 7.3 Register 2060 – COP

```text
COP = float[0x200161A4 + 0x1C]
MAIN:2060 = int(COP × 100)
```

**Skalierung `/100` ist bestätigt.**

Zusätzlich zeigt die Berechnungsroutine:

```text
COP = Q_total / P_total_electric
```

wenn die elektrische Gesamtleistung ungleich 0 ist.

---

# 8. 2137 und 2138 – jetzt funktional geschlossen

Der aktuelle Softwarestand nennt:

```text
2137 = Elektrische Leistung / Spiegel von 2054 (Kandidat)
2138 = Thermische Leistung / Spiegel von 2059 (Kandidat)
```

Das ist **nicht ganz korrekt**.

Die V3.3 benutzt unterschiedliche Floatfelder:

```text
2137 ← 0x200161A4 + 0x20
2138 ← 0x200161A4 + 0x10
2054 ← 0x200161A4 + 0x14
2059 ← 0x200161A4 + 0x18
```

und jeweils:

```text
2137 = float × 10
2138 = float × 10
```

## 8.1 2137 – reine elektrische WP-/Inverterleistung

Die Berechnungsroutine um `0x0807F954ff` erzeugt den Wert aus den elektrischen Inverter-/Netzgrößen.

Bei 3-phasigem Betrieb werden unter anderem verwendet:

```text
AC-Spannung
Phasenströme
√3 = 1,732
Leistungsfaktor 0,9
1000-W-Skalierung
```

Funktional ist damit bestätigt:

> **2137 = elektrische Leistung des eigentlichen Wärmepumpen-/Inverterpfads vor Addition eines zusätzlichen Leistungsanteils**

Skalierung:

```text
raw / 10 = kW
```

## 8.2 2138 – reine thermische WP-Leistung

Die Firmware benutzt die klassische Wasser-Leistungsbeziehung mit der Konstanten:

```text
1,163
```

und Größen aus:

```text
Volumenstrom
× Temperaturdifferenz
× 1,163
```

Damit:

> **2138 = thermische Leistung der eigentlichen Wärmepumpe vor Addition eines zusätzlichen Leistungsanteils**

Skalierung:

```text
raw / 10 = kW
```

## 8.3 Verhältnis zu 2054 / 2059

Die Firmware bildet anschließend:

```text
2054-Basis = P_WP + P_add
2059-Basis = Q_WP + P_add
```

Der zusätzliche Beitrag wird in der V3.3 aus einem konfigurationsabhängigen Hilfs-/Hydraulikpfad übernommen und sowohl der elektrischen Eingangsleistung als auch der abgegebenen Wärmeleistung zugeschlagen. Das Verhalten ist konsistent mit einem resistiven Zusatzheizer bzw. gleichwertigen 1:1-Elektrowärmeanteil.

Deshalb sind 2137/2138 **keine Spiegel**, sondern die saubereren „WP-only“-Leistungswerte.

Empfohlene Namen:

```text
2137 = Elektrische WP-/Inverterleistung ohne Zusatzheizer
2138 = Thermische WP-Leistung ohne Zusatzheizer
```

**Bewertung: Funktion und Skalierung bestätigt; exakte Herstellerkurzbezeichnung offen.**

---

# 9. Register 2071–2073 – Soll und Ist sauber unterscheiden

Aktueller Softwarestand:

```text
2071 = Kompressorfrequenz
2072 = Betriebsfrequenz des Kompressors
2073 = Max. Frequenz vom Kompressortreiber
```

Präziser:

```text
2071 = Kompressor-Sollfrequenz
2072 = Kompressor-Ist-/Betriebsfrequenz
2073 = vom Driver gemeldete maximale zulässige Frequenz
```

2071 stammt aus:

```text
0x20016AA4 + 0x08
```

und wird direkt als:

```text
INV1:1999
```

an das Inverterboard übertragen.

2072/2073 kommen vom Inverter zurück.

**Softwareaktion:** nur Name/Description von 2071 präzisieren.

---

# 10. 2080–2082 – Inverterstatus und Driverfehler

## 10.1 Register 2080

Jetzt geschlossen:

```text
INV1:2099
    ↓
0x200168C4 +0x00
    ↓
MAIN:2080
```

Die fachliche Bedeutung des Wortes ist weiter offen, aber die Provenance ist bestätigt.

Empfohlener Name:

```text
Inverter-/Driver-Statuswort 2099 (Semantik offen)
```

## 10.2 Register 2081

```text
INV1:2100
    ↓ Fehlerfilter / lokaler Comm-Bit-Zusatz
MAIN:2081
```

Damit:

> **2081 = Inverter-/Compressor-Driver Fault Word 1**

Besonders wichtig:

```text
2081 Bit15
```

wird **nicht** aus INV1:2100 übernommen. Die V3.3 erzeugt dieses Bit selbst, wenn gültige Antworten von Unit `0x01` ausbleiben.

Ein Watchdogzähler bei:

```text
0x20016F9E
```

läuft bis `0xF0`; anschließend wird der Kommunikationsfehler gesetzt und die Inverter-Istfrequenz auf 0 gesetzt.

## 10.3 Register 2082

```text
INV1:2109
    ↓ Fehlerfilter
MAIN:2082
```

Damit:

> **2082 = Inverter-/Compressor-Driver Fault Word 2**

Die vorhandenen Bitmaps in `FoxAir_Control` sind grundsätzlich wertvoll und werden nicht pauschal umbenannt; sie sollen in einem separaten Alarmbit-Audit nochmals gegen Binary + passende Driver-Dokumentation geprüft werden.

---

# 11. Register 2109 – nicht mehr als „Reserviert“ behandeln

Der Hauptstatusbuilder schreibt 2109 nicht in jedem Durchlauf, aber ein separater V3.3-Pfad schreibt nach:

```text
Mirror-Offset 0x8F8
→ MAIN:2109
```

Quelle:

```text
0x20016EF0
```

Damit ist klar:

> 2109 ist intern aktiv beschrieben und darf nicht mehr als sicher „Reserviert“ klassifiziert werden.

Semantik: **offen**.

Empfohlener vorläufiger Name:

```text
Interner V3.3-Statuswert 2109 (Semantik offen)
```

---

# 12. Energiezähler 2117–2128 – 32-Bit-Struktur

Die aktuelle Software interpretiert mehrere Low-Wörter bereits sinnvoll, führt die jeweiligen High-Wörter aber als Reserve.

Die V3.3 beweist eine native 32-Bit-Struktur.

## 12.1 Bestätigte Paare

| High | Low | Runtime-Quelle | aktueller Softwareinhalt |
|---:|---:|---|---|
| 2117 | 2118 | `0x200161A4+0x58` | elektrisch Heizen |
| 2119 | 2120 | `+0x60` | thermisch Heizen |
| 2121 | 2122 | `+0x54` | elektrisch Kühlen |
| 2123 | 2124 | `+0x64` | thermisch Kühlen |
| 2125 | 2126 | `+0x50` | bisher beide Reserve |
| 2127 | 2128 | `+0x5C` | bisher beide Reserve |

Der 32-Bit-Wert lautet jeweils:

```text
value32 = (HIGH << 16) | LOW
```

Damit sind insbesondere:

```text
2117
2119
2121
2123
```

**keine Reservewörter**.

## 12.2 Drittes Energiepaar

Die Energie-Akkumulationsroutine besitzt drei gegenseitig ausschließende elektrische Betriebszweige und drei entsprechende thermische Zählerpfade.

Da Heizen und Kühlen bereits den bekannten vier Paaren zugeordnet sind, sind:

```text
2125/2126
2127/2128
```

**sehr wahrscheinlich**:

```text
Warmwasser/DHW elektrische Energie
Warmwasser/DHW thermische Energie
```

Die 32-Bit-Struktur ist **bestätigt**; die DHW-Bezeichnung ist **sehr wahrscheinlich** und sollte bei einem Warmwasserlauf live gegengeprüft werden.

---

# 13. Register 2136 – zweiter T04-/Außentemperaturwert

Der aktuelle Softwarestand beschreibt 2136 als:

```text
Berechneter x0,1-Regel-/Modulwert (Kandidat)
```

Das Binary schließt die Funktion direkt:

```text
0x0806C9D2:
    BL 0x0808799C
    → MAIN:2136
```

Der Helper:

```text
0x0808799C
```

ist aus der Sensoranalyse bestätigt als:

```text
T04 / Außentemperatur
```

Damit:

> **2136 = zweiter T04-/Außentemperaturwert, x0,1 °C**

Der reale Mitschnitt zeigt beispielsweise:

```text
2048 = 25,8 °C
2136 = 25,6 / 25,7 °C
```

Die geringe Differenz ist mit unterschiedlichen Aktualisierungszeitpunkten der beiden Veröffentlichungswege vereinbar.

**Softwareaktion:** Kandidatenbeschreibung ersetzen.

---

# 14. Register 2140–2143 – zwei 32-Bit-Werte

Aktuell sind 2140–2143 einzeln als unbekannte RAW-Werte geführt.

Der Statusbuilder zeigt stattdessen:

```text
2140 = High-Wort von 0x200161A4+0x6C
2141 = Low-Wort  von 0x200161A4+0x6C

2142 = High-Wort von 0x200161A4+0x68
2143 = Low-Wort  von 0x200161A4+0x68
```

Damit sind dies **zwei 32-Bit-Zähler/Akkumulatoren**, nicht vier unabhängige 16-Bit-Werte.

Fachliche Bedeutung: noch offen.

**Softwareaktion:** Pairing und 32-Bit-Provenance dokumentieren; Namen noch nicht spekulativ festlegen.

---

# 15. Register 2146 – Capability-/Statusbitfeld

Der reale Mitschnitt zeigt regelmäßig:

```text
2146 = 44 = 0x002C
```

Das Binary erklärt exakt, warum.

Der Builder setzt den Wert zunächst auf 0 und setzt anschließend:

```text
Bit2 = immer 1
Bit3 = immer 1
Bit5 = immer 1
```

Damit entsteht als V3.3-Basis:

```text
0x04 | 0x08 | 0x20 = 0x2C
```

Zusätzlich sind variabel:

```text
Bit1 ← internes Flag aus 0x20015C68+0x10E
Bit4 ← 0x20016E3C != 0
Bit6 ← 0x20016FB2 != 0
```

Damit lautet die neue Klassifikation:

> **2146 = V3.3 Capability-/Statusbitfeld**

Die exakten fachlichen Namen der einzelnen Bits sind noch offen.

**Softwareaktion:** `RAW/Funktion unbekannt` zu `BITFIELD/Capability-Status` hochstufen; Bits 2,3,5 als V3.3-Basisflags dokumentieren, ohne erfundene Funktionsnamen.

---

# 16. Register 2147

```text
MAIN:2147 ← signed 0x20015C68 + 0x110
```

Damit ist das Register aktiv befüllt.

Semantik: offen.

**Softwareaktion:** „intern befüllter V3.3-Wert“ statt vollständig unbekannt/reserviert.

---

# 17. V3.3-Erweiterungsbereich 2150–2180

Dies ist die größte Lücke im aktuellen `FoxAir_Control`-Katalog.

`foxair_phnix_registers.json` endet aktuell bei:

```text
2149
```

Die V3.3 erzeugt und broadcastet aber:

```text
2091 … 2180
```

und mehrere Register jenseits 2149 haben echte Runtime-Quellen.

## 17.1 Bestätigte Quellen

| MAIN | Quelle | Typ aus Binary | Live-Beispiel | Semantik |
|---:|---|---|---:|---|
| 2150 | im Hauptbuilder nicht gesetzt | – | 0 | Reserve/anderer Pfad |
| 2151 | `0x20016A44+0x14` | uint8 | 0 | offen |
| 2152 | `0x20016A44+0x1C` | int16 | 1 | offen |
| 2153 | `0x20015EF0+0x06` | int16 | 0 | offen |
| 2154 | `0x20015EF0+0x0A` | uint16 | 0 | offen |
| 2155 | `0x20015EF0+0x0C` | uint16 | 0 | offen |
| 2156 | `0x20015EF0+0x08` | int16 | 0 | offen |
| 2157 | `0x20015EF0+0x10` | uint16 | 0 | offen |
| 2158 | `0x20015EF0+0x12` | uint16 | 0 | offen |
| 2159 | im Hauptbuilder nicht gesetzt | – | 0 | Reserve/anderer Pfad |
| 2160 | `0x2001605C+0x66` | uint16 | 0 | offen |
| 2161 | `0x20016100+0x78` | uint16 | 0 | offen |
| 2162 | `0x20016100+0x66` | uint16 | 0 | offen |
| 2163 | berechneter Wert, auf 100 begrenzt | Prozent-/Ratio-artig | 0 | offen |
| 2164 | `0x2001605C+0x7A` | uint16 | **450** | offen |
| 2165 | `0x20016100+0x7A` | uint16 | **350** | offen |
| 2166 | `0x20016100+0x46` | int16 | **1** | offen |
| 2167–2177 | im Hauptbuilder nicht befüllt | – | 0 | Reserve/anderer Pfad |
| 2178 | `0x20016DB4+0x00` | uint16 | 0 | offen |
| 2179 | `0x20016DB4+0x02` | uint16 | 0 | offen |
| 2180 | `0x20016DB4+0x04` | uint16 | 0 | offen |

Damit darf der Bereich **nicht** pauschal als Reserve verworfen werden.

Die V3.3 nutzt formal/älter dokumentierte Reserveplätze für private Diagnose-/Erweiterungswerte.

## 17.2 Register 2163

2163 ist besonders interessant, weil es nicht einfach kopiert wird.

Die Firmware berechnet einen Wert über Floating-Point-Helfer aus der `0x20016100`-Struktur und begrenzt das Ergebnis anschließend auf:

```text
max 100
```

Damit ist eine Prozent-/Auslastungs-/Verhältnisgröße sehr wahrscheinlich.

Die fachliche Bezeichnung bleibt bis zur Writer-/Live-Korrelation offen.

---

# 18. Register 2130–2132 – vorhandene Softwarebezeichnungen bestätigt

Die aktuellen Namen:

```text
2130 = IPM-Temperatur des externen Lüftermotorantriebs
2131 = Leistung des externen Lüftermotorantriebs
2132 = Strom des externen Lüftermotorantriebs
```

passen zur V3.3 und zur Unit-1-/Unit-4-Fan-Driver-Architektur.

Diese Register sollen **nicht** korrigiert, sondern nur um Provenance ergänzt werden.

---

# 19. Register 2106 – Kandidat bleibt zunächst Kandidat

`FoxAir_Control` hat aus Livebeobachtungen bereits eine starke Kandidatenbeschreibung für 2106 als zyklisches Pumpenregel-/PWM-Fenster.

Der aktuelle Audit liefert noch keinen ausreichenden Grund, diesen Namen härter festzuschreiben oder zu verwerfen.

Status:

```text
starker Live-Kandidat, noch nicht vollständig statisch geschlossen
```

Dies ist ein gutes Beispiel dafür, dass der Audit nicht jede bestehende Hypothese künstlich „bestätigt“.

---

# 20. Register 2111/2112 – Display-Identität

Die aktuelle Software nennt:

```text
2111 = Display Nr.
2112 = Display Version
```

Der reale interne Bus liefert auf Unit `0x03` unter anderem:

```text
Softwarecode 463
Version 17 = V1.7
```

und der öffentliche Status zeigt entsprechend:

```text
2111 = 463
2112 = 17
```

Die Zuordnung ist damit deutlich stärker als die bisherige reine Forum-Notiz.

**Bewertung: bestätigt durch internen Bus + öffentlichen Status.**

---

# 21. Aktionsliste für FoxAir_Control

## Sofort sicher korrigierbar

```text
2019 Bit0  → Kompressor tatsächlich laufend / Istfrequenz != 0
2019 Bit2  → mindestens ein Lüfter tatsächlich aktiv

2026       → Inverter-Diagnose INV1:2113 High-Byte
2027       → Inverter-Diagnose INV1:2113 Low-Byte
2028       → Inverter-Diagnose INV1:2118

2057       → T35 AC Input Current
2071       → Kompressor-Sollfrequenz

2080       → Inverter-/Driver-Statuswort INV1:2099
2081       → Inverter-/Driver Fault Word 1
2082       → Inverter-/Driver Fault Word 2

2109       → intern beschriebener V3.3-Status, nicht sicher Reserve

2117       → High-Wort zu 2118
2119       → High-Wort zu 2120
2121       → High-Wort zu 2122
2123       → High-Wort zu 2124

2136       → T04 Außentemperatur, zweiter Veröffentlichungsweg
2137       → elektrische WP-/Inverterleistung ohne Zusatzanteil, /10 kW
2138       → thermische WP-Leistung ohne Zusatzanteil, /10 kW

2140/2141 → 32-Bit-Paar
2142/2143 → 32-Bit-Paar
2146       → Capability-/Statusbitfeld; Basis 0x2C
2147       → intern befüllter V3.3-Wert
```

## Neu in den Katalog aufnehmen

```text
2150 … 2180
```

mit den oben dokumentierten Runtime-Quellen und zunächst konservativen Namen.

## Noch nicht hart umbenennen

```text
2106
2125–2128 fachliche DHW-Namen
2140–2143 fachliche Zählernamen
2146 einzelne Capability-Bitnamen
2151–2166 fachliche Namen
2178–2180 fachliche Namen
```

---

# 22. Empfohlenes Datenmodell für den zukünftigen Masterkatalog

Für jedes Register sollten künftig mindestens gespeichert werden:

```text
namespace
register
name
block/code
function
access
raw_type
signed
scale
unit
value_map / bit_map
runtime_source
remote_source
producer
consumer
confidence
provenance
notes
```

Beispiel:

```text
namespace: MAIN
register: 2057
name: AC Input Current
block: T
code: T35
raw_type: int16
unit: A
runtime_source: 0x200168C4+0x0E
remote_source: INV1:2106
confidence: confirmed
```

Damit lassen sich später GUI, Logger, Modbusdump und Dokumentation aus derselben Wissensbasis generieren.

---

# 23. Nächste Audit-Phasen

Nach diesem Statusblock ist die sinnvolle Reihenfolge:

1. **Parameter 1001ff komplett auditieren**
   - H / F / C / D / E / P / A / SG
   - Read/Write
   - Grenzen
   - Default
   - Live-RAM-Kopie
   - tatsächliche Verbraucher im Code
2. **Engineering-/Servicebereich 8001–8090**
3. **interne Board-Namespaces** getrennt katalogisieren
   - INV1:1999–2014 / 2099–2149
   - FAN4:1011–1024
   - HMI3:3001ff
   - HYD5/HYD61
4. daraus einen gemeinsamen maschinenlesbaren V3.3-Masterkatalog erzeugen.

---

# 24. Verwandte Dokumente

- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)

