# Mainboard-Firmware V3.3 – MAIN:2139 Frequenzbegrenzungs-/Schutzstatus

Stand: 28. August 2026

Dieses Dokument untersucht `MAIN:2139` der Mainboard-Firmware `82400644 / V3.3`.

Frühere Audits konnten das Register nur als aktives, aber fachlich unbekanntes Statuswort klassifizieren. Die inzwischen rekonstruierten Writer zeigen, dass `MAIN:2139` mehrere **Frequenzbegrenzungs- und Schutzzustände** sammelt.

Bewertung:

- **bestätigt** – Quelle und Schutzsemantik im V3.3-Binary geschlossen
- **sehr wahrscheinlich** – Datenpfad stark geschlossen, letzte Herstellerbezeichnung offen
- **offen** – Bit existiert bzw. kann gesetzt werden, fachliche Bedeutung noch nicht belastbar geschlossen

---

# 1. Kurzfazit

Aktuell sind folgende Bits geschlossen:

| Bit | Maske | Bedeutung | Pumpen-Override 100 % |
|---:|---:|---|---|
| 0 | `0x0001` | noch offen | offen |
| 1 | `0x0002` | übermäßige T01/T02-Wasserspreizung / A24-Schutz | **ja, bestätigt** |
| 2 | `0x0004` | noch offen | offen |
| 3 | `0x0008` | A27 Temperaturdifferenz-Frequenzbegrenzung | direkte Pumpenkopplung nicht separat bestätigt |
| 4 | `0x0010` | Niederdruck-Frequenzbegrenzung | **ja, bestätigt** |
| 5 | `0x0020` | AC-Eingangsstrom-Frequenzbegrenzung | direkte Pumpenkopplung nicht separat bestätigt |
| 6 | `0x0040` | Abgastemperatur-/Discharge-Frequenzbegrenzung | **ja, bestätigt** |

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

Im bisherigen Pumpen-Xref-Audit wurde für Bit5 keine separate direkte Vollpumpenbedingung nachgewiesen. Das Bit ist daher sicher ein Frequenz-Limiterstatus, aber nicht automatisch ein Pumpen-Override.

**Bewertung: bestätigt.**

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

# 7. Zusammenhang zur Pumpenregelung

Mindestens drei der geschlossenen `MAIN:2139`-Schutzzustände besitzen eine direkte Kopplung zum 100-%-Pumpenpfad:

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

Nicht für jedes `2139`-Bit ist diese Pumpenkopplung bestätigt. Insbesondere Bit3 und Bit5 sind aktuell als Frequenz-Limiterstatus geschlossen, aber nicht als eigenständige Pumpen-Overridequelle.

Details zum Pumpenpfad:

[`FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md`](FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md)

---

# 8. Offene Bits

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

# 9. Status

| Aussage | Bewertung |
|---|---|
| `MAIN:2139` ist ein Frequenzbegrenzungs-/Schutzstatuswort | bestätigt |
| Bit1 = übermäßige Wasser-Spreizung / A24 | bestätigt |
| Bit3 = A27 Temperaturdifferenz-Limiter | bestätigt |
| Bit4 = Niederdruck-Limiter | bestätigt |
| Bit5 = AC-Eingangsstrom-Limiter | bestätigt |
| Bit6 = Abgastemperatur-Limiter | bestätigt |
| Bit1/4/6 erzwingen zusätzlich 100 % Pumpen-PWM | bestätigt |
| Bit3/5 erzwingen direkt 100 % Pumpen-PWM | bisher nicht nachgewiesen |
| Bit0 | offen |
| Bit2 | offen |
