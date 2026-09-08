# Mainboard-Firmware V3.3 – Kompressor- und Inverteransteuerung

Stand: 8. September 2026

Diese Datei dokumentiert die vollständige bisher rekonstruierte Kette von der Kompressor-Sollwertbildung im FoxAir-/PHNIX-Mainboard bis zum externen Inverter-/Leistungsboard Unit `0x01` und zurück. Am Ende befindet sich ein **V3.4-Nachtrag**, der mehrere bisher offene Punkte schließt. V3.4-Codeadressen dürfen wegen der anderen Imagebasis nicht als V3.3-Adressen gelesen werden.

Untersuchtes V3.3-Binary:

```text
Produkt-/Softwarekennung: 82400644
Firmware:                 V3.3
Größe:                    287598 Byte
MD5:                      CEB6A4BF386FF644E23E410023E74673
SHA-256:                  6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:               0x08050000
```

Bewertung:

- **bestätigt** – direkt im jeweiligen Binary bzw. zusätzlich im realen Busverkehr nachgewiesen
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

Dieser Wert wird öffentlich als Register `2071` bereitgestellt und unmittelbar an Unit `0x01` gesendet.

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

Bestätigte C-Parameter im Liveblock `0x20016B20`:

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

Zusätzliche Sonderpfade können diese normale Sollwertbildung vorgeben bzw. übersteuern, beispielsweise Abtauung, Ölrückführung, Schutz-/Derating-Zustände sowie Factory-/Manual-Betrieb.

---

# 4. Beispiel Ölrückführung

Die Oil-Return-State-Machine setzt bei aktiver Ölrückführung nominal `60 Hz` als Kompressoranforderung.

Auch dieser Sonderwert läuft anschließend durch die gemeinsame Ausgangskette und landet bei:

```text
0x20016AA4+0x08
→ Register 2071
→ Unit 0x01 / Register 1999
```

Das bestätigt, dass Unit `0x01` der gemeinsame Endpunkt sowohl für normale Regelung als auch für Sonderzustände ist.

---

# 5. Modbus-Master-Scheduler

Der Unit-`0x01`-Dialog ist Bestandteil des festen internen V3.3-Schedulers um:

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

Der V3.3-Modbus-Request-Builder liegt bei `0x080695F0`.

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

## H33 != 0

```text
FC10 1999, 16 Wörter
FC03 2099, 51 Wörter
```

Die zusätzlichen Register enthalten Fan-Driver-Sollwerte und -Rückmeldungen.

Der reale Mitschnitt zeigt die H33-integrierte 16/51-Wort-Variante. **Bewertung: bestätigt.**

---

# 7. FC10-Sollwertpaket an Unit 0x01

Sendepuffer V3.3:

```text
0x2001232C
```

## 7.1 Remote-Register 1999 – Kompressor-Sollfrequenz

```text
0x20016AA4+0x08
→ INV1:TX:1999
```

**Bewertung: bestätigt.**

## 7.2 Remote-Register 2000 – Run-/Mode-Wort

Bytegenau:

```text
wenn Sollfrequenz == 0:
    Reg. 2000 = 0

wenn Sollfrequenz != 0 und internes Flag 0x20016FBA == 0:
    Reg. 2000 = 1

wenn Sollfrequenz != 0 und internes Flag 0x20016FBA != 0:
    Reg. 2000 = 3
```

Die Funktion als Run-/Mode-Kommando ist bestätigt; die offizielle Bedeutung der Modi `1` und `3` bleibt offen.

## 7.3 Remote-Register 2001

```text
Reg. 2001 = 0
```

im normalen beobachteten Pfad. Offizielle Funktion offen.

## 7.4 Remote-Register 2002 – Maximalstrom A39

Früher war lediglich die Quelle bekannt:

```text
0x200162D8 + 0x5C
```

Der V3.4-Audit hat den Parameterpfad vollständig geschlossen:

```text
MAIN:1343 / A39
= Max. Current Value / Maximaler Stromwert
      ↓
0x200162D8 + 0x5C
      ↓
INV1:TX:2002
```

Damit gilt:

> **INV1:TX:2002 = vom Mainboard an den Inverter übertragener A39-Maximalstrom-/Stromlimitwert.**

A39 ist im Registerkatalog als `AMP_X2` definiert, also `A = RAW / 2` für die Bedien-/Katalogdarstellung. Eine spezielle Empfängersemantik für A39=0 ist noch nicht belegt.

**Bewertung: in V3.4 bestätigt; die RAM-Struktur ist gegenüber V3.3 gleich.**

## 7.5 Remote-Register 2003 – Driver-/Kompressormodellcode

Quelle ist C04:

```text
0x20016B20 + 0x06
```

Wenn C04 ungleich null ist:

```text
INV1:TX:2003 = C04 + 0x083A
```

sonst `0`.

Beispiel:

```text
C04 = 13
→ INV1:TX:2003 = 2119
```

Der vollständige V3.4-Xref-Audit findet **keine lokale C04→Kompressordaten-Tabelle auf dem Mainboard**. C04 wird hier im Wesentlichen als opaque Driver-/Kompressormodell-Selektor behandelt.

Daher beweist der zulässige C04-Bereich `0..99` nicht 100 physische Verdichtertypen. Die konkrete Modell-/Motorparametertabelle sitzt sehr wahrscheinlich im Unit-1-Driver.

**Bewertung: Transport/Transformation bestätigt; konkrete C04→Verdichterzuordnung offen.**

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

Für V3.3 stammen die beiden Fan-Sollwerte aus:

```text
2008 ← 0x20016F0A
2009 ← 0x20016F0C
```

V3.4 verwendet im entsprechenden Schedulerpfad dagegen:

```text
2008 ← 0x20016F18
2009 ← 0x20016F1A
```

Das ist ein wichtiger Versionsunterschied bei **internen RAM-Adressen**, nicht bei den Remote-Registern.

V3.4 schließt zusätzlich die F01-Selektoren:

```text
MAIN:1059 / F01 == 3 → Driver-Selektor 1
MAIN:1059 / F01 == 4 → Driver-Selektor 2
```

Details stehen in `FW3.3-LUEFTERREGELUNG.md` und `FW3.4-HARDWARE-KONFIGURATION.md`.

---

# 9. FC03-Telemetrie von Unit 0x01

Der Scheduler liest:

```text
Slave 0x01
FC03
Start 2099
```

Die Antwortwörter werden in `0x200168C4` überführt.

| Unit-1-Register | internes Ziel | Funktion |
|---:|---:|---|
| 2099 | `0x200168C4+0x00` | noch offen |
| 2100 | `+0x02` | Driver Fault Word 1 / in öffentlichen Fehlerpfad |
| 2101 | `+0x04` | noch offen |
| 2102 | `+0x06` | Kompressor-Istfrequenz |
| 2103 | `+0x08` | maximale Inverter-/Kompressorfrequenz |
| 2104 | `+0x0A` | IPM-/Temperaturgrenzwertpfad |
| 2105 | `+0x0C` | AC-Eingangsspannung |
| 2106 | `+0x0E` | AC-Eingangsstrom |
| 2107 | `+0x10` | Kompressor-Phasenstrom |
| 2108 | `+0x12` | DC-Bus-Spannung |

Öffentliche Hauptpfade:

```text
Unit1-Reg2102 → MAIN:2072
Unit1-Reg2103 → MAIN:2073
Unit1-Reg2105 → MAIN:2062
Unit1-Reg2106 → MAIN:2057
Unit1-Reg2107 → MAIN:2042
Unit1-Reg2108 → MAIN:2043
```

**Bewertung: bestätigt.**

---

# 10. Plausibilisierung mit realem Bus

Bei stillstehendem Verdichter wurden unter anderem beobachtet:

```text
2102 = 0
2105 ≈ 228…229
2106 = 2
2108 ≈ 313…315
```

Passend zu:

```text
Istfrequenz       0 Hz
AC-Spannung       ~229 V
kleiner Eingangsstrom
DC-Zwischenkreis  ~313 V
```

---

# 11. Öffentlicher Kompressorstatus 2019 Bit 0

`MAIN:2019 Bit0` wird aus:

```text
0x200168C4 + 0x06 != 0
```

gebildet und zeigt damit tatsächlichen vom Driver gemeldeten Verdichterlauf.

Diagnostisch:

```text
2071 > 0, 2072 = 0
```

bedeutet: Mainboard fordert an, Inverter meldet noch keinen realen Lauf.

---

# 12. Diagnose der Verbindung zum Leistungsboard

Normaler H33=1-Zyklus:

```text
Mainboard → 0x01: FC10 Start 1999, 16 Wörter
0x01 → Mainboard: FC10 ACK
Mainboard → 0x01: FC03 Start 2099, 51 Wörter
0x01 → Mainboard: FC03 Antwort, 51 Wörter
```

Damit lassen sich Kommunikationsprobleme von Regel-/Driverproblemen trennen.

---

# 13. Wo endet die Mainboardregelung und wo beginnt der Inverter?

## Regelmainboard

verantwortlich für:

- Betriebsart
- Temperaturregelung
- Kompressor-Sollfrequenz
- C02/C03 und dynamische Frequenzgrenzen
- Abtau-Sollwerte
- Oil Return
- Schutz-/Derating-Vorgaben
- Fan-Sollwerte
- A26-abhängige Maschinenreferenz und relative Frequenzlimits

## Unit-0x01-Leistungsboard

verantwortlich für:

- Umsetzung des Frequenzsollwertes in reale Motorleistung
- Inverter-/IPM-Leistungselektronik
- DC-Zwischenkreis
- Messung von Strömen und Spannungen
- Rückmeldung der tatsächlichen Frequenz
- Interpretation des C04-Driverprofils
- Interpretation des A39-Maximalstromwertes
- bei H33=1 zusätzlich Fan-Motor-Driver-Kommunikation/-Leistungselektronik

---

# 14. Verhältnis zum separaten Fan-Driver Unit 0x04

Die Firmware unterstützt zusätzlich:

```text
Unit 0x04
FC03 1011…1024
```

als separaten Fan-Motor-Driver-Pfad.

Dieser Pfad kann Lüfter-Istwerte direkt in dieselben Runtime-Felder schreiben, aus denen MAIN:2074/2075 entstehen.

Bei der real untersuchten Anlage läuft der H33-erweiterte Unit-1-Pfad; Unit 0x04 wurde gepollt, antwortete im beobachteten Mitschnitt aber nicht.

---

# 15. Noch offene Kompressor-/Inverterpunkte

1. Remote-Reg. 2000 Modi `1` und `3` offiziell benennen.
2. C04 → konkrete Verdichter-/Motortyp-Tabelle auf der Unit-1-Seite rekonstruieren.
3. Unit-1-Reg. 2099–2149 vollständig benennen.
4. Inverter-/Driver-Fehlerbits und Abschaltursachen vollständig kartieren.
5. physische Inverterplatine/P-N identifizieren.
6. prüfen, welche Schutzentscheidungen das Unit-0x01-Board zusätzlich autonom trifft.
7. Empfängersemantik von A39=0 auf dem Unit-1-Board klären.

Der frühere offene Punkt **„Remote-Reg. 2002 vollständig zurückverfolgen“ ist geschlossen**: `INV1:TX:2002 = MAIN:1343 / A39 Max. Current Value`.

---

# 16. Verwandte Dokumente

- [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) – Hardwareparameter, A26-Maschinenprofile, C04, A39, MAIN:1422
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md)
- [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)

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

---

# 18. V3.4-Nachtrag – A26-Maschinenreferenz, DIAG 6023 und MAIN 1422

Die V3.4-Analyse schließt einen zusätzlichen, für die Hardware-/Leistungsklassifikation wichtigen Pfad.

## 18.1 A26 ist mehr als der Kältemittelname

`MAIN:1054 / A26` wird einerseits über `A26 % 2` für R32/R290-Stoffdaten ausgewertet:

```text
0,2,4,6 → R32-Familie
1,3,5,7 → R290-Familie
```

Andererseits wählt der **volle A26-Wert 0..7** eines von acht `7×8`-Maschinenkennfeldern.

Die Achsen sind bestätigt:

```text
7 Zeilen  = T04 Außentemperatur
8 Spalten = T02 Auslass-/Vorlaufwassertemperatur
```

Der Tabellenwert bildet eine Referenzfrequenz:

```text
F_ref = 30 Hz + Index × 6 Hz
```

Details und vollständige Tabellen: `FW3.4-HARDWARE-KONFIGURATION.md`.

## 18.2 F_ref ist 100-%-Maschinenreferenz, nicht direkter Sollwert

V3.4 benutzt `F_ref` sowohl zur Diagnose als auch für echte relative Frequenzlimits.

Diagnose:

```text
DIAG:6023 ≈ MAIN:2072 / F_ref × 100
```

`DIAG:6023` selbst hat keinen nachgewiesenen Rückverbrauch in EEV-, Fan-, COP- oder Leistungsregelung.

Regelung:

```text
F_limit = Prozent × F_ref / 100
```

anschließend:

```text
dynamische Mindestfrequenz <= F_limit <= C03
```

## 18.3 MAIN:1422

`MAIN:1422` liegt bei:

```text
0x20016A24 + 0x00
Factory-Default V3.4 = 70
```

und wird in einem SG-Ready-/Zusatzheizungs-Koordinationspfad als Prozentwert benutzt:

```text
F_limit = MAIN:1422 % × F_ref
```

Der zugehörige Aktivstatus ist:

```text
0x20016A44+0x09
→ MAIN:2139 Bit8
```

Die State-Machine berücksichtigt A31/A32/A33/A35, H18 und einen SG-Ready-Mode-4-/High-PV-Pfad. `MAIN:1422` ist daher **kein statischer GL7/GL9/GL12-Hardwareparameter**.

## 18.4 Konsequenz für die Maschinenkonfiguration

Die eigentliche Hardware-/Leistungsklasse ergibt sich nach jetzigem Stand aus einer Kombination von:

```text
C04  Verdichter-/Driverprofil
A26  Kältemittel + Maschinenreferenzkennfeld
C03  maximale Frequenz
A39  maximales Stromlimit
Fxx  Lüfterhardware/-kennlinien
H33  Driverarchitektur
A40  Nenn-Wasserdurchfluss
```

Ein einzelnes Mainboardregister „Nennheizleistung 7/9/12 kW“ wurde nicht gefunden.

**Bewertung: V3.4-Datenflüsse bestätigt; konkrete GL-Leistungsklassen-Zuordnung noch offen.**
