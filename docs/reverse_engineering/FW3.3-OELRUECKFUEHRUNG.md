# Mainboard-Firmware V3.3 – Ölrückführung / Oil Return

Stand: 23. August 2026

Diese Datei dokumentiert die statisch rekonstruierte Ölrückführungslogik der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3`.

Die Aussagen wurden direkt am Binary `phnixIot_device_OTA` verifiziert. Das untersuchte Image hat:

```text
Größe:       287598 Byte
MD5:         CEB6A4BF386FF644E23E410023E74673
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:  0x08050000
```

Bewertungsstufen:

- **bestätigt** – direkt im Binary nachgewiesen oder zusätzlich durch reale Betriebsdaten gestützt
- **sehr wahrscheinlich** – Datenfluss ist geschlossen, einzelne physikalische Benennung bleibt indirekt
- **Hypothese** – noch nicht ausreichend verifiziert

---

## 1. Kurzfazit

Die V3.3 besitzt eine explizite Ölrückführungslogik für längeren Verdichterbetrieb bei niedriger Drehzahl.

Im normalen Anlagenbetrieb mit `H34 = 0` gilt:

```text
Kompressor-Istfrequenz 1…35 Hz
        │
        │ 7200 s zusammenhängend
        │ = 120 Minuten
        ▼
Ölrückführung aktiv
        │
        ▼
Kompressor-Sollfrequenz nominal 60 Hz
        │
        │ 180 s
        │ = 3 Minuten
        ▼
Rückkehr in die normale Frequenzregelung
```

Sobald die Istfrequenz `0 Hz` oder mindestens `36 Hz` beträgt, wird die zuvor angesammelte Niedriglastzeit auf `0` zurückgesetzt.

Die Ölrückführung ist **nicht direkt als Modbus-Statusregister veröffentlicht**. Weder der laufende 120-Minuten-Zähler noch das Active-Flag noch die Restzeit der dreiminütigen Ölrückführung werden in den öffentlichen Statusspiegel kopiert.

**Bewertung: bestätigt.**

---

## 2. Interne Runtime-Struktur

Die zentrale Struktur liegt bei:

```text
0x20016DEC
```

Rekonstruierte Felder:

| Adresse | Offset | Bedeutung | Bewertung |
|---:|---:|---|---|
| `0x20016DEC` | `+0x00` | qualifizierte zusammenhängende Niedriglastlaufzeit | bestätigt |
| `0x20016DEE` | `+0x02` | Restzeit des aktiven Oil-Return-Zyklus | bestätigt |
| `0x20016DF0` | `+0x04` | Oil Return aktiv, `0/1` | bestätigt |

Die zentrale Timer-/Triggerfunktion liegt ungefähr bei:

```text
0x0805BBB8 … 0x0805BC8A
```

---

## 3. Eingang: tatsächliche Verdichterfrequenz

Die Routine benutzt nicht die berechnete Sollfrequenz, sondern die tatsächliche vom Inverter zurückgemeldete Verdichterfrequenz:

```text
0x200168C4 + 0x06
```

Dieser Wert wird im Hauptstatusspiegel als:

```text
Register 2072 = Betriebsfrequenz / Istfrequenz des Kompressors
```

veröffentlicht.

Die Qualifikation ist bytegenau:

```text
Istfrequenz == 0 Hz
    → Low-Speed-Zähler = 0

Istfrequenz >= 36 Hz
    → Low-Speed-Zähler = 0

Istfrequenz 1…35 Hz
    → Low-Speed-Zähler darf weiterlaufen
```

Damit zählt die Firmware **keine allgemeine Verdichterlaufzeit**. Benötigt werden zusammenhängende Phasen unterhalb 36 Hz.

Beispiel:

```text
119 min bei 32 Hz
kurzzeitig 40 Hz
→ Zähler sofort wieder 0
→ neue 120-Minuten-Qualifikation beginnt
```

Auch ein Verdichterstopp setzt den Zähler zurück.

**Bewertung: bestätigt.**

---

## 4. Normaler Trigger: 7200 Sekunden

Im normalen Pfad wird der Low-Speed-Zähler mit der Konstanten:

```text
0x1C20 = 7200
```

verglichen.

Die Routine wird in einer Sekundenzeitbasis abgearbeitet. Das passt zusätzlich exakt zum real beobachteten Verhalten der V3.3:

```text
7200 s = 120 min
```

Bei Erreichen der Schwelle setzt die Firmware:

```text
Low-Speed-Zähler = 0
OilReturnActive   = 1
Restzeit          = 180
```

**Bewertung: bestätigt.**

---

## 5. Oil Return aktiv: nominal 60 Hz für 180 Sekunden

Das Active-Flag `0x20016DF0` wird im eigentlichen Kompressor-Sollwertregler ausgewertet, unter anderem in den Bereichen um:

```text
0x08073F5E
0x08074992
```

Bei aktivem Oil Return wird dort ein Sollwert von:

```text
60 Hz
```

angefordert.

Dieser Wert läuft anschließend weiterhin durch die normalen Frequenz- und Modellbegrenzungen und wird schließlich nach:

```text
0x20016AA4 + 0x08
```

übernommen. Diese Variable ist der veröffentlichte und an den Inverter gesendete Kompressor-Sollwert:

```text
Register 2071
```

Die Restzeit wird von `180` bis `0` heruntergezählt:

```text
180 s = 3 min
```

Danach wird das Active-Flag wieder gelöscht und die normale Sollfrequenzregelung übernimmt.

Wichtig:

> `60 Hz` ist die Oil-Return-Anforderung vor den normalen nachgelagerten Verdichterbegrenzungen. Schutz- und Modellgrenzen können weiterhin verhindern, dass der reale Verdichter exakt 60 Hz erreicht.

**Bewertung: bestätigt.**

---

## 6. H34 – ERP Testing Mode und der 6-Stunden-Sonderpfad

Der Parameterzugriff:

```text
0x20016774 + 0x2A
```

entspricht:

```text
Register 1020 = H34 = ERP Testing Mode
```

Die Ölrückführungsroutine behandelt H34 explizit.

### H34 = 0

Normaler Anlagenbetrieb:

```text
1…35 Hz für 7200 s
→ Oil Return
→ nominal 60 Hz für 180 s
```

### H34 = 1 oder 2

Im normalen Oil-Return-Zweig werden Low-Speed-Zähler und Active-Flag zurückgesetzt. Die normale 120-Minuten-Auslösung ist damit unterdrückt.

### H34 = 3

Nur in diesem ERP-/Prüfmodus wird eine zusätzliche Betriebsbereichslogik aktiv, welche den internen Wert:

```text
0x20016FB7
```

bildet.

Wenn dieser Wert ungleich `0` ist, benutzt die Oil-Return-Routine statt 7200 die Schwelle:

```text
0x5460 = 21600
21600 s = 360 min = 6 h
```

Damit ist die früher offene Frage wesentlich präziser beantwortet:

> Die 6-Stunden-Variante ist kein normaler temperaturabhängiger Wechsel der realen Anlage bei H34=0, sondern gehört zum H34=3-ERP-/Testmodus.

**Bewertung: bestätigt** für H34-Gate und 21600-s-Zweig.

---

## 7. Bedeutung von `0x20016FB7`

Der Writer liegt in einer größeren temperatur- und betriebszustandsabhängigen Prüfroutine ab ungefähr:

```text
0x08061AA8
```

Die eigentliche Zusammenfassung nach `0x20016FB7` erfolgt ungefähr im Bereich:

```text
0x0806226C … 0x0806229A
```

Ein interner Zwischenszustand:

```text
0x20016FB5
```

kann Werte ungefähr `0…12` annehmen. Daraus wird `FB7` als gelatchte Bereichsklasse `0/1/2` gebildet.

Vereinfacht:

```text
FB5 = 0
    → FB7 = 0

FB5 in unteren aktiven Bereichen
    → FB7 = 1

FB5 in oberen aktiven Bereichen
    → FB7 = 2

bestimmte Übergangsstates
    → bisherigen FB7-Wert halten
```

Die Klassifizierung benutzt unter anderem:

- T01 Einlasswasser
- T02 Auslasswasser
- T04 Außentemperatur
- Temperaturdifferenzen / Referenzwerte
- Verdichterbetriebsbedingungen

Entscheidend für die Oil-Return-Interpretation ist aber:

```text
Die gesamte FB7-Erzeugung ist an H34 == 3 gekoppelt.
```

Damit muss `FB7` **für die normale H34=0-Anlage nicht extern rekonstruiert werden**, um den regulären Oil Return zu verfolgen.

**Bewertung: bestätigt** für Gate und Datenfluss; die originale PHNIX-Bezeichnung der internen Bereichsklassen bleibt unbekannt.

---

## 8. Keine direkte Modbus-Anzeige für Oil Return

Alle direkten Xrefs auf die Struktur `0x20016DEC` wurden geprüft.

Sie gruppieren sich funktional in:

1. Timer-/Triggerlogik
2. Reset-/Shutdownpfad
3. Kompressor-Sollwertregler

Es wurde **kein Xref aus dem Status-/Modbus-Builder** gefunden.

Daher werden folgende Werte nicht direkt in Register 2001–2180 gespiegelt:

| interner Wert | RAM | Modbus direkt |
|---|---:|---|
| angesammelte Low-Speed-Zeit | `0x20016DEC` | nein |
| Restzeit des aktiven Oil Return | `0x20016DEE` | nein |
| Oil Return Active | `0x20016DF0` | nein |

Auch im untersuchten Service-/Engineering-Zugriff wurde keine direkte Spiegelung dieser drei RAM-Werte gefunden.

**Bewertung: bestätigt für den untersuchten V3.3-Code.**

---

## 9. Was während Oil Return per Modbus sichtbar ist

Direkt sichtbar sind nur die Folgen:

```text
2071 = Kompressor-Sollfrequenz
2072 = Kompressor-Istfrequenz
```

Während einer normalen Ölrückführung wird 2071 typischerweise auf nominal 60 Hz angehoben und 2072 folgt.

Das ist jedoch kein eindeutiger Oil-Return-Indikator, da 60 Hz auch aus der normalen Leistungsregelung entstehen können.

Register 2019 Bit 0 zeigt lediglich, dass der Verdichter tatsächlich läuft. Auch dieses Bit unterscheidet keinen Oil Return vom Normalbetrieb.

---

## 10. Externe Rekonstruktion für FoxAir-Control / Logger

Für die normale Anlage mit:

```text
H34 = 0
```

lässt sich der interne Qualifikationszähler aus Register 2072 sehr gut nachbilden.

Pseudocode:

```text
if 1 <= compressor_actual_hz <= 35:
    low_speed_seconds += elapsed_seconds
else:
    low_speed_seconds = 0

if low_speed_seconds >= 7200:
    inferred_oil_return = true
    inferred_remaining = 180
    low_speed_seconds = 0
```

Während des inferierten Oil Return:

```text
remaining -= elapsed_seconds

wenn remaining <= 0:
    inferred_oil_return = false
```

### Sinnvolle Diagnosewerte

Ein externer Logger könnte damit darstellen:

```text
Oil Return Qualifikation: 01:47:23 / 02:00:00
Oil Return in ca.:        00:12:37
```

bzw. nach Trigger:

```text
Oil Return:               aktiv
Restzeit geschätzt:       00:02:14
Sollfrequenz 2071:        60 Hz
Istfrequenz 2072:         58 Hz
```

### Wichtige Grenzen der externen Rekonstruktion

1. **Persistenz erforderlich**  
   Wird FoxAir-Control oder der Logger neu gestartet, kennt er die bereits im Mainboard angesammelte Low-Speed-Zeit nicht. Der externe Counter sollte daher persistent gespeichert werden.

2. **Mainboard-Neustart erkennen**  
   Ein Mainboard-Neustart löscht auch den internen Oil-Return-Zustand. Der externe Counter sollte bei erkanntem Mainboard-Neustart ebenfalls zurückgesetzt werden.

3. **Start mitten im aktiven Oil Return**  
   Wenn der Logger erst während eines laufenden Oil Return startet, gibt es keinen direkten Modbus-Marker. `2071=60` und `2072≈60` sind dann nur ein Indiz.

4. **Nachgelagerte Frequenzlimits**  
   Die Firmware fordert nominal 60 Hz an; Schutzgrenzen können die tatsächlich erreichte Frequenz reduzieren.

5. **H34 != 0**  
   Der oben beschriebene virtuelle 120-Minuten-Counter gilt für den normalen H34=0-Betrieb. H34=1/2 unterdrücken den normalen Pfad; H34=3 aktiviert den ERP-/Testsonderweg.

---

## 11. Rekonstruierter Normalalgorithmus

```text
if H34 == 0:
    if actual_compressor_hz == 0 or actual_compressor_hz >= 36:
        low_speed_counter = 0
    else:
        low_speed_counter += 1

        if low_speed_counter >= 7200:
            low_speed_counter = 0
            oil_return_active = 1
            oil_return_remaining = 180

elif H34 == 1 or H34 == 2:
    low_speed_counter = 0
    oil_return_active = 0

elif H34 == 3:
    # ERP-/Testmodus-Sonderlogik
    # FB7 wird aus separater Temperatur-/Betriebsbereichslogik erzeugt.
    # FB7 != 0 benutzt 21600 s als Oil-Return-Schwelle.
    ...

if oil_return_remaining > 0:
    oil_return_remaining -= 1
else:
    oil_return_active = 0

if oil_return_active:
    compressor_target_nominal = 60 Hz
```

---

## 12. Offene Restpunkte

Der normale Oil-Return-Pfad ist für V3.3 weitgehend geschlossen. Offen bleiben nur Nebenfragen:

1. vollständige semantische Benennung aller H34=3-ERP-Bereichsstates `FB5/FB7`
2. Prüfung, ob bestimmte Schutzabschaltungen die 180-s-Phase vorzeitig verlassen können, bevor der normale Timer abläuft
3. praktische Gegenprobe eines kompletten Oil-Return-Zyklus mit gleichzeitig geloggten Registern 2071/2072 und externer 120-Minuten-Rekonstruktion

Für den normalen Anlagenbetrieb ist keine dieser Fragen erforderlich, um die Grundfunktion nachzubilden.

---

## 13. Zusammenhang mit anderen Analysen

Siehe außerdem:

- `FW3.3-ERKENNTNISSE.md` – zentrale Gesamtübersicht
- `FW3.3-EEV-SMART-REGELUNG.md` – EEV-/Smart-Regelung
- `FW3.3-LUEFTERREGELUNG.md` – Lüfter-Sollwertbildung, Rückmeldungen und Buspfad
