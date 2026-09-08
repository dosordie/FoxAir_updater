# Mainboard-Firmware V3.3 – MAIN:2139 Frequenzbegrenzungs-/Schutzstatus

Stand: 8. September 2026

Dieses Dokument untersucht `MAIN:2139` der Mainboard-Firmware `82400644 / V3.3` und enthält einen klar gekennzeichneten V3.4-Nachtrag für neu geschlossene höhere Bits.

Frühere Audits konnten das Register nur als aktives, aber fachlich unbekanntes Statuswort klassifizieren. Die inzwischen rekonstruierten Writer zeigen, dass `MAIN:2139` mehrere **Frequenzbegrenzungs- und Schutzzustände** sammelt.

Bewertung:

- **bestätigt** – Quelle und Schutzsemantik im jeweils genannten Binary geschlossen
- **sehr wahrscheinlich** – Datenpfad stark geschlossen, letzte Herstellerbezeichnung offen
- **offen** – Bit existiert bzw. kann gesetzt werden, fachliche Bedeutung noch nicht belastbar geschlossen

---

# 1. Kurzfazit

Aktuell sind folgende Bits geschlossen:

| Bit | Maske | Bedeutung | Pumpen-Override 100 % | Quelle |
|---:|---:|---|---|---|
| 0 | `0x0001` | noch offen | offen | V3.3 |
| 1 | `0x0002` | übermäßige T01/T02-Wasserspreizung / A24-Schutz | **ja, bestätigt** | V3.3 |
| 2 | `0x0004` | noch offen | offen | V3.3 |
| 3 | `0x0008` | A27 Temperaturdifferenz-Frequenzbegrenzung | direkte Pumpenkopplung nicht separat bestätigt | V3.3 |
| 4 | `0x0010` | Niederdruck-Frequenzbegrenzung | **ja, bestätigt** | V3.3 |
| 5 | `0x0020` | AC-Eingangsstrom-Frequenzbegrenzung | direkte Pumpenkopplung nicht separat bestätigt | V3.3 |
| 6 | `0x0040` | Abgastemperatur-/Discharge-Frequenzbegrenzung | **ja, bestätigt** | V3.3 |
| **8** | **`0x0100`** | **SG-/Zusatzheizungs-Koordination: relatives Verdichterfrequenzlimit über MAIN:1422 aktiv** | **nicht nachgewiesen** | **V3.4** |

Damit ist `MAIN:2139` kein klassisches Fehlerwort im Sinn „Störung vorhanden/Anlage aus“, sondern ein Sammelstatus für aktive Schutz- bzw. Leistungsbegrenzungszustände.

---

# 2. Bit1 – übermäßige Wasser-Spreizung / A24

Interne Quelle:

```text
0x20016D2C + 0x0B
```

Die zugehörige State-Machine bildet die absolute Differenz der beiden Wasserkanäle:

```text
abs(T_out - T_in)
```

und vergleicht sie gegen:

```text
MAIN:1044 / A24
= Excess Temp. Diff. Between inlet and Outlet Temp.
```

Der interne Zustand ist hysteretisch bzw. mehrstufig (`0/1/2`). Sobald er aktiv ist, wird:

```text
MAIN:2139 Bit1 = 1
```

und der Pumpenregler geht auf:

```text
MAIN:2115 = 100 %
```

mit Löschung der Auto-PWM-Qualifikation.

**Bewertung: bestätigt.**

---

# 3. Bit3 – A27 Temperaturdifferenz-Frequenzbegrenzung

Der zugehörige Schutzpfad verwendet:

```text
MAIN:1056 / A27
= Temp Difference A Of Limiting Frequency
```

Der aktive Zustand wird als:

```text
MAIN:2139 Bit3
```

publiziert.

Damit ist die Herstellerfunktion dieses Bits als temperaturdifferenzabhängige Frequenzbegrenzung geschlossen.

Für diesen Bitpfad wurde im bisherigen Pumpen-Audit **keine eigenständige direkte 100-%-Pumpenkopplung** nachgewiesen. Das ist wichtig, weil nicht automatisch jedes gesetzte `2139`-Bit die Umwälzpumpe beeinflusst.

**Bewertung: Semantik bestätigt.**

---

# 4. Bit4 – Niederdruck-Frequenzbegrenzung

Interne Quelle:

```text
0x20016E24 + 0x02
```

Messgröße:

```text
MAIN:2069 / T15
= Niederdruck
```

Schwellenparameter:

```text
MAIN:1342 / A38
= Low Pressure of Limiting Frequency
```

Bei aktivem Zustand:

```text
MAIN:2139 Bit4 = 1
```

Derselbe interne Status wird direkt von der Pumpenroutine geprüft:

```text
0x20016E24+0x02 != 0
-> MAIN:2115 = 100 %
-> 10-min-Auto-PWM-Qualifikation löschen
```

Damit koppelt V3.3 den Niederdruck-Limiter nicht nur an die Verdichterfrequenz, sondern erzwingt gleichzeitig maximalen Wasserdurchsatz.

**Bewertung: bestätigt.**

---

# 5. Bit5 – AC-Eingangsstrom-Frequenzbegrenzung

Messgröße:

```text
MAIN:2057 / T35
= AC Input Current
```

Die Limit-State-Machine vergleicht den aktuellen Eingangsstrom mit einem intern bestimmten Stromlimit.

Erkennbar sind gestaffelte Eingriffs-/Halte-/Rückkehrschwellen um ungefähr:

```text
100 %
90 %
80 %
```

des Limits sowie eine Entprellung von 20 Zyklen.

Der aktive Zustand wird als:

```text
MAIN:2139 Bit5
```

publiziert.

Seit dem V3.4-Hardwareaudit ist zusätzlich bestätigt, dass `MAIN:1343 / A39 = Max. Current Value` über `0x200162D8+0x5C` direkt als `INV1:TX:2002` an das Inverter-/Leistungsboard übertragen wird. Damit ist A39 ein zentraler statischer Stromlimit-/Driverparameter; `MAIN:2057` bleibt die reale AC-Eingangsstrom-Rückmeldung für den laufenden Limiter.

Im bisherigen Pumpen-Xref-Audit wurde für Bit5 keine separate direkte Vollpumpenbedingung nachgewiesen. Das Bit ist daher sicher ein Frequenz-Limiterstatus, aber nicht automatisch ein Pumpen-Override.

**Bewertung: V3.3-Limiter bestätigt; A39→INV1:2002 zusätzlich in V3.4 bestätigt.**

---

# 6. Bit6 – Abgastemperatur-/Discharge-Frequenzbegrenzung

Interne Quelle:

```text
0x20016D2C + 0x09 Bit0
```

Messgröße:

```text
MAIN:2053 / T12
= Abgas-/Discharge-Temperatur
```

Die Schutzlogik wird erst nach einer Laufzeit-/Regelfreigabe ausgewertet und besitzt Hysterese.

Bei aktivem Zustand:

```text
MAIN:2139 Bit6 = 1
```

Derselbe interne Zustand ist außerdem eine direkte Vollpumpenbedingung:

```text
0x20016D2C+0x09 Bit0 = 1
-> MAIN:2115 = 100 %
-> Auto-PWM-Qualifikation löschen
```

**Bewertung: bestätigt.**

---

# 7. V3.4-Nachtrag: Bit8 – SG-/Zusatzheizungs-Koordination

V3.4 packt den internen Zustand:

```text
0x20016A44 + 0x09 != 0
```

als:

```text
MAIN:2139 |= 0x0100
→ MAIN:2139 Bit8 = 1
```

Dieser Zustand ist mit einem echten Verdichter-Frequenzlimit gekoppelt.

## 7.1 MAIN:1422 als relative Grenze

```text
MAIN:1422
Live: 0x20016A24 + 0x00
Factory-Default V3.4: 70
```

Der Limiter berechnet sinngemäß:

```text
F_limit = MAIN:1422 × F_ref / 100
```

und klemmt das Ergebnis anschließend zwischen:

```text
dynamische Mindestfrequenz
und
C03 / maximale Kompressorfrequenz
```

`F_ref` ist die A26-/T04-/T02-abhängige 100-%-Referenzfrequenz, die in `FW3.4-HARDWARE-KONFIGURATION.md` vollständig dokumentiert ist.

## 7.2 Herkunft des Zustands

Die zugehörige State-Machine verwendet unter anderem:

```text
MAIN:1049 / A31  Electric Heater On AT
MAIN:1050 / A32  Electric Heater Delays Comp. On Time
MAIN:1063 / A33  Electric Heater Opening Temp. Diff
MAIN:1031 / A35  Electric Heater Off Temp. Diff
MAIN:1032 / H18  Electric Heater Energy Stage
```

und besitzt einen aktiven Pfad für:

```text
SG-Ready Mode 4 / High PV
```

Damit lautet die derzeit belastbare Arbeitsbezeichnung:

> **Bit8 = SG-/Zusatzheizungs-Koordination: relatives Verdichterfrequenzlimit über MAIN:1422 aktiv.**

Der Writer des Bits und der Frequenzlimit-Datenfluss sind bestätigt. Die originale PHNIX-Bitbezeichnung und die vollständige Zuordnung der benachbarten internen Zustände `0x20016A44+8/+9/+A` zu den physischen E-Heizer-Ausgängen bleiben offen.

**Bewertung: Datenfluss bestätigt; Herstellerwortlaut offen.**

---

# 8. Zusammenhang zur Pumpenregelung

Mindestens drei der V3.3-geschlossenen `MAIN:2139`-Schutzzustände besitzen eine direkte Kopplung zum 100-%-Pumpenpfad:

```text
Bit1  Wasser-ΔT/A24
Bit4  Niederdruck-Limiter
Bit6  Abgastemperatur-Limiter
```

Die Wirkung lautet jeweils sinngemäß:

```text
Schutzzustand aktiv
-> Verdichterleistung begrenzen
und gleichzeitig
-> Wasserpumpe 100 %
-> Auto-PWM-Qualifikation verwerfen
```

Das ist thermodynamisch plausibel: Bei kritischen Zuständen versucht V3.3 zusätzlich, den maximal verfügbaren Wasserdurchsatz bereitzustellen.

Nicht für jedes `2139`-Bit ist diese Pumpenkopplung bestätigt. Insbesondere Bit3, Bit5 und das neue V3.4-Bit8 sind aktuell als Frequenz-Limiterstatus geschlossen, aber **nicht** als eigenständige Pumpen-Overridequelle.

Details zum Pumpenpfad:

[`FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md`](FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md)

---

# 9. Offene Bits

Noch nicht fachlich geschlossen:

```text
MAIN:2139 Bit0
MAIN:2139 Bit2
```

Außerdem können abhängig von Anlagenvariante/Optionen weitere höhere Bits relevant sein. Diese werden nicht ohne Writer-/Verbrauchernachweis benannt.

Für die offenen Bits sollten als nächstes die Writer des internen `2139`-Sammelworts einzeln rückwärts verfolgt und gegen folgende Kandidaten abgeglichen werden:

- Hochdruck-Frequenzbegrenzung,
- Inverter-/IPM-Temperaturbegrenzung,
- Spannungs-/Versorgungsbegrenzung,
- weitere Verdampfung/Kondensation-bezogene Temperatur-Limiter.

Diese Kandidaten sind ausdrücklich **noch keine Zuordnungen**.

---

# 10. Status

| Aussage | Bewertung |
|---|---|
| `MAIN:2139` ist ein Frequenzbegrenzungs-/Schutzstatuswort | bestätigt |
| Bit1 = übermäßige Wasser-Spreizung / A24 | bestätigt V3.3 |
| Bit3 = A27 Temperaturdifferenz-Limiter | bestätigt V3.3 |
| Bit4 = Niederdruck-Limiter | bestätigt V3.3 |
| Bit5 = AC-Eingangsstrom-Limiter | bestätigt V3.3 |
| Bit6 = Abgastemperatur-Limiter | bestätigt V3.3 |
| **Bit8 = SG-/Zusatzheizungs-Koordination, relatives Limit über MAIN:1422** | **bestätigt V3.4 für Writer/Limitpfad; Herstellerwortlaut offen** |
| Bit1/4/6 erzwingen zusätzlich 100 % Pumpen-PWM | bestätigt V3.3 |
| Bit3/5/8 erzwingen direkt 100 % Pumpen-PWM | bisher nicht nachgewiesen |
| Bit0 | offen |
| Bit2 | offen |

---

# 11. Verwandte Dokumente

- [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) – A26/T04/T02-Referenzkennfeld, A39, C04, MAIN:1422 und Hardwareprofile
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md`](FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
