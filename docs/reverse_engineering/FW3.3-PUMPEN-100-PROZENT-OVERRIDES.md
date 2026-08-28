# Mainboard-Firmware V3.3 – Pumpen-Overrides auf 100 % PWM

Stand: 28. August 2026

Diese Datei dokumentiert die in der Mainboard-Firmware `82400644 / V3.3` rekonstruierten Bedingungen, die den normalen automatischen Pumpenregler übersteuern und die Haupt-Umwälzpumpe auf **100 % logische PWM** setzen.

Untersuchtes Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
Pumpenroutine: 0x08084474
```

Bewertung:

- **bestätigt** – Datenpfad und Wirkung direkt im Binary geschlossen
- **sehr wahrscheinlich** – fachliche Bedeutung aus Writer/Verbrauchern stark ableitbar
- **offen** – Wirkung bestätigt, Herstellerbezeichnung des Flags noch nicht sicher benannt

---

# 1. Gemeinsamer Vollpumpenpfad

Der zentrale Override-Zielpfad liegt ungefähr bei:

```text
raw 0x348F2
VA  0x080848F2
```

Wenn eine der vorgeschalteten Bedingungen aktiv wird, setzt V3.3:

```text
runtime +0x0A = 120     ; P12-Regelzähler sofort auf fällig
runtime +0x02 = 100     ; logische Pumpen-Soll-PWM
runtime +0x09 = 0       ; 10-min-Auto-Qualifikation löschen
```

Damit ist die Wirkung stärker als nur „vorübergehend 100 %“:

> **Ein Override erzwingt 100 % Pumpenleistung und verwirft gleichzeitig die bereits erreichte Auto-PWM-Qualifikation.**

Nach Wegfall des Overrides muss die Auto-PWM-Freigabe erneut aufgebaut werden, sofern die übrigen Bedingungen dies erfordern.

`runtime +0x02` wird anschließend als `MAIN:2115` veröffentlicht.

**Bewertung: bestätigt.**

---

# 2. Übersicht der direkten Bedingungen vor 0x348F2

| Bedingung | Rohquelle | Wirkung | Fachliche Bewertung |
|---|---|---|---|
| Betriebs-/Sonderzustand ungleich 0 | `0x2001660C+0x20`, Bits 2..3 | 100 %, Requalifikation | offen |
| internes Override-/Schutzflag !=0 | `0x20016658+0x0E` | 100 %, Requalifikation | offen |
| Bit 7 eines zentralen Betriebsflags gesetzt | `0x2001660C+0x20`, Bit 7 | 100 %, Requalifikation | sehr wahrscheinlich Sonder-/Abtauzustand |
| Wasser-Temperaturkanal A ungültig | Helper `0x0808795C` -> `0x20015FA8+0x04` | 100 %, Requalifikation | bestätigt als Valid-/Fehlerflag des ΔT-Sensorkanals |
| Wasser-Temperaturkanal B ungültig | Helper `0x08087992` -> `0x20015FA8+0x0A` | 100 %, Requalifikation | bestätigt als Valid-/Fehlerflag des ΔT-Sensorkanals |
| erforderliches Run-/Enable-Bit fehlt | `0x20016E0C+0x03`, Bit 1 | 100 %, Requalifikation | sehr wahrscheinlich Betriebsfreigabe |
| `A40 == 0` | `0x20016C9C+0x0A` | 100 %, Requalifikation | bestätigt |
| kein gültiger Durchfluss vorhanden | `0x20016FAC == 0` | 100 %, Requalifikation | bestätigt |
| Betriebsart 1: Temperatur-Plausibilitätsbedingung verletzt | Mode `0x200164B8+0x02 == 1`, Helper `0x08072D98`, Helper `0x08087966` | 100 %, Requalifikation | Datenpfad bestätigt, Herstellersemantik der Grenze offen |
| Betriebsart 0: zweite Temperatur-Plausibilitätsbedingung verletzt | Mode `0x200164B8+0x02 == 0`, Helper `0x08087966`, `0x20016744+0x14` | 100 %, Requalifikation | Datenpfad bestätigt, Herstellersemantik der Grenze offen |
| internes Fault-/Betriebsflag !=0 | `0x20016E24+0x02` | 100 %, Requalifikation | bestätigt; zusätzlich Quelle von `MAIN:2139` Bit 4 |
| internes Betriebsflag !=0 | `0x20016D2C+0x0B` | 100 %, Requalifikation | offen |
| internes Betriebsflag !=0 | `0x20016BC8+0x0F` | 100 %, Requalifikation | offen |
| Statusfeld Bits 1..2 !=0 | `0x20016214+0x01`, Bits 1..2 | 100 %, Requalifikation | offen |
| internes Bit gesetzt | `0x20016D2C+0x09`, Bit 0 | 100 %, Requalifikation | bestätigt; zusätzlich Quelle von `MAIN:2139` Bit 6 |
| physischer Eingang PE12 aktiv | GPIOE IDR `0x40011800`, Maske `0x1000` | 100 %, Requalifikation | physischer Digitaleingang bestätigt, Klemmenname offen |
| physischer Eingang PE13 aktiv | GPIOE IDR `0x40011800`, Maske `0x2000` | 100 %, Requalifikation | physischer Digitaleingang bestätigt, Klemmenname offen |
| internes Bitfeld `0x18` aktiv | `0x20016BE0+0x0E`, Bits 3..4 | 100 %, Requalifikation | offen |
| Außentemperatur-Hysterese aktiv | Pumpenruntime `+0x07` | 100 %, Requalifikation | bestätigt; 20/22 °C Hysterese in einem Runtime-Modus |
| falsche ΔT-Richtung länger ca. 30 s | Pumpenruntime `+0x01` | 100 %, Requalifikation | bestätigt |

---

# 3. Ungültige Wasser-Temperaturkanäle erzwingen 100 %

Die beiden Helper:

```text
0x0808795C -> signed Feld 0x20015FA8+0x04
0x08087992 -> signed Feld 0x20015FA8+0x0A
```

werden unmittelbar vor dem Vollpumpenpfad geprüft.

Wenn einer der beiden Werte ungleich 0 ist:

```text
-> 100 % PWM
-> Auto-Qualifikation löschen
```

Die zugehörigen Temperaturhelper sind:

```text
0x08087930
0x08087966
```

Sie liefern die beiden Wasser-Temperaturkanäle, aus denen die Pumpenregelung abhängig von der Betriebsart ihre Spreizung bildet.

Damit ist fachlich belastbar:

> **Wenn einer der für die Wasser-ΔT-Regelung benötigten Temperaturkanäle ungültig/gestört ist, darf V3.3 die Pumpe nicht automatisch herunterregeln und fährt sie stattdessen auf 100 %.**

Die exakte Herstellerbezeichnung der beiden Sensoren (Ein-/Ausgang in der jeweiligen Helper-Reihenfolge) wird hier bewusst nicht vertauscht; die Orientierung wird in der Pumpenroutine je nach Betriebsart umgedreht.

**Bewertung: bestätigt.**

---

# 4. A40 = 0 sperrt Auto-PWM

Direkte Bedingung:

```text
0x20016C9C+0x0A = MAIN:1344 / A40
```

Wenn:

```text
A40 == 0
```

springt die Firmware auf den 100-%-Pfad.

Das ist logisch konsistent mit der restlichen Regelung, weil A40 für folgende Schwellen benötigt wird:

```text
10-min-Qualifikation:  ca. 1,2 x A40
Fallback-Minimum:      ca. 0,8 x A40
```

Ohne gültigen Nenn-Wasserdurchfluss gibt V3.3 daher keine automatische Pumpenabsenkung frei.

**Bewertung: bestätigt.**

---

# 5. Kein gültiger Durchfluss -> 100 %

Direkte Bedingung:

```text
0x20016FAC == 0
```

Dieses Runtimeflag wird im Durchfluss-Erfassungsweg gesetzt, wenn ein gültiger lokaler H31/PWM-Durchfluss bzw. ein gültiger externer H30=3/HYD61-Durchfluss zur Verfügung steht.

Wenn kein gültiger Durchfluss vorliegt:

```text
-> keine Auto-PWM-Absenkung
-> 2115 = 100 %
-> 10-min-Qualifikation = 0
```

Damit ist bestätigt:

> **Die Auto-PWM-Regelung ist ausdrücklich fail-safe bezüglich der Durchflusserfassung: ohne gültige Durchflussquelle läuft die Pumpe auf Vollleistung.**

**Bewertung: bestätigt.**

---

# 6. Falsche Wasser-ΔT-Richtung länger ca. 30 s

Die Pumpenroutine überwacht die Richtung der Wasser-Spreizung abhängig vom Runtime-Modus `0x200164B8+0x02`.

Ein separater Zähler bei:

```text
0x20016FEC
```

zählt bis 60 Pumpentasks.

Taskperiode:

```text
60 x 0,5 s = 30 s
```

Bleibt die Spreizung über diese Zeit in der zur Betriebsart falschen Richtung:

```text
Pumpenruntime +0x01 = 1
```

und dieses Flag führt direkt auf den Vollpumpenpfad.

Damit:

> **Eine über etwa 30 s unplausible Vorlauf-/Rücklauf-Richtung sperrt die Auto-PWM-Regelung und erzwingt 100 %.**

**Bewertung: bestätigt.**

---

# 7. Außentemperatur-Hysterese 20/22 °C

Ein weiteres Pumpenruntimeflag `+0x07` wird über T04/Außentemperatur geführt.

In dem betroffenen Runtime-Modus gilt:

```text
T04 < 20,0 °C  -> Flag = 1
T04 >=22,0 °C  -> Flag = 0
20,0..21,9 °C -> Zustand halten
```

Wenn das Flag aktiv ist, führt es direkt auf 100 % PWM.

Die exakte Herstellerbezeichnung des zugehörigen Betriebsmodus wird noch nicht erzwungen benannt; der Temperaturdatenpfad und die 20/22-°C-Hysterese sind dagegen geschlossen.

**Bewertung: bestätigt.**

---

# 8. Zentraler Betriebsbitblock 0x2001660C+0x20

Dieser Bytewert wird mehrfach im V3.3-Binary benutzt.

Für die Pumpenregelung sind zwei Teile relevant:

```text
Bits 2..3 != 0 -> 100 %
Bit 7 == 1     -> 100 %
```

Bit 7 tritt zusätzlich in mehreren Sonderbetriebs-/Schutz-State-Machines auf. Sein Verhalten ist stark kompatibel mit einem Sonderzyklus wie Abtau-/Defrostbetrieb, die endgültige Herstellerbezeichnung ist aber noch nicht vollständig aus einem öffentlichen Registertext geschlossen.

Daher aktuelle Bewertung:

```text
Bits 2..3 : Betriebs-/Sonderzustand, Wirkung bestätigt, Name offen
Bit 7     : Sonder-/Abtaubetrieb sehr wahrscheinlich, noch nicht final benannt
```

Wichtig ist unabhängig von der Benennung:

> **Wenn diese Zustände aktiv sind, ist die normale P11/P12-Auto-PWM-Regelung absichtlich außer Kraft.**

---

# 9. Interne Fault-/Statusflags 0x20016E24 und 0x20016D2C

## 9.1 0x20016E24+0x02

Dieses signed Byte wird vor dem Vollpumpenpfad geprüft:

```text
!= 0 -> 100 % PWM
```

Zusätzlich wird dasselbe Feld in der Fault-Sammelroutine in das interne Faultword `0x20016F24` übernommen:

```text
0x20016E24+0x02 !=0
-> 0x20016F24 |= 0x0010
```

`0x20016F24` wird wiederum als:

```text
MAIN:2139
```

publiziert.

Damit ist neu geschlossen:

> **MAIN:2139 Bit 4 stammt von `0x20016E24+0x02`; derselbe Fehler-/Statuszustand erzwingt Pumpen-PWM 100 %.**

Die konkrete Fehlerbezeichnung dieses Bits bleibt noch offen.

## 9.2 0x20016D2C+0x09 Bit 0

Auch dieses Bit führt direkt zu 100 % PWM.

In derselben Fault-Sammelroutine gilt:

```text
(0x20016D2C+0x09) & 0x01
-> 0x20016F24 |= 0x0040
```

Damit ist ebenfalls neu geschlossen:

> **MAIN:2139 Bit 6 stammt von `0x20016D2C+0x09 Bit 0`; aktiver Zustand erzwingt 100 % Pumpen-PWM.**

Konkrete Herstellerbezeichnung noch offen.

## 9.3 Weitere interne Flags

Direkte Vollpumpenbedingungen bestehen außerdem für:

```text
0x20016D2C+0x0B != 0
0x20016BC8+0x0F != 0
0x20016214+0x01 Bits 1..2 != 0
0x20016BE0+0x0E & 0x18 != 0
0x20016658+0x0E != 0
```

Die Wirkung ist jeweils bestätigt; die fachliche Einzelbezeichnung wird bewusst offen gelassen, bis Writer/öffentliche Statusabbildung vollständig geschlossen sind.

---

# 10. Zwei physische Digitaleingänge auf GPIOE

Die Pumpenroutine prüft direkt den GPIO-Eingangsregisterblock:

```text
GPIOE IDR = 0x40011800 + 0x0C
```

über Helper `0x08089D08`.

Geprüft werden:

```text
PE12 / Maske 0x1000
PE13 / Maske 0x2000
```

Ist einer der beiden Eingänge aktiv:

```text
-> 100 % PWM
-> Auto-Qualifikation löschen
```

Damit ist bestätigt, dass zwei reale Hardwareeingänge die Pumpenautomatik direkt überstimmen können.

Die konkrete Klemmen-/Funktionsbezeichnung von PE12 und PE13 ist noch offen und sollte über Board-I/O-Mapping bzw. Schaltplan/Mitschnitt geschlossen werden.

**Bewertung: physischer Eingang und Wirkung bestätigt; Funktionsname offen.**

---

# 11. Erforderliches Run-/Enable-Bit

Die Firmware prüft:

```text
0x20016E0C+0x03, Bit 1
```

Wenn dieses Bit **nicht** gesetzt ist:

```text
-> 100 % PWM
```

Dasselbe Runtimefeld wird auch im 10-min-Qualifikationspfad als Betriebsfreigabe verwendet.

Damit ist sicher:

> **Auto-PWM wird nur in einem bestimmten aktiven Betriebszustand zugelassen; außerhalb dieses Zustands bleibt die Pumpe auf 100 %.**

Ob das Bit exakt „Kompressor läuft“, „Heiz-/Kühlbetrieb aktiv“ oder eine kombinierte Run-Freigabe bedeutet, bleibt bis zur vollständigen Writeranalyse offen.

**Bewertung: Wirkung bestätigt, Bezeichnung sehr wahrscheinlich Betriebsfreigabe.**

---

# 12. Temperatur-Plausibilitätsgates je Betriebsart

Zusätzlich zur 30-s-Richtungsprüfung existieren zwei sofort wirkende Temperaturgrenzen.

## Runtime-Modus 1

Sinngemäß:

```text
wenn mode == 1
und (helper_0x08072D98 - 4,0 K) < Wasserkanal_0x08087966:
    -> 100 %
```

## Runtime-Modus 0

Sinngemäß:

```text
wenn mode == 0
und Wasserkanal_0x08087966 < (0x20016744+0x14 + 4,0 K):
    -> 100 %
```

Die Konstanten sind jeweils `40 raw = 4,0 K`.

Die Datenpfade sind bestätigt. Die exakten Herstellertexte der beiden Vergleichsgrößen werden erst dann benannt, wenn der Helper `0x08072D98` und das Parameterfeld `0x20016744+0x14` vollständig fachlich geschlossen sind.

---

# 13. Weitere 100-%-Pfade nach dem Haupt-Gate

Auch nach dem zentralen Gate existieren weitere Vollpumpenpfade.

Bestätigt sind unter anderem:

1. **nicht unterstützter/unerwarteter Runtime-Modus** außerhalb der vorgesehenen Werte 0/1 -> 100 %,
2. **interner Lauf-/Zeitwert `0x20016AA4+0x06 < 60`** -> 100 %,
3. **10-min-Qualifikation `runtime +0x09 == 0`** -> 100 %,
4. feste/Factory-/Sondervorgaben können 100 % direkt setzen,
5. finale Plausibilitätsbegrenzung setzt Werte außerhalb `1..100` auf 100 %.

Damit ist diagnostisch wichtig:

```text
P10 = 0
MAIN:2115 = 100
```

ist in V3.3 ein normaler und häufig absichtlich erzeugter Zustand. Er bedeutet nicht automatisch einen Fehler der Pumpenregelung.

---

# 14. Separater Hardware-/Hydraulik-Gate nahe der PWM-Ausgabe

Unmittelbar vor der finalen Hardware-PWM-Ausgabe existiert noch ein weiterer Gate-Pfad.

Bei einer bestimmten H30-Konfiguration wird ein Bit aus:

```text
0x20016BE0+0x0E, Bit 0
```

verwendet; ansonsten wird ein physischer GPIOC-Eingang über:

```text
GPIOC IDR
Maske 0x0002
```

geprüft.

Wenn dieser Eingangszustand nicht die erwartete Freigabe liefert, setzt die Firmware die Pumpenvorgabe ebenfalls auf 100 %.

Die Struktur passt zu einem hydraulischen/Hardware-Freigabesignal, die endgültige Klemmenbezeichnung ist noch offen.

**Bewertung: Wirkung bestätigt; fachliche Bezeichnung offen.**

---

# 15. Praktische Bedeutung

Die automatische P11/P12-Regelung ist in V3.3 bewusst konservativ aufgebaut.

Sie darf die Pumpe nur dann unter 100 % fahren, wenn gleichzeitig unter anderem gilt:

```text
- gültige Wasser-Temperaturkanäle
- plausibles ΔT
- gültiger Durchfluss
- A40 != 0
- erforderlicher Betriebszustand aktiv
- keine relevanten Fault-/Sonderflags
- keine physischen Overrideeingänge aktiv
- keine 20/22-°C-Sperre
- keine 30-s-ΔT-Richtungsstörung
- Auto-PWM-Qualifikation abgeschlossen
```

Das erklärt, warum MAIN:2115 nach Start, Abtauung, Sensor-/Durchflussproblemen oder bestimmten Betriebszuständen längere Zeit 100 % bleiben kann, obwohl `P10=0` eingestellt ist.

---

# 16. Neue Zuordnungen aus diesem Audit

Neu belastbar geschlossen:

```text
MAIN:2139 Bit 4
<- 0x20016E24+0x02
-> gleichzeitig Pumpen-Override auf 100 %

MAIN:2139 Bit 6
<- 0x20016D2C+0x09 Bit 0
-> gleichzeitig Pumpen-Override auf 100 %
```

Damit ist MAIN:2139 nicht mehr vollständig semantisch leer: mindestens zwei seiner Bits stammen direkt aus internen Fehler-/Betriebsflags, die auch die Pumpenregelung auf Vollleistung zwingen.

Die Herstellerbezeichnungen dieser beiden Bits sind noch offen.

---

# 17. Offene Restpunkte

Noch fachlich zu benennen:

1. `0x2001660C+0x20` Bits 2..3,
2. `0x2001660C+0x20` Bit 7 endgültige Herstellerbezeichnung,
3. `0x20016658+0x0E`,
4. `0x20016D2C+0x0B`,
5. `0x20016BC8+0x0F`,
6. `0x20016214+0x01` Bits 1..2,
7. `0x20016BE0+0x0E` Bits 3..4,
8. PE12/PE13 Klemmenfunktion,
9. GPIOC Maske `0x0002` Klemmenfunktion,
10. genaue Herstellerbezeichnung der `MAIN:2139` Bits 4 und 6,
11. genaue Bedeutung des Betriebsfreigabebits `0x20016E0C+3 Bit1`,
12. vollständige Semantik der beiden unmittelbaren Temperatur-Plausibilitätsgrenzen.

Die Auswirkungen dieser Bedingungen auf die Pumpenregelung sind dagegen bytegenau geschlossen.
