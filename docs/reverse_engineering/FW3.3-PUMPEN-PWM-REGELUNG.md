# Mainboard-Firmware V3.3 – Umwälzpumpe, PWM-Regelung und Durchflussberechnung

Stand: 27. August 2026

Dieses Dokument beschreibt die in der Mainboard-Firmware `82400644 / V3.3` rekonstruierte Regelung der Haupt-Umwälzpumpe. Schwerpunkt sind die Parameter `H31`, `P10`, `P11`, `P12`, die Statusregister `2077`, `2106`, `2115`, `2116`, die automatische Delta-T-Regelung sowie die aus der Pumpen-PWM-Rückmeldung berechnete Wasserdurchflussrate.

Die Firmware wird ausschließlich analysiert und nicht verändert.

## Bewertungsstufen

- **bestätigt** – direkt im untersuchten V3.3-Binary nachgewiesen
- **live bestätigt** – zusätzlich am realen Gerät beobachtet
- **sehr wahrscheinlich** – Datenfluss weitgehend geschlossen, einzelne letzte Verknüpfung noch nicht bewiesen
- **offen** – Bedeutung oder Kopplung noch nicht vollständig geschlossen

---

# 1. Relevante öffentliche Register

| Register | Parameter / Status | Bedeutung | Bewertung |
|---:|---|---|---|
| `1041` | `H31` | Typ der Zirkulationswasserpumpe / Kennlinienauswahl für Durchflussberechnung | bestätigt |
| `1205` | `P10` | Pumpendrehzahl; `0` = automatische PWM-Regelung, `>0` = feste Soll-PWM in % | bestätigt |
| `1432` | `P11` | Ziel-Temperaturdifferenz für Pumpendrehzahlregelung, x0,1 K | bestätigt |
| `1433` | `P12` | PWM-Anpassung je Regelereignis / Schrittweite in Prozentpunkten | bestätigt |
| `2077` | `T39` | berechnete Wasserdurchflussrate, raw/100 m³/h | bestätigt |
| `2106` | – | zyklisches Pumpenregel-/PWM-Regelfenster, starker Kandidat | live beobachtet, Kopplung noch nicht final bewiesen |
| `2115` | – | aktuell von der Mainboardregelung vorgegebene Pumpen-PWM in % | bestätigt |
| `2116` | – | gemessene PWM-Rückmeldung der Pumpe in % | bestätigt |

Die Parameter liegen in unterschiedlichen Live-Strukturen:

```text
0x20016C6C
  +0x0C -> MAIN:1205 / P10

0x20016278
  +0x00 byte -> MAIN:1432 / P11
  +0x01 byte -> MAIN:1433 / P12
```

`1041 / H31` gehört zum H-/Grundkonfigurationsblock `0x20016774`.

---

# 2. P10 / MAIN:1205 – feste oder automatische Pumpendrehzahl

`P10` entscheidet, ob die Hauptumwälzpumpe mit einer festen PWM-Vorgabe oder durch die interne Delta-T-Regelung gefahren wird.

## 2.1 P10 > 0 – feste PWM

Für Werte größer 0 wird P10 im normalen Pumpenbetrieb direkt als logische Pumpenvorgabe verwendet:

```text
P10 = 45
    -> normale Soll-PWM ungefähr 45 %
    -> MAIN:2115 ungefähr 45
```

Werte oberhalb 100 werden auf 100 % begrenzt.

Wichtig: `2115` muss nicht immer identisch mit `P10` sein. Start-, Schutz-, Abtau-, Frostschutz- oder andere Zwangszustände können die Pumpenvorgabe übersteuern.

## 2.2 P10 = 0 – automatische PWM-Regelung

Bei `P10 = 0` wird die automatische Pumpendrehzahlregelung aktiviert.

Beim Eintritt in den Auto-Pfad kann die Pumpenvorgabe zunächst auf 100 % gesetzt werden. Die eigentliche Delta-T-Regelung reduziert bzw. erhöht sie anschließend schrittweise.

Die zentrale Regelroutine liegt im untersuchten Build ungefähr bei:

```text
VA 0x08084474
```

Die Routine berücksichtigt mindestens:

- aktuelle Wasserspreizung,
- `P11` Zielspreizung,
- `P12` Schrittweite,
- aktuelle/letzte Kompressor-Sollfrequenz,
- Mindestdurchflussbedingungen,
- aktuelle Pumpen-PWM.

**Bewertung: bestätigt.**

---

# 3. P11 / MAIN:1432 – Zielspreizung

`P11` ist die Ziel-Temperaturdifferenz für die automatische Pumpendrehzahlregelung.

Skalierung:

```text
P11 raw / 10 = K
```

Beispiel:

```text
P11 = 44
-> 4,4 K Zielspreizung
```

Die Firmware verwendet eine betriebsrichtungsabhängig positiv orientierte Wasserspreizung. Die beiden Wasser-Temperaturkanäle werden je nach Betriebsart so ausgewertet, dass die für die Regelung relevante Differenz mit konsistentem Vorzeichen vorliegt.

Daher sollte P11 in der Dokumentation als **Ziel-Wasserspreizung** und nicht als starr definierte mathematische Reihenfolge eines einzelnen Sensorpaares beschrieben werden.

**Bewertung: bestätigt.**

---

# 4. P12 / MAIN:1433 – Anpassung je Regelereignis

`P12` ist die Schrittweite, mit der die automatische Regelung die logische Pumpen-PWM verändert.

Beispiel:

```text
P12 = 2
-> normaler Korrekturschritt = 2 Prozentpunkte
-> großer Korrekturschritt   = 4 Prozentpunkte
```

Die Firmware benutzt dabei nicht nur eine einfache Ein/Aus-Schwelle, sondern mehrere Delta-T-Bereiche.

---

# 5. Delta-T-Regelgesetz

Sinngemäß wird gebildet:

```text
Fehler = Ist-Spreizung - P11
```

Die Regelung arbeitet ungefähr mit folgenden Schwellen:

| Ist-Spreizung relativ zu P11 | PWM-Korrektur |
|---|---:|
| `>= P11 + 3,0 K` | `+ 2 × P12` |
| `>= P11 + 1,0 K` | `+ P12` |
| ungefähr innerhalb `±1 K` | keine Delta-T-Korrektur |
| `<= P11 - 1,0 K` | `- P12` |
| `<= P11 - 3,0 K` | `- 2 × P12` |

Hydraulische Bedeutung:

```text
Ist-Delta-T zu groß
-> Wassermenge zu klein
-> Pumpen-PWM erhöhen

Ist-Delta-T zu klein
-> Wassermenge zu groß
-> Pumpen-PWM reduzieren
```

Beispiel mit:

```text
P11 = 44 -> 4,4 K
P12 = 2
```

ungefähr:

```text
Ist-Delta-T >= 7,4 K -> +4 %-Punkte
Ist-Delta-T >= 5,4 K -> +2 %-Punkte

ca. 3,5 ... 5,3 K    -> keine Delta-T-Korrektur

Ist-Delta-T <= 3,4 K -> -2 %-Punkte
Ist-Delta-T <= 1,4 K -> -4 %-Punkte
```

**Bewertung: bestätigt für Schwellenstruktur und P12-Schritte.**

---

# 6. Feed-Forward über die Kompressor-Sollfrequenz

Die automatische Pumpenregelung reagiert zusätzlich auf Änderungen der Kompressor-Sollfrequenz.

Die Sollfrequenz ist dieselbe Regelgröße, die öffentlich als `MAIN:2071` veröffentlicht und an das Inverterboard übertragen wird.

Wenn sich die Sollfrequenz gegenüber dem gespeicherten Vergleichswert ungefähr um mindestens 6 Hz verändert, wird zusätzlich ein P12-Schritt auf die Pumpen-PWM gegeben:

```text
Kompressor-Sollfrequenz steigt um ca. >= 6 Hz
-> zusätzlich +P12 Pumpen-PWM

Kompressor-Sollfrequenz fällt um ca. >= 6 Hz
-> zusätzlich -P12 Pumpen-PWM
```

Damit besitzt die Pumpenregelung neben dem eigentlichen Delta-T-Regler eine Vorsteuerung auf Leistungsänderungen des Verdichters.

Zweck:

```text
Verdichterleistung steigt
-> erwarteter Wärmestrom steigt
-> Pumpenleistung wird vorsorglich angehoben
-> Delta-T muss nicht erst deutlich weglaufen
```

**Bewertung: bestätigt.**

---

# 7. Mindestdurchfluss-Schutz innerhalb der Auto-Regelung

Die automatische Regelung berücksichtigt einen Mindest-/Soll-Durchfluss.

Wenn der aktuelle bzw. intern geglättete Wasserdurchfluss am unteren Grenzwert liegt, wird eine weitere Reduzierung der Pumpen-PWM unterdrückt.

Sinngemäß:

```text
wenn Ist-Durchfluss <= Mindestdurchfluss:
    positive PWM-Korrektur erlaubt
    negative PWM-Korrektur gesperrt
```

Damit kann der Delta-T-Regler nicht nur zur Einhaltung der Zielspreizung immer weiter herunterregeln und dabei den für die Wärmepumpe erforderlichen Mindestvolumenstrom unterschreiten.

Im Gesamtsystem stehen hierzu insbesondere die bekannten Durchflussparameter wie `A40` Nenn-Wasserdurchfluss und weitere Betriebs-/Abtaugrenzen zur Verfügung. Die genaue vollständige Prioritätskette aller Durchflussgrenzen ist separat zu betrachten.

**Bewertung: bestätigt für die Sperrlogik; vollständige Herkunft jedes Grenzwertes noch nicht vollständig dokumentiert.**

---

# 8. Grenzen des normalen Auto-Reglers

Im normalen automatischen Regelpfad wird die resultierende Pumpenvorgabe auf ungefähr folgenden Bereich begrenzt:

```text
Minimum: 16 %
Maximum: 92 %
```

Sinngemäß:

```text
PWM_auto = clamp(PWM_auto + Korrektur, 16, 92)
```

Diese Grenzen gelten für den normalen Auto-Regelpfad.

Andere Zustände können die Pumpe außerhalb dieses Bereiches ansteuern, insbesondere bis 100 %.

Daher darf aus einem beobachteten `MAIN:2115 = 100` nicht geschlossen werden, dass die Auto-Regelung selbst ein Soll von 100 % berechnet hat.

**Bewertung: bestätigt.**

---

# 9. MAIN:2115 – aktuelle Pumpen-PWM-Vorgabe

`MAIN:2115` stammt aus der Runtime-Pumpenstruktur und repräsentiert die aktuell wirksame **logische** Pumpen-Sollvorgabe in Prozent.

Datenfluss:

```text
P10 fest
oder
Auto-Regler P10=0
oder
Override / Schutzfunktion
        |
        v
Runtime Pumpen-Soll-PWM
        |
        v
MAIN:2115
        |
        v
Hardware-PWM-Ausgabe
```

Damit ist 2115 der wichtigste öffentliche Diagnosewert, um die tatsächliche Pumpenansteuerung durch das Mainboard zu beobachten.

**Bewertung: bestätigt.**

---

# 10. Invertierung zwischen logischer Pumpenleistung und Hardware-PWM

Vor der Ausgabe auf die Hardware wird die logische Prozentvorgabe invertiert.

Sinngemäß:

```text
Hardware_PWM = (100 - logische_Pumpenleistung) * 10
```

Damit ist `MAIN:2115` bewusst die für Diagnose und Bedienung sinnvolle Pumpenleistung in Prozent und **nicht** das rohe Timer-Compare-/Duty-Cycle-Register des Mikrocontrollers.

Dies erklärt, warum ein hoher logischer Pumpenwert elektrisch als kleinerer bzw. invertierter PWM-Duty-Cycle erscheinen kann.

**Bewertung: bestätigt.**

---

# 11. MAIN:2116 – echte Pumpen-PWM-Rückmeldung

`MAIN:2116` ist keine zweite Sollvorgabe und keine direkte Drehzahl in rpm.

Die Firmware misst die Rückmeldeleitung der Pumpe per Timer Input Capture. Aus zwei Capture-Werten wird das Tastverhältnis bestimmt und auf Prozent skaliert.

Sinngemäß:

```text
Feedback_ratio = Capture_A / Capture_B
MAIN:2116      = int(Feedback_ratio * 100)
```

Die relevante Capture-/Auswerteroutine liegt im untersuchten Build ungefähr bei:

```text
VA 0x08061790
```

Damit gilt:

> `MAIN:2116` = gemessenes PWM-Tastverhältnis der Pumpen-Rückmeldeleitung in Prozent.

Dieses Signal wird anschließend zur Berechnung des Wasserdurchflusses verwendet.

**Bewertung: bestätigt.**

---

# 12. H31 / MAIN:1041 – Pumpentyp und Kennlinienauswahl

Die Firmware kennt folgende H31-Werte:

| H31 | Pumpentyp |
|---:|---|
| `0` | keine Durchflusserkennung |
| `1` | Grundfos 25-75 |
| `2` | Grundfos 25-105 |
| `3` | Grundfos 25-125 |
| `4` | Shimge APM25 9-130 |
| `5` | Shimge APM25 12-130 |

H31 beeinflusst nicht nur eine Anzeige, sondern wählt die Kennlinie aus, mit der `MAIN:2116` in einen berechneten Wasserdurchfluss umgesetzt wird.

**Bewertung: bestätigt.**

---

# 13. Durchflussberechnung aus PWM-Feedback

Der rekonstruierte Datenfluss lautet:

```text
Pumpen-Rückmeldeleitung
        |
        v
Timer Input Capture
        |
        v
PWM-Rückmeldung in %
        |
        +-----> MAIN:2116
        |
        v
H31-Pumpenkennlinie
        |
        v
berechneter Wasserdurchfluss
        |
        v
MAIN:2077 / T39
```

`MAIN:2077` ist als Wasserdurchflussrate mit folgender Skalierung veröffentlicht:

```text
2077 raw / 100 = m³/h
```

**Bewertung: bestätigt.**

---

# 14. H31-Kennlinien und Maximalwerte

Im V3.3-Binary sind pumpentypspezifische Koeffizienten und Maximalwerte hinterlegt.

## 14.1 Übersicht

| H31 | Typ | Kennlinienkoeffizient | max. berechneter Durchfluss |
|---:|---|---:|---:|
| 0 | keine Durchflusserkennung | 0 | 0 |
| 1 | Grundfos 25-75 | 0,0300 | 2,10 m³/h |
| 2 | Grundfos 25-105 | 0,0570 | 4,00 m³/h |
| 3 | Grundfos 25-125 | 0,0570 | 4,00 m³/h |
| 4 | Shimge APM25 9-130 | 0,0646 plus Offset/Sonderpfad | 4,50 m³/h |
| 5 | Shimge APM25 12-130 | 0,0570 | 4,00 m³/h |

**Bewertung: bestätigt für die im untersuchten Build verwendeten Konstanten und Auswahlpfade.**

## 14.2 Grundfos 25-75

Für H31=1 gilt näherungsweise:

```text
Q[m³/h] = 0,0300 * PWM_Feedback[%]
```

Beispiel:

```text
2116 = 50 %
Q = 0,0300 * 50
Q = 1,50 m³/h
```

Anschließend wird auf maximal etwa 2,10 m³/h begrenzt.

## 14.3 Grundfos 25-105 / 25-125 und Shimge APM25 12-130

Für H31=2, H31=3 und H31=5 verwendet dieser V3.3-Build für die Durchflussabschätzung denselben Koeffizienten:

```text
Q[m³/h] = 0,0570 * PWM_Feedback[%]
```

Beispiel:

```text
2116 = 50 %
Q = 0,0570 * 50
Q = 2,85 m³/h
```

Maximalwert ungefähr 4,00 m³/h.

Damit werden diese drei Pumpentypen zumindest in dieser konkreten Durchflussberechnung identisch behandelt, obwohl die Pumpenbezeichnungen unterschiedlich sind.

## 14.4 Shimge APM25 9-130

H31=4 besitzt einen eigenen Sonderpfad.

Unter ungefähr 5 % Rückmelde-PWM wird kein Durchfluss angesetzt:

```text
PWM_Feedback < ca. 5 %
-> Q = 0
```

Darüber gilt näherungsweise:

```text
Q[m³/h] = 0,0646 * (PWM_Feedback[%] - 5)
```

Beispiel:

```text
2116 = 50 %
Q = 0,0646 * (50 - 5)
Q ~= 2,91 m³/h
```

Maximalwert ungefähr 4,50 m³/h.

**Bewertung: bestätigt für den separaten H31=4-Pfad und die Konstanten.**

---

# 15. Hoher PWM-Feedbackbereich wird nicht als normaler Durchfluss interpretiert

Die Firmware prüft die gemessene Pumpen-PWM-Rückmeldung vor der Durchflussberechnung.

Ab ungefähr:

```text
Feedback >= 85 %
```

wird das Signal für die normale Durchflussberechnung als ungültig bzw. nicht verwertbar behandelt.

Das bedeutet:

```text
2116 kann ein hohes PWM-Feedback anzeigen,
aber 2077 muss daraus nicht proportional weiter ansteigen.
```

Dieser Bereich darf nicht mit der Soll-PWM `2115` verwechselt werden.

```text
2115 = Mainboard -> Pumpe, logische Soll-PWM
2116 = Pumpe -> Mainboard, Rückmelde-PWM
```

Die unterschiedliche Semantik ist wesentlich.

**Bewertung: bestätigt für die Grenzprüfung; die genaue Herstellerbedeutung des hohen Feedbackbereichs ist noch offen.**

---

# 16. Regeltakt / P12-Periode

Im Auto-Regler existiert ein interner Zähler, der bis ungefähr 120 läuft, bevor ein neuer Pumpenregelentscheid ausgeführt wird.

Damit ist strukturell bestätigt:

```text
1 P12-Regelentscheidung nach 120 Aufrufen des betreffenden Pumpenregeltasks
```

Die absolute Zeit ergibt sich erst aus der Aufrufperiode dieses Tasks.

## 16.1 Live-Beobachtung MAIN:2106

Am realen Gerät wurde im Kühlbetrieb am 15. Juli 2026 beobachtet:

```text
MAIN:2106 pulst ungefähr alle 5 Minuten von 0 auf 1
und nach etwa 9...11 Sekunden wieder auf 0.
```

Beobachtete Pulse lagen unter anderem ungefähr bei:

```text
13:30
13:35
13:40
13:45
13:50
13:55
14:00
14:05
```

Währenddessen blieb `MAIN:2115` in der damaligen Beobachtung stabil bei 50 %.

Daher ist `2106` ein sehr starker Kandidat für ein Pumpenregel-/PWM-Regelfenster bzw. für einen P12-Regelzyklus.

Noch **nicht** final bewiesen ist jedoch:

```text
MAIN:2106 == exakt derselbe interne 120er-Regelzähler
```

Bis dieser letzte Datenfluss geschlossen ist, soll 2106 weiterhin als **starker Kandidat** und nicht als endgültig bestätigtes Regelzyklusflag dokumentiert werden.

---

# 17. Gesamtregelung als Datenfluss

```text
                             MAIN:1205 / P10
                                   |
                    +--------------+--------------+
                    |                             |
                 P10 > 0                        P10 = 0
                    |                             |
                    v                             v
             feste PWM-Vorgabe              Auto-Regler
                    |                             |
                    |                      Ist-Delta-T - P11
                    |                             |
                    |                    +/-P12 / +/-2*P12
                    |                             |
                    |                 Kompressor-Feed-Forward
                    |                       +/-P12 bei ~6 Hz
                    |                             |
                    |                  Mindestdurchfluss-Schutz
                    |                             |
                    |                      Clamp ca. 16...92 %
                    |                             |
                    +--------------+--------------+
                                   |
                                   v
                         Runtime Pumpen-Soll-PWM
                                   |
                                   v
                              MAIN:2115
                                   |
                                   v
                         invertierte HW-PWM-Ausgabe
                                   |
                                   v
                                 Pumpe
                                   |
                     PWM-Rückmeldeleitung
                                   |
                                   v
                          Timer Input Capture
                                   |
                                   v
                              MAIN:2116
                                   |
                                   v
                           H31-Kennlinie
                                   |
                                   v
                         Wasserdurchfluss T39
                                   |
                                   v
                              MAIN:2077
```

---

# 18. Diagnose- und Live-Testempfehlung

Für einen vollständigen Live-Test der automatischen Pumpenregelung sollten mindestens folgende Register gleichzeitig mitgeloggt werden:

```text
1041  H31 Pumpentyp
1205  P10 Pumpendrehzahl / Auto=0
1432  P11 Zielspreizung
1433  P12 Schrittweite

relevante Wasser-Ein-/Auslasstemperaturen
2071  Kompressor-Sollfrequenz
2072  Kompressor-Istfrequenz
2077  Wasserdurchfluss
2106  vermutetes Pumpen-Regelfenster
2115  Pumpen-Soll-PWM
2116  Pumpen-Feedback-PWM
```

Ein besonders aussagekräftiger Test ist:

1. `P10=0` aktivieren.
2. P11/P12 notieren.
3. Bei stabil laufendem Verdichter die Wasser-Spreizung, 2071, 2077, 2106, 2115 und 2116 mit hoher zeitlicher Auflösung loggen.
4. Auf Änderungen von 2115 relativ zu Delta-T-Abweichung und Änderungen von 2071 achten.
5. Prüfen, ob 2115-Schritte genau `P12` bzw. `2*P12` entsprechen.
6. 2106 zeitlich mit diesen Regelentscheidungen korrelieren.

Damit lässt sich insbesondere die noch offene direkte Kopplung von `2106` zum internen 120er-Regelzähler live schließen.

---

# 19. Kurzfassung für Registermapping

```text
1041 / H31
Zirkulationswasserpumpentyp / Durchflusskennlinie
0 = keine Durchflusserkennung
1 = Grundfos 25-75
2 = Grundfos 25-105
3 = Grundfos 25-125
4 = Shimge APM25 9-130
5 = Shimge APM25 12-130

1205 / P10
Pumpendrehzahl
0 = automatische Delta-T-PWM-Regelung
1..100 = feste Pumpen-PWM in %

1432 / P11
Ziel-Wasserspreizung, raw/10 K

1433 / P12
PWM-Anpassung je Regelereignis in Prozentpunkten

2077 / T39
berechneter Wasserdurchfluss, raw/100 m³/h
Quelle: PWM-Rückmeldung 2116 + H31-Kennlinie

2106
zyklisches Pumpenregel-/PWM-Regelfenster, sehr starker Kandidat
Live ca. 5-minütig beobachtet; exakte Kopplung zum internen 120er-Zähler noch offen

2115
aktuelle logische Pumpen-Soll-PWM in %

2116
gemessene PWM-Rückmeldung der Pumpe in %
Grundlage der firmwareinternen Durchflussberechnung
```

---

# 20. Noch offene Punkte

1. Direkte Xref-Kette `MAIN:2106` zum internen 120er Pumpenregelzähler vollständig schließen.
2. Alle Override-Pfade katalogisieren, die `2115` unabhängig von P10/Auto-Regler auf einen festen Wert bzw. 100 % setzen.
3. Vollständige Prioritätskette aller Mindestdurchflussbedingungen dokumentieren.
4. Herstellersemantik des Pumpen-Feedbackbereichs ab ungefähr 85 % klären.
5. H31-Kennlinien mit realen Pumpenmessungen gegen `MAIN:2077` korrelieren.
6. Prüfen, ob die Koeffizienten bei anderen Firmwarefamilien identisch sind oder firmware-/pumpenfamilienabhängig variieren.

---

# 21. Fazit

Die V3.3 besitzt eine deutlich umfangreichere Pumpenregelung als eine einfache feste PWM-Ausgabe.

Bei `P10=0` wird die Pumpendrehzahl automatisch aus der Wasser-Spreizung geregelt. P11 definiert die Zielspreizung, P12 die Schrittweite. Zusätzlich reagiert die Regelung vorauseilend auf Änderungen der Kompressor-Sollfrequenz und verhindert ein weiteres Herunterregeln bei zu geringem Wasserdurchfluss.

`MAIN:2115` ist die aktuelle Soll-PWM des Mainboards. `MAIN:2116` ist dagegen eine echte, per Timer gemessene PWM-Rückmeldung der Pumpe. Über die durch `H31` ausgewählte Pumpenkennlinie wird daraus der öffentliche Wasserdurchfluss `MAIN:2077 / T39` berechnet.

Damit ist insbesondere die bisherige Vermutung bestätigt:

> **2116 ist die Pumpen-PWM-Rückmeldung und wird in der Firmware tatsächlich zur Berechnung des Wasserdurchflusses verwendet.**
