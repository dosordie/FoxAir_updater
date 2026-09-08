# Mainboard-Firmware V3.4 – Hardware-Konfiguration und Maschinenprofile

Stand: 8. September 2026

Dieses Dokument beschreibt, **an welchen Parametern die Firmware 82400644 / V3.4 unterschiedliche Hardware- und Maschinenvarianten konfiguriert** und welche Wirkung diese Parameter im Mainboardcode bzw. auf dem internen Inverter-/Fan-Bus besitzen.

Es ist bewusst als V3.4-Dokument angelegt. Viele RAM-Strukturen sind gegenüber V3.3 unverändert, die Codeadressen liegen wegen der anderen Imagebasis jedoch an anderen Stellen.

Untersuchtes Binary:

```text
Produkt-/Softwarekennung: 82400644
Firmwareversion:          0034 / V3.4
Dateigröße:               289806 Byte
SHA-256:                  97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890
Imagebasis:               0x08080000
```

Bewertung:

- **bestätigt** – direkt in V3.4 nachgewiesen
- **sehr wahrscheinlich** – Datenfluss geschlossen, Herstellerbezeichnung bzw. physische Modellzuordnung noch offen
- **Hypothese** – plausible Zuordnung, aber noch nicht ausreichend belegt

---

# 1. Kurzfazit

Die Produkt-/Leistungsklasse einer FoxAir-/PHNIX-Wärmepumpe wird **nicht durch einen einzelnen Parameter „7 kW / 9 kW / 12 kW“** festgelegt.

Die V3.4 kombiniert mehrere Hardware- und Maschinenparameter:

| Parameter | MAIN | Funktion | Wirkung |
|---|---:|---|---|
| H33 | 1019 | Fan- und Compressor-Driver integriert | bestimmt interne Driverarchitektur und Modbus-Paketlängen |
| A26 | 1054 | Kältemittel-/Maschinenprofil | R32/R290-Stoffdaten + T04×T02-Maschinenkennfeld |
| F01 | 1059 | Lüftermotortyp | Auswahl integrierter/externer DC-Fan-Driver-Pfade |
| F10 | 1074 | Lüfteranzahl | Einzel-/Doppellüfter, zweiter Sollkanal wird aktiviert/unterdrückt |
| F18/F19 | 1081/1083 | minimale Lüfterdrehzahlen | Kennlinienuntergrenzen |
| F23 | 1089 | Nenn-Drehzahl DC-Lüfter | Fan-Hardware-/Kennlinienreferenz |
| F25/F26 | 1103/1104 | maximale Lüfterdrehzahlen | Kennlinienobergrenzen |
| C03 | 1220 | maximale Kompressorfrequenz | absolute obere Grundgrenze des Verdichters |
| C04 | 1221 | Kompressormodell | wird als Driver-/Kompressorprofil an Unit 1 übertragen |
| A39 | 1343 | Maximaler Stromwert | wird direkt als Stromlimit an Unit 1 übertragen |
| A40 | 1344 | Nenn-Wasserdurchfluss | hydraulische Nenn-/Plausibilitätsgröße; Teil der Maschinenkonfiguration |

Wichtig:

> `MAIN:1422` gehört **nicht** zur statischen Hardware-/Leistungsklasse. V3.4 benutzt den Wert als relative Verdichterbegrenzung in einem SG-Ready-/Zusatzheizungs-Koordinationspfad.

---

# 2. H33 – Driverarchitektur

```text
MAIN:1019 / H33
0 = Fan Motor Driver und Compressor Driver getrennt
1 = integriert
```

Live-RAM:

```text
0x20016774 + 0x28
```

V3.4 benutzt H33 weiterhin unmittelbar im Unit-1-Scheduler.

## H33 = 0

```text
Unit 1 FC10 ab 1999: 5 Wörter
Unit 1 FC03 ab 2099: 22 Wörter
```

## H33 != 0

```text
Unit 1 FC10 ab 1999: 16 Wörter
Unit 1 FC03 ab 2099: 51 Wörter
```

Die lange Variante enthält zusätzlich Fan-Driver-Sollwerte und -Telemetrie.

**Bewertung: bestätigt.**

---

# 3. C04 – Kompressor-/Driverprofil

```text
MAIN:1221 / C04
Live: 0x20016B20 + 0x06
Registerbereich laut Parameterdefinition: 0..99
```

V3.4 behandelt C04 auf dem Mainboard **nicht als lokale Tabelle mit konkreten Kompressordaten**. Der wesentliche Laufzeitverbraucher liegt im Unit-1-Sendepaket:

```text
wenn C04 == 0:
    INV1:TX:2003 = 0
sonst:
    INV1:TX:2003 = C04 + 0x083A
```

Beispiel:

```text
C04 = 13
→ 13 + 0x083A
→ INV1:TX:2003 = 2119
```

Damit ist C04 ein **opaque Driver-/Kompressormodell-Selektor** aus Sicht des Mainboards.

## Was daraus nicht folgt

Der erlaubte Bereich `0..99` beweist **nicht**, dass es 100 physische Verdichtertypen gibt. Das Mainboard reicht eine numerische Profilkennung weiter. Die eigentliche Zuordnung zu Motor-/Verdichterparametern sitzt sehr wahrscheinlich im Unit-1-Inverterboard bzw. dessen Firmware.

## Offene Zuordnung

Noch nicht geschlossen ist beispielsweise:

```text
C04 = x → konkreter PHNIX-/Hitachi-/GMCC-/anderer Verdichtertyp
```

Dafür ist ein Vergleich mehrerer Geräteprofile oder die Firmware/Parameterliste des Unit-1-Boards erforderlich.

**Bewertung: Transport und Transformation bestätigt; konkrete C04→Verdichtertabelle offen.**

---

# 4. A39 – maximales Stromlimit; INV1:TX:2002 geschlossen

```text
MAIN:1343 / A39
Bezeichnung: Max. Current Value / Maximaler Stromwert
Typ: AMP_X2
Einheit: A
```

Live-RAM:

```text
0x200162D8 + 0x5C
```

V3.4 schließt damit einen früher offenen Punkt der V3.3-Analyse:

```text
MAIN:1343 / A39
      ↓
0x200162D8 + 0x5C
      ↓
INV1:TX:2002
      ↓
Inverter-/Leistungsboard
```

Damit ist:

> **INV1:TX:2002 = vom Mainboard übertragener Maximalstrom-/Stromlimitwert A39.**

Die Parameterdefinition `AMP_X2` bedeutet für die Bedien-/Katalogdarstellung:

```text
Ampere = RAW / 2
```

Ob ein Rohwert `0` auf dem Inverter „kein Limit“, „Driverdefault“ oder eine andere Sondersemantik bedeutet, ist im Mainboard nicht abschließend belegt.

**Bewertung: Datenfluss bestätigt.**

---

# 5. Elektrische Begrenzung im Betrieb

Zur statischen Konfiguration A39 kommen die realen Messwerte:

```text
MAIN:2057 / T35 = AC Input Current
MAIN:2042 / T36 = Kompressor-Phasenstrom
```

Der bereits rekonstruierte Frequenzbegrenzungsstatus `MAIN:2139 Bit5` gehört zur AC-Eingangsstrombegrenzung.

Damit ergibt sich die Kette:

```text
A39 Maximalstrom
   ↓
INV1:TX:2002
   ↓
Inverter / reale Stromaufnahme
   ↓
MAIN:2057 / T35
   ↓
Strom-Limiter / Derating
   ↓
MAIN:2139 Bit5
```

**Bewertung: A39-Transport bestätigt; Bit5-Strom-Limiter aus V3.3 bestätigt und strukturell mit V3.4 kompatibel.**

---

# 6. A26 – Kältemittel und Maschinenprofil

```text
MAIN:1054 / A26
Live: 0x20016744 + 0x12
```

Die aktuelle Registerbelegung lautet:

| A26 | Profil |
|---:|---|
| 0 | R32 |
| 1 | R290 |
| 2 | R32-1 |
| 3 | R290-1 |
| 4 | R32-2 |
| 5 | R290-2 |
| 6 | R32-3 |
| 7 | R290-3 |

## 6.1 Parität wählt das physische Kältemittel

V3.4 enthält zahlreiche Pfade mit:

```text
A26 % 2
```

Damit gilt direkt:

```text
gerade A26: 0,2,4,6 → R32-Familie
ungerade A26: 1,3,5,7 → R290-Familie
```

Diese Auswahl wird in thermodynamischen Rechen-/Tabellenpfaden verwendet. A26 ist daher **keine reine Anzeigeoption**.

**Bewertung: bestätigt.**

## 6.2 Der volle Wert 0..7 wählt zusätzlich ein Maschinenkennfeld

Neben der Paritätsauswahl wird A26 vollständig als Tabellenindex benutzt:

```text
Tabellenbasis + A26 * 0x38
```

Dabei ist:

```text
0x38 = 56 Byte = 7 × 8
```

Es existieren damit acht getrennte 7×8-Profile.

Die beiden Achsen konnten geschlossen werden:

```text
7 Zeilen  = T04 Außentemperatur
8 Spalten = T02 Auslass-/Vorlaufwassertemperatur
```

Öffentlich:

```text
T04 = MAIN:2048; direkter lokaler Zusatzweg MAIN:2136
T02 = MAIN:2046
```

Die State-Machines besitzen jeweils eine Hysterese von ungefähr `0,9 K`.

---

# 7. A26-Kennfeldachsen

## 7.1 T04 / Außentemperatur – 7 Klassen

Beim Ansteigen der Temperatur:

| Zeile | T04 |
|---:|---:|
| 0 | `< -21 °C` |
| 1 | `-21 … < -14 °C` |
| 2 | `-14 … < -1 °C` |
| 3 | `-1 … < +11 °C` |
| 4 | `+11 … < +22 °C` |
| 5 | `+22 … < +28 °C` |
| 6 | `>= +28 °C` |

Rückschaltschwellen liegen ungefähr bei:

```text
-21,9 / -14,9 / -1,9 / +10,1 / +21,1 / +27,1 °C
```

## 7.2 T02 / Auslasswassertemperatur – 8 Klassen

Beim Ansteigen:

| Spalte | T02 |
|---:|---:|
| 0 | `< 20 °C` |
| 1 | `20 … < 40 °C` |
| 2 | `40 … < 45 °C` |
| 3 | `45 … < 50 °C` |
| 4 | `50 … < 55 °C` |
| 5 | `55 … < 60 °C` |
| 6 | `60 … < 65 °C` |
| 7 | `>= 65 °C` |

Rückschaltschwellen:

```text
19,1 / 39,1 / 44,1 / 49,1 / 54,1 / 59,1 / 64,1 °C
```

**Bewertung: beide Achsen direkt rückverfolgt.**

---

# 8. Bedeutung der A26-Tabellenwerte

Der 7×8-Tabellenwert ist ein Index auf folgende Frequenzreihe:

```text
30, 36, 42, 48, 54, 60, 66, 72,
78, 84, 90, 96, 102, 108, 114 Hz
```

also:

```text
F_ref = 30 Hz + Index × 6 Hz
```

Wichtig: `F_ref` ist **nicht einfach der unmittelbar an den Verdichter gesendete Sollwert**.

V3.4 benutzt den Wert als **betriebspunktabhängige 100-%-Referenzfrequenz**.

Einerseits wird daraus ein Diagnosewert gebildet:

```text
Last_% ≈ Verdichter-Istfrequenz / F_ref × 100
```

Andererseits wird `F_ref` als Basis realer relativer Frequenzgrenzen verwendet:

```text
F_limit = Prozent × F_ref / 100
```

anschließend mit der dynamischen Mindestfrequenz und C03 geklemmt.

Damit ist A26 tatsächlich Teil der **Maschinenleistungscharakteristik**.

---

# 9. Extrahierte A26-Profile

## 9.1 R32 – A26 0, 2, 4 und 6

In diesem 7×8-Kennfeld sind alle vier R32-Profile byteidentisch:

```text
90 90 90 90 90 90 84 78
90 90 90 90 90 84 78 72
90 90 90 90 84 78 72 66
90 90 90 84 78 72 66 60
90 90 84 78 72 66 60 54
84 84 78 72 66 60 54 48
66 66 60 54 48 48 48 42
```

Damit gilt für **dieses Kennfeld**:

```text
A26=0 = A26=2 = A26=4 = A26=6
```

Das bedeutet nicht zwingend, dass die Profile in allen anderen Firmwaretabellen identisch sind.

## 9.2 R290 – A26 1

```text
84 90 90 90 90 90 90 84
90 90 90 90 90 90 90 84
90 90 84 78 78 72 72 66
90 84 78 72 72 66 66 60
84 78 72 66 66 60 60 54
78 72 66 60 60 54 54 48
72 66 60 54 54 48 48 42
```

## 9.3 R290-1 – A26 3

```text
108 102 102  96  96  90 72 48
108 102 102 102  96  90 72 48
108 108 108 108 102 102 78 48
102 114 114 114 114 108 84 78
102 114 114 114 114 108 84 78
102 102 102 102  96  90 78 54
102 102 102  90  84  78 60 48
```

Dieses Profil reicht bis `114 Hz` und unterscheidet sich deutlich vom Basis-R290-Profil.

## 9.4 R290-2 – A26 5

In diesem Kennfeld identisch zu A26=1 / R290.

## 9.5 R290-3 – A26 7

```text
108 108 108 102  96 90 84 78
108 108 108 102  96 90 90 78
108 108 108 102 102 96 90 84
108 108 108 108 102 96 90 78
 96  84  78  72  72 66 60 54
 84  78  72  66  66 60 54 48
 66  66  60  54  48 48 48 42
```

Dieses Profil reicht bis `108 Hz`.

## Interpretation

Die Suffixe `-1/-2/-3` sind damit **nicht lediglich alternative Namen für dasselbe Kältemittel**. Mindestens bei R290 wählen sie unterschiedliche Maschinen-/Leistungskennfelder.

Eine konkrete Zuordnung wie `R290-1 = GL12` ist **noch nicht belegt**.

---

# 10. DIAG:6023 – relative Verdichterlast

V3.4 veröffentlicht die aus `F_ref` abgeleitete relative Last im Engineering-Diagnosebereich.

```text
DIAG:6023
≈ MAIN:2072 / F_ref × 100
```

`DIAG:6023` selbst besitzt keinen nachgewiesenen Rückverbrauch durch Lüfter-, EEV-, COP- oder Leistungsregelung. Es ist damit ein **Diagnose-/Anzeigewert**.

Die zugrunde liegende Referenzfrequenz `F_ref` besitzt dagegen echte Verbraucher in der Verdichterbegrenzung.

Für Live-Tests eignet sich deshalb:

```text
FC03 DIAG:6022..6023
```

zusammen mit:

```text
MAIN:1054 A26
MAIN:2046 T02
MAIN:2048 T04
MAIN:2072 Istfrequenz
```

**Bewertung: DIAG-Datenfluss in V3.4 bestätigt; Live-Verifikation am realen Gerät noch ausstehend.**

---

# 11. MAIN:1422 – kein Hardwareparameter

```text
MAIN:1422
Live: 0x20016A24 + 0x00
Factory-Default V3.4: 70
```

Ein Verdichter-Limitpfad benutzt:

```text
F_limit = MAIN:1422 % × F_ref
```

und klemmt das Ergebnis anschließend zwischen dynamischer Mindestfrequenz und C03.

Der Aktivzustand liegt intern bei:

```text
0x20016A44 + 0x09
```

und wird als:

```text
MAIN:2139 Bit8 / 0x0100
```

veröffentlicht.

Die zugehörige State-Machine verwendet unter anderem:

```text
A31 / MAIN:1049  Electric Heater On AT
A32 / MAIN:1050  Electric Heater Delays Comp. On Time
A33 / MAIN:1063  Electric Heater Opening Temp. Diff
A35 / MAIN:1031  Electric Heater Off Temp. Diff
H18 / MAIN:1032  Electric Heater Energy Stage
```

und besitzt einen Pfad für:

```text
SG-Ready Mode 4 / High PV
```

Daher ist die derzeitige Arbeitsklassifikation:

> **MAIN:1422 = relative Verdichter-Frequenz-/Leistungsgrenze im SG-Mode-4-/Zusatzheizungs-Koordinationspfad.**

Der Datenfluss `1422 → Prozent × F_ref → Verdichter-Hz-Grenze` ist bestätigt. Der originale PHNIX-Parametername und die vollständige 1:1-Zuordnung aller internen Zusatzheizungszustände sind noch offen.

**Wichtig:** MAIN:1422 darf nicht als statische Maschinen-/Nennleistungsklasse dokumentiert werden.

---

# 12. MAIN:2139 Bit8

V3.4 packt:

```text
0x20016A44+0x09 != 0
```

als:

```text
MAIN:2139 Bit8 = 1
```

Der Zustand gehört zum oben beschriebenen relativen Verdichterlimit über MAIN:1422.

Arbeitsname:

```text
Bit8 = SG-/Zusatzheizungs-Koordination: relatives Verdichterfrequenzlimit aktiv
```

**Bewertung: Writer und Limitpfad bestätigt; Herstellerwortlaut offen.**

---

# 13. Lüfterhardware

## 13.1 F01 – Lüftermotortyp

```text
MAIN:1059 / F01
Live: 0x20016A04 + 0x00
```

Bekannte Werte:

```text
0 = Legacy Hochgeschwindigkeits-Lüfter
1 = Legacy zweistufiger Lüfter
3 = DC Fan Motor
4 = DC Fan Motor External Drive
```

Im V3.4-Unit-1-Paket werden die aktuellen DC-Varianten übersetzt:

```text
F01 == 3 → Driver-Selektor 1
F01 == 4 → Driver-Selektor 2
```

Diese Selektoren werden in den erweiterten H33-Paketbereich geschrieben.

Damit hat F01 eine echte Hardwarewirkung und ist nicht nur eine UI-Auswahl.

## 13.2 F10 – Lüfteranzahl

```text
MAIN:1074 / F10
Live: 0x20016A04 + 0x18

0 = Einzel-Lüfter
1 = Doppel-Lüfter
```

V3.4 benutzt F10 in der Fan-Regelung. Bei Einzel-Lüfter-Konfiguration wird der zweite Sollkanal in den relevanten Pfaden auf 0 gesetzt; bei Doppel-Lüfter-Konfiguration wird er aktiv verwendet.

## 13.3 Weitere Hardware-/Kennlinienparameter

| MAIN | Code | Bedeutung |
|---:|---|---|
| 1081 | F18 | minimale Lüfterdrehzahl Kühlen |
| 1083 | F19 | minimale Lüfterdrehzahl Heizen |
| 1089 | F23 | Nenn-Drehzahl DC-Lüfter |
| 1103 | F25 | maximale Lüfterdrehzahl Kühlen |
| 1104 | F26 | maximale Lüfterdrehzahl Heizen |
| 1061 | F27 | Fan Motor Power Curve; genaue physische Einheit/Semantik weiterhin vorsichtig behandeln |
| 1093 | D14 | Fan-Speed-/Power-Ratio beim Eintritt in Defrost |
| 1094 | D15 | Fan-Speed-/Power-Ratio beim Austritt aus Defrost |
| 1095 | D16 | maximale Fan-Motor-Leistung für Forced-Defrost-Bedingung |

Aktuelle externe Fan-Driver-Telemetrie:

```text
MAIN:2131 / T47 = Leistung externer Fan-Driver
MAIN:2132 / T48 = Strom externer Fan-Driver
```

Es wurde **kein einzelner Parameter „Lüfter = 150 W / 250 W / 400 W“** als alleiniger Hardwareselektor gefunden.

---

# 14. V3.4-Scheduler und Adressunterschiede zu V3.3

Die RAM-Strukturen sind weitgehend gleich geblieben, die Codeadressen haben sich durch die V3.4-Imagebasis verschoben.

V3.4 Unit-1-Scheduler, relevante Stellen ungefähr:

```text
0x08093FA8  A39/Remote 2002 laden
0x08093FB6  C04 laden
0x08093FC8  C04 + 0x083A
0x08094062  FC10 ab 1999
0x080940C0  FC03 ab 2099
```

Literal-/RAM-Zuordnung:

```text
0x200162D8  Timer/Optionsblock inkl. A39
0x20016B20  C-Parameter
0x20016774  H-/Grundkonfiguration inkl. H33
0x20016A04  F-/Lüfterparameter
```

V3.4 interne Fan-Sollkanäle liegen in diesem Schedulerpfad bei:

```text
0x20016F18
0x20016F1A
```

V3.3 benutzte in der entsprechenden Analyse:

```text
0x20016F0A
0x20016F0C
```

Deshalb dürfen interne Code-/Runtimeadressen zwischen Firmwareversionen nicht ungeprüft übernommen werden.

---

# 15. Heizleistung / Gerätegröße

Ein direkter Parameter:

```text
"Nennheizleistung = 7/9/12 kW"
```

wurde im Mainboard-Binary **nicht gefunden**.

Die öffentlichen Werte:

```text
MAIN:2059  Unit Capacity / aktuelle thermische Gesamtleistung
MAIN:2138  thermische WP-Leistung ohne Zusatzanteil
```

sind Laufzeit-/Diagnosewerte und keine Hardwareauswahl.

Die physische Maschinenleistung ergibt sich nach jetzigem Stand aus einer Kombination von:

```text
C04  Verdichter-/Driverprofil
A26  Kältemittel + Maschinenkennfeld
C03  maximale Frequenz
A39  maximales Stromlimit
Fxx  Fan-Hardware und Kennlinien
H33  Driverarchitektur
A40  Nenn-Wasserdurchfluss / hydraulische Auslegung
```

Daher ist die Arbeitshypothese, dass verschiedene GL-Leistungsklassen mit derselben Mainboard-Software `82400644` über diese Parameterkombination differenziert werden.

Eine konkrete Zuordnung GL7/GL9/GL12 zu C04/A26/A39/C03 ist noch nicht bestätigt.

---

# 16. Sinnvolle Vergleichswerte zwischen Geräten

Für einen belastbaren Vergleich unterschiedlicher FoxAir-/PHNIX-Gerätegrößen sollten mindestens folgende Register gemeinsam erfasst werden:

```text
1019 H33
1054 A26
1059 F01
1074 F10
1081 F18
1083 F19
1089 F23
1103 F25
1104 F26
1220 C03
1221 C04
1343 A39
1344 A40
1422 verstecktes relatives Zusatzheizungs-/SG-Limit
```

Zusätzlich im Betrieb:

```text
2042 Kompressor-Phasenstrom
2046 T02
2048 T04
2057 AC Input Current
2071 Sollfrequenz
2072 Istfrequenz
2073 Inverter-Maximalfrequenz
2139 Limiterstatus
DIAG:6023 relative Verdichterlast
```

Damit lässt sich unterscheiden, ob zwei Geräte sich primär durch Inverter-/Verdichterprofil, Kältemittel-/Maschinenkennfeld, Stromlimit, Fan-Hardware oder Regelgrenzen unterscheiden.

---

# 17. Offene Punkte

1. C04→konkrete Verdichter-/Motortyp-Tabelle auf dem Unit-1-Board rekonstruieren.
2. GL7/GL9/GL12 bzw. weitere Leistungsklassen durch reale Parameterdumps vergleichen.
3. A26-Unterprofile in weiteren thermodynamischen Tabellen vollständig vergleichen.
4. MAIN:1422–1430 als gesamten versteckten SG-/Zusatzheizungs-Parametersatz benennen.
5. MAIN:2139 Bit8 und die zugehörigen internen Zustände `0x20016A44+8/+9/+A` bis zu den physischen E-Heizer-Ausgängen verfolgen.
6. F27 „Fan Motor Power Curve“ physikalisch und hinsichtlich Skalierung vollständig schließen.
7. Unit-1-Inverterfirmware beschaffen/analysieren, um C04 und A39 auf der Empfängerseite zu bestätigen.

---

# 18. Verwandte Dokumente

- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md)
- [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)

