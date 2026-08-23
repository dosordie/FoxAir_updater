# Mainboard-Firmware V3.3 – EEV-, Smart- und Ventilantriebsregelung

Stand: 23. August 2026

Diese Datei dokumentiert die EEV-Regelung der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3` im Detail. Sie ergänzt [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md).

Die Firmware ist für die Imagebasis `0x08050000` gelinkt. Alle hier genannten Codeadressen verwenden diese korrigierte Basis.

## Bewertungsstufen

- **bestätigt** – direkt im Binary bzw. in der Registertabelle nachgewiesen
- **sehr wahrscheinlich** – Datenfluss ist geschlossen, letzte Hersteller-/Sensorbezeichnung fehlt
- **offen** – Zuordnung ist noch nicht vollständig beweisbar

> Terminologie: In der Firmware und Registerliste heißt das Ventil **EEV (Electronic Expansion Valve)**. `E01=1` heißt offiziell **Auto**. Wenn praktisch von „Normal“ gegenüber „Smart“ gesprochen wird, entspricht „Normal“ hier dem Auto-Modus.

---

# 1. Gesamtarchitektur

Der Haupt-EEV-Pfad lässt sich inzwischen von den Parametern bis zu den realen Motorphasen verfolgen:

```text
E01 / Betriebszustand
        ↓
Heiz-/Kühl-Superheat-Sollwert E02/E18
        ↓
5-Sample-Istwertfilter / Superheat-Regler
        ↓
20-Zustands-Regelmatrix
        ↓
Auto-EEV-Sollwert
        ↓
bei E01=2 zusätzlich:
Smart-Kennfeld (Verdichterfrequenz × Außentemperatur)
        ↓
Skalierung nach Einlasswassertemperatur
        ↓
Smart-Mittelpunkt
        ↓
E19-Fenster um Smart-Mittelpunkt
        ↓
gemeinsame Mindest-/Schutzgrenzen
        ↓
max. 480 Schritte
        ↓
EEV-Ziel 0x20016AC4+2
        ↓
Stepper-State-Machine 0x08054592
        ↓
interne Istposition 0x20016AC4+4
        ↓
8-Phasen-Halbschrittfolge
        ↓
GPIOD PD9…PD12
```

Das separate EVI-/Economizer-EEV besitzt einen parallelen Laufzeitblock und Motortreiber, aber **keinen Smart-Modus**.

---

# 2. Parameter E01…E19

EEV-Parameterblock:

```text
0x200169E4
```

| Register | Parameter | Offset | Funktion | Default |
|---:|---|---:|---|---:|
| 1131 | E01 | `+0x00` | Haupt-EEV-Modus: `0=Manuell, 1=Auto, 2=Smart` | 1 |
| 1132 | E02 | `+0x02` | Ziel-Superheat Heizen | 5,0 °C |
| 1133 | E03 | `+0x04` | Anfangsschritte Heizen | 350 |
| 1137 | E07 | `+0x06` | Mindestschritte Haupt-EEV | 100 |
| 1138 | E08 | `+0x08` | Anfangsschritte Kühlen | 200 |
| 1139 | E09 | `+0x0A` | EVI-EEV-Modus: `0=Manuell, 1=Auto` | 1 |
| 1140 | E10 | `+0x0C` | EVI-EEV Anfangsschritte | 350 |
| 1143 | E13 | `+0x0E` | EVI Ziel-Superheat | 3,0 °C |
| 1144 | E14 | `+0x10` | EVI Mindestschritte | 100 |
| 1147 | E17 | `+0x12` | Haupt-EEV-Schritte beim Abtauen | 480 |
| 1148 | E18 | `+0x14` | Ziel-Superheat Kühlen | 3,0 °C |
| 1149 | E19 | `+0x16` | Smart-Korrekturbereich in Prozent | 20 % |

Die Initialisierung um `0x080521AC` setzt diese Defaults auch im RAM.

Hinter E19 liegen im Live-Block zusätzlich drei interne Werte:

```text
+0x18 = 180
+0x1A = 200
+0x1C = 150
```

Sie werden auf diese Werte zurückgesetzt, falls sie 0 sind. Ihre offiziellen externen Parameternamen sind noch **offen**; sie dürfen nicht einfach den Registern 1150–1152 zugeordnet werden.

Weitere Register aus Display/Registermapping, deren genaue RAM-Provenienz noch nicht vollständig geschlossen ist:

```text
1141  reserviert e03-4, Default 125
1142  reserviert e03-2, Default 185
1200  E03-1, Initial Steps Heating1, Default 250
1215  E07-4, EEV min Steps4, Default 90
1216  E07-5, EEV min Steps5, Default 85
```

---

# 3. Laufzeitstruktur des Haupt-EEV

Hauptstruktur:

```text
0x20016AC4
```

Bestätigte Felder:

| Offset | Typ | Bedeutung |
|---:|---|---|
| `+0x00` | byte | Flags; Bit 0 wird bei Änderung/Clamp des Zielwerts gesetzt |
| `+0x02` | uint16 | **EEV-Zielposition in Schritten** |
| `+0x04` | uint16 | **intern geführte tatsächliche Schrittmotorposition** |
| `+0x06` | byte | Regler-/Smart-Zykluszähler |
| `+0x07` | byte | Stepper-Cadence-Zähler |
| `+0x08` | byte | Warte-/Richtungswechselzähler |
| `+0x09` | byte | Initialisierungs-/Homing-State |
| `+0x0A` | byte | aktuelle Bewegungsrichtung |
| `+0x0C` | byte | Hilfs-/Reglerzustand, unter anderem vom dynamischen Regler verwendet |
| `+0x10` | float | 5-Sample-Mittel des Haupt-Superheat-/Differenzwerts |
| `+0x14` | float | 5-Sample-Mittel des zweiten/EVI-Differenzwerts |
| `+0x18` | float | Akkumulator für Hauptwert |
| `+0x1C` | float | Akkumulator für zweiten/EVI-Wert |

Der zentrale EEV-Regelblock liegt ungefähr bei:

```text
0x08059980 … 0x0805B1F4
```

Der reale Motortreiber beginnt bei:

```text
0x08054592
```

**Bewertung: bestätigt.**

---

# 4. Bildung der gemessenen Superheat-/Differenzwerte

Im Bereich ungefähr `0x080597BC…0x080599AC` werden temperaturbasierte Differenzwerte zunächst in Fließkomma umgerechnet und akkumuliert.

Für beide Kanäle gilt:

```text
Summe += aktueller Differenzwert
Samplecounter++

nach 5 Samples:
    Mittelwert = Summe / 5.0
    Summe = 0
```

Gespeichert werden:

```text
0x20016AC4+0x10  Hauptkanal
0x20016AC4+0x14  zweiter/EVI-Kanal
```

Die Verwendung von `+0x10` in der Haupt-EEV-Regelung bestätigt funktional, dass es sich um den maßgeblichen Ist-Superheat-/Differenzwert des Hauptventils handelt. `+0x14` gehört sehr wahrscheinlich zum EVI-EEV-Pfad.

Die genaue Auswahl der zugrunde liegenden Temperatursensoren wechselt teilweise mit Heiz-/Kühl-/Sonderzuständen und ist noch nicht in jedem Zweig physikalisch benannt.

**Hauptfunktion: bestätigt; vollständige Sensor-Provenienz aller Sonderzweige: offen.**

---

# 5. Manual – E01 = 0

Modusabfragen befinden sich unter anderem bei:

```text
0x08059A1C
0x08059B36
```

Bei `E01=0` wird die normale geschlossene Superheat-Regelung übersprungen.

Grundwerte:

```text
Heizen → E03
Kühlen → E08
```

Manual bedeutet trotzdem nicht „Motorwert unter allen Umständen unverändert“. Abtauung, Homing, Sicherheits-/Mindestöffnungen, Start-/Recoveryzustände und die harte Maximalgrenze können weiterhin eingreifen.

**Bewertung: bestätigt.**

---

# 6. Auto / „Normal“ – E01 = 1

Auto ist der normale geschlossene Superheat-Regler.

Sollwerte:

```text
Heizen → E02
Kühlen → E18
```

Der Regler klassifiziert seinen Zustand über zwei Achsen:

```text
0x20016FA9  4 Zustände 0…3
0x20016FA8  5 Zustände 0…4
```

und kombiniert sie zu:

```text
state = (FA9 << 4) | FA8
```

Der Dispatcher ab `0x0805A6D4` kennt exakt 20 Kombinationen:

```text
00 01 02 03 04
10 11 12 13 14
20 21 22 23 24
30 31 32 33 34
```

Damit handelt es sich um eine 4×5-Regelmatrix.

## 6.1 FA9 – Superheat-Band

`0x20016FA9` wird aus dem Haupt-Mittelwert `0x20016AC4+0x10` und einer kleinen Schwellwerttabelle klassifiziert.

Tabelle bei:

```text
0x08092730
```

als Bytes wiederholt:

```text
15, 35, 45, 10, 30, 35
```

Die konkrete Auswahl hängt vom Betriebs-/Konfigurationspfad ab. Die Achse ist aufgrund des Datenflusses **sehr stark als Haupt-Superheat-Band bestätigt**.

## 6.2 FA8 – zusätzliche Schutz-/Temperaturachse

`0x20016FA8` ist eine 5-stufige Klassifikation eines signed Werts aus dem Sensor-/Messblock:

```text
0x20015FA8 + 0x66
```

Schwellwerttabelle bei:

```text
0x080926AC
```

mit Varianten:

```text
60, 70, 80, 90
60, 70, 80, 95
```

Die Variable wirkt wie eine zusätzliche thermische/Schutzgröße, ist aber noch **nicht sicher einem konkreten physikalischen Sensor oder Druck-/Temperaturwert zugeordnet**.

## 6.3 Aktionen der 20 Zustände

Direkt bestätigte harte Schrittänderungen sind unter anderem:

```text
State 00 → -8 oder -4 Schritte
State 01 → -6 oder -2 Schritte
State 02 → bis -4 Schritte
State 03 → bis -2 Schritte
State 04 → keine direkte Korrektur
State 34 → bis +8 Schritte
```

Die mittleren Matrixbereiche verwenden zusätzlich den dynamischen Korrekturhelper:

```text
0x080548A4
```

Teilweise wird dessen Eingang vorher um `-1` oder `-2` verschoben. Damit ist die vollständige Matrix keine einfache feste Tabelle `±N`, sondern kombiniert harte Randkorrekturen mit einem kontinuierlicheren dynamischen Regler.

Strukturell bestätigt:

| FA9 \ FA8 | 0 | 1 | 2 | 3 | 4 |
|---:|---|---|---|---|---|
| 0 | stark schließen `-8/-4` | schließen `-6/-2` | schließen bis `-4` | schließen bis `-2` | neutral |
| 1 | dynamischer Helper | dynamischer Helper | dynamischer Helper | dynamischer Helper | Helper mit verschobenem Eingang |
| 2 | Helper, Eingang -1 | Helper, Eingang -1 | Helper, Eingang -1 | Helper, Eingang -1 | Helper, Eingang -2 |
| 3 | Helper, Eingang -1 | Helper, Eingang -2 | Helper, Eingang -2 | Helper, Eingang -2 | stark öffnen bis `+8` |

**Bewertung: Matrix und direkte Randaktionen bestätigt.** Die exakte physikalische Benennung der FA8-Achse bleibt offen.

## 6.4 Dynamischer Helper 0x080548A4

Der Helper erhält zwei Fließkommawerte und bildet zunächst:

```text
error = input2 - input1
```

Er verwendet zusätzliche signed Konfigurations-/Gainwerte aus einem Parameterblock und internen Zuständen. Im Funktionsverlauf sind Fehlerzonen um ungefähr:

```text
-5, -3, -2, +2, +3, +5
```

sichtbar.

Er besitzt:

- einen mehrstufigen Fehler-/Gain-Pfad,
- interne gespeicherte Reglerwerte bei `0x20016EB0` und `0x20016EB4`,
- eine Änderungsbegrenzung des gespeicherten Werts auf ungefähr `±5` je Aktualisierung,
- eine interne Korrekturbegrenzung von ungefähr `-60…+60`,
- abschließende Begrenzung gegen den gültigen EEV-Bereich bis 480 Schritte.

Der Helper ist damit ein dynamischer, zustandsbehafteter Korrekturregler und nicht nur eine feste Schritt-Lookup-Tabelle.

**Bewertung: Verhalten bestätigt; exakte Herstellerbezeichnung/PID-Terminologie offen.**

---

# 7. Smart – E01 = 2: Grundprinzip

Smart verwendet **weiterhin das Ergebnis der normalen Superheat-Regelung**. Es ersetzt den Auto-Regler nicht.

Zusätzlich erzeugt Smart einen lastabhängigen Vorsteuer-Arbeitspunkt:

```text
Verdichter-Sollfrequenz
       ×
Außentemperatur
       ↓
4×6-Grundkennfeld
       ↓
Skalierung nach Einlasswassertemperatur
       ↓
Smart-Mittelpunkt
       ↓
Auto-Sollwert auf Mittelpunkt ± E19 % begrenzen
```

Der dynamische Smart-Mittelpunkt wird gespeichert bei:

```text
0x20016F4E
```

**Bewertung: bestätigt.**

---

# 8. Smart-Achse 1 – Außentemperatur, 6 Zustände

Statebyte:

```text
0x20016FC5
```

Sensorhelper:

```text
0x0808799C
```

Dieser Helper ist im Sensorblock als **T04 / Außentemperatur / Register 2048** identifiziert.

Sensor-Validity/Fehlerhelper:

```text
0x080879C8
```

Bei ungültigem Außentemperatursensor wird Smart-State 5 erzwungen.

State-Machine ungefähr:

```text
0x08059D98 … 0x08059EBA
```

Exakte Übergänge in Rohwerten `/10 °C`:

```text
State 0:
  AT >= -12,9 °C → 1

State 1:
  AT >= -6,9 °C  → 2
  AT <  -14,9 °C → 0

State 2:
  AT >= +0,1 °C  → 3
  AT <  -8,9 °C  → 1

State 3:
  AT >= +7,1 °C  → 4
  AT <  -1,9 °C  → 2

State 4:
  AT >= +20,1 °C → 5
  AT <  +5,1 °C  → 3

State 5:
  AT < +18,1 °C  → 4
```

Damit entstehen sechs deutlich hysteretische Außentemperaturbereiche.

Bei Sensorfehler wird State 5 verwendet. Dass dies als bewusstes Fail-safe-Verhalten gedacht ist, ist **sehr wahrscheinlich**; das Verhalten selbst ist bestätigt.

---

# 9. Smart-Achse 2 – Verdichter-Sollfrequenz, 4 Zustände

Statebyte:

```text
0x20016FC4
```

Quelle ist die Sollfrequenz aus:

```text
0x20016AA4+0x08
```

entsprechend Register 2071.

State-Machine ungefähr:

```text
0x08059F76 … 0x0805A024
```

Exakt:

```text
State 0:
  f >= 46 Hz → 1

State 1:
  f >= 61 Hz → 2
  f <  44 Hz → 0

State 2:
  f >= 76 Hz → 3
  f <  59 Hz → 1

State 3:
  f < 74 Hz  → 2
```

Praktisch also ungefähr:

```text
State 0  unter ~45 Hz
State 1  ~45…60 Hz
State 2  ~60…75 Hz
State 3  ab ~75 Hz
```

mit Hysterese.

**Bewertung: bestätigt.**

---

# 10. Smart-Grundkennfeld 4×6

Das Kennfeld liegt fest im Flash bei:

```text
0x080925C0
```

48 Byte = 24 `uint16`-Werte.

Zeilen = Verdichterfrequenz-State 0…3.  
Spalten = Außentemperatur-State 0…5.

| Frequenz-State \ AT-State | 0 | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|---:|
| **0** | 52 | 58 | 66 | 85 | 100 | 155 |
| **1** | 60 | 75 | 85 | 115 | 135 | 210 |
| **2** | 65 | 85 | 100 | 140 | 160 | 250 |
| **3** | 80 | 98 | 125 | 170 | 190 | 320 |

Lookup:

```text
base = table[freq_state][ambient_state]
```

Das Kennfeld öffnet das Ventil grundsätzlich weiter bei höherer Verdichterlast und – in diesem Kennfeld – überwiegend bei wärmerer Außentemperatur.

**Werte und Lookup: bestätigt.** Die regelungstechnische Interpretation als Massenstrom-/Last-Vorsteuerung ist **sehr wahrscheinlich**.

---

# 11. Smart-Achse 3 – Einlasswassertemperatur, 4 Zustände

Statebyte:

```text
0x20016FC3
```

Sensorhelper:

```text
0x08087930
```

= **T01 Einlasswassertemperatur / Register 2045**.

Validity-Helper:

```text
0x0808795C
```

Bei ungültigem T01 wird State 1, also der neutrale Faktor 1,0, erzwungen.

State-Machine ungefähr:

```text
0x08059EC2 … 0x08059F76
```

Exakte Übergänge:

```text
State 0:
  T01 >= 20,1 °C → 1

State 1:
  T01 > 30,0 °C  → 2
  T01 < 18,1 °C  → 0

State 2:
  T01 > 40,0 °C  → 3
  T01 <= 28,0 °C → 1

State 3:
  T01 <= 38,0 °C → 2
```

Die Zustände multiplizieren den zuvor aus Frequenz × Außentemperatur gewählten Kennfeldwert:

```text
State 0 → × 1,2
State 1 → × 1,0
State 2 → × 0,9
State 3 → × 0,8
```

Die Fließkommakonstanten `1.2`, `0.9` und `0.8` sind direkt im Binary vorhanden.

Damit gilt:

```text
smart_center = table[freq_state][ambient_state] × water_factor
```

und das Ergebnis wird nach Integer-Konvertierung bei `0x20016F4E` gespeichert.

**Bewertung: vollständig bestätigt.**

---

# 12. E19 – exaktes Smart-Regelfenster

Der Smart-only-Block ab ungefähr:

```text
0x0805ADFA
```

prüft erneut ausdrücklich:

```text
E01 == 2
```

und verwendet:

```text
Smart-Mittelpunkt = 0x20016F4E
E19               = 0x200169E4+0x16
```

Exakte Mathematik:

```text
ratio = E19 / 100.0

lower = smart_center × (1.0 - ratio)
upper = smart_center × (1.0 + ratio)

wenn lower > 0 und Auto_Target < lower:
    Target = lower

wenn Target > upper:
    Target = upper
```

Mit Default E19 = 20 %:

```text
Target ∈ [0,8 × smart_center ; 1,2 × smart_center]
```

Beispiel:

```text
smart_center = 300
E19          = 20 %

zulässig     = 240…360 Schritte
```

## 12.1 Randfälle von E19

Direkt aus der Mathematik:

```text
E19 = 0
→ lower = upper = smart_center
→ normaler Auto-Regler wird praktisch auf den Smart-Mittelpunkt festgeklemmt

E19 = 100
→ lower = 0
→ upper = 2 × smart_center

E19 > 100
→ rechnerische untere Grenze wird negativ
→ wegen des Guards `lower > 0` greift keine negative Untergrenze
→ obere Smart-Grenze bleibt wirksam
```

Der in der Registertabelle erlaubte Bereich `0…300 %` ist damit tatsächlich durch den Code sinnvoll erklärbar.

**Bewertung: bestätigt.**

---

# 13. Wichtige Konsequenz: Smart ist nicht die letzte Begrenzungsstufe

Nach dem E19-Fenster folgen gemeinsame Schutzregeln. Smart darf daher nicht als alleinige endgültige Ventilbegrenzung betrachtet werden.

Grundsätzlich gilt weiterhin:

```text
Target >= E07 bzw. zusätzliche temperaturabhängige Mindestöffnung
Target <= 480
```

Ein später Schutzblock ungefähr `0x0805B090…0x0805B1F4` kann bei bestimmten Betriebs-/Frequenzbedingungen die Öffnung auf einen höheren Mindestwert anheben.

Die Mindestöffnung wird dabei abhängig von T04/Außentemperatur aus fünf verschiedenen Quellen gewählt:

```text
AT < -9,9 °C  → Mindestwert aus 0x200167A4+0x2C
AT < -4,9 °C  → Mindestwert aus 0x20016744+0x2C
AT < +0,1 °C  → Mindestwert aus 0x20016B20+0x14
AT < +7,1 °C  → Mindestwert aus 0x20016B20+0x12
AT >= +7,1 °C → Mindestwert aus 0x20016B20+0x10
```

Ist der aktuelle EEV-Sollwert kleiner, wird er auf den jeweiligen Mindestwert angehoben.

Die Registertabelle bestätigt zusätzliche segmentierte EEV-Minimumparameter, unter anderem `E07-4` und `E07-5`. Die vollständige 1:1-Zuordnung aller fünf oben verwendeten RAM-Quellen zu offiziellen E07-x-Namen ist noch **offen**.

Danach erfolgt die harte Obergrenze:

```text
Target > 480 → Target = 480
```

**Bewertung: Schutzlogik bestätigt; offizielle Namen aller fünf Mindestparameter noch offen.**

---

# 14. Startöffnung und Außentemperatur-Fallback

Beim Start der normalen EEV-Regelung wird abhängig vom Betriebsmodus grundsätzlich gewählt:

```text
Heizen → E03
Kühlen → E08
```

Im Heizpfad existiert zusätzlich ein Fallback, wenn der primäre E03-Wert 0 ist. Dann wird die Startöffnung nach Außentemperatur gewählt.

Bestätigte Struktur:

```text
Außensensor ungültig → 200 Schritte
AT < -9,9 °C         → Wert aus 0x2001656C+0x4C
AT < -4,9 °C         → Wert aus 0x2001656C+0x4A
AT < +0,1 °C         → interner EEV-Wert +0x1C, Default 150
AT < +7,1 °C         → interner EEV-Wert +0x1A, Default 200
sonst                 → interner EEV-Wert +0x18, Default 180
```

Damit besitzt bereits der Startvorgang eine Außentemperatur-Vorsteuerung, auch unabhängig vom eigentlichen Smart-Kennfeld.

Die offiziellen Parameternamen der beiden Werte `0x2001656C+0x4A/+0x4C` und der drei internen Werte `+0x18/+0x1A/+0x1C` sind noch offen.

---

# 15. Sonderzustände und Abtauung

E17 / Register 1147 ist direkt als:

```text
EEV-Schritte beim Abtauen
Default = 480
```

hinterlegt.

Der Haupt-EEV-Regler enthält mehrere vorgelagerte bzw. nachgelagerte Zweige für:

- Abtauung,
- Start-/Anlaufzustände,
- Recovery,
- Sensorfehler,
- spezielle Betriebsflags.

Diese Pfade können den normalen Auto-/Smart-Sollwert umgehen oder überschreiben.

Unter anderem ist bestätigt:

- E17 wird im Abtaukontext verwendet,
- bestimmte Start-/Recoveryflags erzwingen feste bzw. initiale Öffnungen,
- in einem sensorfehlerabhängigen Sonderpfad kann eine feste Öffnung von 350 Schritten gesetzt werden,
- danach greifen weiterhin gemeinsame Mindest-/Maximalgrenzen.

Die exakten Herstellerbezeichnungen aller beteiligten internen Flags (`0x20016E0C`, `0x2001660C`, `0x20016F8C` u. a.) sind noch nicht vollständig aufgelöst.

---

# 16. Realer Haupt-EEV-Schrittmotor

Der berechnete Sollwert bleibt nicht abstrakt. Die Firmware besitzt eine eigene Stepper-State-Machine ab:

```text
0x08054592
```

Sie vergleicht:

```text
Sollposition = 0x20016AC4+0x02
Istposition  = 0x20016AC4+0x04
```

und bewegt die interne Istposition jeweils um einen Schritt in Richtung Sollposition.

## 16.1 Aufrufteilung

Der Zähler bei `+0x07` wird bei jedem Funktionsaufruf erhöht.

Erst bei:

```text
+0x07 >= 16
```

wird der eigentliche Stepper-Teil ausgeführt und der Zähler wieder 0 gesetzt.

Eine absolute Zeit pro Motorstep kann daraus noch **nicht** abgeleitet werden, weil die absolute Schedulerperiode dieses Aufrufs noch nicht separat bewiesen ist.

## 16.2 Richtungswechselpause

Bei einer Richtungsänderung wird:

```text
+0x08 = 25
```

gesetzt.

Solange dieser Zähler ungleich 0 ist, wird heruntergezählt und nicht weiter gesteppt. Damit besitzt der Treiber eine explizite Pause nach Richtungswechsel.

## 16.3 Richtung

`+0x0A` kodiert die Bewegungsrichtung:

```text
Richtung 1 → Istposition +1
Richtung 2 → Istposition -1
```

Bei erreichtem Sollwert wird die Richtung zurückgesetzt und nach einer Pause die Wicklungsansteuerung abgeschaltet.

**Bewertung: bestätigt.**

---

# 17. Homing / mechanischer Nullpunkt

Besonders interessant sind die Stepper-States 5 und 6.

Bei State 5 setzt die Firmware:

```text
Istposition = 0x226 = 550 Schritte
Sollposition = 0
State = 6
```

Danach fährt der normale Schritttreiber solange in Schließrichtung, bis intern Soll = Ist erreicht ist und keine Bewegung mehr ansteht. Anschließend wird die Istposition nochmals explizit auf 0 gesetzt und der State beendet.

Das Verhalten entspricht eindeutig einem **Überfahr-/Homingvorgang gegen den geschlossenen mechanischen Anschlag**:

```text
logische Position künstlich auf 550 setzen
→ 550 Schritte in Richtung „zu“
→ Ventil sicher mechanisch geschlossen
→ interne Position = 0
```

Da der normale Regelbereich maximal 480 Schritte beträgt, sind die 550 Schritte ein plausibler Überfahrweg zur Nullpunktkalibrierung.

**Verhalten: bestätigt. Bezeichnung als Homing/Nullpunktfahrt: sehr wahrscheinlich bis praktisch eindeutig.**

---

# 18. Hardwareausgänge des Haupt-EEV

Der Hauptventiltreiber schreibt direkt auf:

```text
GPIOD ODR = 0x4001140C
```

Betroffen sind:

```text
PD9
PD10
PD11
PD12
```

Der Code löscht diese Bits zunächst mit der Maske:

```text
0xE1FF
```

und setzt anschließend einen Wert aus einer 8-stufigen Halbschrittfolge bei:

```text
0x080927A0
```

Tabelle:

```text
0x0200
0x0600
0x0400
0x0C00
0x0800
0x1800
0x1000
0x1200
```

Das sind genau Bitkombinationen auf PD9…PD12.

Die Tabellenposition wird aus:

```text
Istposition mod 8
```

gebildet.

Damit ist die komplette Aktorkette bis auf die vier realen MCU-Pins geschlossen.

**Haupt-EEV Motorphasen = GPIOD PD9…PD12 – bestätigt.**

---

# 19. EVI-/Economizer-EEV

Das zweite Ventil besitzt einen parallelen Laufzeitblock:

```text
0x20016B04
```

Auch hier gelten unter anderem:

```text
+0x02 Zielposition
+0x04 interne Istposition
```

Der parallele Stepperpfad benutzt:

```text
GPIOE ODR = 0x4001180C
PE7…PE10
```

Maske:

```text
0xF87F
```

Halbschritttabelle bei:

```text
0x080927B0
```

```text
0x0080
0x0180
0x0100
0x0300
0x0200
0x0600
0x0400
0x0480
```

Damit:

```text
EVI-EEV Motorphasen = GPIOE PE7…PE10
```

**bestätigt.**

EVI besitzt über E09 nur:

```text
0 = Manuell
1 = Auto
```

Es gibt keinen EVI-Smart-Modus. E01/E19 und das 4×6-Smart-Kennfeld gelten nur für das Haupt-EEV.

---

# 20. Öffentliche EEV-Schrittwerte

Die Registertabelle benennt:

```text
2020 = EEV-Schritte
2022 = EVI EEV-Schritte
```

Im Statusaufbau um `0x080716F8` werden ausdrücklich die **internen Istpositionen `+0x04`** beider Ventilstrukturen gelesen:

```text
main:  [0x20016AC4 + 4]
EVI:   [0x20016B04 + 4]
```

und in den Statusblock übernommen.

Damit ist stark belegt, dass die öffentlich gemeldeten Ventilschritte die tatsächlich intern nachgeführte Motorposition und nicht nur den Regler-Sollwert repräsentieren. Die letzte 1:1-Provenance vom Statusblock bis zu Register 2020/2022 sollte für eine absolut formale Bestätigung noch separat geschlossen werden.

**Bewertung: sehr wahrscheinlich / nahezu bestätigt.**

---

# 21. Smart-Regelung als Gesamtformel

Der Kern lässt sich damit kompakt ausdrücken:

```text
ambient_state = hysteresis(T04)
freq_state    = hysteresis(compressor_target_hz)
water_state   = hysteresis(T01)

base = SMART_TABLE[freq_state][ambient_state]

water_factor = {
    0: 1.2,
    1: 1.0,
    2: 0.9,
    3: 0.8
}

smart_center = base × water_factor[water_state]

auto_target = result_of_normal_superheat_controller()

if E01 == 2:
    ratio = E19 / 100
    lower = smart_center × (1-ratio)
    upper = smart_center × (1+ratio)
    target = clamp(auto_target, lower_if_positive, upper)
else:
    target = auto_target

target = apply_operating_and_temperature_minimums(target)
target = min(target, 480)

stepper_move(actual_position, target)
```

Das ist die derzeit vollständigste aus V3.3 rekonstruierte Funktionsbeschreibung.

---

# 22. Auto vs. Smart – technische Bewertung

## Auto

```text
Superheat-Rückkopplung
→ 4×5-Regelzustandsmatrix
→ dynamischer Korrekturhelper
→ Schutzgrenzen
→ Ventil
```

Der Regler kann innerhalb der normalen Schutzgrenzen relativ frei auf den gemessenen Superheat reagieren.

## Smart

```text
Last-/Umgebungs-Vorsteuerung
  (Verdichterfrequenz × Außentemperatur × Wasserfaktor)
            +
normaler Superheat-Regler
            ↓
E19 begrenzt Abweichung vom Vorsteuer-Arbeitspunkt
            ↓
Schutzgrenzen
            ↓
Ventil
```

Smart ist damit eine **Kennfeld-Vorsteuerung mit weiterhin aktiver Feedbackregelung**.

Regelungstechnisch sehr wahrscheinlich beabsichtigt:

- Ventil früh in die Nähe des erwarteten Betriebspunkts bringen,
- große und langsame Suchbewegungen des Superheat-Reglers vermeiden,
- den möglichen Korrekturbereich um den Kennfeld-Arbeitspunkt definieren.

Die Kehrseite ergibt sich direkt aus dem Code: Ist der Kennfeld-Arbeitspunkt unter besonderen realen Anlagenbedingungen nicht optimal, kann E19 die normale Superheat-Regelung daran hindern, so weit vom Kennfeldwert wegzulaufen wie im Auto-Modus.

---

# 23. Was für einen realen Auto-vs.-Smart-Vergleich loggen wäre

Für eine spätere reale Validierung wären besonders aussagekräftig:

```text
E01
E19
Register 2020 EEV-Schritte
Register 2071 Kompressor-Sollfrequenz
Register 2072 Kompressor-Istfrequenz
Register 2045 T01 Einlasswasser
Register 2048 T04 Außentemperatur
relevante Kältemittel-/Superheat-Temperaturen
Heizen/Kühlen/WW/Abtau-State
```

Aus diesen Werten kann für Smart der erwartete Kennfeldbereich offline berechnet werden. Bei E19=20 müsste die normale Ventilposition – vor nachgeschalteten Mindestschutzgrenzen – grundsätzlich im Bereich `SmartCenter ±20 %` liegen.

---

# 24. Verbleibende offene EEV-Punkte

Die zentrale Smart-Regelung selbst ist weitgehend geschlossen. Offen bleiben vor allem Randzuordnungen:

1. **FA8-Schutzachse:** physikalische Identität des Werts `0x20015FA8+0x66` eindeutig benennen.
2. **Dynamischer Helper `0x080548A4`:** die verwendeten Gain-/Konfigurationsbytes offiziell benennen und die Hersteller-Terminologie des Reglers bestimmen.
3. **Startöffnungsparameter:** die internen Werte `+0x18/+0x1A/+0x1C` sowie `0x2001656C+0x4A/+0x4C` auf offizielle E03-x-Register zurückführen.
4. **Temperaturabhängige Mindestöffnungen:** alle fünf RAM-Quellen des Schutzprofils exakt den offiziellen E07-x-Parametern zuordnen.
5. **Register 2020/2022:** letzte Spiegelkopie formal schließen, um „Istposition“ statt „Sollposition“ ohne Restvorbehalt zu bestätigen.
6. **Absolute Stepper-Geschwindigkeit:** Schedulerperiode von `0x08054592` bestimmen; erst dann lassen sich `16 Aufrufe pro Step` und `25 Aufrufe Richtungswechselpause` in Millisekunden umrechnen.
7. **Sonderzustände:** alle internen Betriebsflags der Start-/Recovery-/Sensorfehlerübersteuerungen offiziell benennen.
8. **EVI-Regler:** die parallele Auto-Superheat-Regelung des EVI-Ventils in derselben Detailtiefe wie das Haupt-EEV rekonstruieren.

Diese offenen Punkte ändern den beschriebenen Smart-Kernalgorithmus nicht mehr.
