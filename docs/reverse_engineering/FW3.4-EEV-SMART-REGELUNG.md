# Mainboard-Firmware V3.4 – EEV-/Smart-Regelung

Stand: 13. September 2026

Gezielte Reverse-Engineering-Analyse der FoxAir/PHNIX GL9 Mainboard-Firmware `82400644 / V3.4` mit Schwerpunkt **Haupt-EEV**, Auto/Smart, `E03-1…5` und `E07-1…5`. Die GL9 besitzt kein EVI-/Economizer-Ventil; dessen Regelung wird in diesem Dokument bewusst nicht weiter verfolgt.

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
- `MAIN:2065` = **Verdampfungstemperatur** aus dem Niederdruck-/Kältemittelpfad; DWIN/PHNIX bestätigt die Bezeichnung.
- `MAIN:2066` = **Abgasüberhitzung**, `MAIN:2067` = **Rückgas-/Saugüberhitzung**; die DWIN-Texte bestätigen damit die zuvor nur funktional abgeleiteten Namen.
- `MAIN:1351/E20` und `MAIN:1352/E21` sind die beiden öffentlichen Gain-/Zeitparameter des Feedbackreglers. Der Regler ist **PI-artig**, besitzt eine Totzone von ungefähr `±0,5 K`, eine proportionale Begrenzung von etwa `±60` Schritten und eine Ausgangs-Slew-Rate von höchstens etwa `±5` Sollwertschritten pro tatsächlicher Korrektur.
- Bei kleiner Regelabweichung `-2 K < Fehler < +2 K` verarbeitet der PI-Helper nur **jeden vierten Aufruf**. Damit beträgt das effektive Korrekturintervall nahe am Sollwert ungefähr **3,11 s** statt 0,778 s.
- Die 20 Auto-Matrixzustände sind vollständig rekonstruiert. Die Randzustände berücksichtigen zusätzlich den **Trend von T12/Heißgas** gegenüber dem vorherigen T12-Sample.
- `E20/E21` werden vom Mainboard ohne Wertebereichsprüfung als signed 8-bit übernommen. Auch die DWIN-Kommunikationsroutine führt keine Min/Max-Prüfung durch. Insbesondere `E21=0` ist wegen der direkten Berechnung `1/E21` **nicht zulässig/sicher**.
- Der Haupt-EEV-Regler wird ungefähr alle **0,778 s** aufgerufen; die 5-Sample-Überhitzungsmittelung umfasst damit ungefähr **3,89 s**.
- Der Stepper kann ungefähr **20,1 Schritte/s** nachfahren.
- `E17` wird im öffentlich erkennbaren **Abtaubetrieb `MAIN:2012 = 2`** in einem Defrost-Unterzustand direkt als Haupt-EEV-Zielposition benutzt.
- `MAIN:2011` ist der öffentliche **Gerät-EIN/AUS-/Betriebsstatus** (`1=Ein`, `0=Aus`). Der bisher anonyme interne Schalter `0x2001660C+0x1F Bit0` gehört zu diesem Status.
- `0x20016AA4+0x02` ist kein Startzähler, sondern ein **180-Takt-Stabilisierungs-/Ausschaltcountdown**. Im OFF-Pfad ergibt sich daraus eine harte EEV-Sequenz **480 → 0 Schritte**.
- `0x20016FD7` ist nur ein **Latch 'E07-Gate war aktiv'**; beim Abfallen des Gates startet es den 180er Countdown einmalig neu.
- Der bisher unbekannte Overrideblock `0x20016C10` gehört zum **Werkstest / Automatic Commercial Inspection**. `MAIN:1378` ist dort die direkte Haupt-EEV-Vorgabe; dieser Pfad ist für den normalen GL9-Betrieb irrelevant.
- Der frühe feste `350`-Schritt-Pfad ist als **T04-Sensorfehler-/Ungültigkeitsfallback** geschlossen (`0x08088134` liest das T04-Statusfeld `0x20015FA8+0x16`).
- `185 × 0,9 ≈ 166` ist **nicht** der direkte Firmwarepfad; `0,9` skaliert den Smart-Kennfeldwert nach T01.

---

# 2. Präzisierte Registernamen

| MAIN | Param. | Empfohlene Bezeichnung | Firmwarebedeutung |
|---:|---|---|---|
| 1131 | E01 | **Haupt-EEV Regelmodus** | `0=Manuell, 1=Auto, 2=Smart` |
| 1132 | E02 | **Haupt-EEV Ziel-Regelüberhitzung Heizen** | Sollwert; Istwert `MAIN:2067` |
| 1133 | E03 | **Haupt-EEV Heiz-Basis-/Startöffnung global** | kann E03-x im untersuchten Basispfad übersteuern |
| 1137 | E07 | **Haupt-EEV Mindestöffnung <61 Hz** | im aktiven E07-Schutzpfad bei `MAIN:2072 <61 Hz` |
| 1147 | E17 | **Haupt-EEV Abtau-Zielöffnung** | wird in einem Defrost-State direkt als EEV-Zielposition gesetzt |
| 1148 | E18 | **Haupt-EEV Ziel-Regelüberhitzung Kühlen** | Sollwert derselben Feedbackregelung |
| 1149 | E19 | **Smart-EEV Korrekturfenster ± %** | `SmartCenter × (1 ± E19/100)` |
| 1351 | E20 | **Haupt-EEV P-/Fehlerverstärkung** | signed 8-bit; proportionaler Skalierungsparameter, Default `1` |
| 1352 | E21 | **Haupt-EEV I-/Zeitfaktor (Divisor)** | signed 8-bit; geht als `1/E21` in den zeitabhängigen Anteil ein, Default `1` |
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
| 2011 | – | **Gerät-EIN/AUS-/Betriebsstatus** | `1=Ein`, `0=Aus`; aus `0x2001660C+0x1F Bit0` aufgebaut |
| 2012 | – | **Betriebsmodusstatus** | `2=Abtauen`; öffentlicher Defroststatus des E17-Pfads |
| 2020 | – | **Haupt-EEV Istposition / Schritte** | intern nachgeführte Stepperposition |
| 2053 | T12 | **Verdichter-Austritts-/Heißgastemperatur** | 5-stufige Auto-Matrixachse |
| 2065 | – | **Verdampfungstemperatur** | aus Niederdruck + A26/Kältemittel berechnete Sättigungsreferenz, `0,1 °C` |
| 2066 | – | **Abgasüberhitzung, 5-Sample-Mittel** | DWIN/PHNIX-Klartext bestätigt; 4-stufige Auto-Matrixachse, `0,1 K` |
| 2067 | – | **Rückgas-/Saugüberhitzung, 5-Sample-Mittel** | DWIN/PHNIX-Klartext bestätigt; Haupt-EEV-Feedback-Istwert, `0,1 K` |
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
1147 E17   → 0x200169E4+0x12
1148 E18   → 0x200169E4+0x14
1149 E19   → 0x200169E4+0x16
1351 E20   → 0x20016C9C+0x08 (signed byte)
1352 E21   → 0x20016C9C+0x09 (signed byte)

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

Das Gate-Bit `0x20016E18+3 Bit1` ist funktional als **übergeordnete Stabil-/Normalbetriebsfreigabe** einzuordnen. Die zentrale Setz-/Löschfunktion liegt in V3.4 bei ungefähr `0x0805E3A4`.

Direkt rekonstruierte Bedingungen sind unter anderem:

```text
0x20016E18+3 Bit0 == 0
    → Gate Bit1 löschen

öffentlicher Abtaubetrieb MAIN:2012 == 2
(zugehöriger interner Defroststatus 0x2001660C+0x20 Bits2..3 != 0)
    → Gate Bit1 sofort setzen

Stabilisierungs-/Ausschaltcountdown 0x20016AA4+0x02 != 0
    → Gate Bit1 löschen

sonst u. a. Mindest-/Stabilitätsbedingungen:
    0x20016BC8+0x02 >= 120
    UND (0x20016FA0+0x00 >= 50
         ODER 0x20016214+0x01 Bits1..2 >= 2)
    UND 0x20016E8C+0x01 >= 20
    UND weitere Mode-/Statusbedingungen
    → Gate Bit1 setzen
```

`0x20016AA4+0x02` ist **nicht** `MAIN:2071`. `MAIN:2071 / Kompressor-Sollfrequenz` liegt im selben Block bei `+0x08`. Das Feld `+0x02` ist inzwischen funktional als **180-Takt-Stabilisierungs-/Ausschaltcountdown** geschlossen: bei laufendem Verdichter und noch nicht freigegebenem Gate wird es auf `180` zurückgesetzt; bei stehendem Verdichter läuft es herunter. Zusätzlich merkt `0x20016FD7`, dass Gate Bit1 zuvor aktiv war. Fällt das Gate ab, startet dieses Latch den 180er Countdown einmalig neu und wird anschließend gelöscht.

Damit ist die **Funktion** des Gates weitgehend geschlossen: Es verhindert die normale E07-Mindestöffnungslogik während nicht stabilisierten Start-/Ausschalt-/Sonderphasen und erlaubt sie erst nach erfüllten Betriebs-/Zeitbedingungen. Während Abtauung wird es dagegen bewusst sofort gesetzt. Ein 1:1-Spiegel dieses Bits im öffentlichen Statusbereich wurde trotz Xref-Suche nicht gefunden. Offen bleibt damit im Wesentlichen nur der offizielle PHNIX-Klartextname des internen Gate-Bits.

---

# 6. MAIN:2020 / 2065 / 2066 / 2067

## 6.1 MAIN:2020

```text
0x20016AC4+0x04
→ Statusbuilder
→ MAIN:2020
```

Damit ist `2020` die intern nachgeführte **EEV-Istposition**.

## 6.2 MAIN:2065 = Verdampfungstemperatur

Der bislang nur als wahrscheinliche Sättigungsreferenz geführte Wert ist jetzt geschlossen:

```text
0x20016D5C+0x0A
→ Statusbuilder
→ MAIN:2065
```

Der Wert wird aus dem **Niederdruckpfad** unter Berücksichtigung des über `A26` gewählten Kältemittels berechnet. Der DWIN-/PHNIX-Referenzcode führt denselben öffentlichen Wert unter der Bezeichnung **„Verdampfungstemperatur“** (`蒸发温度`).

Damit gilt:

> **MAIN:2065 = aus Niederdruck berechnete Verdampfungs-/Sättigungstemperatur, 0,1 °C.**

Das schließt zugleich die wichtigste Referenzgröße der Saugüberhitzungsbildung.

## 6.3 Gemeinsame 5-Sample-Aufbereitung

```text
0x20016AC4+0x10 = Mittelwert Kanal 1 → MAIN:2066/10
0x20016AC4+0x14 = Mittelwert Kanal 2 → MAIN:2067/10
0x20016AC4+0x18 = Summe Kanal 1
0x20016AC4+0x1C = Summe Kanal 2
0x20016AC4+0x0E = Samplecounter
```

Nach fünf Samples wird jeweils durch `5.0` geteilt und der Akkumulator gelöscht.

## 6.4 MAIN:2067 = Rückgas-/Saugüberhitzung

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

> **MAIN:2067 = Rückgas-/Saugüberhitzung des Haupt-EEV, 5-Sample-Mittel.**

Der DWIN-/PHNIX-Referenzcode bestätigt für diesen Kanal die Rückgas-/Saugüberhitzungs-Semantik; die funktionale Zuordnung als Feedback-Istwert ist zusätzlich direkt im Mainboardcode geschlossen.

Primärer physikalischer Pfad:

```text
T05 Saugtemperatur
-
Verdampfungs-/Sättigungsreferenz aus Niederdruckpfad
```

Die Referenz `0x20016D5C+0x0A` ist **MAIN:2065 / Verdampfungstemperatur** und wird aus dem Niederdruckpfad A26-/kältemittelspezifisch berechnet. Derselbe Block enthält bei `+0x08` `MAIN:2069 / T15 Niederdruck`.

Fallbacks verwenden je nach Zustand T06 bzw. T03 als Referenz.

## 6.5 MAIN:2066 = Abgasüberhitzung

Kanal 1 ist die 4-stufige Auto-Matrixachse.

Normaler Hauptpfad:

```text
T12 Heißgas / Verdichter-Austritt
-
T03 Verdampfer-/Coil-Temperatur
```

In bestimmten Sonder-/Betriebszweigen wird T02 Auslasswasser als Referenz benutzt.

Der DWIN-/PHNIX-Referenzcode bezeichnet diesen Kanal als **Abgasüberhitzung**. Damit ist die bisher vorsichtigere Bezeichnung „Abgas-/Referenztemperaturdifferenz“ nicht mehr nötig.

> **MAIN:2066 = Abgasüberhitzung, 5-Sample-Mittel.**

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

## 7.3 Matrixwirkung – alle 20 Zustände

Dispatcherzustände:

```text
00 01 02 03 04
10 11 12 13 14
20 21 22 23 24
30 31 32 33 34
```

Zusätzlich zur aktuellen T12-Klasse speichert die Firmware das vorherige T12-Sample bei:

```text
0x20016F20 = vorheriges T12 / Heißgas
```

Nach der Matrixauswertung wird das aktuelle T12 dorthin übernommen. Die Randzustände verwenden damit nicht nur die absolute Heißgastemperatur, sondern auch deren **Trend**.

Vollständig rekonstruierte Wirkung:

| 2066-State \ T12-State | 0 | 1 | 2 | 3 | 4 |
|---:|---|---|---|---|---|
| **0** | T12 nicht steigend: `−8`; steigend: `−4` | nicht steigend: `−6`; steigend: `−2` | nicht steigend: `−4`; steigend: keine direkte Schrittänderung | nicht steigend: `−2`; steigend: keine direkte Schrittänderung | neutral / keine direkte Korrektur |
| **1** | PI mit E02/E18 | PI mit E02/E18 | PI mit E02/E18 | PI mit E02/E18 | PI mit **E02/E18 −1 K** |
| **2** | PI mit **E02/E18 −1 K** | PI mit −1 K | PI mit −1 K | PI mit −1 K | PI mit **E02/E18 −2 K** |
| **3** | PI mit **E02/E18 −1 K** | PI mit **E02/E18 −2 K** | PI mit −2 K | PI mit −2 K | bei T12 nicht fallend/steigend: **`+8` Schritte**, bei fallendem T12 keine direkte +8-Korrektur |

Die direkten `±N`-Aktionen setzen/rebasieren zusätzlich interne Reglerzustände, damit der PI-Anteil nicht gegen die harte Randkorrektur weiterintegriert.

Interpretation des Codes:

- **niedrige Abgasüberhitzung + niedrige T12-Klasse:** Ventil wird aktiv geschlossen; stärker, wenn T12 nicht ansteigt;
- **mittlere Bereiche:** normale PI-Regelung gegen E02/E18;
- **hohe thermische Zustände:** wirksamer Soll-SH wird um `1…2 K` abgesenkt, wodurch der PI-Regler tendenziell weiter öffnet;
- **State 34:** solange T12 noch nicht fällt, erfolgt zusätzlich eine direkte `+8`-Schritt-Öffnung.

Auto ist damit eine **zustandsabhängige nichtlineare Überhitzungsregelung mit zusätzlicher Heißgas-Trendlogik**.

---

# 8. Feedback-Helper 0x08054868 – PI-artiger Haupt-EEV-Regler

Eingänge:

```text
s0 = Überhitzungs-Sollwert E02/E18 (zustandsabhängig ggf. verschoben)
s1 = MAIN:2067/10 = Rückgas-/Saugüberhitzung
error = actual - target
```

Die beiden bislang anonymen Konfigurationsbytes sind öffentliche Parameter:

```text
MAIN:1351 / E20 → 0x20016C9C+0x08  signed8
MAIN:1352 / E21 → 0x20016C9C+0x09  signed8
```

Beide stehen im untersuchten Defaultdatensatz auf `1`.

## 8.1 E20

E20 wirkt als **proportionaler Fehler-/Gainfaktor** des Haupt-EEV-Feedbackreglers. Die proportionale Korrektur ist nicht linear über den gesamten Fehlerbereich, sondern wird über mehrere Fehlerzonen gestuft und schließlich begrenzt.

Im rekonstruierten Pfad liegt die maximale proportionale Einzelkorrektur bei ungefähr:

```text
±60 Schritte
```

## 8.2 E21

E21 geht in den zeitabhängigen/integralen Anteil über einen Divisor ein:

```text
... × (1 / E21)
```

Damit verhält sich E21 funktional wie ein **I-/Zeitfaktor bzw. Integralskalierungs-Divisor**.

Die Parameter-Synchronisation ist direkt:

```text
MAIN:1351 → low byte → E20 / 0x20016C9C+8
MAIN:1352 → low byte → E21 / 0x20016C9C+9
```

Das Mainboard führt dabei **keine Wertebereichs- oder Nullprüfung** durch. Im DWIN-Referenzcode werden E20 (`0547H/2547H`) und E21 (`0548H/2548H`) ebenfalls nur über die generische `Four_Variable_Communication` synchronisiert; diese Routine prüft Änderungen, aber keine Min-/Max-Werte.

Unmittelbar danach berechnet der Regler:

```text
I_factor = 1.0 / E21
```

Daher gilt für die Firmwareanalyse eindeutig:

> **E21=0 darf nicht verwendet werden.** Das Mainboard selbst verhindert den Wert nicht. Ob ein bestimmtes DGUS-Seitenwidget die Eingabe zusätzlich begrenzt, ist davon unabhängig und im ASM-Kommunikationspfad nicht belegt.

## 8.3 Reglercharakteristik

Der Helper ist zustandsbehaftet und besitzt folgende rekonstruierte Eigenschaften:

```text
Fehler = MAIN2067 - wirksamer Soll-SH
Totzone: ungefähr ±0,5 K
Fehlerzonen: um ±0,5 / ±2 / ±3 / ±5 K
P-Korrektur: E20 × Fehler, zonenabhängig skaliert, begrenzt etwa ±60 Schritte
I-Korrektur: (1/E21) × Fehler × zonenabhängigen Faktor
Ausgangsänderung je tatsächlich verarbeiteter Korrektur: max. etwa ±5 Schritte
```

Zusätzlich existiert eine **zeitliche Beruhigung nahe am Sollwert**:

```text
wenn -2 K < Fehler < +2 K:
    interner Zähler ++
    Aufruf 1..3 → bisheriges Ziel unverändert zurückgeben
    Aufruf 4    → Korrektur berechnen, Zähler zurücksetzen
sonst:
    Zähler zurücksetzen und sofort korrigieren
```

Bei einem Scheduleraufruf etwa alle `0,778 s` ergibt das:

```text
|Fehler| >= 2 K → mögliche Korrektur etwa alle 0,778 s
|Fehler| <  2 K → mögliche Korrektur etwa alle 3,11 s
```

Die nominelle ±5-Schritt-Slew-Begrenzung entspricht außerhalb der kleinen Fehlerzone maximal ungefähr `6,4 Schritte/s`. Innerhalb `±2 K` ist die effektive Sollwertänderung durch die 4-Aufruf-Beruhigung entsprechend langsamer.

Ein expliziter D-Anteil wurde nicht gefunden. Die Struktur ist daher am treffendsten als **nichtlinearer PI-artiger Überhitzungsregler mit Totzone, Fehlerzonen, Debounce und Slew-Begrenzung** zu bezeichnen.

Der Steppermotor selbst kann schneller nachfahren; siehe Zeitbasis weiter unten.

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

# 12. E17 – direkter Abtaupfad

`E17 / MAIN:1147` ist vollständig als **Haupt-EEV Abtau-Zielöffnung** geschlossen.

Der öffentliche Betriebsmodusstatus ist:

```text
MAIN:2012 = 2  → Abtauen / Defrost
```

Derselbe interne Defrostzustand, aus dem der Statusbuilder `MAIN:2012 = 2` erzeugt, lässt den Abtau-Unterzustandsautomaten laufen. In dessen State `2` schreibt V3.4 den Parameter E17 direkt in die Haupt-EEV-Zielposition:

```text
öffentlicher Betrieb: MAIN:2012 == 2
    ↓
interner Defrost-Unterzustand 0x200168F0[0] == 2
    ↓
0x200169E4+0x12 = E17 / MAIN:1147
    ↓
0x20016AC4+0x02 = Haupt-EEV-Zielposition
```

Vereinfacht:

```text
if MAIN2012 == DEFROST and defrost_substate == 2:
    main_EEV_target = E17
```

Damit ist E17 nicht nur über Defaultwert oder Kontext interpretiert, sondern **binär bis zum öffentlichen Abtaustatus nachgewiesen**. Während desselben Defrostbetriebs wird außerdem das E07-Gate sofort gesetzt.

---

# 13. Scheduler- und Stepper-Zeitbasis

Die V3.4 schaltet auf **72 MHz Systemtakt**. APB1 läuft mit `/2`; für den TIM6-Pfad ergibt sich durch die STM32-Timerverdopplung wieder ein Timerclock von **72 MHz**.

TIM6 wird mit:

```text
PSC = 111
ARR = 499
```

konfiguriert. Daraus folgt:

```text
72 MHz / (112 × 500) ≈ 1285,714 Hz
Timerinterrupt ≈ 0,7778 ms
```

Jeder vierte Timerinterrupt gibt den Stepper-/Basistask frei:

```text
4 × 0,7778 ms ≈ 3,111 ms
```

Der Haupt-EEV-Steppertreiber führt erst bei jedem 16. solchen Taskaufruf einen Motorstep aus:

```text
16 × 3,111 ms ≈ 49,78 ms pro Schritt
≈ 20,1 Schritte/s
```

Beispiele:

```text
100 Schritte ≈ 4,98 s
200 Schritte ≈ 9,96 s
480 Schritte ≈ 23,9 s
```

Der große Reglerscheduler besitzt **50 Slots**; ein Slot wird nach fünf 3,111-ms-Basistakten weitergeschaltet:

```text
5 × 3,111 ms ≈ 15,56 ms pro Slot
50 × 15,56 ms ≈ 0,778 s pro vollständigem Schedulerumlauf
```

Der Haupt-EEV-Regler sitzt in diesem 50-Slot-Zyklus und wird damit ungefähr alle **0,778 s** aufgerufen.

Da 2066/2067 über fünf Regler-/Messsamples gemittelt werden, entspricht die Mittelungszeit ungefähr:

```text
5 × 0,778 s ≈ 3,89 s
```

Wichtig für Logauswertungen: `2020` kann deshalb einer Sollwertänderung sichtbar hinterherlaufen. Die Regelung darf nicht so interpretiert werden, als könne das Ventil einen neuen Zielwert sprunghaft erreichen.

---

# 14. Sonderpfade: Werkstest, Start/Homing und Sensorfallback

## 14.1 `0x20016C10` = Werkstest / Automatic Commercial Inspection

Der zuvor unbekannte Overrideblock ist geschlossen. Die Parameter-Synchronisation ordnet den Block dem öffentlichen Factory-Test-Bereich zu:

```text
MAIN:1371 → 0x20016C10+0x04  Factory test mode
MAIN:1372 → +0x06            Automatic commercial inspection on/off
MAIN:1373 → +0x07            Commercial inspection mode
MAIN:1374 → +0x0A            Target temperature
MAIN:1375 → +0x09            Compressor frequency
MAIN:1376 → +0x0C            Fan 1 speed
MAIN:1377 → +0x0E            Fan 2 speed
MAIN:1378 → +0x10            Main EEV
MAIN:1380 → +0x08            Water-pump speed
```

Der DWIN-Referenzcode bezeichnet `MAIN:1378` ausdrücklich als:

> **自动商检主路电子膨胀阀 – Automatic commercial inspection main electronic expansion valve**

Im Haupt-EEV-Code gilt sinngemäß:

```text
if factory_internal_state(+5) == 3:
    if MAIN1378 / block+0x10 != 0:
        target = MAIN1378
    else:
        target = normal_base
```

Damit ist `0x20016C10` **kein unbekannter Recovery-Regler**, sondern ein Werkstest-/Produktionsprüfpfad. Für den normalen GL9-Betrieb ist er nicht relevant.

## 14.2 Ausschalt-/Druckausgleich-/Homingpfad vor der normalen Regelung

Der bisher als anonymer globaler Schalter geführte Wert ist öffentlich benennbar:

```text
0x2001660C+0x1F Bit0
→ MAIN:2011

MAIN:2011 = 1  → Gerät/Betrieb EIN
MAIN:2011 = 0  → Gerät/Betrieb AUS
```

Damit ist dieser Zweig kein unbekannter Start-State, sondern der **Gerät-EIN/AUS-Pfad** der EEV-Logik.

Der zweite wichtige Wert:

```text
0x20016AA4+0x02
```

ist ebenfalls **kein Startzähler**. Er wird auf `180` gesetzt und bei stehendem Verdichter pro EEV-Regler-/Schedulerumlauf heruntergezählt. Bei einer EEV-Reglerperiode von ungefähr `0,778 s` entspricht das insgesamt rund:

```text
180 × 0,778 s ≈ 140 s
```

Im OFF-/Stabilisierungszweig gilt:

```text
E07-Gate aktiv
    → Haupt-EEV-Ziel = 480 Schritte

E07-Gate inaktiv:
    Countdown >= 61
        → Haupt-EEV-Ziel = 480 Schritte

    Countdown < 61
        → Haupt-EEV-Ziel = 0 Schritte
```

Nach einem Neustart des Countdowns bei `180` ergibt sich damit ungefähr:

```text
180 … 61  → ca. 93 s bei 480 Schritten
60 … 0    → ca. 47 s bei 0 Schritten
```

Die reale Reihenfolge ist also ausdrücklich:

```text
480 Schritte  →  0 Schritte
```

und **nicht** `0 → 480`.

Funktional passt das zu einer **Ausschalt-/Druckausgleich-/anschließenden Schließ-/Homingsequenz**. Die Firmware hält das Ventil zunächst vollständig offen und fährt es erst im letzten Teil des Countdownfensters auf 0.

Zusätzlich existiert das Byte:

```text
0x20016FD7
```

Dieses ist kein eigener Schutz- oder Recoveryzustand, sondern lediglich ein **Latch „E07-Gate war zuvor aktiv“**:

```text
Gate Bit1 aktiv
    → latch = 1

Gate fällt später ab und latch == 1
    → Countdown 0x20016AA4+2 einmalig wieder auf 180 setzen
    → latch löschen
```

Damit ist auch der früher unbekannte zusätzliche Resettrigger des 180er Countdowns funktional geschlossen.

Danach existiert ein weiterer Starttabellenpfad, der abhängig von Maschinen-/Mode-/Statewerten direkt eine vorberechnete EEV-Anfangsöffnung auswählt. Sind dessen Bedingungen nicht erfüllt, läuft vor der vollständig normalen Matrixregelung ein weiterer Verzögerungszähler.

## 14.3 T04-Sensorfehlerfallback

Der frühe feste Zielwert `350` ist jetzt physikalisch zugeordnet. Die Funktion:

```text
0x08088134
```

liest direkt:

```text
0x20015FA8+0x16 = Status-/Gültigkeitsfeld des T04-Sensoreintrags
```

Im frühen Regel-/Startfenster gilt sinngemäß:

```text
T04 gültig   → normale Basisöffnung verwenden
T04 ungültig → 350 Schritte
```

Damit ist der 350-Schritt-Wert ein **T04-Sensorfehler-/Ungültigkeitsfallback** und kein unbekannter Recovery-Sollwert.

## 14.4 Weitere Start-/Sonderlogik

Die wesentlichen zuvor anonymen Sonderpfade sind inzwischen zugeordnet:

- `MAIN:2011` trennt Gerät EIN/AUS,
- `MAIN:2012=2` kennzeichnet Defrost,
- E17 ist daran als direkte Abtau-Zielöffnung angebunden,
- `0x20016AA4+2` ist der 180-Takt-Stabilisierungs-/Ausschaltcountdown,
- `0x20016FD7` ist nur dessen Gate-Abfall-Latch,
- `MAIN:1378` gehört zum Factory-/Commercial-Inspection-Override,
- der feste 350-Schritt-Pfad ist der T04-Sensorfehlerfallback.

Einzelne interne Mode-/Statebytes besitzen weiterhin keinen Hersteller-Klartextnamen. Für die normale Auto-/Smart-Regelung verändern diese fehlenden Symbolnamen das rekonstruierte Regelmodell jedoch nicht mehr.

---

# 15. Kompakter Pseudocode

```text
# Heizbasis
base = E03 if E03 != 0 else E03_segment_direct(T04)

# Regelgrößen (5-Sample-Mittel)
discharge_sh = MAIN2066/10
suction_sh   = MAIN2067/10

# Auto-Matrix
aux_state = hysteresis(discharge_sh, A26_refrigerant_thresholds)
hotgas_state = hysteresis(T12, A26_refrigerant_thresholds)
state = (aux_state << 4) | hotgas_state

auto_target = nonlinear_PI_feedback(state, E02_or_E18, suction_sh, E20, E21)

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

# 16. Noch offene Punkte

Für die **praktische GL9-Haupt-EEV-Regelung** sind die relevanten Funktionsblöcke inzwischen nahezu vollständig geschlossen. Übrig bleiben im Wesentlichen nur noch Benennungs-/HMI-Details:

1. **E07-Gate `0x20016E18+3 Bit1`:** Funktion, Defrost-Sofortsetzung, Countdown-Sperre und wesentliche Normalbetriebsbedingungen sind rekonstruiert. Offen ist nur der offizielle PHNIX-Klartextname; ein direkter 1:1-Statusspiegel im öffentlichen Bereich 2001–2180 wurde nicht nachgewiesen.
2. **DGUS-Widgetgrenzen für E20/E21:** Mainboard und DWIN-Kommunikationscode begrenzen E20/E21 nicht. Falls die konkrete DGUS-Seite per Widget-Metadaten Min/Max erzwingt, wäre dies nur noch eine HMI-Eigenschaft. Für die Firmware gilt unabhängig davon: `E21=0` vermeiden.
3. **Einzelne interne State-Symbolnamen:** Einige Start-/Tabellen-/Modebytes besitzen keinen bekannten PHNIX-Klartextnamen. Ihre Wirkung im Haupt-EEV-Pfad ist jedoch bereits nachvollziehbar.

Nicht mehr offen sind:

- die 20 Einzelaktionen der Auto-Matrix einschließlich T12-Trend,
- `0x20016C10` / `MAIN:1378` als Factory-Test-/Commercial-Inspection-Override,
- der feste 350-Schritt-Pfad als T04-Sensorfehlerfallback,
- E20/E21-Datenfluss und fehlende Mainboard-Nullprüfung,
- E17 als bis `MAIN:2012=2` rückverfolgte Abtau-Zielöffnung,
- `MAIN:2011` als Gerät-EIN/AUS-/Betriebsstatus,
- `0x20016AA4+2` als 180-Takt-Stabilisierungs-/Ausschaltcountdown,
- die OFF-Sequenz **480 → 0 Schritte**,
- `0x20016FD7` als einmaliges E07-Gate-Abfall-Latch.

Damit ist das **normale GL9-Haupt-EEV-Verhalten in Auto und Smart einschließlich Mindestöffnung, Ausschalt-/Druckausgleich-/Homingpfad, Abtauung, Werkstest und Sensorfallback praktisch vollständig rekonstruierbar**. Die verbleibenden Punkte betreffen überwiegend Herstellerbezeichnungen bzw. HMI-Metadaten, nicht mehr die Regelwirkung.

---

# 17. Empfohlenes Logging

```text
MAIN:1131 E01
MAIN:1132 E02
MAIN:1147 E17
MAIN:1149 E19
MAIN:1351 E20
MAIN:1352 E21
MAIN:2011 Gerät-EIN/AUS-/Betriebsstatus
MAIN:2012 Betriebsmodusstatus / 2=Abtauen
MAIN:2020 EEV-Istposition
MAIN:2045 T01 Einlasswasser
MAIN:2048 T04 wirksame Außentemperatur
MAIN:2053 T12 Heißgastemperatur
MAIN:2065 Verdampfungstemperatur
MAIN:2066 Abgasüberhitzung
MAIN:2067 Rückgas-/Saugüberhitzung
MAIN:2071 Kompressor-Sollfrequenz
MAIN:2072 Kompressor-Istfrequenz
Betriebsmodus / Abtauzustand
```

Damit lassen sich die Auto-Matrixstates, die drei Smart-Achsen, das E19-Fenster und die zeitliche Reaktion des PI-artigen Haupt-EEV-Reglers offline rekonstruieren.
