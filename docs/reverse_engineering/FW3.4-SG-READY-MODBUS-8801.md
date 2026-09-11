# Mainboard-Firmware V3.4 – SG Ready / PV-Steuerung über Modbus Register 8801

Stand: 11. September 2026

Dieses Dokument ist die aktuelle Referenz für die SG-Ready-/PV-Logik der Mainboard-Firmware `82400644 / V3.4`.

Es führt zwei getrennte virtuelle Steuerpfade zusammen:

1. den bereits unter V3.3 statisch und am realen Gerät bestätigten klassischen SG-Ready-Modbuspfad mit `MAIN:1334 / SG01 = 3`,
2. den in V3.4 rekonstruierten neuen 3-stufigen PV-Pfad mit `MAIN:1334 / SG01 = 7`.

Wichtig für die Beweislage:

- Die Live-Tests des klassischen `SG01=3`-Pfads stammen vom 24.08.2026 unter V3.3.
- Der neue `SG01=7`-Pfad wurde aus V3.4 statisch rekonstruiert.
- Am 11.09.2026 wurden unter V3.4 `SG01=7` mit `8801=1` (Low PV) und `8801=2` (Neutral) am realen Gerät erfolgreich getestet.
- `SG01=7` mit `8801=3` (High PV) ist noch nicht live getestet; der statische Codepfad spricht jedoch dafür, dass auch dieser Zustand vorhanden ist.
- Bei Änderungen von `MAIN:1336 / SG03` im aktiven Low-PV-Zustand wurde live eine leichte Reaktionsverzögerung beobachtet. Diese ist noch nicht zeitlich vermessen.
- Die statische V3.4-Analyse zeigt für reine `1336`-Änderungen keinen 10-Minuten-State-Hold; die beobachtete kurze Verzögerung ist daher getrennt von der klassischen 10-Minuten-Umschaltsperre zu behandeln.
- Für Zustandswechsel innerhalb des neuen State-6/7/8-Pfads ist noch nicht abschließend bestätigt, ob derselbe feste 10-Minuten-Hold wie beim klassischen State-1/2/3/4-Pfad gilt.

---

# 1. Kurzfazit

## Klassischer virtueller SG-Ready-Pfad

```text
MAIN:1334 / SG01 = 3
        ↓
ENG:CTRL:8801 = 1..4
        ↓
virtuelle SG-Kontaktkombination
        ↓
klassische SG-Ready-State-Machine
        ↓
MAIN:2133 = tatsächlich aktiver SG-Modus 1..4
```

Dieser Pfad ist aus V3.3 vollständig geschlossen und live bestätigt.

## Neuer V3.4-PV-Pfad

```text
MAIN:1334 / SG01 = 7
        ↓
ENG:CTRL:8801 = 1..3
        ↓
interne States 6 / 7 / 8
        ↓
Low PV / Neutral / High PV
        ↓
MAIN:2133 = 1 / 2 / 3
```

Der neue Pfad bildet damit nicht vier klassische SG-Kontaktzustände nach, sondern bietet eine kompakte 3-stufige PV-Führung.

| `SG01 / 1334` | `8801` | interner State | `MAIN:2133` | Bedeutung | Status |
|---:|---:|---:|---:|---|---|
| 7 | 1 | 6 | 1 | Low PV / Leistungsbegrenzung | **live bestätigt 11.09.2026** |
| 7 | 2 | 7 | 2 | Neutral / Normalregelung | **live bestätigt 11.09.2026** |
| 7 | 3 | 8 | 3 | High PV / Sollwertverschiebungen | **statisch rekonstruiert, Live-Test offen** |

---

# 2. Relevante Register

| Register | Name | Rolle |
|---:|---|---|
| `1334` | `SG01` | Auswahl des SG-/PV-Quellpfads |
| `1335` | `SG02` | klassische Mode-1-Schlafzeit |
| `1336` | `SG03` | Leistungswert; im neuen Low-PV-Pfad wirksam |
| `1337` | `SG04` | klassischer SG-Parameter; für den neuen `SG01=7`-Pfad bisher nicht als wirksam nachgewiesen |
| `1338` | `SG05` | High-PV-Offset Warmwasser |
| `1339` | `SG06` | High-PV-Offset Heizen |
| `1340` | `SG07` | High-PV-Offset Kühlen |
| `1341` | `SG08` | weiterer klassischer SG-Parameter / Zusatzfunktion |
| `2034` | Statusbits | physische SG-Hardwareeingänge; Bits 12/13 |
| `2133` | SG-Status | tatsächlich aktiver bzw. nach außen gemeldeter SG-/PV-Zustand |
| `8801` | `ENG:CTRL` | virtueller SG-/PV-Sollzustand über direkten User-/Mainboard-Modbus |

Der SG-Parameterblock liegt bereits in V3.3 zusammen bei `1334–1341`. Die neue V3.4-Logik nutzt dieselben Parameter, wertet sie im `SG01=7`-Pfad aber anders bzw. gezielter aus.

---

# 3. SG01 / MAIN:1334 – bekannte Auswahlwerte

Aus dem bisherigen Reverse Engineering sind folgende Werte funktional bekannt:

```text
1334 = 0  SG deaktiviert
1334 = 1  1-Kontakt-Modus
1334 = 2  2 physische SG-Kontakte
1334 = 3  klassischer virtueller SG-Ready-Modus über 8801
1334 = 7  neuer V3.4 3-Stufen-PV-Modus über 8801
```

`1334=7` ist inzwischen nicht mehr nur ein statischer Firmwarebefund: Der Pfad wurde am 11.09.2026 mit `8801=1` und `8801=2` am realen Gerät erfolgreich benutzt.

Die Werte zwischen `3` und `7` sind damit nicht automatisch frei oder bedeutungslos; sie sind in diesem Dokument lediglich nicht als Teil der beiden untersuchten virtuellen Pfade klassifiziert.

---

# 4. Klassischer virtueller Modbuspfad: SG01 = 3

Der klassische Pfad wurde in V3.3 bytegenau rekonstruiert und am realen Gerät funktional getestet.

```text
MAIN:1334 = 3
```

schaltet die Quelle auf den virtuellen Engineering-Eingang:

```text
ENG:CTRL:8801
```

## Mapping

| `8801` | virtueller Kontakt A | virtueller Kontakt B | Firmware-SG-Modus | `2133` |
|---:|---:|---:|---|---:|
| 1 | 1 | 0 | Mode 1 / Schlafmodus | 1 |
| 2 | 0 | 0 | Mode 2 / wenig PV / Normalzustand | 2 |
| 3 | 0 | 1 | Mode 3 / mittel PV | 3 |
| 4 | 1 | 1 | Mode 4 / High PV | 4 |

Für diesen klassischen Pfad gilt aus V3.3:

```text
8801 = 1 -> A=1, B=0
8801 = 2 -> A=0, B=0
8801 = 3 -> A=0, B=1
8801 = 4 -> A=1, B=1
```

`8801 = 0` erzeugt dort keinen gültigen virtuellen SG-Zustand. Werte `>=5` wurden für diesen klassischen V3.3-Pfad nicht als gültiger SG-Zustand akzeptiert.

---

# 5. Klassischer Pfad – Bedeutung der vier Modi

Die vorhandenen SG-Parameter passen beim klassischen Pfad zu den vier Firmwarezuständen:

```text
1335 SG02 -> Mode 1 Schlafmodus-Zeit
1336 SG03 -> Mode 2 Leistungswert
1337 SG04 -> Mode 3 Leistungswert
1338–1341 -> Mode 4 Sollwertanhebungen / Zusatzfunktionen
```

Praktische Interpretation:

```text
Mode 1 -> Schlaf-/Sperrzustand
Mode 2 -> Normalzustand / wenig PV
Mode 3 -> erhöhte Aufnahme / mittel PV
Mode 4 -> High PV / starke Anforderung
```

Live unter V3.3 beobachtet:

```text
8801 = 1
1334 = 3
→ effektiver Mode 1
→ WP im Schlafmodus
→ WP startet nicht
```

und:

```text
8801 = 4
1334 = 3
→ effektiver Mode 4
→ WP startet
→ erwartete High-Power-Reaktion
```

---

# 6. Neuer V3.4-Pfad: SG01 = 7

V3.4 enthält einen zusätzlichen expliziten Pfad für:

```text
MAIN:1334 / SG01 = 7
```

Dieser Pfad benutzt ebenfalls `ENG:CTRL:8801`, interpretiert dessen Werte aber nicht als die vier klassischen SG-Ready-Kontaktkombinationen.

Statisch rekonstruiert gilt:

```text
8801 = 1 -> interner State 6 -> Low PV
8801 = 2 -> interner State 7 -> Neutral
8801 = 3 -> interner State 8 -> High PV
```

Die internen States `6/7/8` werden nach außen nicht direkt ausgegeben. Für `MAIN:2133` erfolgt eine Rückabbildung auf:

```text
State 6 -> 2133 = 1
State 7 -> 2133 = 2
State 8 -> 2133 = 3
```

Sinngemäß entspricht dies einer Ausgabe `internal_state - 5`.

## Live-Verifikation 11.09.2026

Am realen Gerät mit Firmware V3.4 erfolgreich getestet:

```text
1334 = 7
8801 = 1
→ Low-PV-Pfad funktioniert

1334 = 7
8801 = 2
→ Neutral-/Normalpfad funktioniert
```

Noch offen:

```text
1334 = 7
8801 = 3
→ High PV / State 8
```

Der State-8-Codepfad ist statisch vorhanden; die reale Wirkung ist noch nicht bestätigt.

---

# 7. State 6 / 8801 = 1 – Low PV

Bei:

```text
1334 = 7
8801 = 1
```

wird intern State `6` gewählt.

Die V3.4-Regellogik verwendet in diesem Zustand:

```text
MAIN:1336 / SG03
```

als Leistungsbegrenzungswert.

Praktische Bedeutung:

```text
wenig PV verfügbar
→ WP darf grundsätzlich weiterarbeiten
→ Leistungsaufnahme / Leistungsanforderung wird über SG03 begrenzt
→ keine High-PV-Temperaturaufschläge
```

Wichtig: Dieser Zustand ist damit funktional etwas anderes als der klassische Mode-1-Schlaf-/Sperrzustand des `SG01=3`-Pfads, obwohl `MAIN:2133` nach außen den Wert `1` meldet.

## Live-Status

`1334=7` mit `8801=1` wurde am 11.09.2026 erfolgreich am realen Gerät getestet.

Bei Änderungen von `1336 / SG03` innerhalb des bereits aktiven Low-PV-Zustands wurde eine **leichte Reaktionsverzögerung** der tatsächlichen Wirkung beobachtet.

Noch offen sind insbesondere:

- exakte Einheit/Skalierung von `SG03`,
- quantitative Beziehung zu Verdichterfrequenz bzw. Leistungsaufnahme,
- genaue Dauer der beobachteten kurzen Reaktionsverzögerung,
- welcher nachgelagerte Regler die Verzögerung verursacht.

---

# 8. State 7 / 8801 = 2 – Neutral

Bei:

```text
1334 = 7
8801 = 2
```

wird intern State `7` gewählt.

Dieser Zustand verhält sich nach der statischen Analyse als neutraler Bypass-/Normalzustand:

```text
keine SG-Leistungsbegrenzung
keine SG-Temperaturverschiebung
normale WP-Regelung nach den regulären Sollwerten
```

Damit eignet sich `8801=2` im neuen Pfad als Mittelstellung zwischen Low- und High-PV.

**Live bestätigt am 11.09.2026:** `1334=7` mit `8801=2` funktioniert am realen Gerät als Neutral-/Normalpfad.

---

# 9. State 8 / 8801 = 3 – High PV

Bei:

```text
1334 = 7
8801 = 3
```

wird intern State `8` gewählt.

In diesem Zustand aktiviert V3.4 gezielt die SG-Sollwertverschiebungen:

```text
1338 / SG05 -> Warmwasser-Sollwert anheben
1339 / SG06 -> Heizungs-Sollwert anheben
1340 / SG07 -> Kühl-Sollwert absenken
```

Sinngemäß:

```text
WW_effektiv      = WW_normal      + SG05
Heizen_effektiv  = Heizen_normal  + SG06
Kühlen_effektiv  = Kühlen_normal  - SG07
```

Das ältere Display-/DWIN-Changelog passt dazu: Für `SG05`, `SG06` und `SG07` wurde der zulässige Bereich auf `25` erweitert.

`SG04 / MAIN:1337` wurde bei der bisherigen statischen Verfolgung des neuen State-6/7/8-Pfads nicht als wirksamer Parameter identifiziert.

**Bewertung: V3.4 statisch rekonstruiert; Live-Test von `8801=3` steht noch aus.**

---

# 10. Warum der neue Pfad für PV-Regelungen interessant ist

Der neue `SG01=7`-Pfad reduziert die externe Steuerung auf drei semantisch klare Zustände:

```text
PV knapp:
8801 = 1
→ interne Leistungsbegrenzung über SG03

Normal:
8801 = 2
→ normale WP-Regelung

PV-Überschuss:
8801 = 3
→ WW-/Heiz-Sollwert anheben bzw. Kühl-Sollwert absenken
```

Damit kann eine externe Steuerung wie Node-RED die Wärmepumpe grob nach verfügbarer PV-Leistung führen, ohne laufend die normalen Heizungs- oder Warmwasser-Sollwerte selbst zu überschreiben.

Für den Low-PV-Zustand ist besonders interessant, dass `1336 / SG03` innerhalb desselben Zustands verändert werden kann. Nach der statischen Analyse ist eine solche Parameteränderung nicht an den klassischen 10-Minuten-State-Hold gekoppelt. Im Live-Test wurde jedoch eine kurze Wirkungslatenz beobachtet, die bei dynamischer Nachführung berücksichtigt werden muss.

Die internen Schutz-, Betriebs- und Sollwertlogiken der Wärmepumpe bleiben dabei grundsätzlich im Regelpfad.

---

# 11. MAIN:2133 als Rückmeldung

Für den klassischen `SG01=3`-Pfad ist `MAIN:2133` als tatsächlich aktiver SG-Modus bestätigt:

| `2133` | klassischer Pfad |
|---:|---|
| 0 | WP aus oder SG deaktiviert |
| 1 | Mode 1 / Schlafmodus |
| 2 | Mode 2 / wenig PV |
| 3 | Mode 3 / mittel PV |
| 4 | Mode 4 / High PV |

Für den neuen `SG01=7`-Pfad ergibt die V3.4-Analyse:

| interner State | `2133` | neue Bedeutung | Live-Status |
|---:|---:|---|---|
| 6 | 1 | Low PV | **bestätigt** |
| 7 | 2 | Neutral | **bestätigt** |
| 8 | 3 | High PV | **offen** |

Damit ist `2133` kontextabhängig zu interpretieren. `2133=1` bedeutet bei `SG01=3` Schlafmodus, bei `SG01=7` dagegen Low-PV-Leistungsbegrenzung.

Für externe Steuerungen sollten deshalb immer beide Register gemeinsam betrachtet werden:

```text
1334 = ausgewählter SG-/PV-Pfad
8801 = gewünschter Zustand
2133 = tatsächlich gemeldeter Zustand
```

---

# 12. Fester 10-Minuten-Hold – klassischer Pfad

Für den klassischen V3.3-Pfad ist ein fester 10-Minuten-Umschalttimer codebasiert und live konsistent bestätigt.

Bei jeder akzeptierten Mode-Umschaltung wird intern:

```text
1200
```

in den Hold-Timer geschrieben.

Die SG-Routine läuft im klassischen Pfad mit 0,5-s-Zyklen:

```text
1200 × 0,5 s = 600 s = 10 Minuten
```

Solange der Timer größer Null ist:

```text
Timer--
keine neue SG-Modusübernahme
```

`8801` kann währenddessen bereits einen neuen Wert enthalten; `MAIN:2133` bleibt bis zur erlaubten Übernahme auf dem alten Zustand.

---

# 13. Änderung von MAIN:1334 setzt den klassischen Hold zurück

Unter V3.3 live bestätigt:

```text
wenn SG-Quelle geändert:
    previous_source = new_source
    hold_timer = 0
    interne Übergangszustände zurücksetzen
```

Diagnosebeispiel für den klassischen Pfad:

```text
8801 = gewünschter Zustand
1334 = 0
1334 = 3
```

Danach kann der aktuelle `8801`-Wert sofort neu angenommen werden und startet anschließend wieder einen neuen Hold.

Dieser Mechanismus sollte nicht als Trick für schnelle normale Regelung missbraucht werden.

---

# 14. Verzögerungen im neuen SG01=7-Pfad

Beim neuen V3.4-Pfad müssen zwei Arten von Änderungen klar getrennt werden:

## 14.1 Änderung der Stufe über 8801

Beispiele:

```text
8801: 1 -> 2   Low PV -> Neutral
8801: 2 -> 3   Neutral -> High PV
8801: 3 -> 1   High PV -> Low PV
```

Für diese State-Wechsel ist derzeit noch nicht abschließend bestätigt, ob:

```text
- derselbe 10-Minuten-Hold wie beim klassischen Pfad gilt,
- ein anderer Timer gilt,
- oder die drei PV-Stufen ohne diesen klassischen Hold übernommen werden.
```

`8801=1` und `8801=2` sind als Zustände live bestätigt; die genaue Umschaltzeit zwischen den Zuständen wurde beim bisherigen Test noch nicht systematisch vermessen.

## 14.2 Änderung von 1336 / SG03 bei bereits aktivem Low PV

Beispiel:

```text
1334 = 7
8801 = 1
→ Low PV bereits aktiv

1336 wird geändert
→ State 6 bleibt aktiv
→ nur der Low-PV-Leistungswert ändert sich
```

Die statische V3.4-Analyse zeigt hier **keinen Weg über den klassischen 10-Minuten-State-Hold**. `SG03/1336` wird im laufenden SG-/Regelpfad erneut eingelesen und im aktiven State 6 verwendet.

Daraus folgt:

> Eine reine Änderung von `1336` sollte nicht 10 Minuten auf eine neue State-Freigabe warten müssen.

Im Realtest am 11.09.2026 wurde trotzdem eine **leichte Verzögerung zwischen Änderung von `1336` und sichtbarer Wirkung** festgestellt.

Diese Verzögerung ist derzeit:

```text
vorhanden:       live beobachtet
genaue Dauer:    noch nicht gemessen
10-Minuten-Hold: nach statischer Analyse nein
Ursache:         noch offen
```

Mögliche nachgelagerte Ursachen wie normale Leistungsregelung, Verdichterfrequenzrampe oder weitere Filter-/Zeitglieder sind plausibel, aber derzeit **nicht als Ursache bestätigt**.

Für eine dynamische PV-Regelung sollte `1336` daher nicht im Sekundenraster aggressiv nachgeregelt werden, bevor die reale Reaktionszeit vermessen ist.

## 14.3 Aktueller Verzögerungsstatus kompakt

| Änderung | bekannte Verzögerung | Status |
|---|---|---|
| klassischer `SG01=3`, neuer `8801`-State | fester 10-Minuten-Hold | **V3.3 Binary + live bestätigt** |
| Änderung `1334` im klassischen Pfad | setzt Hold zurück | **V3.3 Binary + live bestätigt** |
| neuer `SG01=7`, Wechsel `8801=1/2/3` | noch nicht systematisch vermessen | **offen** |
| `1336/SG03` ändern, während `SG01=7` + `8801=1` aktiv ist | kurze Wirkungslatenz beobachtet; keine 10 Minuten erwartet | **live beobachtet, Dauer offen** |

---

# 15. MAIN:2034 bleibt Hardware-Rohstatus

Bits 12/13 von `MAIN:2034` repräsentieren die realen SG-Hardwareeingänge.

Beim klassischen virtuellen Pfad `SG01=3` müssen diese Bits nicht der Vorgabe aus `8801` folgen, weil die virtuellen Kontakte intern erzeugt werden.

Für den neuen `SG01=7`-Pfad ist ebenfalls nicht zu erwarten, dass `2034` die virtuelle 3-Stufen-Vorgabe spiegelt; `2034` ist als physischer Eingangsrückkanal zu behandeln.

---

# 16. Direkter User-Modbus versus Warmlink/LTE 0x63

Für V3.3 ist bestätigt, dass der direkte User-/Mainboard-Modbus für `ENG:CTRL:8801–8820` FC03-, FC06- und FC10-Pfade besitzt.

Für `8801` wurde dort live bestätigt:

```text
Lesen          -> funktioniert
Schreiben      -> funktioniert
0..4           -> bleiben im Register
Rücklesen      -> funktioniert
SG-Wirkung     -> bestätigt
```

Der separate Warmlink-/LTE-Dispatcher auf Unit `0x63` besitzt dagegen in V3.3 normale Bereiche für:

```text
FC03: 1001–1540, 2001–2180, 8001–8090
FC06: 1001–1540, 8001–8090
FC10: 1001–1540, 5091–5180, 7001–7090, 7091–7180, 8001–8090
```

`8801–8820` ist dort nicht als normaler Bereich enthalten.

Live unter V3.3:

```text
0x63:1334 lesen       -> funktioniert
0x63:1334 schreiben   -> funktioniert
0x63:2133 lesen       -> funktioniert
0x63:8801 FC03        -> Timeout / keine Antwort
```

Ein formal passender LTE-FC10-ACK auf `8801` wurde zwar beobachtet, ein Apply auf das echte User-Modbus-`8801` aber nicht bestätigt.

Daher bleibt die praktische Empfehlung:

> Für die virtuelle SG-/PV-Steuerung `8801` über den direkten User-/Mainboard-Modbus verwenden.

Die Dispatcher-Adressen und RAM-Adressen aus der V3.3-Analyse dürfen nicht ungeprüft als V3.4-Codeadressen übernommen werden.

Details zum separaten Warmlink-Pfad:

[`FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md`](FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md)

---

# 17. Live-Testmatrix für SG01 = 7

| Test | Einstellung | Erwartung aus V3.4-Analyse | Status / zu beobachten |
|---|---|---|---|
| Neutral | `1334=7`, `8801=2` | normale Regelung | **live bestätigt 11.09.2026** |
| Low PV | `1334=7`, `8801=1` | Leistungsbegrenzung über `1336/SG03` | **live bestätigt 11.09.2026** |
| High PV | `1334=7`, `8801=3` | SG05/06/07 aktiv | **noch offen** |
| `1336` im Low-PV-State ändern | `1334=7`, `8801=1`, nur `1336` ändern | Leistungswert wird ohne State-Wechsel nachgeführt | **Wirkung bestätigt; leichte Verzögerung beobachtet, Dauer vermessen** |
| Low→Neutral | `1→2` | Zustandswechsel | Übernahmezeit / möglicher Hold noch vermessen |
| Neutral→High | `2→3` | Zustandswechsel | Übernahmezeit / möglicher Hold |
| High→Low | `3→1` | Zustandswechsel | Übernahmezeit / möglicher Hold |
| Quellenwechsel | `1334: 7→0→7` | interner Reset möglich | Hold-/State-Verhalten |
| Neustart | Reboot mit `1334=7` | Persistenz offen | 1334/8801/2133 nach Boot |

Zusätzlich sollten für Low PV verschiedene `SG03`-Werte getestet werden, um Skalierung, Grenzwerte, tatsächliche Leistungsbegrenzung und die reale Reaktionszeit quantitativ zu bestimmen.

Für High PV sollten `SG05`, `SG06` und `SG07` zunächst mit kleinen, eindeutig erkennbaren Werten getestet werden.

---

# 18. Konsequenz für externe Steuerungen

## Klassischer Pfad

```text
MAIN:1334 = 3
ENG:CTRL:8801 = 1..4
MAIN:2133 = effektive Rückmeldung 1..4
```

Dabei den bestätigten 10-Minuten-Hold berücksichtigen.

## Neuer V3.4-PV-Pfad

```text
MAIN:1334 = 7

8801 = 1 -> Low PV       [live bestätigt]
8801 = 2 -> Neutral      [live bestätigt]
8801 = 3 -> High PV      [Live-Test offen]

1336 / SG03 -> Low-PV-Leistungswert
1338 / SG05 -> High-PV-WW-Anhebung
1339 / SG06 -> High-PV-Heiz-Anhebung
1340 / SG07 -> High-PV-Kühl-Absenkung

2133 = 1 / 2 / 3 -> gemeldete Stufe
```

Für eine PV-Regelung bietet es sich an, den State relativ selten über `8801` zu wechseln und innerhalb des aktiven Low-PV-State den Leistungswert über `1336` nachzuführen.

Dabei beachten:

- Für reine `1336`-Änderungen ist kein 10-Minuten-State-Hold erkennbar.
- Eine kurze reale Wirkungslatenz wurde jedoch beobachtet.
- Vor einer schnellen geschlossenen Regelung sollte diese Latenz zunächst gemessen werden.
- Für State-Wechsel über `8801` im neuen Pfad ist das genaue Hold-/Timing-Verhalten noch offen.

---

# 19. Konsequenz für FoxAir_Control

Für die Register-/UI-Beschreibung sollte `MAIN:1334 / SG01` nicht mehr nur mit `0..3` dokumentiert werden.

Mindestens bekannte Auswahlwerte:

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
3 = klassischer Modbus-/virtueller SG-Ready-Zustand
7 = neuer V3.4 3-Stufen-PV-Modus über 8801
```

Für `ENG:CTRL:8801` ist die Bedeutung abhängig von `SG01`:

```text
wenn SG01 = 3:
    1..4 = klassische SG-Ready-Modi

wenn SG01 = 7:
    1 = Low PV      [live bestätigt]
    2 = Neutral     [live bestätigt]
    3 = High PV     [statisch bestätigt, Live-Test offen]
```

Zusätzlicher Hinweis für `1336 / SG03`:

```text
bei SG01=7 und 8801=1:
    dynamischer Low-PV-Leistungswert
    kein klassischer 10-Minuten-Hold für reine Parameteränderung erkennbar
    kurze reale Wirkungslatenz beobachtet
```

Die UI sollte deshalb `8801` nicht ohne Kontext von `1334` beschriften.

---

# 20. Abschlussstatus

| Punkt | Status |
|---|---|
| `1334=3` klassischer virtueller Pfad | **V3.3 Binary + live bestätigt** |
| `8801` Mapping 1..4 bei `SG01=3` | **V3.3 Binary + live bestätigt** |
| `8801` direkter User-Modbus R/W | **V3.3 live bestätigt** |
| klassischer 10-Minuten-Hold | **V3.3 Binary bestätigt + live konsistent** |
| Änderung von `1334` resettiert klassischen Hold | **V3.3 Binary + live bestätigt** |
| `1334=7` neuer V3.4-PV-Pfad grundsätzlich | **V3.4 statisch + live bestätigt** |
| `8801=1 -> State 6 / Low PV` | **V3.4 statisch + live bestätigt 11.09.2026** |
| `8801=2 -> State 7 / Neutral` | **V3.4 statisch + live bestätigt 11.09.2026** |
| `8801=3 -> State 8 / High PV` | **V3.4 statisch rekonstruiert; Live-Test offen** |
| `State 6/7/8 -> 2133=1/2/3` | **States 6/7 live bestätigt; State 8 offen** |
| Low PV nutzt `SG03/1336` | **V3.4 statisch + live bestätigt** |
| `1336` während Low PV dynamisch änderbar | **live bestätigt** |
| 10-Minuten-Hold bei reiner `1336`-Änderung | **statisch nicht erkennbar / nicht erwartet** |
| kurze Wirkungslatenz nach `1336`-Änderung | **live beobachtet; Dauer/Ursache offen** |
| Neutral = Normalregelung | **V3.4 statisch + live bestätigt** |
| High PV nutzt `SG05/1338`, `SG06/1339`, `SG07/1340` | **V3.4 statisch rekonstruiert; Live-Test offen** |
| `SG04/1337` im neuen Pfad wirksam | **bisher nicht nachgewiesen** |
| 10-Minuten-Hold bei State-Wechseln unter `SG01=7` | **offen / noch vermessen** |
| `2034` als physischer Eingangsrückkanal | **für klassischen Pfad bestätigt; für neuen Pfad als Rohstatus einzuordnen** |
| Warmlink `0x63` als direkter Ersatz für User-Modbus-8801 | **V3.3 nicht bestätigt / normaler Dispatcher unterstützt 8801 nicht** |

Damit ist der neue V3.4-`SG01=7`-Pfad inzwischen teilweise live geschlossen: Low PV und Neutral funktionieren am realen Gerät. Für High PV sowie das genaue Timing der State-Wechsel und die kurze Reaktionslatenz von `1336` stehen noch gezielte Messungen aus.
