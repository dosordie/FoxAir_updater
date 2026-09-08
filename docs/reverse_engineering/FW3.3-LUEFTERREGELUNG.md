# Mainboard-Firmware V3.3 – Lüfterregelung

Stand: 8. September 2026

Diese Datei dokumentiert die statisch rekonstruierte Lüfterregelung der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3`. Am Ende befindet sich ein klar gekennzeichneter **V3.4-Nachtrag** zu F01/F10, H33 und den in V3.4 verschobenen internen Sollkanälen.

Untersucht wurde für den Hauptteil dasselbe V3.3-Mainboard-Image wie in den übrigen V3.3-Analysen:

```text
Größe:       287598 Byte
MD5:         CEB6A4BF386FF644E23E410023E74673
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:  0x08050000
```

Bewertungsstufen:

- **bestätigt** – direkt im jeweils genannten Binary nachgewiesen bzw. mit Register-/Busdaten geschlossen
- **sehr wahrscheinlich** – Datenfluss ist geschlossen, die originale PHNIX-Bezeichnung eines Parameters fehlt noch
- **Hypothese** – plausible, aber noch nicht ausreichend belegte Zuordnung

---

## 1. Kurzfazit

Die V3.3 regelt die Lüfter nicht über einen lokalen PWM-Ausgang des Mainboards. Stattdessen:

```text
Temperaturen / Betriebszustände / Schutzfunktionen
        ↓
Mainboard-Lüfterregler
        ↓
interne Sollkanäle 0x20016F0A / 0x20016F0C
        ↓
FC10-Busausgabe
        ↓
Remote-/Leistungsmodul
        ↓
Lüfter
        ↓
Rückmeldung über Bus
        ↓
0x2001691C +0x0C / +0x0E
        ↓
Modbus 2074 / 2075
```

Die öffentlichen Register sind funktional klar getrennt:

| Register | Funktion | Bewertung |
|---:|---|---|
| 2074 | Drehzahl/Rückmeldung Lüftermotor 1 | bestätigt |
| 2075 | Drehzahl/Rückmeldung Lüftermotor 2 | bestätigt |
| 2076 | Zieldrehzahl des Lüftermotors, primärer Sollkanal | bestätigt |
| 2019 Bit 2 | mindestens ein Lüfter meldet tatsächliche Aktivität | bestätigt |

Der normale V3.3-Hauptregler liegt ungefähr bei:

```text
0x0805FEA8 … 0x08060B06
```

Sein zentraler Regelwert ist **Register 2049 = Verdampfertemperatur**. Daraus wird über stückweise lineare Kennlinien der Lüfter-Sollwert gebildet. Außentemperatur, Kompressorzustände, Schutzfunktionen und Abtauung können den Sollwert anschließend begrenzen oder überschreiben.

---

## 2. Modbus 2074, 2075 und 2076

Der Statusbuilder übernimmt drei Werte aus der Lüfter-Runtime-Struktur:

```text
0x2001691C
```

| Struktur | Offset | Modbus | Funktion |
|---:|---:|---:|---|
| `0x2001691C` | `+0x02` | 2076 | veröffentlichter Lüfter-Zielsollwert |
| `0x2001691C` | `+0x0C` | 2074 | tatsächliche Lüfterrückmeldung 1 |
| `0x2001691C` | `+0x0E` | 2075 | tatsächliche Lüfterrückmeldung 2 |

**Bewertung: bestätigt.**

---

## 3. V3.3: primärer und zweiter Lüfter-Sollkanal

V3.3:

```text
0x20016F0A = Lüfter-Sollkanal 1
0x20016F0C = Lüfter-Sollkanal 2
2076       = veröffentlichter Sollwert von Kanal 1
```

Die Statuslogik übernimmt den ersten Kanal nach `0x2001691C+0x02` und veröffentlicht ihn als 2076.

**Bewertung: bestätigt.**

---

## 4. Register 2019 Bit 2 ist kein Sollbefehl

Der Builder prüft die tatsächlichen Rückmeldungen:

```text
0x2001691C +0x0C
0x2001691C +0x0E
```

Wenn mindestens einer dieser Werte ungleich `0` ist:

```text
MAIN:2019 Bit2 = 1
```

Damit bedeutet Bit 2 funktional:

> Mindestens ein Lüfter liefert eine von Null verschiedene tatsächliche Drehzahl-/Aktivitätsrückmeldung.

Es ist **kein Lüfter-Enable-Befehl** und keine Kopie von 2076.

---

## 5. Lüfterrückmeldungen kommen über den Bus

Die Werte `0x2001691C+0x0C/+0x0E` werden aus empfangenen Busdaten aktualisiert.

Damit sind 2074 und 2075 keine lokal vom Mainboard gemessenen PWM-Tachowerte, sondern Rückmeldungen eines angeschlossenen Leistungs-/Inverter-/Lüftermoduls.

Die Firmware unterstützt mehrere Hardware-/Plattformvarianten; der Datenfluss zum öffentlichen Hauptstatus ist eindeutig.

---

## 6. V3.3-Buspfad der Lüfter-Sollwerte

Vor dem FC10-Paket:

```text
0x20016F0A → 0x2001233E
0x20016F0C → 0x20012340
```

Bei der 16-Wort-H33-Variante ab Remote-Register 1999 ergibt sich:

```text
0x2001233E → INV1:TX:2008
0x20012340 → INV1:TX:2009
```

Damit:

```text
Lüfterregler
  ↓
0x20016F0A / 0x20016F0C
  ↓
FC10 ab 1999
  ↓
INV1:TX:2008 / 2009
  ↓
Remote-/Leistungsmodul
```

**Bewertung: bestätigt.**

---

## 7. Live-Struktur der Lüfterparameter

Der Lüfterregler benutzt den Parameterblock:

```text
0x20016A04
```

| Live-Offset | MAIN | Code / Rolle |
|---:|---:|---|
| `+0x00` | 1059 | **F01 / Lüftermotortyp** |
| `+0x02` | 1060 | F02 / Temperaturstützpunkt |
| `+0x04` | 1062 | F03 / Temperaturstützpunkt |
| `+0x06` | 1066 | F05 / alternativer Temperaturstützpunkt |
| `+0x08` | 1068 | F06 / alternativer Temperaturstützpunkt |
| `+0x0A` | 1081 | **F18 / minimale Lüfterdrehzahl Kühlen** |
| `+0x0C` | 1083 | **F19 / minimale Lüfterdrehzahl Heizen** |
| `+0x0E` | 1087 | F22 / manuelle Fan-Funktion |
| `+0x10` | 1089 | **F23 / DC/AC Fan Rated Speed** |
| `+0x12` | 1103 | **F25 / maximale Lüfterdrehzahl Kühlen** |
| `+0x14` | 1104 | **F26 / maximale Lüfterdrehzahl Heizen** |
| `+0x18` | 1074 | **F10 / Lüfteranzahl** |
| `+0x1A` | 1101 | zusätzlicher Temperatur-/Betriebsgrenzwert |
| `+0x1C` | 1102 | Abschalt-/Untergrenze der Hauptkennlinie |

Die früher bewusst vorsichtig formulierten Zuordnungen `1059≈F01` und `1074≈Doppellüfter` sind inzwischen durch Registerkatalog + V3.4-Verbraucher ausreichend geschlossen.

---

## 8. Primärer Regelwert: Register 2049 = Verdampfertemperatur

Der Lüftercode liest den zentralen Temperaturwert aus:

```text
0x20015FA8 + 0x0C
```

Der Hauptstatusbuilder kopiert dieses Feld nach:

```text
MAIN:2049 = Verdampfertemperatur
```

Damit ist bestätigt:

> Die normale Lüfterkennlinie wird wesentlich aus der Verdampfertemperatur gebildet.

---

## 9. Hauptkennlinie: stückweise linear über Verdampfertemperatur

V3.3 verwendet im Hauptzweig:

```text
T_evap = MAIN:2049

T_off  = MAIN:1102
T_low  = MAIN:1062
T_high = MAIN:1060

S_low  = MAIN:1081 / F18
S_high = MAIN:1103 / F25
```

Sinngemäß:

```text
wenn T_evap <= T_off:
    S = 0
sonst wenn T_evap <= T_low:
    S = S_low
sonst wenn T_evap >= T_high:
    S = S_high
sonst:
    S = lineare Interpolation zwischen S_low und S_high
```

**Bewertung: bestätigt.**

---

## 10. Alternative Kennlinie

Ein alternativer Pfad verwendet analog:

```text
MAIN:1068 / F06
MAIN:1066 / F05
MAIN:1083 / F19
MAIN:1104 / F26
```

und dieselbe Verdampfertemperaturquelle.

**Bewertung: Kennlinienstruktur/Sensorquelle bestätigt.**

---

## 11. Außentemperatur als zusätzliche obere Begrenzung

Neben T03/MAIN:2049 wird T04/Außentemperatur ausgewertet.

In mehreren AT-Bändern entstehen zusätzliche Fan-Limits; im Code treten unter anderem Faktoren `0,8` und `0,6` auf hohe Lüfterreferenzen auf.

```text
Verdampfertemperatur-Kennlinie
        ↓
primärer Sollwert
        ↓
AT-abhängiges Limit
        ↓
begrenzter Fan-Sollwert
```

**Bewertung: bestätigt.**

---

## 12. Einfluss des Kompressorzustands

Zusätzliche Betriebsbedingungen können den Kennlinienwert überschreiben, unter anderem mit:

```text
Soll = (2 × Referenz) / 3
```

wobei abhängig vom Pfad MAIN:1103 oder 1104 als hohe Referenz dient.

---

## 13. Zweiter Lüfter / F10

```text
MAIN:1074 / F10
Live: 0x20016A04 + 0x18
```

Offizielle Belegung:

```text
0 = Einzel-Lüfter
1 = Doppel-Lüfter
```

V3.3 führt zwei Sollkanäle. Je nach F10/Betriebszustand kann Kanal 2:

- auf 0 bleiben,
- Kanal 1 folgen,
- durch einen Sonderpfad separat gesetzt werden.

V3.4 bestätigt diese Interpretation erneut: bei Einzel-Lüfter-Konfiguration wird der zweite Sollkanal in relevanten Pfaden gezielt auf 0 gesetzt; bei Doppel-Lüfter-Konfiguration wird er verwendet.

**Bewertung: bestätigt.**

---

## 14. F01 – Lüftermotortyp

```text
MAIN:1059 / F01
Live: 0x20016A04 + 0x00
```

Aktueller Registerkatalog:

```text
0 = Legacy: Hochgeschwindigkeits-Lüfter
1 = Legacy: zweistufiger Lüfter
3 = DC Fan Motor
4 = DC Fan Motor External Drive
```

V3.3 behandelt insbesondere die Werte 3/4 als aktive Regel-/Topologiepfade; bei Konfiguration 0 werden Sollkanäle in entsprechenden Pfaden auf 0 gesetzt.

V3.4 schließt zusätzlich die Driver-Selektion im integrierten Unit-1-Paket:

```text
F01 == 3 → Fan-Driver-Selektor 1
F01 == 4 → Fan-Driver-Selektor 2
```

Damit ist F01 eindeutig ein **echter Hardware-/Driverselektor** und nicht nur ein Displayparameter.

**Bewertung: bestätigt.**

---

## 15. Schutzübersteuerung

Bei bestimmten Schutzflags im Bereich `0x20016E0C` wird während laufender Anlage der Fan-Sollwert direkt überschrieben, unter anderem mit einer `2/3`-Referenz.

Damit können Schutzfunktionen eine von der normalen Verdampfertemperaturkennlinie unabhängige Lüftervorgabe erzwingen.

---

## 16. Abtauung überschreibt den Normalregler

Die Abtau-State-Machine schreibt direkt auf die V3.3-Sollkanäle:

```text
0x20016F0A
0x20016F0C
```

und kann daher den Normalregler vollständig übersteuern.

Je nach Defrost-State werden:

- beide Lüfter auf 0 gesetzt,
- spezielle Abtau-Sollwerte gebildet,
- Kanal 2 abhängig von F10 mitgeführt oder abgeschaltet.

---

## 17. Internes Fan-Command-Active-Flag

Am Ende der Sollwertbildung prüft V3.3:

```text
0x20016F0A != 0
oder
0x20016F0C != 0
```

und setzt/löscht ein internes Command-Flag.

Dieses Flag bedeutet:

```text
Mainboard fordert mindestens einen Lüfter an
```

und ist ausdrücklich nicht identisch mit `MAIN:2019 Bit2`, das aus der tatsächlichen Rückmeldung entsteht.

---

## 18. Register 2108 – Fan Mute Flag / verwandter Status

`MAIN:2108` wird in älteren Display-/ASM-Unterlagen als Fan-Mute-/Lüfter-Stummschaltstatus bezeichnet.

Es ist nicht der primäre Lüfter-Sollwert und nicht die Grundlage von MAIN:2019 Bit2. Die vollständige Semantik aller 2108-Zustände bleibt ein eigener Restpunkt.

---

## 19. Gesamt-Datenfluss

```text
                    T04 Außentemperatur
                           │
                           ▼
                    zusätzliches Limit
                           │
MAIN:2049                 │
Verdampfertemperatur      │
       │                  │
       ▼                  │
lineare Fan-Kennlinie ────┘
       │
       ▼
Kompressor-/Betriebszustände
       │
       ▼
Schutz-Overrides
       │
       ▼
Defrost-Override
       │
       ▼
interne Fan-Sollkanäle
       │
       ├────────────→ MAIN:2076
       ▼
INV1:TX:2008 / 2009
       │
       ▼
Leistungs-/Fan-Modul
       │
       ▼
Bus-Rückmeldung
       │
       ▼
0x2001691C +0x0C / +0x0E
       │
       ├────────→ MAIN:2074 / 2075
       └────────→ MAIN:2019 Bit2
```

---

## 20. Praktische Diagnose über Modbus

```text
2048 = Außentemperatur
2049 = Verdampfertemperatur
2074 = Lüfter 1 Ist/Rückmeldung
2075 = Lüfter 2 Ist/Rückmeldung
2076 = Lüfter Soll Kanal 1
2019 Bit2 = mindestens ein Lüfter tatsächlich aktiv
```

Beispiel Soll vorhanden, Lüfter steht:

```text
2076 > 0
2074 = 0
2075 = 0
2019 Bit2 = 0
```

→ Mainboard fordert an, aber keine reale Fan-Rückmeldung.

---

## 21. Fan-Leistung / unterschiedliche Hardwareleistung

Es wurde **kein einzelner Parameter gefunden, der direkt eine Nennleistung wie „150 W / 250 W / 400 W Fan“ auswählt**.

Die Fan-Hardware wird vielmehr durch eine Kombination beschrieben:

```text
F01  Driver-/Motortyp
F10  Anzahl Lüfter
F18/F19 minimale Drehzahlen
F23  Nenn-Drehzahl
F25/F26 maximale Drehzahlen
F27  Fan Motor Power Curve
D14/D15 Fan-Speed-/Power-Ratios im Defrost
D16  maximale Fan-Motor-Power für Forced-Defrost-Bedingung
```

Aktuelle externe Driver-Telemetrie:

```text
MAIN:2131 / T47 = Leistung des externen Fan-Motor-Drivers
MAIN:2132 / T48 = Strom des externen Fan-Motor-Drivers
```

Bei `F27 / MAIN:1061` ist der Name „Fan Motor Power Curve“ belegt, die exakte physikalische Skalierung/Einheit soll aber weiterhin nicht vorschnell als Watt interpretiert werden.

---

## 22. Offene Punkte

1. exakte physikalische Einheit/Skalierung der rohen Lüfter-Soll-/Istwerte 2074–2076
2. vollständige Zuordnung aller Hardwareplattformvarianten der Remote-Frames
3. vollständige Semantik von MAIN:2108
4. praktische Live-Gegenprobe der Kennlinien mit 2048/2049/2074–2076
5. F27 „Fan Motor Power Curve“ physikalisch vollständig schließen

Die Hauptarchitektur, Sensorquelle, Kennlinienform, Soll-/Ist-Trennung, F01/F10-Hardwarewirkung, Zwei-Lüfter-Unterstützung, Schutz-/Defrost-Overrides und der Buspfad sind dagegen belegt.

---

## 23. V3.4-Nachtrag – interne Solladressen und H33

V3.4 nutzt weiterhin denselben Unit-1-Remoteaufbau:

```text
INV1:TX:2008 = Fan-Soll 1
INV1:TX:2009 = Fan-Soll 2
```

Die internen RAM-Sollkanäle des entsprechenden V3.4-Schedulerpfads sind jedoch gegenüber V3.3 verschoben:

```text
V3.3:
0x20016F0A
0x20016F0C

V3.4:
0x20016F18
0x20016F1A
```

Damit gilt ausdrücklich:

> Interne Fan-RAM-Adressen dürfen nicht versionsübergreifend ungeprüft übernommen werden. Die Remote-Registersemantik 2008/2009 bleibt dagegen erhalten.

V3.4 bestätigt außerdem erneut H33:

```text
MAIN:1019 / H33 = 0
→ Unit1 FC10 5 Wörter / FC03 22 Wörter

MAIN:1019 / H33 != 0
→ Unit1 FC10 16 Wörter / FC03 51 Wörter
```

Die lange Variante enthält Fan-Driver-Steuerung/-Telemetrie.

Weitere V3.4-Hardwarezusammenhänge stehen in [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md).

---

## 24. Zusammenhang mit anderen Analysen

- [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md) – Hardware-/Maschinenprofile einschließlich F01/F10/F23/F25/F26
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)
- [`FW3.3-EEV-SMART-REGELUNG.md`](FW3.3-EEV-SMART-REGELUNG.md)
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md)
