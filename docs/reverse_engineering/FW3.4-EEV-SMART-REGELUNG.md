# Mainboard-Firmware V3.4 – EEV-/Smart-Regelung

Stand: 13. September 2026

Gezielte Reverse-Engineering-Analyse der FoxAir/PHNIX GL9 Mainboard-Firmware `82400644 / V3.4` mit Schwerpunkt Haupt-EEV, Auto/Smart, `E03-1…5` und `E07-1…5`.

Ergänzt [`FW3.3-EEV-SMART-REGELUNG.md`](FW3.3-EEV-SMART-REGELUNG.md).

```text
Datei:         GL9_V3.4(1).bin
Größe:         289806 Byte
SHA-256:       97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890
Imagebasis:    0x08050000
Initial SP:    0x2000EB90
Reset Vector:  0x08093071
Reset Handler: 0x08093070 (Thumb)
```

> **Adresskorrektur:** Frühere V3.4-Notizen mit `0x08080000` lagen bei aus Dateioffsets berechneten Codeadressen `+0x30000` zu hoch. RAM-/Registeradressen sind davon nicht betroffen.

Bewertung:

- **bestätigt** – Datenfluss im V3.4-Binary geschlossen
- **sehr wahrscheinlich** – Funktion praktisch geschlossen, offizieller Herstellername fehlt
- **offen** – interne State-/Flag-Semantik noch nicht vollständig benannt

---

# 1. Wichtigste Ergebnisse

- `E03-1…5` = **Heiz-Basis-/Startöffnungen nach T04-Außentemperatur**.
- `E07-1…5` = **Mindestöffnungen nach T04**, aber im untersuchten Schutzpfad nur bei **Kompressor-Istfrequenz ≥61 Hz**; darunter gilt globales `E07`.
- Die direkte E03/E07-5er-Auswahl hat **keine Hysterese**.
- `E01=1 Auto` = geschlossene Überhitzungs-Feedbackregelung.
- `E01=2 Smart` = dieselbe Feedbackregelung plus Kennfeld-Vorsteuerung und E19-Clamp.
- `MAIN:2067` = **Istwert der Haupt-EEV-Regelüberhitzung**; E02/E18 werden direkt dagegen geregelt.
- Auto verwendet zusätzlich eine **4×5-Zustandsmatrix** aus `MAIN:2066` und `MAIN:2053/T12`.
- Die Auto-Matrix-Schwellen unterscheiden sich zwischen R32- und R290-Profilen (`A26 % 2`).
- `E19` = **±E19 %**, keine Halbierung.
- `185 × 0,9 ≈ 166` ist **nicht** der direkte Firmwarepfad; `0,9` skaliert den Smart-Kennfeldwert nach T01.

---

# 2. Präzisierte Registernamen

| MAIN | Param. | Empfohlene Bezeichnung | Firmwarebedeutung |
|---:|---|---|---|
| 1131 | E01 | **Haupt-EEV Regelmodus** | `0=Manuell, 1=Auto, 2=Smart` |
| 1132 | E02 | **Haupt-EEV Ziel-Regelüberhitzung Heizen** | Sollwert; Istwert `MAIN:2067` |
| 1133 | E03 | **Haupt-EEV Heiz-Basis-/Startöffnung global** | kann E03-x im untersuchten Basispfad übersteuern |
| 1137 | E07 | **Haupt-EEV Mindestöffnung <61 Hz** | im aktiven E07-Schutzpfad bei `MAIN:2072 <61 Hz` |
| 1148 | E18 | **Haupt-EEV Ziel-Regelüberhitzung Kühlen** | Sollwert derselben Feedbackregelung |
| 1149 | E19 | **Smart-EEV Korrekturfenster ± %** | `SmartCenter × (1 ± E19/100)` |
| 1200 | E03-1 | **EEV Heiz-Basisöffnung T04 ≥ +7,1 °C** | direktes T04-Band |
| 1142 | E03-2 | **EEV Heiz-Basisöffnung T04 +0,1…+7,0 °C** | direktes T04-Band |
| 1206 | E03-3 | **EEV Heiz-Basisöffnung T04 −4,9…0,0 °C** | direktes T04-Band |
| 1207 | E03-4 | **EEV Heiz-Basisöffnung T04 −9,9…−5,0 °C** | direktes T04-Band |
| 1208 | E03-5 | **EEV Heiz-Basisöffnung T04 ≤ −10,0 °C** | direktes T04-Band |
| 1209 | E07-1 | **EEV Mindestöffnung ≥61 Hz, T04 ≥ +7,1 °C** | aktiver E07-Schutzpfad |
| 1210 | E07-2 | **EEV Mindestöffnung ≥61 Hz, T04 +0,1…+7,0 °C** | dito |
| 1211 | E07-3 | **EEV Mindestöffnung ≥61 Hz, T04 −4,9…0,0 °C** | dito |
| 1215 | E07-4 | **EEV Mindestöffnung ≥61 Hz, T04 −9,9…−5,0 °C** | dito |
| 1216 | E07-5 | **EEV Mindestöffnung ≥61 Hz, T04 ≤ −10,0 °C** | dito |
| 2020 | – | **Haupt-EEV Istposition / Schritte** | intern nachgeführte Stepperposition |
| 2053 | T12 | **Verdichter-Austritts-/Heißgastemperatur** | 5-stufige Auto-Matrixachse |
| 2066 | – | **EEV Abgas-/Referenztemperaturdifferenz, 5-Sample-Mittel** | 4-stufige Auto-Matrixachse, `0,1 K` |
| 2067 | – | **Haupt-EEV Regelüberhitzung / Saugüberhitzung, 5-Sample-Mittel** | Feedback-Istwert, `0,1 K` |
| 2071 | – | **Kompressor-Sollfrequenz** | Smart-Frequenzachse |
| 2072 | – | **Kompressor-Istfrequenz** | E07-Umschaltung bei 61 Hz |

`MAIN:1141 = reserved e03-4` aus älteren Tabellen ist für V3.4 **nicht** die reale E03-4-Zuordnung. `E03-4 = MAIN:1207`.

---

# 3. E03-/E07-Provenienz

```text
1131 E01   → 0x200169E4+0x00
1132 E02   → 0x200169E4+0x02
1133 E03   → 0x200169E4+0x04
1137 E07   → 0x200169E4+0x06
1138 E08   → 0x200169E4+0x08
1139 E09   → 0x200169E4+0x0A
1140 E10   → 0x200169E4+0x0C
1143 E13   → 0x200169E4+0x0E
1144 E14   → 0x200169E4+0x10
1147 E17   → 0x200169E4+0x12
1148 E18   → 0x200169E4+0x14
1149 E19   → 0x200169E4+0x16

1200 E03-1 → 0x200169E4+0x18
1142 E03-2 → 0x200169E4+0x1A
1206 E03-3 → 0x200169E4+0x1C
1207 E03-4 → 0x2001656C+0x4A
1208 E03-5 → 0x2001656C+0x4C

1209 E07-1 → 0x20016B20+0x10
1210 E07-2 → 0x20016B20+0x12
1211 E07-3 → 0x20016B20+0x14
1215 E07-4 → 0x20016744+0x2C
1216 E07-5 → 0x200167A4+0x2C
```

**Bewertung: bestätigt.**

---

# 4. E03-1…5 – exakte Bänder

Auswahlgröße: **T04 / wirksame Außentemperatur**. V3.4-T04-Helper ungefähr `0x08088108`.

Direkte signed Vergleiche in `0,1 °C`:

```text
-99, -49, +1, +71
```

| E03 | MAIN | Rohbedingung | Exakter Bereich | beobachteter Wert |
|---|---:|---|---|---:|
| E03-1 | 1200 | `T04 >= 71` | **≥ +7,1 °C** | 250 |
| E03-2 | 1142 | `1 <= T04 < 71` | **+0,1…+7,0 °C** | 185 |
| E03-3 | 1206 | `-49 <= T04 < 1` | **−4,9…0,0 °C** | 140 |
| E03-4 | 1207 | `-99 <= T04 < -49` | **−9,9…−5,0 °C** | 125 |
| E03-5 | 1208 | `T04 < -99` | **≤ −10,0 °C** | 110 |

Keine Hysterese:

```text
+7,0 → E03-2     +7,1 → E03-1
 0,0 → E03-3     +0,1 → E03-2
-5,0 → E03-4     -4,9 → E03-3
-10,0 → E03-5    -9,9 → E03-4
```

Heiz-Basispfad vereinfacht:

```text
if E01 == MANUAL:
    base = E03
elif E03 != 0:
    base = E03
elif T04 invalid:
    base = 200
else:
    base = E03_segment[T04]
```

Damit sind E03-x **temperatursegmentierte Heiz-Basis-/Startöffnungen**, nicht das Smart-Kennfeld.

---

# 5. E07-1…5 und 61-Hz-Umschaltung

Direkte T04-Bänder identisch zu E03:

| E07 | MAIN | Bereich | beobachteter Wert |
|---|---:|---|---:|
| E07-1 | 1209 | **T04 ≥ +7,1 °C** | 130 |
| E07-2 | 1210 | **+0,1…+7,0 °C** | 130 |
| E07-3 | 1211 | **−4,9…0,0 °C** | 110 |
| E07-4 | 1215 | **−9,9…−5,0 °C** | 90 |
| E07-5 | 1216 | **T04 ≤ −10,0 °C** | 85 |

Auch hier keine Hysterese in der 5er-Auswahl.

Im aktiven E07-Schutzpfad (`0x20016E18+3 Bit1`) gilt:

```text
if MAIN:2072 < 61 Hz:          # Kompressor-Istfrequenz
    target = max(target, E07)
else:
    target = max(target, E07_segment[T04])
```

Provenienz der Frequenz:

```text
INV1:RX:2102
→ 0x200168C4+0x06
→ MAIN:2072
```

Bei ca. **29 Hz** ist daher – sofern das Gate aktiv ist – **globales E07** relevant, nicht E07-2.

E07/E07-x sind softwareseitige Mindestöffnungen, **keine mechanischen Minima**.

**Offen:** offizieller Herstellername des Gate-Bits `0x20016E18+3 Bit1`.

---

# 6. MAIN:2020 / 2066 / 2067

## 6.1 MAIN:2020

```text
0x20016AC4+0x04
→ Statusbuilder
→ MAIN:2020
```

Damit ist `2020` die intern nachgeführte **EEV-Istposition**.

## 6.2 Gemeinsame 5-Sample-Aufbereitung

```text
0x20016AC4+0x10 = Mittelwert Kanal 1 → MAIN:2066/10
0x20016AC4+0x14 = Mittelwert Kanal 2 → MAIN:2067/10
0x20016AC4+0x18 = Summe Kanal 1
0x20016AC4+0x1C = Summe Kanal 2
0x20016AC4+0x0E = Samplecounter
```

Nach fünf Samples wird jeweils durch `5.0` geteilt und der Akkumulator gelöscht.

## 6.3 MAIN:2067 = Regelüberhitzung

Der Auto-Regler ruft den Feedback-Helper direkt mit:

```text
s0 = E02 oder E18
s1 = [0x20016AC4+0x14] = MAIN:2067/10
```

V3.4-Beispiel:

```text
0x0805A78E  vldr s1,[EEV_runtime,#20]
0x0805A792  vmov.f32 s0,s16
0x0805A796  bl 0x08054868
```

Damit ist funktional bestätigt:

> **MAIN:2067 = Haupt-EEV Regelüberhitzung / Saugüberhitzung, 5-Sample-Mittel.**

Primärer physikalischer Pfad:

```text
T05 Saugtemperatur
-
Verdampfungs-/Sättigungsreferenz aus Niederdruckpfad
```

Die Referenz `0x20016D5C+0x0A` ist sehr wahrscheinlich die aus Niederdruck berechnete Verdampfungs-/Sättigungstemperatur: derselbe Block enthält bei `+0x08` `MAIN:2069 / T15 Niederdruck` und wird A26-/kältemittelspezifisch berechnet.

Fallbacks verwenden je nach Zustand T06 bzw. T03 als Referenz.

## 6.4 MAIN:2066 = Abgas-/Referenzdifferenz

Kanal 1 ist die 4-stufige Auto-Matrixachse.

Normaler Hauptpfad:

```text
T12 Heißgas / Verdichter-Austritt
-
T03 Verdampfer-/Coil-Temperatur
```

In bestimmten Sonder-/Betriebszweigen wird T02 Auslasswasser als Referenz benutzt.

Daher derzeit beste technische Bezeichnung:

> **MAIN:2066 = EEV Abgas-/Referenztemperaturdifferenz, 5-Sample-Mittel.**

---

# 7. Auto E01=1 – 4×5-Matrix exakt benannt

```text
high_state = 4 Zustände aus MAIN:2066
low_state  = 5 Zustände aus MAIN:2053/T12
state      = (high_state << 4) | low_state
```

Interne Statebytes:

```text
0x20016FB5 = MAIN:2066-State 0…3
0x20016FB4 = T12-State 0…4
```

Profilwahl über `A26 % 2`:

```text
A26 gerade   → R32-Familie
A26 ungerade → R290-Familie
```

## 7.1 MAIN:2066 – 4 Zustände

Flash `0x08092FD0`:

```text
R32:  15, 35, 45 K
R290: 10, 30, 35 K
```

Rückschaltung jeweils ca. `2 K` tiefer:

| Profil | 0→1 / 1→0 | 1→2 / 2→1 | 2→3 / 3→2 |
|---|---|---|---|
| **R32** | **15 / 13 K** | **35 / 33 K** | **45 / 43 K** |
| **R290** | **10 / 8 K** | **30 / 28 K** | **35 / 33 K** |

Die Überlappung ist echte Hysterese; in z. B. `13…15 K` hängt der State von der Historie ab.

## 7.2 T12 / MAIN:2053 – 5 Zustände

Flash `0x08092F4C`:

```text
R32:  60, 70, 80, 90 °C
R290: 60, 70, 80, 95 °C
```

Rückschaltung ca. `2 K` tiefer:

| Profil | 0→1 / 1→0 | 1→2 / 2→1 | 2→3 / 3→2 | 3→4 / 4→3 |
|---|---|---|---|---|
| **R32** | **60/58 °C** | **70/68 °C** | **80/78 °C** | **90/88 °C** |
| **R290** | **60/58 °C** | **70/68 °C** | **80/78 °C** | **95/93 °C** |

Damit ist die ehemals offene zweite Matrixachse als **Verdichter-Austritts-/Heißgastemperatur T12** geschlossen.

## 7.3 Matrixwirkung

Dispatcherzustände:

```text
00 01 02 03 04
10 11 12 13 14
20 21 22 23 24
30 31 32 33 34
```

Direkt sichtbare Randaktionen:

```text
00 → stark schließen, etwa -8/-4 Schritte
01 → schließen, etwa -6/-2 Schritte
02 → bis -4
03 → bis -2
04 → neutraler Randfall
...
34 → stark öffnen, bis +8
```

Die inneren Zustände verwenden überwiegend den Feedback-Helper `0x08054868`; teils wird E02/E18 vorher um `-1` oder `-2 K` verschoben.

Auto ist daher eine **zustandsabhängige nichtlineare Überhitzungsregelung mit Heißgas-/Differenzklassifikation**.

---

# 8. Feedback-Helper 0x08054868

Eingänge:

```text
s0 = Überhitzungs-Sollwert E02/E18 (zustandsabhängig ggf. verschoben)
s1 = MAIN:2067/10
error = actual - target
```

Im Code liegen mehrere nichtlineare Fehlerzonen um ungefähr:

```text
-5, -3, -2, ... +2, +3, +5 K
```

Zusätzlich werden signed Konfigurationsbytes aus:

```text
0x20016C9C+0x08
0x20016C9C+0x09
```

verwendet (Defaults `1/1`). Sie wirken als Gain-/Skalierungsparameter; offizielle Namen/öffentliche Register sind noch nicht geschlossen.

Der Helper ist zustandsbehaftet und begrenzt seine Korrektur. Ohne Herstellerbeleg sollte er nicht „PID“ genannt werden; passend ist **nichtlinearer, zustandsbehafteter Überhitzungs-Korrekturregler**.

---

# 9. Smart E01=2 – exakte Achsen

Smart nutzt weiterhin das Auto-Ergebnis:

```text
SmartCenter = SMART_TABLE[freq_state][T04_state] × T01_factor
Target = clamp(AutoTarget, SmartCenter ± E19%)
```

## 9.1 Frequenzachse = MAIN:2071 Sollfrequenz

```text
0→1 bei >=46 Hz; 1→0 bei <44 Hz
1→2 bei >=61 Hz; 2→1 bei <59 Hz
2→3 bei >=76 Hz; 3→2 bei <74 Hz
```

**Nicht verwechseln:** Smart = Sollfrequenz `2071`; E07-61-Hz-Umschaltung = Istfrequenz `2072`.

## 9.2 Smart-T04-Achse = MAIN:2048, 6 Zustände

```text
0→1 >= -12,9 °C; 1→0 < -14,9 °C
1→2 >=  -6,9 °C; 2→1 <  -8,9 °C
2→3 >=  +0,1 °C; 3→2 <  -1,9 °C
3→4 >=  +7,1 °C; 4→3 <  +5,1 °C
4→5 >= +20,1 °C; 5→4 < +18,1 °C
```

Diese 6er-Hystereseachse ist **nicht** identisch mit den direkten 5 E03/E07-Bändern.

## 9.3 T01-Einlasswasserfaktor = MAIN:2045

```text
State 0 → ×1,2
State 1 → ×1,0
State 2 → ×0,9
State 3 → ×0,8
```

Übergänge:

```text
0→1 bei >=20,1 °C; 1→0 bei <18,1 °C
1→2 bei > 30,0 °C; 2→1 bei <=28,0 °C
2→3 bei > 40,0 °C; 3→2 bei <=38,0 °C
```

## 9.4 Smart-Grundkennfeld

Flash `0x08092E60`:

| f-State \ T04-State | 0 | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|---:|
| **0** | 52 | 58 | 66 | 85 | 100 | 155 |
| **1** | 60 | 75 | 85 | 115 | 135 | 210 |
| **2** | 65 | 85 | 100 | 140 | 160 | 250 |
| **3** | 80 | 98 | 125 | 170 | 190 | 320 |

---

# 10. E19

```text
ratio = E19 / 100.0
lower = SmartCenter × (1-ratio)
upper = SmartCenter × (1+ratio)
```

Bei `E19=20`:

```text
0,80 × SmartCenter … 1,20 × SmartCenter
```

**Keine Halbierung auf ±10 %.**

---

# 11. 166-Schritte-Plateau

Die auffällige Rechnung:

```text
185 × 0,9 = 166,5
```

ist **nicht** der direkte Smart-Codepfad. `0,9` skaliert den Smart-Kennfeldwert, nicht E03-2.

Ein realer Firmwarepfad zu exakt 166 existiert bei:

```text
freq_state = 0
T04_state  = 5
T01_state  = 2
E19        = 20 %
```

Dann:

```text
SMART_TABLE[0][5] = 155
155 × 0,9 → Integer SmartCenter 139
139 × 1,20 → Integer upper 166
```

Wenn `MAIN:2067 > E02` den Auto-Regler weiter öffnen lässt, kann Smart exakt bei 166 klemmen.

**Wichtig:** Dieser konkrete Pfad braucht T04-State 5:

```text
Eintritt: T04 >= +20,1 °C
Verbleib: solange T04 >= +18,1 °C
```

Daher:

- bei `T04 < +18,1 °C` ist dieser spezielle 166-Pfad ausgeschlossen;
- zwischen `+18,1…+20,0 °C` ist State 5 nur durch Hysterese möglich;
- ab `+20,1 °C` wird State 5 sicher neu betreten.

Der Messpunkt muss deshalb mit `2048/T04`, `2045/T01`, `2071`, `2067` und `2020` abgeglichen werden.

---

# 12. Kompakter Pseudocode

```text
# Heizbasis
base = E03 if E03 != 0 else E03_segment_direct(T04)

# Regelgrößen (5-Sample-Mittel)
aux = MAIN2066/10
sh  = MAIN2067/10

# Auto-Matrix
aux_state = hysteresis(aux, A26_refrigerant_thresholds)
hotgas_state = hysteresis(T12, A26_refrigerant_thresholds)
state = (aux_state << 4) | hotgas_state

auto_target = nonlinear_feedback(state, E02_or_E18, sh)

# Smart
if E01 == 2:
    fs = hysteresis(MAIN2071, 46/44, 61/59, 76/74)
    ats = hysteresis(T04,
                     -12.9/-14.9, -6.9/-8.9,
                     +0.1/-1.9, +7.1/+5.1,
                     +20.1/+18.1)
    ws = hysteresis(T01, 20.1/18.1, 30/28, 40/38)
    smart_center = trunc(SMART_TABLE[fs][ats] * [1.2,1.0,0.9,0.8][ws])
    target = clamp(auto_target,
                   smart_center*(1-E19/100),
                   smart_center*(1+E19/100))
else:
    target = auto_target

# Mindestöffnung
if E07_gate:
    if MAIN2072 < 61:
        target = max(target, E07)
    else:
        target = max(target, E07_segment_direct(T04))

target = min(target, 480)
```

---

# 13. Noch offene Punkte

1. `0x20016E18+3 Bit1`: offizieller Name des E07-Mindestöffnungs-Gates.
2. `0x20016C9C+8/+9`: öffentliche/Engineering-Zuordnung und Herstellername der Feedback-Gain-/Skalierungsbytes.
3. offizieller PHNIX-Klartextname für `MAIN:2066`.
4. öffentliche/Herstellerbezeichnung der sehr wahrscheinlich niederdruckabgeleiteten Verdampfungs-/Sättigungstemperatur `0x20016D5C+0x0A`.
5. Start-/Recovery-/Sensorfehler-/Abtau-Bypässe vollständig auf offizielle Flags mappen.
6. absolute Scheduler-/Stepper-Zeitbasis bestimmen.
7. EVI-/Economizer-EEV-Regler in derselben Detailtiefe schließen.

---

# 14. Empfohlenes Logging

```text
MAIN:1131 E01
MAIN:1132 E02
MAIN:1149 E19
MAIN:2020 EEV-Istposition
MAIN:2045 T01 Einlasswasser
MAIN:2048 T04 wirksame Außentemperatur
MAIN:2053 T12 Heißgastemperatur
MAIN:2066 Abgas-/Referenztemperaturdifferenz
MAIN:2067 Haupt-EEV Regelüberhitzung
MAIN:2071 Kompressor-Sollfrequenz
MAIN:2072 Kompressor-Istfrequenz
Betriebsmodus / Abtauzustand
```

Damit lassen sich die Auto-Matrixstates, die drei Smart-Achsen und das E19-Fenster offline rekonstruieren.
