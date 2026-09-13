# Mainboard-Firmware V3.4 – EEV-/Smart-Regelung und segmentierte E03/E07-Parameter

Stand: 13. September 2026

Diese Datei dokumentiert die gezielte Nachanalyse der PHNIX-/FoxAir-GL9-Mainboard-Firmware **V3.4** mit Schwerpunkt auf Haupt-EEV, Smart-Modus und den segmentierten Parametern `E03-1…5` / `E07-1…5`.

Sie baut auf [`FW3.3-EEV-SMART-REGELUNG.md`](FW3.3-EEV-SMART-REGELUNG.md) auf, korrigiert bzw. schließt dort noch offene Registerzuordnungen und dokumentiert V3.4-spezifische Codeadressen. Codeadressen aus V3.3 und V3.4 dürfen wegen der unterschiedlichen Imagebasis/Linklage nicht vermischt werden.

Analysiertes Image:

```text
GL9_V3.4(1).bin
SHA256 97b4bb09bf854bd3c7521278de05354d9bb04a862dd05a864582b365d7af5890
Imagebasis ungefähr 0x08080000
```

## Bewertungsstufen

- **bestätigt** – Datenfluss/Codepfad in V3.4 direkt geschlossen
- **sehr wahrscheinlich** – funktional eindeutig, letzte symbolische Herstellerbezeichnung fehlt
- **offen** – physikalische oder zeitliche Bedeutung eines internen Zustands ist noch nicht vollständig bewiesen

---

# 1. Kurzfassung der neuen V3.4-Erkenntnisse

1. Die fünf `E03-x`-Werte sind **temperatursegmentierte Heiz-Start-/Basisöffnungen**. Sie werden über **T04 / Außentemperatur** mit Grenzen bei ungefähr `+7 / 0 / -5 / -10 °C` ausgewählt.
2. `E03=1133` ist **nicht Legacy**. Ein ungleich 0 gesetztes globales E03 kann im Heiz-Basispfad die segmentierten E03-x-Werte übersteuern. Die Segmentwerte werden insbesondere als temperaturabhängiger Fallback/Basiswert verwendet, wenn der globale Heiz-Basiswert 0 ist.
3. Die fünf `E07-x`-Werte sind **temperatursegmentierte Mindestöffnungen** des Haupt-EEV. Auch sie werden über T04 mit denselben fünf Temperaturbändern ausgewählt.
4. `E07=1137` bleibt aktiv. Bei gesetztem Schutzflag wird bei **Kompressor-Istfrequenz < 61 Hz** gegen das globale E07 geklemmt; ab **61 Hz** wird stattdessen die temperatursegmentierte E07-x-Mindestöffnung verwendet. Die Frequenzquelle ist `0x200168C4+0x06` = **Register 2072 Kompressor-Istfrequenz**.
5. `E01=2 Smart` ersetzt die normale Superheat-Regelung **nicht**. E02 bleibt im Smart-Modus aktiv. Smart berechnet zusätzlich einen Vorsteuer-Arbeitspunkt und begrenzt das Ergebnis der Feedbackregelung mit E19 um diesen Arbeitspunkt.
6. `E19` wird exakt als **±E19 %** interpretiert. Es gibt keine Halbierung auf ±E19/2.
7. Die frühere Vermutung `E03-2 185 × 0,9 = 166` ist **nicht der tatsächliche Codepfad**. Der Faktor `0,9` gehört zur Skalierung des Smart-Kennfelds nach T01/Einlasswassertemperatur.
8. Für die beobachteten 166 Schritte existiert ein sehr plausibler, exakt passender Firmwarepfad:

```text
Smart-Tabelle: 155
T01-Faktor:    × 0,9
               = 139,5 → Integer 139
E19 = 20 %:    obere Grenze = 139 × 1,20 = 166,8 → Integer 166
```

Damit kann ein dauerhaftes Plateau bei 166 entstehen, wenn die normale Superheat-Regelung weiter öffnen möchte, aber am oberen Smart/E19-Limit anliegt.

---

# 2. Präzisierte Registernamen

Die folgenden Namen sind für eine Registerliste bzw. FoxAir-Control aussagekräftiger als die bisherigen generischen/teilweise falschen Texte.

| Register | Param. | Empfohlene präzisere Bezeichnung | V3.4-Bedeutung |
|---:|---|---|---|
| 1131 | E01 | **Haupt-EEV Regelmodus** | `0=Manuell, 1=Auto, 2=Smart` |
| 1132 | E02 | **Haupt-EEV Soll-Saugüberhitzung Heizen** | Feedback-Sollwert; auch in Smart aktiv |
| 1133 | E03 | **Haupt-EEV Heiz-Basis-/Startöffnung global** | globale Heiz-Basis; kann E03-x übersteuern |
| 1137 | E07 | **Haupt-EEV Mindestöffnung <61 Hz** | globale Mindestgrenze im aktiven Schutzpfad bei Verdichter-Istfrequenz <61 Hz |
| 1149 | E19 | **Smart-EEV Korrekturfenster ± %** | `SmartCenter × (1 ± E19/100)` |
| 1200 | E03-1 | **EEV Heiz-Basisöffnung AT-Band 1 (warm)** | T04 >= ca. +7 °C |
| 1142 | E03-2 | **EEV Heiz-Basisöffnung AT-Band 2** | ca. 0…+7 °C |
| 1206 | E03-3 | **EEV Heiz-Basisöffnung AT-Band 3** | ca. -5…0 °C |
| 1207 | E03-4 | **EEV Heiz-Basisöffnung AT-Band 4** | ca. -10…-5 °C |
| 1208 | E03-5 | **EEV Heiz-Basisöffnung AT-Band 5 (kalt)** | T04 < ca. -10 °C |
| 1209 | E07-1 | **EEV Mindestöffnung ab 61 Hz, AT-Band 1 (warm)** | Verdichter-Istfrequenz >=61 Hz; T04 >= ca. +7 °C |
| 1210 | E07-2 | **EEV Mindestöffnung ab 61 Hz, AT-Band 2** | Verdichter-Istfrequenz >=61 Hz; ca. 0…+7 °C |
| 1211 | E07-3 | **EEV Mindestöffnung ab 61 Hz, AT-Band 3** | Verdichter-Istfrequenz >=61 Hz; ca. -5…0 °C |
| 1215 | E07-4 | **EEV Mindestöffnung ab 61 Hz, AT-Band 4** | Verdichter-Istfrequenz >=61 Hz; ca. -10…-5 °C |
| 1216 | E07-5 | **EEV Mindestöffnung ab 61 Hz, AT-Band 5 (kalt)** | Verdichter-Istfrequenz >=61 Hz; T04 < ca. -10 °C |
| 2020 | – | **Haupt-EEV Istposition / Schritte** | in V3.4 formal bis `0x20016AC4+0x04` = intern nachgeführte Stepper-Istposition geschlossen |
| 2067 | – | **EEV Differenz-/Überhitzungswert Kanal 2** | V3.4: `0x20016AC4+0x14 × 10`; physikalische Bezeichnung noch zu schließen. Nicht vorschnell nur „Saugüberhitzung“ nennen |

## 2.1 Öffentliche Statusregister 2020 und 2066/2067

Der V3.4-Statusbuilder schließt zwei bisher offene Spiegelpfade:

```text
0x20016AC4+0x04  interne nachgeführte Haupt-EEV-Stepperposition
      ↓
0x200164B8+0x0C
      ↓
MAIN:2020
```

Damit ist **Register 2020 die intern nachgeführte EEV-Istposition in Schritten**, nicht nur der Regler-Sollwert. Für das EVI-Ventil existiert derselbe Pfad über `0x20016B04+0x04`.

Für die beiden bislang reservierten Differenz-/Überhitzungsregister gilt direkt:

```text
MAIN:2066 = trunc((0x20016AC4+0x10) × 10)
MAIN:2067 = trunc((0x20016AC4+0x14) × 10)
```

Beide internen Werte werden als 5-Sample-Mittel temperaturbasierter Differenzen gebildet. Welcher davon herstellerseitig exakt als Saugüberhitzung, Austrittsüberhitzung bzw. zweiter Kältekreis-/EVI-Differenzwert bezeichnet wird, wird weiter verfolgt. Daher ist für `2067` die neutrale Bezeichnung **„EEV Differenz-/Überhitzungswert Kanal 2“** derzeit belastbarer als nur „Saugüberhitzung“.

**2020: bestätigt. 2066/2067 Datenquelle und Skalierung: bestätigt; physikalische Benennung: offen.**

---

### Hinweis zu Register 1141

In älteren Tabellen steht bei `1141` sinngemäß `reserviert e03-4`. Das ist für V3.4 **falsch**. Die V3.4-Synchronisation führt `1141` nicht in den EEV-E03-x-Block. Das echte **E03-4 ist Register 1207**.

---

# 3. Exakte V3.4-Zuordnung der E03-/E07-Register zum RAM

Die Modbus-Holding-Spiegelstruktur liegt in V3.4 bei:

```text
0x20012788
```

Für den untersuchten Parameter-Synchronisationspfad gilt:

```text
Modbus_Register = 501 + source_offset / 2
```

Der Haupt-EEV-Parameterblock liegt weiterhin bei:

```text
0x200169E4
```

Direkt bestätigte Zuordnung:

```text
1131 E01   → 0x200169E4 + 0x00
1132 E02   → 0x200169E4 + 0x02
1133 E03   → 0x200169E4 + 0x04
1137 E07   → 0x200169E4 + 0x06
1138 E08   → 0x200169E4 + 0x08
1139 E09   → 0x200169E4 + 0x0A
1140 E10   → 0x200169E4 + 0x0C
1142 E03-2 → 0x200169E4 + 0x1A
1143 E13   → 0x200169E4 + 0x0E
1144 E14   → 0x200169E4 + 0x10
1147 E17   → 0x200169E4 + 0x12
1148 E18   → 0x200169E4 + 0x14
1149 E19   → 0x200169E4 + 0x16
1200 E03-1 → 0x200169E4 + 0x18
1206 E03-3 → 0x200169E4 + 0x1C
1207 E03-4 → 0x2001656C + 0x4A
1208 E03-5 → 0x2001656C + 0x4C
1209 E07-1 → 0x20016B20 + 0x10
1210 E07-2 → 0x20016B20 + 0x12
1211 E07-3 → 0x20016B20 + 0x14
1215 E07-4 → 0x20016744 + 0x2C
1216 E07-5 → 0x200167A4 + 0x2C
```

Damit sind die beiden in der V3.3-Dokumentation noch offenen 5er-Gruppen jetzt vollständig auf die externen Register zurückgeführt.

**Bewertung: bestätigt.**

---

# 4. E03-1…5: tatsächliche Auswahl

Der Heiz-Basispfad in V3.4 verwendet T04/Außentemperatur. Die Sensorabfrage liegt im V3.4-Image über den T04-Helper um:

```text
0x080B8108
```

Die exakten Vergleiche erfolgen in `/10 °C` und ergeben:

```text
T04 < -9,9 °C              → E03-5 = Register 1208
-9,9 <= T04 < -4,9 °C      → E03-4 = Register 1207
-4,9 <= T04 < +0,1 °C      → E03-3 = Register 1206
+0,1 <= T04 < +7,1 °C      → E03-2 = Register 1142
T04 >= +7,1 °C             → E03-1 = Register 1200
```

Bei ungültigem Außentemperatursensor existiert in diesem Fallbackpfad eine feste Ersatzöffnung von:

```text
200 Schritte
```

## 4.1 Rolle des globalen E03

Der relevante Heizpfad lässt sich sinngemäß so zusammenfassen:

```text
if E01 == MANUELL:
    heating_base = E03_global
else:
    if E03_global != 0:
        heating_base = E03_global
    else:
        if T04_invalid:
            heating_base = 200
        else:
            heating_base = E03_segment[T04]
```

Daraus folgen zwei wichtige Aussagen:

- E03-x sind **keine ausschließlich Smart-spezifischen Kennfeldwerte**.
- Ein von 0 verschiedener globaler E03 kann die temperatursegmentierte E03-x-Auswahl in diesem Heiz-Basispfad **übersteuern**.

Die sinnvollste Benennung ist daher **segmentierte Heiz-Basis-/Startöffnung nach Außentemperatur** und nicht „Smart-Basiswert“.

**Bewertung: bestätigt.**

---

# 5. E07-1…5: tatsächliche Mindestöffnungen

Die V3.4-Schutzlogik verwendet dieselben T04-Bänder:

```text
T04 < -9,9 °C              → E07-5 = Register 1216
-9,9 <= T04 < -4,9 °C      → E07-4 = Register 1215
-4,9 <= T04 < +0,1 °C      → E07-3 = Register 1211
+0,1 <= T04 < +7,1 °C      → E07-2 = Register 1210
T04 >= +7,1 °C             → E07-1 = Register 1209
```

Wenn der aktuelle EEV-Sollwert unter der gewählten Grenze liegt, wird er auf den jeweiligen E07-x-Wert angehoben.

Das bestätigt:

> **E07-1…5 sind segmentabhängige softwareseitige Mindestöffnungen, keine mechanischen Mindestpositionen.**

## 5.1 Rolle des globalen E07 und die 61-Hz-Umschaltung

Der entscheidende V3.4-Vergleich liest:

```text
0x200168C4 + 0x06
```

Dieser Wert ist aus der bereits geschlossenen Inverter-Telemetrie eindeutig:

```text
Unit-1 FC03 Remote-Reg. 2102
→ 0x200168C4 + 0x06
→ MAIN Register 2072
= Kompressor-Istfrequenz
```

Im EEV-Schutzpfad wird bei gesetztem `0x20016E18+3 Bit1` unterschieden:

```text
wenn Kompressor-Istfrequenz < 61 Hz:
    wenn Target < E07_global:
        Target = E07_global

wenn Kompressor-Istfrequenz >= 61 Hz:
    min_value = E07_segment[T04]
    wenn Target < min_value:
        Target = min_value
```

Damit ist die vorher vermeintliche „Start-/Zeitumschaltung“ korrigiert: **61 ist eine Frequenzschwelle in Hz, keine Zeitangabe.**

Bei den beobachteten ca. 29 Hz liegt dieser Schutzpfad – sofern das zugehörige Schutzflag aktiv ist – auf der **globalen E07-Grenze**, nicht auf E07-x.

Die genaue offizielle Bedeutung des Gate-Flags `0x20016E18+3 Bit1` ist noch offen; die Frequenz- und Clamp-Funktion selbst ist bestätigt.

**Bewertung: bestätigt.**

---

# 6. Auto vs. Smart und die Rolle von E02

Die V3.4-Analyse bestätigt die Architektur aus V3.3.

## Auto / E01 = 1

Auto arbeitet als geschlossene Superheat-Regelung. Im Heizpfad wird E02 geladen und als Sollwert in die normale EEV-Regelung eingespeist.

Vereinfacht:

```text
SH_error = SH_actual - E02
Auto_Target = feedback_controller(SH_error, additional_state)
Auto_Target = apply_common_protection(Auto_Target)
```

## Smart / E01 = 2

Smart verwendet **denselben normalen Superheat-Regler weiter**. E02 wird daher nicht ignoriert.

Zusätzlich:

```text
SmartCenter = f(compressor_target_hz, T04, T01)
Target = clamp(Auto_Target,
               SmartCenter × (1-E19/100),
               SmartCenter × (1+E19/100))
```

Danach greifen weitere gemeinsame Mindest-/Schutzgrenzen.

Damit ist die präzise Beschreibung:

> **Auto = Superheat-Feedbackregelung. Smart = dieselbe Feedbackregelung plus last-/temperaturabhängige Kennfeld-Vorsteuerung und E19-Begrenzungsfenster.**

Das erklärt unmittelbar, warum im Smart-Modus die reale Saugüberhitzung dauerhaft oberhalb E02 liegen kann: Wenn der Auto-Regler weiter öffnen möchte, aber bereits an der Smart/E19-Obergrenze anliegt, bleibt das Ventil am Limit stehen.

**Bewertung: bestätigt.**

---

# 7. Smart-Kennfeld in V3.4

Die Smart-Architektur ist gegenüber V3.3 inhaltlich erhalten.

V3.4-Zustände:

```text
0x20016FCF  T01-/Wasserzustand, 4 Zustände
0x20016FD0  Verdichterfrequenz-Zustand, 4 Zustände
0x20016FD1  T04-/Außentemperatur-Zustand, 6 Zustände
```

Der berechnete Smart-Mittelpunkt wird in V3.4 gespeichert bei:

```text
0x20016F5C
```

Das feste 4×6-Kennfeld liegt im V3.4-Flash um:

```text
0x080C2E60
```

und lautet:

| Verdichter-State \ T04-State | 0 | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|---:|
| **0** | 52 | 58 | 66 | 85 | 100 | 155 |
| **1** | 60 | 75 | 85 | 115 | 135 | 210 |
| **2** | 65 | 85 | 100 | 140 | 160 | 250 |
| **3** | 80 | 98 | 125 | 170 | 190 | 320 |

## 7.1 Verdichterfrequenz-Achse

Quelle ist die Verdichter-Sollfrequenz; die V3.3-Provenienz führt diese auf Register 2071 zurück. V3.4 verwendet dieselbe Zustandsmaschine:

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

Bei ungefähr 29 Hz liegt damit **Frequenz-State 0** vor.

## 7.2 T04-/Außentemperatur-Achse

Die sechs hysteretischen Zustände sind:

```text
0 → 1 bei T04 >= -12,9 °C
1 → 0 bei T04 <  -14,9 °C

1 → 2 bei T04 >= -6,9 °C
2 → 1 bei T04 <  -8,9 °C

2 → 3 bei T04 >= +0,1 °C
3 → 2 bei T04 <  -1,9 °C

3 → 4 bei T04 >= +7,1 °C
4 → 3 bei T04 <  +5,1 °C

4 → 5 bei T04 >= +20,1 °C
5 → 4 bei T04 <  +18,1 °C
```

Damit ist dieses Smart-Kennfeld **nicht identisch** mit den fünf E03/E07-Außentemperatursegmenten.

## 7.3 T01-/Einlasswasser-Faktor

Der Kennfeldwert wird anschließend über vier T01-Zustände skaliert:

```text
State 0 → × 1,2
State 1 → × 1,0
State 2 → × 0,9
State 3 → × 0,8
```

Die Zustandsübergänge liegen ungefähr bei 20/30/40 °C mit Hysterese um 18/28/38 °C.

Damit gilt:

```text
SmartCenter = SMART_TABLE[freq_state][ambient_state]
              × inlet_water_factor[T01_state]
```

**Bewertung: bestätigt.**

---

# 8. E19 – exakte Mathematik

V3.4 prüft für diesen Block ausdrücklich:

```text
E01 == 2
```

und berechnet:

```text
ratio = E19 / 100.0
lower = SmartCenter × (1.0 - ratio)
upper = SmartCenter × (1.0 + ratio)
```

Anschließend wird das Ergebnis der normalen Feedbackregelung auf dieses Fenster begrenzt.

Für E19=20 gilt damit:

```text
lower = 0,8 × SmartCenter
upper = 1,2 × SmartCenter
```

Es gibt **keine Division durch 2** und kein verstecktes ±10-%-Fenster.

**Bewertung: bestätigt.**

---

# 9. Erklärung des beobachteten 166-Schritte-Plateaus

Beobachtet wurde unter anderem:

```text
E01 Smart
E02 = 3,0 K
E03-2 = 185
E19 = 20 %
Verdichter etwa 29 Hz
EEV lange exakt 166 Schritte
Saugüberhitzung etwa 4,5…4,7 K
```

Die zunächst auffällige Rechnung:

```text
185 × 0,90 = 166,5
```

ist numerisch korrekt, aber **nicht der in V3.4 gefundene Smart-Codepfad**. Der Faktor 0,9 wird auf den Smart-Kennfeldwert angewendet, nicht direkt auf E03-2.

## 9.1 Firmwarepfad, der exakt 166 ergibt

Unter folgenden Smart-Zuständen:

```text
Verdichter-State = 0      # z. B. ~29 Hz
T04-State         = 5
T01-State         = 2     # Faktor 0,9
E19               = 20 %
```

liefert die Tabelle:

```text
SMART_TABLE[0][5] = 155
```

Dann:

```text
155 × 0,9 = 139,5
```

Der Zwischenwert wird bei der Integer-Konvertierung auf:

```text
SmartCenter = 139
```

gebracht.

Die E19-Obergrenze ist anschließend:

```text
139 × 1,20 = 166,8
```

und die Integer-Konvertierung ergibt:

```text
upper = 166 Schritte
```

Wenn der normale Superheat-Regler wegen `SH_actual > E02` weiter öffnen möchte, wird er daher genau bei **166 Schritten** abgeschnitten.

Das erklärt gleichzeitig:

- das lange exakt konstante Plateau,
- die Saugüberhitzung oberhalb des E02-Sollwerts,
- und warum 166 keine absolute mechanische Mindestöffnung ist.

### Wichtig

Dieser konkrete 166-Pfad ist an die genannten internen Smart-Zustände gebunden. Für einen realen Messpunkt sollte deshalb parallel mindestens geloggt werden:

```text
T04 / Außentemperatur
T01 / Einlasswasser
Verdichter-Sollfrequenz
EEV-Schritte
Saugüberhitzung
E01
E19
```

**Mathematik und Codepfad: bestätigt. Dass genau dieser Zustandsvektor beim konkreten Feldmesspunkt aktiv war: sehr wahrscheinlich, aber durch das Messlog zu bestätigen.**

---

# 10. Warum das EEV beim Start unter 166 fahren kann

166 ist keine globale Untergrenze. Die Firmware besitzt mehrere vorgelagerte und nachgelagerte Zustände:

- Initialisierung/Homing,
- Start-/Recoveryzweige,
- globaler E07-Clamp,
- späterer E07-x-Clamp,
- Auto-/Smart-Feedback,
- E19-Fenster,
- Sonderzustände und Abtauung.

Das E19-Fenster ist daher **nicht in jeder Startphase die einzige oder letzte aktive Regelbedingung**. Werte unter 166 während des Anlaufs widersprechen dem oben beschriebenen Smart-Plateau nicht.

---

# 11. Rekonstruierter Pseudocode V3.4

```text
# Heiz-Basis-/Startwert
if E01 == MANUAL:
    heating_base = E03
else:
    if E03 != 0:
        heating_base = E03
    elif T04 invalid:
        heating_base = 200
    else:
        heating_base = E03_by_ambient_band(T04)

# normale Feedbackregelung
if heating:
    superheat_setpoint = E02
else:
    superheat_setpoint = E18

auto_target = normal_superheat_controller(
    superheat_actual,
    superheat_setpoint,
    additional_thermal_state
)

# Smart-Zusatz
if E01 == SMART:
    freq_state    = hysteresis(compressor_target_hz,
                               46/44, 61/59, 76/74)
    ambient_state = hysteresis(T04,
                               -12.9/-14.9,
                               -6.9/-8.9,
                               +0.1/-1.9,
                               +7.1/+5.1,
                               +20.1/+18.1)
    water_state   = hysteresis(T01,
                               ca. 20/18,
                               30/28,
                               40/38)

    base = SMART_TABLE[freq_state][ambient_state]
    factor = [1.2, 1.0, 0.9, 0.8][water_state]
    smart_center = trunc(base * factor)

    ratio = E19 / 100.0
    lower = trunc(smart_center * (1-ratio))
    upper = trunc(smart_center * (1+ratio))

    target = clamp(auto_target, lower_if_positive, upper)
else:
    target = auto_target

# gemeinsame Schutz-/Mindestgrenzen
if E07_protection_flag:
    if compressor_actual_hz < 61:
        target = max(target, E07)
    else:
        target = max(target, E07_by_ambient_band(T04))

target = min(target, 480)

stepper_move_to(target)
```

---

# 12. Was gegenüber der V3.3-Dokumentation jetzt geschlossen ist

In `FW3.3-EEV-SMART-REGELUNG.md` waren insbesondere noch offen:

- die vollständige Zuordnung der fünf Startöffnungsquellen zu E03-1…5,
- die vollständige Zuordnung der fünf temperaturabhängigen Mindestöffnungen zu E07-1…5.

V3.4 schließt beide Punkte vollständig:

```text
E03-1 = 1200
E03-2 = 1142
E03-3 = 1206
E03-4 = 1207
E03-5 = 1208

E07-1 = 1209
E07-2 = 1210
E07-3 = 1211
E07-4 = 1215
E07-5 = 1216
```

Zusätzlich ist jetzt die Fehlbezeichnung von Register 1141 als angebliches `E03-4` widerlegt.

---

# 13. Noch offene Punkte für weitere Analyse

1. **E07-Gate-Flag `0x20016E18+3 Bit1`**: offizielle Bedeutung des Flags benennen. Die daran gekoppelte 61-Hz-Umschaltung ist bereits bestätigt.
2. **FA8-Achse des normalen 4×5-Superheat-Reglers**: Sensor-/Schutzgröße weiterhin physikalisch eindeutig benennen.
3. **Dynamischer Feedback-Helper**: exakte Hersteller-Terminologie und Parameter/Gains vollständig entschlüsseln.
4. **Sonderzustände**: Start-/Recovery-/Sensorfehlerflags bis zu ihren offiziellen Status-/Fehlerbezeichnungen zurückführen.
5. **2066/2067-Semantik**: die öffentlichen Quellen `+0x10/+0x14` und Skalierung ×10 sind geschlossen; die exakten physikalischen Herstellernamen der beiden Differenz-/Überhitzungskanäle sind noch zu benennen.
6. **Absolute Stepper-Zeitbasis**: Schedulerperiode bestimmen, um Step-Cadence und Richtungswechselpause in Millisekunden anzugeben.

Diese offenen Punkte ändern den zentralen Smart-Algorithmus und die jetzt geschlossene E03-/E07-Segmentzuordnung nicht.
