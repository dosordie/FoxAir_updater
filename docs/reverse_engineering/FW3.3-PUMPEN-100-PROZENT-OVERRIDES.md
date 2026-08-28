# Mainboard-Firmware V3.3 – Pumpen-Overrides auf 100 % PWM

Stand: 28. August 2026

Diese Datei dokumentiert die in der Mainboard-Firmware `82400644 / V3.3` rekonstruierten Bedingungen, die den normalen automatischen Pumpenregler übersteuern und die Haupt-Umwälzpumpe auf **100 % logische PWM** setzen.

Untersuchtes Binary:

```text
Softwarecode:   82400644
Firmware:       V3.3
Imagebasis:     0x08050000
Pumpenroutine:  0x08084474
```

Bewertung:

- **bestätigt** – Datenpfad und Wirkung direkt im V3.3-Binary geschlossen
- **sehr wahrscheinlich** – Writer/Verbraucher und Parameterbezug schließen die fachliche Funktion weitgehend, letzte Herstellerbezeichnung fehlt
- **offen** – Wirkung bestätigt, fachliche Bedeutung noch nicht ausreichend geschlossen

---

# 1. Gemeinsamer Vollpumpenpfad

Der zentrale Override-Zielpfad liegt ungefähr bei:

```text
raw 0x348F2
VA  0x080848F2
```

Wenn eine vorgeschaltete Override-Bedingung aktiv wird, setzt V3.3:

```text
Pumpenruntime +0x0A = 120   ; 60-s-P12-Regelzähler sofort auf fällig
Pumpenruntime +0x02 = 100   ; logische Pumpen-Soll-PWM
Pumpenruntime +0x09 = 0     ; 10-min-Auto-Qualifikation löschen
```

Damit ist die Wirkung stärker als nur „vorübergehend 100 %“:

> **Ein Override erzwingt 100 % Pumpenleistung und verwirft gleichzeitig die bereits erreichte Auto-PWM-Qualifikation.**

`Pumpenruntime +0x02` wird anschließend als `MAIN:2115` veröffentlicht.

Nach Wegfall eines solchen Overrides kann daher eine erneute Qualifikationsphase erforderlich sein, bevor die normale P11/P12-Auto-Regelung die Pumpe wieder absenken darf.

**Bewertung: bestätigt.**

---

# 2. Übersicht der bekannten 100-%-Auslöser

| Auslöser | Rohquelle / Bezug | Wirkung | Bewertung |
|---|---|---|---|
| aktiver Abtau-/Defrostzustand | `0x2001660C+0x20`, Bits 2..3; führt zu `MAIN:2012=2` | 100 %, Requalifikation | **bestätigt** |
| Sterilisation/Pasteurisierung | `0x20016658+0x0E`; führt zu `MAIN:2012=3` | 100 %, Requalifikation | **bestätigt** |
| Warmwasserbetrieb | `0x2001660C+0x20`, Bit 7; führt zu `MAIN:2012=4` | 100 %, Requalifikation | **bestätigt** |
| Wasser-Temperaturkanal A ungültig | `0x20015FA8+0x04` über Helper `0x0808795C` | 100 %, Requalifikation | **bestätigt** |
| Wasser-Temperaturkanal B ungültig | `0x20015FA8+0x0A` über Helper `0x08087992` | 100 %, Requalifikation | **bestätigt** |
| erforderliche Run-/Regelfreigabe fehlt | `0x20016E0C+0x03`, Bit 1 | 100 %, Requalifikation | **sehr wahrscheinlich** |
| `A40 == 0` | `MAIN:1344`, `0x20016C9C+0x0A` | 100 %, Requalifikation | **bestätigt** |
| kein gültiger Durchfluss | `0x20016FAC == 0` | 100 %, Requalifikation | **bestätigt** |
| unmittelbares Temperatur-Plausibilitätsgate verletzt | Runtime-Mode 0/1, Wasser-T02, A23 bzw. Sollwert | 100 %, Requalifikation | **bestätigt**, Modusname teilweise offen |
| Niederdruck-Frequenzbegrenzung aktiv | `0x20016E24+0x02`; `MAIN:2139 Bit4` | 100 %, Requalifikation | **bestätigt** |
| übermäßige T01/T02-Wasserspreizung / A24-Schutz | `0x20016D2C+0x0B`; `MAIN:2139 Bit1` | 100 %, Requalifikation | **bestätigt** |
| hydraulischer Frostschutzstatus aktiv | `0x20016BC8+0x0F` | 100 %, Requalifikation | **sehr wahrscheinlich** |
| Winter-Frostschutz Stufe 1/2 aktiv | `0x20016214+0x01`, Bits 1..2 | 100 %, Requalifikation | **bestätigt** |
| Abgastemperatur-Frequenzbegrenzung aktiv | `0x20016D2C+0x09`, Bit0; `MAIN:2139 Bit6` | 100 %, Requalifikation | **bestätigt** |
| Elektroheizung Stufe 1 aktiv | GPIOE PE12 / O08 / `MAIN:2019 Bit7` | 100 %, Requalifikation | **bestätigt** |
| Elektroheizung Stufe 2 aktiv | GPIOE PE13 / O09 / `MAIN:2019 Bit8` | 100 %, Requalifikation | **bestätigt** |
| Hydraulikmodul-E-Heizung Wasserkreis aktiv | `0x20016BE0+0x0E`, Bit3 / O22 | 100 %, Requalifikation | **bestätigt** |
| Hydraulikmodul-E-Heizung WW-Tank aktiv | `0x20016BE0+0x0E`, Bit4 / O23 | 100 %, Requalifikation | **bestätigt** |
| Außentemperatur-Hysterese aktiv | Pumpenruntime `+0x07`, T04 20/22 °C | 100 %, Requalifikation | **bestätigt** |
| falsche ΔT-Richtung länger ca. 30 s | Pumpenruntime `+0x01` | 100 %, Requalifikation | **bestätigt** |
| 10-min-Auto-Qualifikation noch nicht erreicht | Pumpenruntime `+0x09 == 0` | 100 % im Auto-Pfad | **bestätigt** |
| sehr frühe Laufphase | `0x20016AA4+0x06 < 60` | 100 % | **bestätigt**, genaue Zeitbasis dieses Feldes separat betrachten |
| finales Pumpen-/Hydraulikgate nicht freigegeben | H30-abhängig: `0x20016BE0+0x0E Bit0` oder GPIOC Maske `0x0002` | 100 % | **bestätigt**, Detailsemantik siehe Abschnitt 13 |

---

# 3. Betriebszustände, die Auto-PWM absichtlich abschalten

## 3.1 Abtau-/Defrostzustand

Der Byteblock:

```text
0x2001660C + 0x20
```

wird sowohl in der Pumpenroutine als auch beim Aufbau des öffentlichen Betriebsstatus verwendet.

Für:

```text
Bits 2..3 != 0
```

setzt die Firmware den öffentlichen Betriebszustand auf:

```text
MAIN:2012 = 2
```

Dieser Wert entspricht dem aktiven **Abtau-/Defrostzustand**.

Gleichzeitig führt derselbe Zustand im Pumpenregler auf den Vollpumpenpfad:

```text
Defrost aktiv
-> MAIN:2115 = 100 %
-> Auto-PWM-Qualifikation löschen
```

Damit ist die frühere Bezeichnung „Betriebs-/Sonderzustand offen“ geschlossen.

**Bewertung: bestätigt.**

## 3.2 Sterilisation / Pasteurisierung

Das Feld:

```text
0x20016658 + 0x0E
```

wird im Statusbuilder unmittelbar zur Erzeugung von:

```text
MAIN:2012 = 3
```

verwendet.

`2012=3` ist der Sterilisations-/Pasteurisierungsbetrieb. Derselbe interne Zustand wird im Pumpenregler geprüft:

```text
Sterilisation/Pasteurisierung aktiv
-> 100 % Pumpen-PWM
-> Auto-Qualifikation löschen
```

**Bewertung: bestätigt.**

## 3.3 Warmwasserbetrieb

Im selben zentralen Betriebsbitblock gilt:

```text
0x2001660C+0x20 Bit7 = 1
```

Dieser Zustand führt im Statusbuilder zu:

```text
MAIN:2012 = 4
```

und entspricht dem aktiven Warmwasserbetrieb.

Im Pumpenregler bewirkt Bit7:

```text
Warmwasserbetrieb aktiv
-> 100 % Pumpen-PWM
-> Auto-Qualifikation löschen
```

Damit ist die frühere Vermutung „Bit7 = Sonder-/Abtauzustand“ korrigiert: **Bit7 gehört zum Warmwasserlauf; der Defrostzustand liegt in Bits 2..3.**

**Bewertung: bestätigt.**

---

# 4. Elektroheizungen erzwingen Vollpumpenbetrieb

## 4.1 PE12 / O08 = Elektroheizung Stufe 1

Die Pumpenroutine liest GPIOE und prüft:

```text
PE12 / Maske 0x1000
```

Die Statusabbildung ordnet diesen Pin der ersten Elektroheizstufe zu:

```text
O08 / Electric heater stage 1
MAIN:2019 Bit7
```

Ist die Stufe aktiv, wird Auto-PWM gesperrt und die Hauptpumpe auf 100 % gefahren.

## 4.2 PE13 / O09 = Elektroheizung Stufe 2

Analog:

```text
PE13 / Maske 0x2000
O09 / Electric heater stage 2
MAIN:2019 Bit8
```

Auch dieser Zustand erzwingt 100 % Pumpen-PWM.

Wichtig: PE12/PE13 sind damit **keine unbekannten externen Override-Klemmen**, sondern die Hardwarezustände der beiden elektrischen Heizstufen.

## 4.3 Hydraulikmodul O22/O23

Bei Hydraulikmodul-Konfigurationen prüft die Firmware zusätzlich:

```text
0x20016BE0+0x0E Bit3
0x20016BE0+0x0E Bit4
```

Zuordnung:

```text
Bit3 = O22 / elektrische Heizung Wasserkreis
Bit4 = O23 / elektrische Heizung Warmwasserspeicher
```

Wenn einer dieser Heizpfade aktiv ist:

```text
-> 100 % Pumpen-PWM
-> Auto-PWM-Requalifikation
```

**Bewertung für PE12/PE13 und O22/O23: bestätigt.**

---

# 5. Frostschutzpfade

## 5.1 Winter-Frostschutz Stufe 1/2

Das Statusfeld:

```text
0x20016214+0x01
```

wird im Pumpenregler auf Bits 1..2 geprüft:

```text
Bits 1..2 != 0
-> 100 % Pumpen-PWM
```

Die Writer-/State-Machine-Zuordnung ergibt hier die beiden Winter-Frostschutzstufen.

Damit gilt:

> **Aktiver Winter-Frostschutz hat Vorrang vor der normalen Delta-T-Pumpenregelung.**

**Bewertung: bestätigt.**

## 5.2 Hydraulischer Antifreeze-/Frostschutzstatus

Das Byte:

```text
0x20016BC8+0x0F
```

wird ebenfalls direkt als Vollpumpenbedingung geprüft.

Seine Writer hängen an der Frostschutzlogik um:

```text
MAIN:1038 / A04 = Antifreeze Temp.
MAIN:1039 / A05 = Antifreeze Temp. Difference
```

und an einer Wasser-/Hydrauliktemperatur.

Damit ist die frühere Klassifikation als „internes unbekanntes Betriebsflag“ zu eng. Der Datenpfad passt zu einer hydraulischen Frostschutzanforderung.

**Bewertung: sehr wahrscheinlich Frostschutz-/Antifreeze-Status; exakter interner Herstellername offen.**

---

# 6. Ungültige Wasser-Temperaturkanäle

Die beiden Helper:

```text
0x0808795C -> 0x20015FA8+0x04
0x08087992 -> 0x20015FA8+0x0A
```

liefern Valid-/Fehlerzustände der beiden Wasser-Temperaturkanäle, die die Pumpenregelung für ihre Spreizungsberechnung benötigt.

Wenn einer der Kanäle ungültig ist:

```text
-> 100 % PWM
-> Auto-Qualifikation löschen
```

Damit ist der Regler fail-safe: Ohne belastbare T01/T02-Basis darf die Pumpe nicht automatisch abgesenkt werden.

**Bewertung: bestätigt.**

---

# 7. Durchfluss als Freigabe- und Schutzgröße

## 7.1 A40 muss gültig sein

```text
MAIN:1344 / A40
-> 0x20016C9C+0x0A
```

Wenn:

```text
A40 == 0
```

wird Auto-PWM nicht freigegeben und der Vollpumpenpfad benutzt.

Das ist konsistent mit:

```text
10-min-Qualifikation: ca. 1,2 × A40
Fallback-Minimum:     ca. 0,8 × A40
```

## 7.2 Gültige Durchflussquelle erforderlich

```text
0x20016FAC == 0
-> kein gültiger Durchfluss
-> 100 % Pumpen-PWM
```

Das gilt unabhängig davon, ob der Durchfluss aus:

```text
H31/PWM-Rückmeldung
```

oder bei `H30=3` aus:

```text
HYD61:2047/2048
```

kommt.

Der nach `MAIN:1022` korrigierte Runtime-Durchfluss wird damit nicht nur angezeigt, sondern ist eine echte Freigabe-/Schutzgröße der Pumpenregelung.

**Bewertung: bestätigt.**

---

# 8. Wasser-ΔT-Schutzpfade

## 8.1 Falsche ΔT-Richtung länger ca. 30 s

Ein Zähler bei:

```text
0x20016FEC
```

zählt bis 60 Pumpentasks. Bei einer Taskperiode von 0,5 s entspricht das:

```text
60 × 0,5 s = 30 s
```

Bleibt die Wasser-Spreizung für die aktuelle Betriebsrichtung unplausibel, wird:

```text
Pumpenruntime +0x01 = 1
```

und damit:

```text
-> 100 % PWM
-> Requalifikation
```

**Bewertung: bestätigt.**

## 8.2 Übermäßige T01/T02-Wasserspreizung / A24

Das Feld:

```text
0x20016D2C+0x0B
```

wird aus der absoluten Wasser-Temperaturdifferenz gebildet:

```text
abs(T_out - T_in)
```

und gegen:

```text
MAIN:1044 / A24
= Excess Temp. Diff. Between inlet and Outlet Temp.
```

geführt.

Der Schutzstatus ist hysteretisch bzw. mehrstufig (`0/1/2`). Sobald er ungleich 0 ist:

```text
-> Pumpen-Override 100 %
```

Derselbe Zustand wird in `MAIN:2139` als **Bit1** gesammelt.

Damit ist geschlossen:

```text
MAIN:2139 Bit1
= übermäßige Ein-/Auslasswasser-Temperaturdifferenz / A24-Schutz
```

**Bewertung: bestätigt.**

## 8.3 Sofortige Temperatur-Plausibilitätsgates

Neben dem verzögerten ΔT-Schutz existieren zwei sofortige, runtime-mode-abhängige Temperaturgates.

Für einen Modus gilt sinngemäß:

```text
T02 <= berechneter Sollwert - 4,0 K
```

als Voraussetzung für Auto-PWM.

Für den anderen Modus wird T02 gegen:

```text
MAIN:1043 / A23
= Antifreeze Min Temp / Min. Auslasswassertemperatur-Schutz
```

mit einem 4-K-Abstand geprüft.

Die Rechenwege und die 4,0-K-Konstanten sind bestätigt. Die endgültige öffentliche Benennung des internen Mode-0/1-Feldes bleibt offen.

---

# 9. MAIN:2139 – Frequenzbegrenzungs-/Schutzstatus

`MAIN:2139` ist kein beliebiges unbekanntes Faultword. V3.3 sammelt dort mehrere aktive Schutz- und Frequenzbegrenzungszustände.

Aktuell geschlossene Bits:

| Bit | Maske | Bedeutung | direkte Pumpen-100-%-Kopplung |
|---:|---:|---|---|
| 1 | `0x0002` | übermäßige T01/T02-Wasserspreizung / A24-Schutz | **ja, bestätigt** |
| 3 | `0x0008` | A27 Temperaturdifferenz-Frequenzbegrenzung | Statussemantik bestätigt; direkte Pumpenkopplung separat nicht nachgewiesen |
| 4 | `0x0010` | Niederdruck-Frequenzbegrenzung | **ja, bestätigt** |
| 5 | `0x0020` | AC-Eingangsstrom-Frequenzbegrenzung | Statussemantik bestätigt; direkte Pumpenkopplung separat nicht nachgewiesen |
| 6 | `0x0040` | Abgastemperatur-/Discharge-Frequenzbegrenzung | **ja, bestätigt** |

Noch offen sind insbesondere Bit0 und Bit2 sowie gegebenenfalls höhere, nur unter speziellen Konfigurationen gesetzte Bits.

## 9.1 Bit4 – Niederdruck-Frequenzbegrenzung

Quelle:

```text
0x20016E24+0x02
```

Messgröße:

```text
MAIN:2069 / T15 = Niederdruck
```

Schwellenparameter:

```text
MAIN:1342 / A38
= Low Pressure of Limiting Frequency
```

Bei aktivem Limiter:

```text
MAIN:2139 Bit4 = 1
und
Pumpen-Override = 100 %
```

**Bewertung: bestätigt.**

## 9.2 Bit6 – Abgastemperatur-Frequenzbegrenzung

Quelle:

```text
0x20016D2C+0x09 Bit0
```

Messgröße:

```text
MAIN:2053 / T12 = Abgas-/Discharge-Temperatur
```

Der Zustand wird erst nach einer Laufzeitfreigabe bewertet und besitzt Hysterese.

Bei aktivem Limiter:

```text
MAIN:2139 Bit6 = 1
und
Pumpen-Override = 100 %
```

**Bewertung: bestätigt.**

## 9.3 Bit3 – A27 Temperaturdifferenz-Frequenzbegrenzung

Der zugehörige Schutzpfad verwendet:

```text
MAIN:1056 / A27
= Temp Difference A Of Limiting Frequency
```

und wird als:

```text
MAIN:2139 Bit3
```

publiziert.

**Bewertung: Semantik bestätigt.**

## 9.4 Bit5 – AC-Eingangsstrom-Frequenzbegrenzung

Die Messgröße ist:

```text
MAIN:2057 / T35 = AC Input Current
```

Die State-Machine arbeitet mit gestaffelten Schwellen um ungefähr:

```text
100 %
90 %
80 %
```

des internen Stromlimits und einer Entprellung von 20 Zyklen.

Der aktive Status wird als:

```text
MAIN:2139 Bit5
```

publiziert.

**Bewertung: bestätigt.**

---

# 10. Run-/Regelfreigabe

Die Pumpenroutine prüft:

```text
0x20016E0C+0x03 Bit1
```

Wenn dieses Bit nicht gesetzt ist:

```text
-> 100 % PWM
```

Dasselbe Bit wird auch von weiteren Limiter-/Qualifikationspfaden als Laufzeit-/Regelfreigabe benutzt.

Damit ist sicher:

> **Die automatische Pumpenabsenkung ist nur in einem freigegebenen aktiven Betriebszustand erlaubt.**

Der exakte PHNIX-interne Name des Bits ist noch nicht geschlossen. „Run-/Regelfreigabe“ ist daher eine Funktionsbeschreibung und kein bestätigter Herstellertext.

**Bewertung: Wirkung bestätigt, fachliche Bezeichnung sehr wahrscheinlich.**

---

# 11. Außentemperatur-Hysterese 20/22 °C

Ein Pumpenruntimeflag `+0x07` wird in einem bestimmten Runtime-Modus über T04/Außentemperatur geführt:

```text
T04 < 20,0 °C   -> Flag = 1
T04 >= 22,0 °C  -> Flag = 0
20,0..21,9 °C   -> Zustand halten
```

Wenn das Flag aktiv ist:

```text
-> 100 % Pumpen-PWM
```

Die Hysterese selbst ist bestätigt; die endgültige fachliche Bezeichnung des betroffenen internen Betriebsmodus bleibt offen.

---

# 12. Weitere 100-%-Pfade nach dem Haupt-Gate

Auch nach dem zentralen Override-Gate existieren weitere Vollpumpenbedingungen:

1. unerwarteter/nicht unterstützter Runtime-Modus außerhalb der vorgesehenen Werte 0/1,
2. interner Lauf-/Zeitwert `0x20016AA4+0x06 < 60`,
3. noch nicht abgeschlossene 10-min-Qualifikation (`Pumpenruntime +0x09 == 0`),
4. feste/Factory-/Sondervorgaben,
5. finale Plausibilitätsbegrenzung: Werte außerhalb `1..100` werden auf 100 % gesetzt.

Damit gilt diagnostisch:

```text
P10 = 0
MAIN:2115 = 100
```

nicht automatisch als Fehler. 100 % ist in zahlreichen normalen Start-, Sonder-, Schutz- und Qualifikationszuständen ausdrücklich vorgesehen.

---

# 13. Finales Hardware-/Hydraulikgate

Nahe der endgültigen Hardware-PWM-Ausgabe existiert ein weiteres H30-abhängiges Gate.

Je nach Hydraulikarchitektur wird entweder:

```text
0x20016BE0+0x0E Bit0
```

oder ein physischer GPIOC-Zustand mit:

```text
Maske 0x0002
```

verwendet.

Das GPIOC-Signal lässt sich dem Haupt-Wasserpumpenpfad/O05 zuordnen. Es handelt sich damit nicht um einen beliebigen externen Sensor, sondern um die lokale Pumpen-/Hydraulikfreigabe bzw. den zugehörigen Hardwarezustand.

Wenn die erwartete Freigabe fehlt, setzt die Firmware die Pumpenvorgabe auf 100 %.

**Bewertung: Pumpen-/Hydraulikbezug bestätigt; exakter Signalname für alle H30-Varianten offen.**

---

# 14. Praktische Gesamtaussage

Die V3.3-Pumpenregelung ist bewusst konservativ und fail-safe aufgebaut. Eine Absenkung unter 100 % ist nur zulässig, wenn gleichzeitig unter anderem gilt:

```text
- normaler Heiz-/Kühl-Regelzustand, kein Defrost/WW/Pasteurisierung
- keine aktive elektrische Zusatzheizung
- kein Frostschutz-Sonderzustand
- gültige T01/T02-Wasserkanäle
- plausible Wasser-Spreizung
- gültiger Durchfluss
- A40 != 0
- erforderliche Run-/Regelfreigabe aktiv
- keine relevanten Frequenzbegrenzungs-/Schutzflags
- keine 20/22-°C-Sperre im betreffenden Modus
- keine 30-s-ΔT-Richtungsstörung
- 10-min-Auto-PWM-Qualifikation abgeschlossen
```

Das erklärt insbesondere, warum `MAIN:2115` nach Start, Abtauung, Warmwasser, Pasteurisierung, E-Heizerbetrieb, Frostschutz oder Schutzlimitierungen längere Zeit 100 % bleiben kann, obwohl `P10=0` eingestellt ist.

---

# 15. Korrigierte Zuordnungen gegenüber dem ersten Audit

Die folgenden vorher offenen bzw. falsch vermuteten Einträge sind jetzt geschlossen:

```text
0x2001660C+0x20 Bits2..3
-> Defrost / MAIN:2012=2

0x20016658+0x0E
-> Sterilisation/Pasteurisierung / MAIN:2012=3

0x2001660C+0x20 Bit7
-> Warmwasser / MAIN:2012=4

PE12
-> O08 / Elektroheizung Stufe 1 / MAIN:2019 Bit7

PE13
-> O09 / Elektroheizung Stufe 2 / MAIN:2019 Bit8

0x20016BE0+0x0E Bit3
-> O22 / E-Heizung Wasserkreis

0x20016BE0+0x0E Bit4
-> O23 / E-Heizung WW-Tank

0x20016214+0x01 Bits1..2
-> Winter-Frostschutz Stufe 1/2

0x20016D2C+0x0B
-> übermäßige T01/T02-Wasserspreizung / A24
-> MAIN:2139 Bit1

0x20016E24+0x02
-> Niederdruck-Frequenzbegrenzung
-> MAIN:2139 Bit4

0x20016D2C+0x09 Bit0
-> Abgastemperatur-Frequenzbegrenzung
-> MAIN:2139 Bit6
```

---

# 16. Verbleibende offene Restpunkte

Nach diesem Audit bleiben nur noch wenige fachliche Restpunkte:

1. `MAIN:2139 Bit0` – Quelle/Schutzart noch nicht abschließend benannt.
2. `MAIN:2139 Bit2` – Quelle/Schutzart noch nicht abschließend benannt.
3. mögliche höhere `MAIN:2139`-Bits in Sonderkonfigurationen.
4. exakter PHNIX-interner Herstellername von `0x20016E0C+0x03 Bit1`.
5. endgültige öffentliche Benennung des internen Pumpen-`mode=0/1` für die beiden unmittelbaren Temperatur-Plausibilitätsgates.
6. exakter interner Name von `0x20016BC8+0x0F`; der Bezug zur A04/A05-Frostschutzlogik ist stark, aber der Herstellertext noch nicht gefunden.
7. Detailname des H30-abhängigen finalen Pumpen-/Hydraulikgates.

Die für den praktischen Betrieb wichtigsten 100-%-Overrideursachen sind damit jedoch weitgehend geschlossen.
