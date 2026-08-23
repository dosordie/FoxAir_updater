# Mainboard-Firmware V3.3 – Kompressor- und Inverteransteuerung

Stand: 24. August 2026

Diese Datei dokumentiert die vollständige bisher rekonstruierte Kette von der Kompressor-Sollwertbildung im FoxAir-/PHNIX-Mainboard bis zum externen Inverter-/Leistungsboard Unit `0x01` und zurück.

Untersuchtes Binary:

```text
Produkt-/Softwarekennung: 82400644
Firmware:                 V3.3
Größe:                    287598 Byte
MD5:                      CEB6A4BF386FF644E23E410023E74673
SHA-256:                  6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:               0x08050000
```

Bewertung:

- **bestätigt** – direkt im Binary bzw. zusätzlich im realen Busverkehr nachgewiesen
- **sehr wahrscheinlich** – Datenfluss ist geschlossen, letzte Herstellersemantik fehlt
- **Hypothese** – noch nicht ausreichend verifiziert

---

# 1. Kurzfazit

Das V3.3-Regelmainboard erzeugt **keine direkte Leistungselektronik-Ansteuerung des Verdichtermotors**.

Es berechnet eine Kompressor-Sollfrequenz und übergibt diese per Modbus an ein externes Leistungs-/Inverterboard:

```text
Mainboard-Regelung
      ↓
0x20016AA4 + 0x08
      ↓
Mainboard Register 2071
      ↓
Unit 0x01 / FC10 / Remote-Reg. 1999
      ↓
externes Inverter-/Leistungsboard
      ↓
Verdichter
```

Das Inverterboard liefert anschließend seine Telemetrie per FC03 zurück:

```text
Unit 0x01 / FC03 / ab Remote-Reg. 2099
      ↓
0x200168C4
      ↓
Mainboard-Statusregister
      ├── 2072 Istfrequenz
      ├── 2073 Maximalfrequenz
      ├── 2042 Phasenstrom
      ├── 2043 DC-Bus
      ├── 2057 AC-Eingangsstrom
      └── 2062 AC-Eingangsspannung
```

Bei aktivem `H33 = Fan Motor Driver and Comp. Driver Integrated` wird derselbe Unit-`0x01`-Dialog um die Lüfteransteuerung erweitert.

Damit ist für die untersuchte Anlage bestätigt:

> Das zweite Leistungsboard ist der eigentliche Verdichter-Inverter und übernimmt in der H33-Konfiguration zusätzlich die Fan-Driver-Kommunikation.

---

# 2. Relevante interne Strukturen

## 2.1 Kompressor-Sollwertblock

```text
0x20016AA4
```

Bestätigt:

```text
0x20016AA4 + 0x08 = finale Kompressor-Sollfrequenz
```

Dieser Wert wird öffentlich als:

```text
Register 2071
```

bereitgestellt und unmittelbar an Unit `0x01` gesendet.

## 2.2 Inverter-Telemetrieblock

```text
0x200168C4
```

Bekannte Felder:

| Offset | Bedeutung | öffentlich |
|---:|---|---:|
| `+0x06` | Kompressor-Istfrequenz | 2072 |
| `+0x08` | maximale Inverter-/Kompressorfrequenz | 2073 |
| `+0x0C` | AC-Eingangsspannung | 2062 |
| `+0x0E` | AC-Eingangsstrom | 2057 |
| `+0x10` | Kompressor-Phasenstrom | 2042 |
| `+0x12` | DC-Bus-Spannung | 2043 |

Weitere Felder desselben Blocks enthalten IPM-/Driverdaten und – bei bestimmten Fan-Driver-Konfigurationen – zusätzliche Lüfterantriebs-Telemetrie.

---

# 3. Sollfrequenzbildung vor dem Inverter

Der Inverter bekommt nicht direkt einen Heizleistungs- oder Temperaturfehler. Das Mainboard berechnet selbst die gewünschte Frequenz.

Die bereits bestätigte Regelkette enthält unter anderem:

```text
Betriebsart / Solltemperaturen
       ↓
Kompressor-Regelalgorithmus
       ↓
C-Parameter / dynamische Grenzen
       ↓
Schutz- und Sonderzustände
       ↓
0x20016AA4+0x08
       ↓
2071
```

Bestätigte C-Parameter im Liveblock:

```text
0x20016B20
```

| Register | Parameter | Funktion |
|---:|---|---|
| 1218 | C01 | manuelle Kompressorfrequenz |
| 1219 | C02 | Mindestfrequenz |
| 1220 | C03 | Maximalfrequenz |
| 1221 | C04 | Kompressormodell |
| 1222 | C05 | Mindestfrequenz Kühlen bei niedriger AT |
| 1223 | C06 | Frequenzregelmodus |
| 1227 | C10 | Mindestfrequenz Heizen bei niedriger AT |
| 1217 | C11 | temperaturabhängige obere Frequenzbegrenzung |

Dynamische Mindestfrequenz:

```text
0x20016F83
```

Normaler Endclamp:

```text
Soll <= C03
Soll >= dynamische Mindestfrequenz
```

Zusätzliche Sonderpfade können diese normale Sollwertbildung vorgeben bzw. übersteuern, beispielsweise:

- Abtauung,
- Ölrückführung,
- Schutz-/Derating-Zustände,
- Factory-/Manual-Betrieb.

---

# 4. Beispiel Ölrückführung

Die Oil-Return-State-Machine setzt bei aktiver Ölrückführung nominal:

```text
60 Hz
```

als Kompressoranforderung.

Auch dieser Sonderwert läuft anschließend durch die gemeinsame Ausgangskette und landet bei:

```text
0x20016AA4+0x08
→ Register 2071
→ Unit 0x01 / Register 1999
```

Das bestätigt, dass Unit `0x01` der gemeinsame Endpunkt sowohl für normale Regelung als auch für Sonderzustände ist.

---

# 5. Modbus-Master-Scheduler

Der Unit-`0x01`-Dialog ist Bestandteil des festen internen Schedulers um:

```text
0x08064C40 … 0x08064FC6
```

Die beiden relevanten Zustände sind:

```text
State 5:
    Slave 0x01
    FC10
    Start 1999
    5 oder 16 Wörter

State 6:
    Slave 0x01
    FC03
    Start 2099
    22 oder 51 Wörter
```

Die Länge hängt von H33 ab.

Der Modbus-Request-Builder liegt bei:

```text
0x080695F0
```

---

# 6. H33 – integrierter Fan- und Compressor-Driver

H33 liegt bei:

```text
Register 1019
0x20016774 + 0x28
```

Offizielle Bezeichnung:

```text
H33 = Fan Motor Driver and Comp. Driver Integrated
0 = No
1 = Yes
```

Die Firmware benutzt H33 exakt für die Länge des Unit-`0x01`-Dialogs.

## H33 = 0

```text
FC10 1999, 5 Wörter
FC03 2099, 22 Wörter
```

Das ist der reine/kurze Verdichterdriver-Pfad.

## H33 != 0

```text
FC10 1999, 16 Wörter
FC03 2099, 51 Wörter
```

Die zusätzlichen Register enthalten Fan-Driver-Sollwerte und -Rückmeldungen.

## Reale FoxAir

Der reale Mitschnitt zeigt:

```text
Unit 0x01 FC10 1999 qty=16
Unit 0x01 ACK
Unit 0x01 FC03 2099 qty=51
Unit 0x01 Antwort mit 51 Wörtern
```

Damit läuft die konkrete Anlage in der integrierten H33-Variante.

**Bewertung: bestätigt.**

---

# 7. FC10-Sollwertpaket an Unit 0x01

Sendepuffer:

```text
0x2001232C
```

## 7.1 Remote-Register 1999 – Kompressor-Sollfrequenz

Die Firmware kopiert:

```text
0x20016AA4+0x08
```

in das erste Sendewort:

```text
Unit 0x01, Register 1999
```

Das ist die zentrale Verdichter-Sollfrequenz.

**Bewertung: bestätigt.**

## 7.2 Remote-Register 2000 – Run-/Mode-Wort

Die Firmware bildet das zweite Wort aus der Sollfrequenz und einem internen Modusflag bei:

```text
0x20016FBA
```

Bytegenau:

```text
wenn Sollfrequenz == 0:
    Reg. 2000 = 0

wenn Sollfrequenz != 0 und internes Flag == 0:
    Reg. 2000 = 1

wenn Sollfrequenz != 0 und internes Flag != 0:
    Reg. 2000 = 3
```

Damit ist die Funktion als Run-/Mode-Kommando bestätigt; die offizielle Bedeutung der Modi `1` und `3` wird noch separat benannt.

## 7.3 Remote-Register 2001

```text
Reg. 2001 = 0
```

im normalen beobachteten Pfad.

Die offizielle Funktion ist noch offen.

## 7.4 Remote-Register 2002

Quelle:

```text
0x200162D8 + 0x5C
```

Das Wort wird direkt an den Driver übertragen. Die genaue Semantik ist noch offen.

## 7.5 Remote-Register 2003 – Driver-/Kompressormodellcode

Quelle ist C04:

```text
0x20016B20 + 0x06
```

Wenn C04 ungleich null ist, bildet die Firmware:

```text
Unit1_Reg2003 = C04 + 0x083A
```

ansonsten wird C04 direkt übernommen.

Im realen Mitschnitt wurde beispielsweise:

```text
2003 = 2119
```

beobachtet.

Das ist ein klarer Modell-/Driver-Auswahlpfad; die genaue Kodetabelle ist noch offen.

---

# 8. H33-Zusatzwörter im FC10-Paket

Bei aktivem H33 werden zusätzlich unter anderem aufgebaut:

```text
2006 = Fan-Driver-Selektor 1
2007 = Fan-Driver-Selektor 2
2008 = Lüfter-Sollwert 1
2009 = Lüfter-Sollwert 2
2010 = 0
```

Quellen:

```text
2008 ← 0x20016F0A
2009 ← 0x20016F0C
```

Damit teilt sich das Inverterboard denselben FC10-Block für:

```text
Verdichter
+
Fan-Motor-Driver
```

Die Lüfterregelung selbst bleibt auf dem Regelmainboard; Unit `0x01` erhält nur die bereits berechneten Sollwerte.

---

# 9. FC03-Telemetrie von Unit 0x01

Der Scheduler liest:

```text
Slave 0x01
FC03
Start 2099
```

Die Antwortwörter werden in die Struktur `0x200168C4` überführt.

## 9.1 Direkt rekonstruierte Anfangsregister

| Unit-1-Register | internes Ziel | Funktion |
|---:|---:|---|
| 2099 | `0x200168C4+0x00` | noch offen |
| 2100 | `+0x02` | noch offen |
| 2101 | `+0x04` | noch offen |
| 2102 | `+0x06` | Kompressor-Istfrequenz |
| 2103 | `+0x08` | maximale Inverter-/Kompressorfrequenz |
| 2104 | `+0x0A` | noch offen |
| 2105 | `+0x0C` | AC-Eingangsspannung |
| 2106 | `+0x0E` | AC-Eingangsstrom |
| 2107 | `+0x10` | Kompressor-Phasenstrom |
| 2108 | `+0x12` | DC-Bus-Spannung |

Die öffentlichen Mainboardregister entstehen erst anschließend aus dieser Struktur.

Daraus folgt:

```text
Unit1-Reg2102 → 0x200168C4+6 → Mainboard 2072
Unit1-Reg2103 → 0x200168C4+8 → Mainboard 2073
Unit1-Reg2105 → 0x200168C4+C → Mainboard 2062
Unit1-Reg2106 → 0x200168C4+E → Mainboard 2057
Unit1-Reg2107 → 0x200168C4+10 → Mainboard 2042
Unit1-Reg2108 → 0x200168C4+12 → Mainboard 2043
```

**Bewertung: bestätigt.**

---

# 10. Plausibilisierung mit realem Bus

Im Mitschnitt bei stillstehendem Verdichter wurde in einer Unit-`0x01`-Antwort unter anderem beobachtet:

```text
2102 = 0
2105 ≈ 228…229
2106 = 2
2108 ≈ 313…315
```

Das passt hervorragend zu:

```text
Istfrequenz       0 Hz
AC-Spannung       ~229 V
kleiner Eingangsstrom
DC-Zwischenkreis  ~313 V
```

Damit wird die statische Registerzuordnung zusätzlich durch reale elektrische Größen gestützt.

---

# 11. Öffentlicher Kompressorstatus 2019 Bit 0

Register 2019 Bit 0 wird nicht aus einem Kompressorrelais gebildet.

Die Firmware prüft:

```text
0x200168C4 + 0x06 != 0
```

also die vom Inverter zurückgemeldete tatsächliche Frequenz.

Damit gilt:

```text
2019 Bit 0 = 1
```

nur wenn der Inverter tatsächlich eine von null verschiedene Verdichterfrequenz meldet.

Das ist diagnostisch wichtig:

```text
2071 > 0, aber 2072 = 0
```

bedeutet:

```text
Mainboard fordert Verdichter an,
aber Inverter meldet noch keinen laufenden Verdichter.
```

---

# 12. Diagnose der Verbindung zum Leistungsboard

Der normale H33=1-Zyklus sieht auf dem Draht so aus:

```text
Mainboard → 0x01:
    FC10, Start 1999, 16 Wörter

0x01 → Mainboard:
    FC10 ACK

Mainboard → 0x01:
    FC03, Start 2099, 51 Wörter

0x01 → Mainboard:
    FC03 Antwort, 51 Wörter
```

Damit lassen sich Kommunikationsfehler klar vom Regelalgorithmus unterscheiden.

## Beispiel 1

```text
2071 > 0
FC10 an Unit1 sichtbar
kein ACK / keine FC03-Antwort
```

→ Kommunikations-/Powerboardproblem wahrscheinlich.

## Beispiel 2

```text
FC10/FC03 laufen sauber
2071 > 0
2072 bleibt 0
```

→ Board kommuniziert, startet den Verdichter aber nicht bzw. hält ihn aufgrund eigener Driverbedingungen zurück.

## Beispiel 3

```text
2072 > 0
2019 Bit0 = 1
```

→ tatsächlicher Verdichterlauf vom Driver bestätigt.

---

# 13. Wo endet die Mainboardregelung und wo beginnt der Inverter?

Die Trennlinie ist jetzt klar:

## Regelmainboard

verantwortlich für:

- Betriebsart,
- Temperaturregelung,
- Kompressor-Sollfrequenz,
- C02/C03 und dynamische Frequenzgrenzen,
- Abtau-Sollwerte,
- Oil Return,
- Schutz-/Derating-Vorgaben,
- Fan-Sollwerte.

## Unit-0x01-Leistungsboard

verantwortlich für:

- Umsetzung des Frequenzsollwertes in reale Motorleistung,
- Inverter-/IPM-Leistungselektronik,
- DC-Zwischenkreis,
- Messung von Strömen und Spannungen,
- Rückmeldung der tatsächlichen Frequenz,
- bei H33=1 zusätzlich Fan-Motor-Driver-Kommunikation/-Leistungselektronik.

Damit ist die Systemarchitektur funktional getrennt.

---

# 14. Verhältnis zum separaten Fan-Driver Unit 0x04

Die Firmware unterstützt zusätzlich:

```text
Unit 0x04
FC03 1011…1024
```

als separaten Fan-Motor-Driver-Pfad.

Dieser Pfad kann Lüfter-Istwerte direkt in dieselben Runtime-Felder schreiben, aus denen Mainboard 2074/2075 entstehen.

Bei der realen untersuchten Anlage:

- Unit `0x01` benutzt den H33-erweiterten 16/51-Wort-Dialog,
- Unit `0x04` wird zwar gepollt,
- eine Unit-`0x04`-Antwort wurde im Mitschnitt nicht beobachtet.

Das spricht dafür, dass die Lüfter bei dieser Variante über den integrierten Unit-`0x01`-Driver laufen.

---

# 15. Noch offene Kompressor-/Inverterpunkte

1. Remote-Reg. 2000 Modi `1` und `3` offiziell benennen.
2. Remote-Reg. 2002 vollständig zurückverfolgen.
3. C04 → Remote-Reg. 2003 Modellcodetabelle rekonstruieren.
4. Unit-1-Reg. 2099–2149 vollständig benennen.
5. Inverter-/Driver-Fehlerbits und Abschaltursachen kartieren.
6. Kommunikationstimeouts des Mainboards bis zu öffentlichen Alarmbits verfolgen.
7. physische Inverterplatine/P-N identifizieren.
8. internen Modbus-UART bis USART/GPIO/RS485-Transceiver verfolgen.
9. prüfen, welche Schutzentscheidungen das Unit-0x01-Board zusätzlich autonom trifft.

---

# 16. Verwandte Dokumente

- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) – vollständiger interner Adress-/Boardplan
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) – Berechnung der Fan-Sollwerte vor Übergabe an das Driverboard
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) – Oil-Return-Sonderfrequenz
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md) – Gesamtübersicht

---

# 17. Zusammengefasste Provenance

```text
Temperatur-/Betriebsregelung
        ↓
Kompressorfrequenzregler
        ↓
C-Parameter / Limits / Sonderzustände
        ↓
0x20016AA4+0x08
        ↓
Mainboard 2071
        ↓
Unit 0x01 Remote 1999
        ↓
Inverter-/Leistungsboard
        ↓
Verdichtermotor
        ↓
Unit 0x01 Remote 2102ff
        ↓
0x200168C4
        ↓
Mainboard 2072/2073, Strom, AC/DC usw.
```

Damit ist die Kompressoransteuerung vom Regelalgorithmus bis zur physischen Leistungsboard-Schnittstelle geschlossen.
