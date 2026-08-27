# Mainboard-Firmware V3.3 – Umwälzpumpe, PWM-Regelung und Durchflussberechnung

Stand: 27. August 2026

Dieses Dokument beschreibt die in der Mainboard-Firmware `82400644 / V3.3` rekonstruierte Regelung der Haupt-Umwälzpumpe. Schwerpunkt sind `H30`, `H31`, `P10`, `P11`, `P12`, `A40`, `D22`, die Statusregister `2077`, `2106`, `2115`, `2116`, die automatische Delta-T-Regelung, die lokale Durchflussberechnung aus Pumpen-PWM sowie der externe Durchflusspfad über das Hydraulikmodul Unit `0x61`.

Die Firmware wird ausschließlich analysiert und nicht verändert.

## Bewertungsstufen

- **bestätigt** – direkt im untersuchten V3.3-Binary nachgewiesen
- **live bestätigt** – zusätzlich am realen Gerät beobachtet
- **sehr wahrscheinlich** – Datenfluss weitgehend geschlossen, einzelne Herstellerbezeichnung fehlt noch
- **offen** – Bedeutung oder Kopplung noch nicht vollständig geschlossen

---

# 1. Kurzfazit

Die V3.3 besitzt zwei grundsätzlich verschiedene Quellen für den Wasserdurchfluss:

```text
lokaler Pumpenpfad
    Pumpen-PWM-Feedback -> H31-Kennlinie -> Durchfluss

oder bei H30 == 3:
    Hydraulikmodul Unit 0x61 -> Remote-Reg. 2047/2048 -> Durchfluss
```

Wichtige Ergebnisse:

1. `P10=0` aktiviert die automatische Pumpen-PWM-Regelung; `P10>0` ist eine feste Soll-PWM.
2. `P11` ist die Ziel-Wasserspreizung, `P12` die Änderung der PWM je Regelperiode.
3. Die Pumpen-Regelroutine läuft **alle 0,5 s**.
4. `P12` wird im normalen Auto-Pfad **einmal pro 60 s** angewendet.
5. Vor Freigabe der Auto-Regelung existiert eine **10-minütige Durchfluss-Qualifikation**.
6. Der für die Regelung verwendete Durchfluss wird in **5-s-Fenstern** gemittelt.
7. `2115` ist die logische Soll-PWM; `2116` ist die gemessene PWM-Rückmeldung.
8. `2077` ist der wirksame, nach Kennlinie bzw. externem Eingang und Korrektur bestimmte Wasserdurchfluss, `raw/100 m³/h`.
9. `MAIN:1022` ist **kein Reservefeld**, sondern ein **signed Durchfluss-Korrekturoffset** in derselben Einheit wie `2077`.
10. Bei `H30=3` kann ein externes Hydraulikmodul auf dem internen Boardbus einen echten Durchfluss liefern:
    - `HYD61:2047` = Gültigkeits-/Vorhandenflag
    - `HYD61:2048` = Durchfluss, `raw/100 m³/h`
11. Damit ist eine externe Durchflusseinspeisung technisch möglich, aber **nicht über MAIN:2077** und nicht über ein bisher gefundenes normales MAIN-/ENG-Register. Der firmware-native Weg ist die Emulation von Unit `0x61`.
12. Die frühere Hypothese `MAIN:2106 = P12-/Pumpen-Regelzyklus` ist **verworfen**. Die beobachtete 5-Minuten-Pulsfolge bleibt real, gehört aber nicht zur jetzt bytegenau rekonstruierten 60-s-P12-Periode.

---

# 2. Relevante Register

| Register | Parameter / Status | Bedeutung | Bewertung |
|---:|---|---|---|
| `1022` | bisher Reserve | signed Durchfluss-Korrekturoffset, `0,01 m³/h` pro raw | bestätigt |
| `1036` | `H30` | Hydraulikmodul-/Pumpenarchitektur; Wert `3` aktiviert Unit-`0x61`-Pfad | bestätigt |
| `1041` | `H31` | Pumpentyp / Kennlinienauswahl für lokale Durchflussberechnung | bestätigt |
| `1127` | `D22` | Wasserdurchfluss beim Abtauen; wird auch als Mindestdurchflussgrenze benutzt | bestätigt |
| `1205` | `P10` | `0` = Auto-PWM; `>0` = feste Pumpen-PWM | bestätigt |
| `1344` | `A40` | Nenn-Wasserdurchfluss, `raw/100 m³/h` | bestätigt |
| `1432` | `P11` | Ziel-Wasserspreizung, `raw/10 K` | bestätigt |
| `1433` | `P12` | PWM-Anpassung je Regelperiode, Prozentpunkte | bestätigt |
| `2077` | `T39` | wirksamer Wasserdurchfluss, `raw/100 m³/h` | bestätigt |
| `2106` | – | ungeklärtes Kommunikations-/Runtimefeld; 5-min-Puls live beobachtet | offen |
| `2115` | – | aktuell wirksame logische Pumpen-Soll-PWM in % | bestätigt |
| `2116` | – | gemessene Pumpen-PWM-Rückmeldung in % | bestätigt |

Wichtige Live-Strukturen:

```text
0x20016C6C +0x0C -> MAIN:1205 / P10
0x20016278 +0x00 -> MAIN:1432 / P11
0x20016278 +0x01 -> MAIN:1433 / P12
0x20016C7C +0x0C -> MAIN:1022 / Durchfluss-Korrektur
0x20016774 +0x1C -> MAIN:1036 / H30
0x20016774 +0x1E -> MAIN:1041 / H31
0x20016C9C +0x0A -> MAIN:1344 / A40
0x20016F14       -> wirksamer Durchfluss-Runtimewert
```

---

# 3. P10 – feste oder automatische Pumpendrehzahl

## 3.1 P10 > 0

Im normalen Pumpenbetrieb wird P10 als feste logische PWM-Vorgabe verwendet.

```text
P10 = 45
-> normale Soll-PWM ungefähr 45 %
-> MAIN:2115 ungefähr 45
```

Werte oberhalb 100 werden begrenzt. Betriebs-, Start-, Schutz-, Frostschutz- oder Abtaupfade können die feste Vorgabe übersteuern.

## 3.2 P10 = 0

`P10=0` aktiviert den automatischen Pumpenregler. Die zentrale Routine liegt ungefähr bei:

```text
VA 0x08084474
```

Sie verarbeitet mindestens:

- Ist-Wasserspreizung,
- P11,
- P12,
- Kompressor-Sollfrequenz,
- aktuellen/gemittelten Wasserdurchfluss,
- Mindestdurchflussgrenzen,
- Freigabe-/Qualifikationszustände,
- mehrere Schutz-/Overrideflags.

Beim Eintritt bzw. bei gesperrter Auto-Regelung kann die Pumpe mit 100 % gefahren werden.

---

# 4. Exakte Taskperiode: 0,5 s

Die zeitliche Kette wurde vom Taktbaum bis zum Pumpentask rekonstruiert.

```text
HSE = 8 MHz
PLL = x14
SYSCLK = 112 MHz
APB1 = SYSCLK / 2
APB1-Timerclock = 112 MHz
```

TIM6:

```text
PSC = 111
ARR = 499
```

Damit entsteht ein TIM6-IRQ alle:

```text
0,5 ms
```

Über die nachfolgenden Teiler-/Schedulerstufen:

```text
TIM6
 -> 4er-Teiler
 -> 5er-Subdispatcher
 -> 50er-Slotring
 -> Pumpenroutine 0x08084474
```

wird der Pumpen-Regeltask exakt alle:

```text
0,5 s
```

aufgerufen.

Damit können interne Zähler direkt zeitlich interpretiert werden:

```text
10 Zyklen   = 5 s
120 Zyklen  = 60 s
1200 Zyklen = 10 min
```

**Bewertung: bestätigt.**

---

# 5. P12-Regelperiode = 60 Sekunden

Die Firmware besitzt im Auto-PWM-Pfad einen 120er-Zähler. Da der Pumpentask alle 0,5 s läuft:

```text
120 x 0,5 s = 60 s
```

Damit bedeutet die Herstellerbeschreibung von P12:

> `Pump Speed Adjust Range for Each Period`

in diesem Build konkret:

> **Änderung der Pumpen-PWM je 60-s-Regelperiode.**

Die frühere Vermutung, P12 würde nur etwa alle fünf Minuten angewendet, ist damit widerlegt.

---

# 6. P11/P12 – Delta-T-Regelgesetz

P11 ist die Ziel-Wasserspreizung:

```text
P11 raw / 10 = K
```

P12 ist die PWM-Schrittweite in Prozentpunkten.

Sinngemäß:

```text
Fehler = Ist-Spreizung - P11
```

Die Firmware staffelt die Korrektur:

| Ist-Spreizung relativ zu P11 | PWM-Korrektur |
|---|---:|
| `>= P11 + 3,0 K` | `+ 2 x P12` |
| `>= P11 + 1,0 K` | `+ P12` |
| ungefähr innerhalb `±1 K` | keine Delta-T-Korrektur |
| `<= P11 - 1,0 K` | `- P12` |
| `<= P11 - 3,0 K` | `- 2 x P12` |

Hydraulisch:

```text
Delta-T zu groß -> Volumenstrom erhöhen -> PWM erhöhen
Delta-T zu klein -> Volumenstrom reduzieren -> PWM reduzieren
```

Beispiel:

```text
P11 = 44 -> 4,4 K
P12 = 2

>= 7,4 K -> +4 %-Punkte
>= 5,4 K -> +2 %-Punkte
ca. 3,5...5,3 K -> keine Delta-T-Korrektur
<= 3,4 K -> -2 %-Punkte
<= 1,4 K -> -4 %-Punkte
```

**Bewertung: bestätigt.**

---

# 7. Feed-Forward über Kompressor-Sollfrequenz

Zusätzlich zum Delta-T-Regler reagiert die Pumpenregelung auf Änderungen der Kompressor-Sollfrequenz, also derselben Regelgröße, die öffentlich als MAIN:2071 erscheint.

Bei einer Änderung von ungefähr mindestens 6 Hz:

```text
Kompressor-Soll steigt >= ca. 6 Hz -> zusätzlich +P12
Kompressor-Soll fällt  >= ca. 6 Hz -> zusätzlich -P12
```

Damit besitzt die Pumpenregelung eine Vorsteuerung auf Leistungsänderungen des Verdichters.

**Bewertung: bestätigt.**

---

# 8. 5-s-Durchflussmittel

Der Pumpenregler sammelt 10 Durchflusswerte. Bei 0,5-s-Taskperiode ergibt sich:

```text
10 x 0,5 s = 5 s
```

Der Auto-Regler arbeitet damit nicht nur mit einem einzelnen Momentanwert, sondern mit einem intern über etwa fünf Sekunden gebildeten Durchflusswert.

**Bewertung: bestätigt.**

---

# 9. 10-minütige Auto-PWM-Qualifikation

Vor Freigabe der eigentlichen automatischen Drehzahlabsenkung/-regelung existiert ein 1200er-Zähler:

```text
1200 x 0,5 s = 600 s = 10 min
```

Die Qualifikation läuft nur weiter, solange ein ausreichend hoher Durchfluss vorliegt. Die Schwelle wird aus A40 gebildet und entspricht ungefähr:

```text
Ist-Durchfluss >= 1,2 x A40
```

Erst nach dieser etwa zehnminütigen stabilen Phase darf der normale Auto-PWM-Pfad vollständig arbeiten.

Das passt zur bereits beobachteten Anlagenlogik, dass die variable Pumpenregelung nicht unmittelbar nach Verdichterstart aktiv wird.

**Bewertung: bestätigt für Zähler, Zeitbasis und A40-Faktor.**

---

# 10. Mindestdurchflussgrenze: D22 oder 0,8 x A40

Für die Sperre gegen weiteres Herunterregeln benutzt die Firmware folgende Priorität:

```text
wenn D22 != 0:
    Mindestdurchfluss = D22
sonst:
    Mindestdurchfluss ~= 0,8 x A40
```

Wenn der aktuelle bzw. gemittelte Durchfluss diese Grenze erreicht oder unterschreitet:

```text
positive PWM-Korrektur -> weiterhin erlaubt
negative PWM-Korrektur -> gesperrt
```

Dadurch kann der Delta-T-Regler den Volumenstrom nicht beliebig weit reduzieren.

`MAIN:1127 / D22` ist somit nicht nur für Abtauung relevant, sondern wird in V3.3 auch als explizite Durchfluss-Untergrenze im Pumpenregler genutzt.

**Bewertung: bestätigt.**

---

# 11. Weitere Auto-Regel-Gates und 100-%-Overrides

Die Auto-Regelung besitzt mehrere zusätzliche Freigaben und Schutzpfade.

## 11.1 Temperatur-Richtungsprüfung

Die Firmware überwacht über ungefähr 30 s, ob die Wasserspreizung zur jeweiligen Betriebsart in der erwarteten Richtung liegt. Bleibt die Temperaturdifferenz unplausibel, wird die normale Auto-PWM-Regelung gesperrt bzw. die Pumpe auf 100 % gezwungen.

## 11.2 Außentemperatur-Hysterese

Ein weiterer Betriebszweig verwendet T04/Außentemperatur mit einer Hysterese um:

```text
20 °C / 22 °C
```

In diesem spezifischen Runtime-Zustand kann das Hysterese-Flag den Auto-PWM-Pfad sperren und 100 % erzwingen.

## 11.3 Weitere Flags

Zusätzlich existieren weitere Betriebs-/Schutzflags, die eine normale Auto-Regelung verhindern und 100 % Pumpenleistung erzwingen können. Der Datenfluss ist sichtbar; die Herstellersemantik aller beteiligten Flags ist noch nicht vollständig benannt.

Daher gilt diagnostisch:

```text
P10 = 0
und MAIN:2115 = 100
```

ist kein Widerspruch. Es bedeutet, dass die Auto-Regelung momentan noch nicht freigegeben oder durch einen Override übersteuert ist.

---

# 12. Grenzen des normalen Auto-Reglers

Wenn der normale Auto-Regelpfad freigegeben ist, wird die berechnete PWM ungefähr auf folgenden Bereich begrenzt:

```text
Minimum = 16 %
Maximum = 92 %
```

100 % stammt damit normalerweise aus Start-/Qualifikations-/Schutz-/Overridepfaden und nicht aus dem normalen Endclamp des Delta-T-Reglers.

**Bewertung: bestätigt.**

---

# 13. MAIN:2115 – Soll-PWM

MAIN:2115 repräsentiert die aktuell wirksame **logische Pumpen-Sollvorgabe in Prozent**.

```text
P10 fest
oder
Auto-Regler
oder
Override
    -> Runtime Soll-PWM
    -> MAIN:2115
    -> Hardware-PWM
```

Vor Ausgabe auf den Timer wird die logische Pumpenleistung invertiert:

```text
Hardware_PWM = (100 - logische_Pumpenleistung) x 10
```

MAIN:2115 ist also bewusst die für Bedienung/Diagnose sinnvolle Pumpenleistung und nicht das rohe elektrische Duty-Cycle-Register.

**Bewertung: bestätigt.**

---

# 14. MAIN:2116 – Pumpen-PWM-Rückmeldung

Die Firmware misst die Pumpen-Rückmeldeleitung per Timer Input Capture und bildet aus zwei Capture-Werten ein Tastverhältnis.

Sinngemäß:

```text
feedback = Capture_A / Capture_B
MAIN:2116 = int(feedback x 100)
```

Damit gilt:

> MAIN:2116 ist die gemessene PWM-Rückmeldung der Pumpe in %, nicht rpm und nicht die Soll-PWM.

**Bewertung: bestätigt.**

---

# 15. Feedback >= 85 % – für Durchfluss ungültig

Die Firmware prüft die gemessene PWM-Rückmeldung vor der lokalen Durchflussberechnung.

Bei:

```text
2116 >= 85 %
```

wird die Rückmeldung für die Durchflusskennlinie als ungültig behandelt und der lokal daraus berechnete Durchfluss auf 0 gesetzt.

Wichtig:

- MAIN:2116 kann den gemessenen hohen Wert weiterhin anzeigen.
- Nur die daraus abgeleitete Durchflussberechnung wird verworfen.

**Bewertung: bestätigt.**

---

# 16. H31 – lokale Pumpenkennlinien

| H31 | Typ | Kennlinienfaktor | max. lokaler Durchfluss |
|---:|---|---:|---:|
| 0 | keine Durchflusserkennung | 0 | 0 |
| 1 | Grundfos 25-75 | ca. `0,0300` | 2,10 m³/h |
| 2 | Grundfos 25-105 | ca. `0,0570` | 4,00 m³/h |
| 3 | Grundfos 25-125 | ca. `0,0570` | 4,00 m³/h |
| 4 | Shimge APM25 9-130 | ca. `0,0646`, Sonderkennlinie | 4,50 m³/h |
| 5 | Shimge APM25 12-130 | ca. `0,0570` | 4,00 m³/h |

Für H31 1/2/3/5 gilt im Wesentlichen:

```text
Q[m³/h] ~= Faktor x Feedback[%]
```

Für H31=4 existiert ein Sonderpfad mit ungefähr 5-%-Offset:

```text
Feedback <= ca. 5 % -> Q = 0
Q[m³/h] ~= 0,0646 x (Feedback[%] - 5)
```

Danach greift im lokalen Pfad der pumpenspezifische Maximalwert.

---

# 17. MAIN:1022 – signed Durchfluss-Korrekturoffset

MAIN:1022 war in älteren Registerdaten als Reserve geführt. V3.3 benutzt es jedoch direkt in der Durchflussberechnung.

Live-RAM:

```text
MAIN:1022 -> 0x20016C7C + 0x0C
```

Die Firmware liest es als **signed 16 bit** und addiert es auf den bereits vorhandenen Basisdurchfluss.

Sinngemäß:

```text
wenn base_flow == 0:
    effective_flow = 0
sonst:
    tmp = base_flow + signed(MAIN:1022)
    wenn tmp < 1:
        effective_flow = 0
    sonst:
        effective_flow = tmp
```

Die Einheit ist dieselbe wie MAIN:2077:

```text
1 raw = 0,01 m³/h
```

Beispiele:

```text
1022 = +10  -> +0,10 m³/h
1022 = -10  -> -0,10 m³/h
1022 = +100 -> +1,00 m³/h
```

Der Offset wird sowohl beim lokalen H31/PWM-Pfad als auch beim externen H30=3-Pfad angewendet.

Besonderheiten:

- Bei Basisdurchfluss 0 wird der Offset nicht verwendet; 1022 kann alleine keinen Durchfluss erzeugen.
- Im lokalen H31-Pfad erfolgt danach weiterhin die pumpenspezifische Maximalbegrenzung.
- Im externen H30=3-Pfad wird nicht durch die lokale H31-Qmax-Tabelle begrenzt.

MAIN:1022 liegt im normalen öffentlichen Parameterbereich und ist über den direkten Mainboard-Modbus per FC06/FC10 beschreibbar. Es ist damit praktisch als Kalibrierparameter nutzbar.

**Nicht als schnelle Telemetrieeinspeisung verwenden:** Das Persistenz-/Write-Endurance-Verhalten häufiger 1022-Writes ist noch nicht endgültig geschlossen. Außerdem ist 1022 nur ein Offset auf einen bereits gültigen Basisdurchfluss.

**Bewertung: Funktion und Rechenweg bestätigt; NVRAM-Persistenz bei häufigen Writes offen.**

---

# 18. Externer Durchfluss bei H30 = 3

Die Durchflussroutine besitzt einen echten alternativen Datenpfad.

Entscheidung ungefähr bei VA `0x08061820`:

```text
wenn H30 == 3
und external_valid != 0:
    base_flow = external_flow
sonst:
    base_flow = lokale H31/PWM-Berechnung
```

Runtimefelder:

```text
0x20015C68 + 0x108 -> external_valid
0x20015C68 + 0x10C -> external_flow
```

Der externe Wert wird anschließend als Basis für MAIN:2077 verwendet und erhält ebenfalls die MAIN:1022-Korrektur.

**Bewertung: bestätigt.**

---

# 19. Quelle des externen Werts: Hydraulikmodul Unit 0x61

Die beiden Felder werden nicht von einem normalen MAIN-/ENG-Register geschrieben. Ihr Writer ist der RX-Parser des internen Hydraulikmodul-Dialogs.

Bei H30=3 pollt das Mainboard auf dem internen USART3-Boardbus:

```text
Slave: 0x61
FC:    03
Start: 2001
Qty:   90
```

Der Modbus-Payload beginnt im internen RX-Abbild nach einem Header. Unter Berücksichtigung dieses Headers ergibt die bytegenaue Zuordnung:

```text
HYD61:2047 -> 0x20015C68+0x108 -> external_valid
HYD61:2048 -> 0x20015C68+0x10C -> external_flow
```

Damit:

| Namespace | Register | Funktion | Skalierung |
|---|---:|---|---|
| `HYD61` | `2047` | Gültigkeits-/Vorhandenflag für externen Durchfluss | `0` ungültig, `!=0` gültig |
| `HYD61` | `2048` | externer Wasserdurchfluss | `raw/100 m³/h` |

Die offizielle Herstellerbezeichnung von HYD61:2047 ist noch unbekannt; seine Wirkung als Gate des externen Durchflusswerts ist jedoch direkt im Binary bestätigt.

---

# 20. Kann man einen extern gemessenen Durchfluss einspeisen?

## 20.1 Firmware-native Antwort: ja

Technisch kann ein externer Teilnehmer den Durchfluss liefern, wenn er das von der Firmware erwartete Hydraulikmodul emuliert.

Minimal für den eigentlichen Durchflussdatenpfad:

```text
H30 = 3

Mainboard -> Slave 0x61:
FC03 2001 qty90

Antwort:
HYD61:2047 != 0
HYD61:2048 = gewünschter_Durchfluss_m3h x 100
```

Beispiel:

```text
externer Sensor = 0,64 m³/h
HYD61:2048 = 64
```

Dann verwendet die Mainboard-Durchflussroutine diesen Wert anstelle der lokalen H31/PWM-Kennlinie.

## 20.2 Aber: H30=3 ist kein reiner „External Flow“-Schalter

H30=3 schaltet die gesamte Hydraulikmodularchitektur um. Der interne Scheduler verwendet dann Unit `0x61` statt des normalen lokalen/anderen Hydraulikpfads:

```text
RX: Slave 0x61 / FC03 / 2001 / 90 Wörter
TX: Slave 0x61 / FC10 / 1001 / 90 Wörter
```

Zahlreiche weitere Runtime-/Sensor-/I/O-Helper lesen bei H30=3 Werte aus derselben externen Struktur `0x20015C68`, unter anderem Felder bei:

```text
+0x1C
+0x24
+0x28
+0x6A
+0x70
+0x76
+0x7C
+0x82
+0x88
...
```

Daher wäre es riskant, auf einer realen Anlage einfach H30=3 zu setzen und nur HYD61:2047/2048 zu beantworten. Andere erwartete Hydraulikwerte könnten sonst fehlen oder 0 werden.

Für eine saubere externe Durchflussquelle müsste ein Emulator den **minimal erforderlichen Unit-0x61-Datensatz für die konkrete Anlagenkonfiguration** vollständig bereitstellen.

## 20.3 Kein direkter MAIN:2077-Write

MAIN:2077 ist ein Statuswert. Im normalen Mainboard-Modbus ist kein Schreibpfad gefunden, der einen externen Messwert direkt in den autoritativen Runtimewert `0x20016F14` setzt.

Ebenfalls wurde bisher kein ENG:CTRL-/ENG:A-Register gefunden, dessen Laufzeitverbraucher direkt `0x20015C68+0x10C` beschreibt.

Aktueller Stand:

```text
normaler MAIN-Modbus -> kein echter externer Durchfluss-Setpoint gefunden
ENG/CTRL             -> kein echter externer Durchfluss-Setpoint gefunden
interner HYD61-Bus   -> echter externer Durchflussweg bestätigt
```

---

# 21. MAIN:1022 als theoretischer Workaround

Da MAIN:1022 normal beschreibbar ist, könnte man theoretisch dynamisch rechnen:

```text
1022 = gewünschter_Durchfluss - lokaler_Basisdurchfluss
```

Das wäre jedoch **kein sauberer virtueller Durchflusseingang**:

- funktioniert nur, wenn der Basisdurchfluss ungleich 0 ist,
- ist ein globaler Kalibrier-/Korrekturwert,
- beeinflusst alle nachgelagerten Funktionen, die den effektiven Durchfluss verwenden,
- unterliegt im lokalen Pfad der H31-Qmax-Begrenzung,
- Persistenz und EEPROM-/Flash-Schreibbelastung häufiger Writes sind noch nicht abschließend geklärt.

Daher ist HYD61-Emulation der technisch saubere Firmwareweg für eine echte externe Messwertquelle.

---

# 22. MAIN:2106 – Korrektur der früheren Hypothese

Live wurde am 15.07.2026 im Kühlbetrieb beobachtet:

```text
MAIN:2106 pulst ungefähr alle 5 min von 0 auf 1
und fällt nach etwa 9...11 s wieder auf 0.
MAIN:2115 blieb dabei stabil.
```

Die tiefere Binaryanalyse zeigt jedoch:

1. Der zentrale Mainboard-Statusbuilder erzeugt 2106 und 2107 nicht wie die benachbarten Statuswerte.
2. DWIN nutzt `0x083B = MAIN:2107` explizit als Kommunikations-/Handshakevariable `0x5AA5`.
3. Für `0x083A = MAIN:2106` wurde im DWIN-Code kein direkter Pumpenregelverbraucher gefunden.
4. Die echte P12-Regelperiode ist durch Scheduler und 120er-Zähler auf **60 s** geschlossen.

Damit ist die frühere Bezeichnung:

```text
2106 = Pumpenregel-/PWM-Regelzyklusflag
```

nicht haltbar.

Aktuelle Klassifikation:

> **MAIN:2106 = ungeklärtes Kommunikations-/Runtimefeld. Die ca. 5-minütige Pulsfolge ist live bestätigt, ihre Ursache aber noch offen. Nicht als P12-Regelperiode verwenden.**

---

# 23. Gesamtdatenfluss

```text
                          H30
                           |
             +-------------+-------------+
             |                           |
          H30 != 3                    H30 == 3
             |                           |
             v                           v
       PWM Feedback                  HYD61:2047
             |                       valid != 0 ?
             v                           |
          2116 [%]                       v
             |                       HYD61:2048
             v                       raw/100 m³/h
       H31 Kennlinie                     |
             |                           |
             +-------------+-------------+
                           |
                           v
                    Basisdurchfluss
                           |
                           v
                  + signed MAIN:1022
                           |
                           v
                  wirksamer Durchfluss
                           |
                           +----> MAIN:2077
                           |
                           +----> 5-s-Mittel
                                   |
                                   +--> 10-min-Qualifikation
                                   +--> Mindestdurchfluss-Gates
                                   +--> Auto-PWM-Regler
                                            |
                                   P11/P12 + Frequenz-Feedforward
                                            |
                                            v
                                      MAIN:2115
                                            |
                                            v
                                      Pumpen-PWM
```

---

# 24. Sicherheits- und Testhinweise

Für spätere Live-Tests sind die Varianten unterschiedlich zu bewerten:

### MAIN:1022 statisch ändern

Technisch einfach und über normalen Modbus möglich. Sinnvoll für eine vorsichtige Kalibrierprüfung. Vorher aktuellen Wert sichern und nur kleine Offsets verwenden. Nicht als schnelle Telemetriequelle benutzen, solange die Persistenz nicht geschlossen ist.

### H30=3 ohne Unit-0x61-Emulator

Nicht empfohlen. Die Firmware erwartet dann ein komplettes Hydraulikmodul und bezieht mehrere weitere Werte aus dessen Struktur.

### H30=3 mit vollständigem Unit-0x61-Emulator

Technisch der korrekte Firmwareweg, um einen extern gemessenen Wasserdurchfluss einzuspeisen. Vor einem Test muss zuerst der für die konkrete FoxAir-Konfiguration notwendige Mindestumfang der 90 RX-/TX-Wörter kartiert werden.

---

# 25. Offene Restpunkte

1. Offizielle Herstellerbezeichnung von `HYD61:2047`.
2. Vollständige Semantik aller für H30=3 benötigten HYD61-Wörter.
3. Minimaler sicherer Antwortdatensatz für einen Unit-0x61-Emulator.
4. NVRAM-/EEPROM-Persistenz und Schreibendurance von häufigen MAIN:1022-Änderungen.
5. Tatsächliche Semantik von MAIN:2106.
6. Herstellerbezeichnungen einiger 100-%-Overrideflags im Auto-PWM-Pfad.

Die zentralen Fragen `P12-Periode`, `MAIN:1022`, `H30=3`, `HYD61:2047/2048` und der echte externe Durchflussdatenpfad sind dagegen in V3.3 strukturell geschlossen.
