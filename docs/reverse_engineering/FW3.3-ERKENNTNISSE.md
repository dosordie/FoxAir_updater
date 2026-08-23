# Mainboard-Firmware V3.3 – Reverse-Engineering-Erkenntnisse

Stand: 22. August 2026

Diese Datei dokumentiert die statische Reverse-Engineering-Analyse der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3`.

Sie ist bewusst von der allgemeinen Registertabelle und der DWIN-/DGUS-Displaydokumentation getrennt. Hier werden auch interne RAM-Strukturen, Funktionsadressen, Zustandsmaschinen und noch nicht vollständig benannte Datenfelder dokumentiert.

## Bewertungsstufen

- **bestätigt** – direkt im untersuchten Binary nachgewiesen oder durch Binary und reale Bus-/Gerätedaten gemeinsam bestätigt
- **sehr wahrscheinlich** – Datenfluss ist weitgehend geschlossen, die letzte physikalische oder semantische Zuordnung fehlt noch
- **Hypothese** – plausible Arbeitshypothese, noch nicht ausreichend verifiziert

Die Firmware wird ausschließlich statisch analysiert und nicht verändert.

---

# 1. Untersuchte Firmware

```text
Produkt-/Softwarekennung: 82400644
Firmwareversion:          V3.3
Dateigröße:               287598 Byte
MD5:                      CEB6A4BF386FF644E23E410023E74673
SHA-256:                  6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:               0x08080000
Initial Stack Pointer:    0x2000EB90
Reset Vector:             0x080927D1
Reset Handler Thumb:      0x080927D0
```

Bei Dateioffset `0x42780`, VA `0x080C2780`, steht:

```text
824006440033
```

Die Aufteilung `82400644` + `0033` passt zur realen Gerätekennung und zu den im Code gesetzten Versionswerten.

**Bewertung: bestätigt** für String und Konstanten; die vollständige interne Bildung der Produktkennung ist noch offen.

---

# 2. Modbus-Engine der Hauptsteuerung

| Dateioffset | VA | Funktion | Bewertung |
|---:|---:|---|---|
| `0x0094E` | `0x0808094E` | Modbus-CRC | bestätigt |
| `0x03F62` | `0x08083F62` | FC03-Antwortaufbau | bestätigt |
| `0x04040` | `0x08084040` | FC06-Antwortaufbau | bestätigt |
| `0x040D4` | `0x080840D4` | FC10-Antwortaufbau | bestätigt |
| `0x164C8` | `0x080964C8` | zentraler Modbus-Request-Dispatcher | bestätigt |

Der Hauptdispatcher behandelt FC03, FC06 und FC10. Für FC04 wurde dort kein eigener Pfad gefunden.

## Bestätigte FC03-Bereiche

```text
1001–1540
2001–2180
5001–5090
5091–5180
6001–6090
8801–8820
60010        Spezialpfad
```

`60000` wird beim Schreiben als Sonderbefehl behandelt und ist kein normales Holding Register.

Die Service-/Engineering-Bereiche `5001+`, `6001+`, `8801+`, `60000` und `60010` sind noch nicht vollständig funktional benannt.

---

# 3. Zentraler Registerspiegel

Hauptspiegel:

```text
0x20012788
```

Für `2001–2180` gilt:

```text
RAM = 0x20012788 + 0x820 + 2 × (Register - 2001)
```

Beispiele:

| Register | Spiegeloffset | RAM |
|---:|---:|---:|
| 2034 | `+0x862` | `0x20012FEA` |
| 2103 | `+0x8EC` | `0x20013074` |
| 2104 | `+0x8EE` | `0x20013076` |
| 2105 | `+0x8F0` | `0x20013078` |
| 2133 | `+0x928` | `0x200130B0` |

**Bewertung: bestätigt.**

Zusätzlich existiert ein zweites Kommunikationsabbild bei `0x200112CC`.

## 2103–2105

Im Hauptspiegel werden gesetzt:

```text
2104 = 33
2105 = 644
```

2103 wird in der großen Statusupdate-Routine übersprungen.

Im zweiten Kommunikationsabbild werden dagegen gesetzt:

```text
2103 = 644
2104 = 33
2105 = 416
```

Die Werte sind **bestätigt**. Die Rolle des zweiten Abbilds ist **sehr wahrscheinlich** Display-/Kompatibilitätskommunikation, aber noch nicht bis zum UART-Peripheral geschlossen.

---

# 4. Lastausgangsbitfeld Register 2019

Builder ungefähr ab VA `0x080A1504`; internes Ausgangswort `0x200164C0`.

| Bit | Funktion | Quelle | Bewertung |
|---:|---|---|---|
| 0 | Kompressor läuft | Istfrequenz `0x200168C4+0x06` != 0 | bestätigt |
| 2 | Lüfterstatus | interne Lüfterwerte | bestätigt aktiv |
| 4 | Hauptumwälzpumpe | PB1 bzw. Hydraulikmodul | bestätigt |
| 5 | Warmwasserpumpe | PB2 bzw. Erweiterung | bestätigt |
| 6 | 4-Wege-Ventil | PE11 | bestätigt |
| 7 | E-Heizung Stufe 1 | PE12 | bestätigt |
| 8 | E-Heizung Stufe 2 | PE13 | bestätigt |
| 9 | 3-Wege-Ventil | PE14 | bestätigt |
| 10 | Alarmausgang | PC4 | bestätigt |
| 11 | Kompressor-/Ölsumpfheizung | PE15 | bestätigt |
| 12 | Wannenheizung | PD8 | bestätigt |
| 13–15 | Hydraulik-/Erweiterungsausgänge | Erweiterungsstruktur | bestätigt aktiv |

Bit 0 ist kein Kompressorrelais. Es wird aus der gemeldeten Verdichterfrequenz gebildet.

---

# 5. Verdichter und Inverter

## 5.1 Inverter-Telemetrie

Die Struktur `0x200168C4` ist ein zusammenhängender Inverter-/Verdichter-Telemetrieblock.

| Register | Bedeutung | Quelle |
|---:|---|---|
| 2042 | Kompressor-Phasenstrom | `+0x10` |
| 2043 | DC-Bus-Spannung | `+0x12` |
| 2044 | IPM-Temperatur | gleicher Block |
| 2057 | AC-Eingangsstrom | `+0x0E` |
| 2062 | AC-Eingangsspannung | `+0x0C` |
| 2072 | Kompressor-Istfrequenz | `+0x06` |
| 2073 | maximale Inverter-/Kompressorfrequenz | `+0x08` |

**Bewertung: bestätigt.**

## 5.2 Sollfrequenz Register 2071

Register 2071 stammt aus:

```text
0x20016AA4 + 0x08
```

und ist die tatsächliche Sollfrequenz, die an den Inverter übertragen wird.

## 5.3 Mainboard ↔ Inverter

Mainboard → Inverter:

```text
Slave:         1
Function Code: 0x10
Startregister: 1999 / 0x07CF
```

Das erste Nutzdatenwort ist die Sollfrequenz aus Register 2071.

Inverter → Mainboard:

```text
Slave:         1
Function Code: 0x03
Startregister: 2099 / 0x0833
```

Dieser Ring ist auch in realen Busmitschnitten sichtbar.

```text
Regelung
  ↓
2071 Sollfrequenz
  ↓
FC10 Slave 1 @ 1999
  ↓
Inverter
  ↓
FC03 Slave 1 @ 2099
  ↓
0x200168C4
  ↓
2072/2073, Strom, Spannung, IPM usw.
```

**Bewertung: bestätigt.**

## 5.4 C-Parameter als Live-Struktur

Der Live-Block der Verdichterparameter liegt bei:

```text
0x20016B20
```

Bestätigte Zuordnung:

| Register | Parameter | Live-Offset | Funktion |
|---:|---|---:|---|
| 1218 | C01 | `+0x00` | manuelle Kompressorfrequenz |
| 1219 | C02 | `+0x02` | Mindestfrequenz |
| 1220 | C03 | `+0x04` | Maximalfrequenz |
| 1221 | C04 | `+0x06` | Kompressormodell |
| 1222 | C05 | `+0x08` | Mindestfrequenz Kühlen bei niedriger AT |
| 1223 | C06 | `+0x0A` | Frequenzregelmodus |
| 1227 | C10 | `+0x0C` | Mindestfrequenz Heizen bei niedriger AT |
| 1217 | C11 | `+0x0E` | temperaturabhängige obere Frequenzbegrenzung im Kühl-/Hoch-AT-Pfad |

Die Funktionsnamen der bekannten C-Parameter wurden mit der Registertabelle gegengeprüft; ihre Verwendung im Mainboardcode ist direkt nachgewiesen.

## 5.5 Harte obere und dynamische untere Frequenzgrenze

In der normalen Frequenzregelung um `0x080A552C` wird der berechnete Sollwert zuerst auf C03 begrenzt:

```text
wenn Soll > C03:
    Soll = C03
```

Danach wird gegen die dynamische Mindestfrequenz bei:

```text
0x20016F83
```

geprüft:

```text
wenn Soll < dyn_min:
    Soll = dyn_min
```

Damit ist bestätigt:

```text
C03 = obere Grundgrenze
0x20016F83 = dynamische untere Grundgrenze
```

## 5.6 Dynamische Mindestfrequenz Heizen: C02 ↔ C10

Die Routine um VA `0x080A398E` initialisiert `0x20016F83` zunächst mit C02.

Für den Heizpfad werden die Temperaturgrenzen benutzt:

| Register | Parameter | Bedeutung |
|---:|---|---|
| 1167 | R29 | Low AT Water Temp Limit ON |
| 1168 | R30 | Low AT Water Temp Limit OFF |

Der aktuelle, über Helper `0x080B799C` gelieferte Temperaturwert wird damit verglichen:

```text
Temperatur >= R29
    → dyn_min = C02

Temperatur <= R30
    → dyn_min = C10

R30 < Temperatur < R29
    → lineare Interpolation zwischen C10 und C02
```

**Bewertung: bestätigt** für Datenfluss und Interpolation. Welcher physische Temperaturkanal hinter `0x080B799C` liegt, ist noch offen.

## 5.7 Dynamische Mindestfrequenz Kühlen: C05

Im alternativen Pfad um `0x080A3AF6` wird ebenfalls zunächst C02 geladen. Bei einem Helper-Rohwert unter `-49` wird C05 verwendet und anschließend sichergestellt, dass der resultierende Wert nicht unter C02 liegt.

```text
sehr niedriger Temperaturwert
    → dyn_min = max(C05, C02)
```

Der Rohgrenzwert `-49` ist **bestätigt**. Eine Interpretation als etwa `-4,9 °C` ist **sehr wahrscheinlich**, solange der physische Helper noch nicht benannt ist.

## 5.8 C11-Derating

Die Funktion `0x080B30C0`, aufgerufen aus dem normalen Frequenzpfad, verwendet C03 und C11, zerlegt Frequenzen ab 30 Hz in 6-Hz-Bänder und baut daraus eine temperaturabhängige Begrenzungs-/Bandlogik.

**Bestätigt:** C11 fließt in eine temperaturabhängige Kompressor-Frequenzbegrenzung ein.

Die vollständigen Temperaturstützpunkte und die genaue Bezeichnung aller beteiligten Tabellenfelder sind noch offen.

---

# 6. Kompressor-/Ölsumpfheizung

Ausgang:

```text
PE15 → Register 2019 Bit 11
```

Automatische Steuerung ungefähr ab VA `0x080A2A32`.

## Temperaturhysterese

Im V3.3-Binary hart codiert:

```text
Regelwert < 81      → Heizung EIN
Regelwert 81…99     → Zustand halten
Regelwert >= 100    → Heizung AUS
```

Skalierung `/10 °C` ist **sehr wahrscheinlich** → etwa 8,1 °C EIN / 10,0 °C AUS.

## A34 / Register 1064

Live-Adresse:

```text
0x2001676C
```

A34 wird als Vorheizzeit verwendet:

```text
A34 × 120 interne Zyklen
```

Während der Vorheizzeit ist `0x20016F95 = 1`. Die zentrale Startfreigabe um `0x0808E8FC` verweigert bei gesetztem Flag die Freigabe.

Damit ist **bestätigt**, dass A34 eine echte Startverriegelung erzeugt. Bei `A34=0` entfällt die zusätzliche Vorheizwartezeit; die temperaturabhängige PE15-Heizung bleibt davon unabhängig.

Im Factory-/Manual-Modus steuert `0x20016C10 Bit 4` PE15 direkt.

---

# 7. Abtau-State-Machine

D-Live-Struktur:

```text
0x200166A0
```

| Parameter | Register | Offset |
|---|---:|---:|
| D06 | 1111 | `+0x0C` |
| D11 | 1116 | `+0x16` |
| D17 | 1122 | `+0x22` |
| D18 | 1123 | `+0x24` |
| D19 | 1124 | `+0x26` |
| D20 | 1125 | `+0x28` |
| D21 | 1126 | `+0x2A` |
| D22 | 1127 | `+0x2C` |
| D25 | 1130 | `+0x32` |

Abtaustruktur:

```text
0x200168F0
```

## State 1 – Vorbereitung

```text
Sollfrequenz = 50 Hz
Wartephase
→ 0x20016E0F Bit 3 = 1
→ PE11 / 4-Wege-Ventil umschalten
weitere Wartephase
→ State 2
```

Mechanik **bestätigt**, Bezeichnung „Vorbereitung“ **sehr wahrscheinlich**.

## State 2 – eigentliche Abtauphase

- Sollfrequenz aus D20
- Teilpfad `D20 - 10`
- PE11 bleibt in Abtaustellung
- zusätzlicher 50-Hz-Limitpfad

### D17

Register 2049 / Verdampfertemperatur wird direkt gegen D17 geprüft.

**D17 ist eine aktive Abtau-Ende-/Abschaltbedingung – bestätigt.**

### D22 und Durchfluss

Aktueller Durchfluss:

```text
0x20016F14 → Register 2077
```

D22 wird gegen diesen Wert geprüft und über 20 Zyklen qualifiziert. Das daraus erzeugte interne Statusflag liegt in der Struktur `0x20016214` und wird im State-2-Frequenzpfad ausgewertet.

**Bestätigt:** Das qualifizierte D22-Durchflussflag ist genau die Bedingung, welche die Abtau-Sollfrequenz auf **maximal 50 Hz** begrenzt.

D22 ist damit nicht nur ein passiver Alarm-/Displaywert, sondern greift direkt in die Abtau-Leistungsbegrenzung ein.

### D25

Ein weiterer Endepfad bildet:

```text
D11 - D25
```

und vergleicht dies mit der Einlasswassertemperatur, die auch Register 2045 erzeugt.

**Bewertung: bestätigt.**

## State 3 – Recovery

Um VA `0x080932BC` wird:

```text
0x20016E0F Bit 3 = 0
```

gesetzt → PE11 / 4-Wege-Ventil zurück in Normalstellung. Die Sollfrequenz wird zunächst wieder auf 50 Hz gesetzt; danach folgen weitere Recovery-Bedingungen.

Ventilrückschaltung **bestätigt**, Bezeichnung Recovery **sehr wahrscheinlich**.

---

# 8. SG Ready – Kurzreferenz

Nur zur Vollständigkeit; SG ist nicht mehr Hauptfokus der Analyse.

```text
0x20016948 +0 → 2034 Bit 12
0x20016948 +1 → 2034 Bit 13
0x20016948 +2 → 2133
```

State-Machine ungefähr VA `0x080B1BC0`; reguläre States 1–4, zusätzlich interner State 5. Register 1334–1340 werden direkt verwendet.

---

# 9. Neu zugeordnete Statusregister 2133–2180

| Register | Funktion | Bewertung |
|---:|---|---|
| 2133 | SG-State | bestätigt |
| 2136 | aufbereiteter signed Temperatur-/Regelwert | Charakter bestätigt, physischer Sensor offen |
| 2160 | Zone-1-Raumtemperatur | bestätigt |
| 2161 | Zone-2-Mischwassertemperatur | bestätigt |
| 2162 | Zone-2-Raumtemperatur | bestätigt |
| 2163 | Mischventil-/Mischkreiswert 0…100 % | bestätigt |
| 2164 | Zone-1-Auslauftemperatur nach AT-Kompensation | bestätigt |
| 2165 | Zone-2-Auslauftemperatur nach AT-Kompensation | bestätigt |
| 2166 | signed Wert derselben Zonenstruktur | aktiv, Bedeutung offen |

Weitere aktive Kandidaten:

- 2137/2138: zwei Float-Messgrößen, jeweils `×10`
- 2140/2141: 32-Bit-Wert
- 2142/2143: weiterer 32-Bit-Wert
- 2146: aktives Capability-/Konfigurationsbitfeld
- 2151–2158: separates internes Subsystem
- 2178–2180: zusammenhängender Dreierblock

---

# 10. Verstecktes internes Registerfenster 8001–8090

Dispatcher ungefähr VA `0x08097548`.

```text
Slave/Unit 0x63 = 99
Broadcast 0
FC03
FC06
FC10
Register 8001–8090
```

RAM-Fenster:

```text
0x20015EF0
```

Spiegelungen:

| öffentlich | intern |
|---:|---:|
| 2151 | Low-Byte 8001 |
| 2153 | 8002 |
| 2156 | 8003 |
| 2154 | 8004 |
| 2155 | 8005 |
| 2157 | 8007 |
| 2158 | 8008 |

Internes Register 8006 besitzt eine Änderungserkennung mit 150-Zyklen-Timer. Zentrale Verarbeitung ungefähr `0x080B8E5C–0x080B94FC`.

Die Funktion des Subsystems bleibt **offen**. Eine optionale Erweiterungsfunktion ist nur **Hypothese**.

---

# 11. Hauptumwälzpumpe und PWM-Regelung

## 11.1 Hardware und Grundparameter

Lokaler Pumpenausgang:

```text
PB1
```

Manuell/Werkstest:

```text
0x20016C10 Bit 2 → PB1
```

Weitere bestätigte Live-Parameter:

| Register | Parameter | Live-Adresse / Offset | Bedeutung |
|---:|---|---|---|
| 1033 | H20 | `0x20016774+0x16` | 3-Wege-Ventil-Polarität |
| 1036 | H30 | `0x20016774+0x1C` | lokale Pumpe vs. Hydraulikmodulpfad |
| 1041 | H31 | `0x20016774+0x1E` | Pumpentyp |
| 1203 | P09 | `0x20016C6C+0x0A` | Pumpenschutzintervall |
| 1205 | P10 | `0x20016C6C+0x0C` | Pumpendrehzahl / Auto bei 0 |
| 1344 | A40 | `0x20016C9C+0x0A` | Durchfluss-Referenzwert |

Bei H30=1 wird der Pumpenzustand über das Hydraulik-/Erweiterungsmodul ausgewertet; andernfalls über den lokalen PB1-Pfad.

## 11.2 P09 Pumpenschutz / Antiblockierlauf

Bei stillstehender Pumpe:

```text
7200 interne Zyklen
→ Stunden-Zähler +1
Stunden >= P09 × 24
→ Schutzlauf anfordern
→ Laufcounter = 120 interne Zyklen
```

Die Logik ist **bestätigt**. Aus P09 in Tagen ergibt sich für den periodischen Task sehr konsistent eine Zeitbasis von etwa 0,5 s; diese absolute Scheduler-Zeitbasis ist **sehr wahrscheinlich**, noch nicht separat am Timerinterrupt belegt.

## 11.3 Zwei bislang undokumentierte Parameter: Register 1432 / 1433

Die Hauptparameterkopie bei VA `0x0809A970`/`0x0809A97E` liest:

```text
Mirror +0x746 → 0x20016278+0
Mirror +0x748 → 0x20016278+1
```

Mit der Parameterformel ergeben sich:

```text
Register 1432 → 0x20016278+0
Register 1433 → 0x20016278+1
```

Der Rückkopierpfad schreibt dieselben beiden Livewerte wieder in die entsprechenden Mirroradressen. Damit ist die Registerzuordnung **bestätigt**.

In der Pumpenregelung werden sie verwendet als:

```text
1432 → Soll-ΔT der automatischen Pumpenregelung
1433 → Schrittweite der PWM-/Drehzahlanpassung
```

**Funktionale Bedeutung: bestätigt.**

Die Herstellerbezeichnungen fehlen in der bisherigen Excel-/DWIN-Dokumentation. Aufgrund der bekannten Pumpenparameter ist `1433` ein **sehr starker Kandidat für P12** und `1432` entsprechend für einen benachbarten Pumpen-ΔT-Parameter; die offiziellen Parameternamen sind jedoch noch **nicht bestätigt**.

Schreibrechte, Min/Max und Default dieser beiden Register werden noch separat aus der Parameter-Validierung extrahiert.

## 11.4 Messwerte der Auto-Regelung

Helper:

```text
0x080B7930 → Register 2045 Einlasswassertemperatur
0x080B7966 → Register 2046 Auslasswassertemperatur
```

Die automatische Pumpenregelung bildet daraus abhängig vom Betriebsmodus das korrekte Vorzeichen von ΔT und speichert den aktuellen ΔT-Wert in ihrer internen Pumpenstruktur.

Damit ist **bestätigt**, dass die automatische Pumpendrehzahl nach Wasser-ΔT geregelt wird.

## 11.5 Aktivierung erst nach A40 × 1,2

Die Pumpenfunktion um `0x080B4474` bildet aus A40 exakt:

```text
A40 × 1,2
```

Der Faktor `1,2` liegt als IEEE-754-Double `0x3FF3333333333333` im Literalpool.

Solange:

```text
gefilterter Durchfluss >= A40 × 1,2
```

läuft ein Counter bis `1200`. Danach wird ein Aktivflag gesetzt und die aktuelle Kompressor-Sollfrequenz als Referenz gespeichert.

Mit der aus P09 abgeleiteten Taskzeit von etwa 0,5 s entsprechen 1200 Zyklen **sehr wahrscheinlich 10 Minuten**.

Damit ist der bereits aus dem Anlagenverhalten bekannte Zusammenhang jetzt direkt im V3.3-Binary nachgewiesen:

```text
Flow >= A40 × 1,2 für ungefähr 10 min
→ automatische Pumpenregelung aktiv
```

## 11.6 Mindestdurchfluss: D22 oder A40 × 0,8

Die Firmware verwendet:

```text
wenn D22 != 0:
    Mindest-/Referenzdurchfluss = D22

wenn D22 == 0:
    Mindest-/Referenzdurchfluss = A40 × 0,8
```

Der Faktor ist als exaktes IEEE-754-Double `0.8` im Binary vorhanden.

**Bewertung: bestätigt.**

Damit ist die bisher bekannte Regel `D22 oder A40×0,8` direkt aus der Mainboard-Firmware verifiziert.

## 11.7 Durchflussfilter

Der aktuelle Durchfluss `0x20016F14 / Register 2077` wird vor der Regelung geglättet:

- Samples werden aufsummiert
- Samplecounter wird geführt
- nach 10 Samples wird ein Mittelwert gebildet
- Null-Durchfluss besitzt zusätzliche Sonderbehandlung

Der gefilterte Wert liegt in der Pumpenstruktur bei `+0x0C`.

**Bewertung: bestätigt.**

## 11.8 ΔT-Regelalgorithmus

Soll-ΔT = Register 1432.

Regelfehler:

```text
Fehler = aktuelles ΔT - Soll-ΔT
```

Alle 120 Regelzyklen wird die Drehzahlkorrektur aus Register 1433 angewendet:

```text
Fehler >= +30 raw  → +2 × Schrittweite
Fehler +10…+29     → +1 × Schrittweite
Fehler -9…+9       → keine ΔT-Korrektur
Fehler -29…-10     → -1 × Schrittweite
Fehler <= -30      → -2 × Schrittweite
```

Bei Temperaturfaktor `/10` entsprechen die äußeren Schwellen sehr wahrscheinlich ±3,0 K und die inneren ±1,0 K.

**Bewertung: Rohlogik bestätigt; K-Skalierung sehr wahrscheinlich.**

## 11.9 Vorsteuerung über Verdichterfrequenz

Zusätzlich wird die aktuelle Kompressor-Sollfrequenz mit der beim letzten Zyklus gespeicherten Frequenz verglichen:

```text
Frequenzanstieg >= 6 Hz
    → Pumpenwert + Schrittweite

Frequenzabfall <= etwa -6 Hz
    → Pumpenwert - Schrittweite
```

Damit reagiert die Pumpe nicht nur auf ΔT, sondern antizipiert auch Laständerungen des Verdichters.

**Bewertung: bestätigt.**

## 11.10 Durchfluss-Untergrenzenkorrektur

Der berechnete Mindest-/Referenzdurchfluss aus D22 bzw. A40×0,8 wird gegen den gefilterten Ist-Durchfluss verglichen.

Ist der Durchfluss zu klein, erhöht die Firmware den Pumpenwert zusätzlich.

Damit besitzt die Auto-Regelung drei klar getrennte Einflüsse:

```text
1. ΔT-Regelung
2. Vorsteuerung nach Kompressorfrequenzänderung
3. Mindestdurchflusskorrektur
```

**Bewertung: bestätigt.**

## 11.11 P10: Festwert oder Automatik

Die abschließende Auswahl lautet sinngemäß:

```text
Factory/Manual-Pumpenmodus
    → manueller Wert

sonst P10 >= 1
    → Pumpenwert = P10

P10 = 0
    → automatische Regelung
```

Der Auto-Regler begrenzt seinen internen Pumpenwert auf:

```text
16 … 92
```

Die allgemeine Ausgangsvalidierung akzeptiert 1…100; in verschiedenen Off-/Fallbackpfaden wird 100 verwendet.

**Bewertung: bestätigt.**

## 11.12 PWM-Hardware

Am Ende der Routine:

```text
compare = (100 - Pumpenwert) × 10
```

und Aufruf von `0x080BA918` mit:

```text
Timer = 0x40000C00 = TIM5
Channel = 1 → CCR2
```

Damit:

```text
Hauptpumpen-PWM = TIM5_CH2
CCR2 = (100 - Pumpenwert) × 10
```

Die PWM-Logik ist also gegenüber dem Prozentwert invertiert.

**Bewertung: bestätigt.**

Der konkrete GPIO-Pin von TIM5_CH2 wurde noch nicht bis zur AFIO-Konfiguration zurückverfolgt.

## 11.13 Weitere Temperaturhysterese im Pumpenpfad

Der noch nicht physikalisch benannte Helper `0x080B799C` steuert zusätzlich ein Pumpenflag mit Rohschwellen:

```text
< 200 → Flag setzen
>= 220 → Flag löschen
```

Das entspricht sehr wahrscheinlich einer 20,0/22,0-°C-Hysterese, die physikalische Sensorzuordnung ist aber noch offen.

---

# 12. Aktuell offene Hauptziele

1. verbleibende Writer und Limitquellen von Register 2071 vollständig benennen
2. C11-Derating-Tabelle mit allen Temperaturstützpunkten rekonstruieren
3. Inverter-Run-/Mode-Wörter im FC10-Paket ab 1999 vollständig benennen
4. Register 1432/1433 aus der Parameter-Validierung: Min/Max/Default/RW extrahieren
5. PWM-Pin von TIM5_CH2 bis zur GPIO-/AFIO-Konfiguration verfolgen
6. Helper `0x080B799C` physikalisch eindeutig einem Sensor zuordnen
7. verstecktes Subsystem 8001–8090 identifizieren
8. Register 2137/2138 und 2140–2143 benennen
9. 2146 Bit für Bit auf Ausstattungs-/Capability-Funktionen zurückführen
10. 2151–2158 vollständig entschlüsseln
11. Lüfterregelung über 2074/2075 und 2019 Bit 2 rekonstruieren
12. EEV-/Überhitzungsregelung rekonstruieren
13. Öl-Rückführungszustandsmaschine identifizieren
14. Service-/Engineering-Bereiche 5001–5180, 6001–6090, 8801–8820 sowie 60000/60010 auflösen

---

# 13. Arbeitsprinzip

Neue Register werden möglichst über die vollständige Provenance-Kette dokumentiert:

```text
Modbusregister
  ↓
Registerspiegel
  ↓
interne RAM-Variable
  ↓
Writer / Berechnungsfunktion
  ↓
Sensor, Zustand oder Aktor
  ↓
Verbraucher / Seiteneffekt
```

Damit sollen insbesondere bisher als `reserved` oder unbekannt geführte Register reproduzierbar und mit Confidence-Stufe entschlüsselt werden.