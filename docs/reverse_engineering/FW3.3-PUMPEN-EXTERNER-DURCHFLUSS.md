# Mainboard-Firmware V3.3 – externer Durchfluss über Hydraulikmodul Unit 0x61

Stand: 27. August 2026

Dieses Dokument ergänzt [`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md) um den firmware-nativen Pfad für einen extern gelieferten Wasserdurchfluss.

Untersucht wurde die Mainboard-Firmware `82400644 / V3.3` mit Imagebasis `0x08050000`.

## Bewertungsstufen

- **bestätigt** – direkt im untersuchten V3.3-Binary nachgewiesen
- **sehr wahrscheinlich** – Datenfluss geschlossen, Herstellerbezeichnung fehlt noch
- **offen** – fachliche Einzelbedeutung noch nicht vollständig benannt

---

# 1. Kurzfazit

Ja: Die V3.3 kann einen **extern gelieferten Durchflusswert** verwenden.

Der native Weg ist jedoch **nicht** ein Schreibzugriff auf `MAIN:2077`, sondern ein separates internes Hydraulikmodul:

```text
MAIN:1036 / H30 = 3
        |
        v
interner USART3-Modbus
        |
        v
Slave 0x61
FC03 2001, Qty 90
        |
        +--> HYD61:2047 = Gültigkeits-/Vorhandenflag
        +--> HYD61:2048 = Durchfluss raw/100 m³/h
        |
        v
Mainboard-Runtime 0x20016F14
        |
        +--> MAIN:1022 signed Korrekturoffset
        |
        v
MAIN:2077 / T39
```

Damit ist die Emulation eines externen Durchflusssensors prinzipiell möglich, indem ein eigener Teilnehmer das Hydraulikmodul `0x61` emuliert.

**Wichtig:** `H30=3` aktiviert nicht nur diese zwei Register, sondern den kompletten Hydraulikmodul-Pfad. Ein Emulator muss daher den internen Dialog vollständig genug bedienen und darf die übrigen Hydraulikmodulwerte nicht unbedacht mit Null überschreiben.

---

# 2. Auswahl des externen Pfads über H30

Die Durchflussroutine liegt ungefähr bei:

```text
VA 0x08061790
```

Sie prüft zunächst:

```text
0x20016774 + 0x1C
```

Dieses Feld ist:

```text
MAIN:1036 / H30
```

Für:

```text
H30 == 3
```

wird der externe Hydraulikmodul-Pfad benutzt.

Für andere H30-Werte läuft die lokale Durchflussberechnung aus Pumpen-PWM-Feedback und `H31`-Kennlinie.

**Bewertung: bestätigt.**

---

# 3. Interner Modbus-Dialog von Unit 0x61

Der interne Boardbus läuft über USART3, Mainboard als Master.

Für `H30 == 3` verwendet der zyklische Scheduler:

```text
RX:
Slave 0x61
FC03
Startregister 2001
Qty 90

TX:
Slave 0x61
FC10
Startregister 1001
Qty 90
```

Der RX-Pfad liest damit:

```text
HYD61:2001 ... HYD61:2090
```

Der TX-Pfad schreibt gleichzeitig:

```text
HYD61:1001 ... HYD61:1090
```

Das bedeutet für eine Emulation:

1. auf `0x61 / FC03 / 2001 / 90` korrekt antworten,
2. auf `0x61 / FC10 / 1001 / 90` korrekt reagieren bzw. ACK liefern,
3. den vollständigen 90-Wort-Statusblock konsistent halten.

Nur zwei Wörter einer ansonsten mit Nullen gefüllten 90-Wort-Antwort zu liefern ist nicht empfehlenswert, weil die Firmware weitere Felder aus demselben Antwortblock in Runtime-Strukturen übernimmt.

**Bewertung: bestätigt.**

---

# 4. Herkunft von HYD61:2047 und HYD61:2048

Im RX-Parser für Unit `0x61` liegt das erste Datenwort des Statusblocks bei Offset `+0x1C` des Empfangspuffers.

Damit gilt:

```text
RX-Offset +0x1C = HYD61:2001
```

Die für den Durchfluss verwendeten Wörter liegen bei:

```text
RX-Offset +0x78
RX-Offset +0x7A
```

Umrechnung:

```text
(0x78 - 0x1C) / 2 = 46
2001 + 46 = 2047

(0x7A - 0x1C) / 2 = 47
2001 + 47 = 2048
```

Der Parser kopiert:

```text
HYD61:2047 -> 0x20015C68 + 0x108
HYD61:2048 -> 0x20015C68 + 0x10C
```

**Bewertung: bestätigt.**

---

# 5. Bedeutung von HYD61:2047

Die Durchflussroutine prüft:

```text
wenn 0x20015C68+0x108 == 0:
    externer Durchfluss nicht übernehmen
```

Da dieses Feld direkt aus `HYD61:2047` stammt, gilt:

```text
HYD61:2047 != 0
```

als notwendige Freigabe für den externen Durchflusswert.

Die exakte Herstellerbezeichnung des Wortes ist nicht bekannt. Firmwareseitig ist seine Rolle aber eindeutig:

> **Gültigkeits-/Vorhanden-/Freigabeflag für den externen Durchflusswert.**

Für einen Emulator ist daher konservativ:

```text
HYD61:2047 = 1
```

naheliegend, solange reale Hydraulikmodul-Mitschnitte keine andere Bitsemantik zeigen.

**Bewertung: bestätigt für die Gate-Funktion; Herstellername offen.**

---

# 6. Bedeutung und Skalierung von HYD61:2048

Bei aktivem Gate kopiert die Firmware:

```text
HYD61:2048
    -> 0x20015C68+0x10C
    -> 0x20016F14
```

ohne zusätzliche Multiplikation oder Division.

`0x20016F14` ist derselbe interne Durchfluss-Runtimewert, der später als `MAIN:2077 / T39` veröffentlicht wird.

Für `2077` gilt bestätigt:

```text
raw / 100 = m³/h
```

Daraus folgt unmittelbar auch für den externen Wert:

```text
HYD61:2048 raw / 100 = m³/h
```

Beispiele:

```text
HYD61:2048 = 40  -> 0,40 m³/h
HYD61:2048 = 62  -> 0,62 m³/h
HYD61:2048 = 100 -> 1,00 m³/h
```

**Bewertung: bestätigt.**

---

# 7. MAIN:1022 ist ein signed Durchfluss-Korrekturoffset

`MAIN:1022` war bisher als Reserve geführt.

Die Parameterkopie bestätigt:

```text
MAIN:1022
Mirror 0x20012788 + 0x412
    -> 0x20016C7C + 0x0C
```

Die Durchflussroutine liest dieses Feld als:

```text
signed 16 bit
```

und addiert es zum berechneten bzw. extern gelieferten Durchfluss.

Für den externen Pfad lautet die Logik bytegenau sinngemäß:

```c
if (H30 == 3 && HYD61_2047 != 0) {
    int flow = HYD61_2048 + (int16_t)MAIN_1022;

    if (flow < 1)
        flow = 0;

    effective_flow = flow;
}
```

Dasselbe Korrekturprinzip wird auch im lokalen H31-Kennlinienpfad angewendet.

Damit gilt:

```text
MAIN:1022 raw = 1 -> +0,01 m³/h
MAIN:1022 raw = 10 -> +0,10 m³/h
MAIN:1022 raw = 0xFFF6 = -10 -> -0,10 m³/h
```

Resultate kleiner 1 raw werden auf 0 begrenzt.

Ein passender technischer Name wäre daher:

> **Water Flow Correction / Durchfluss-Korrekturoffset**

**Bewertung: bestätigt.**

---

# 8. Kann MAIN:1022 allein als externer Durchflusseingang benutzt werden?

Nicht sauber.

`1022` ist nur ein **Offset** zu einer bereits vorhandenen Durchflussquelle.

Im lokalen H31-Pfad gilt sinngemäß:

```text
Qeff = QausPWM + signed(1022)
```

Im H30=3-Pfad:

```text
Qeff = HYD61:2048 + signed(1022)
```

Wenn der lokale Grundwert bereits 0 ist, wird der Offset nicht zu einem vollwertigen unabhängigen Sensoreingang.

Außerdem ist `1022` ein normaler Parameter und sehr wahrscheinlich persistent behandelt. Ein zyklisches Schreiben im Sekunden- oder Minutentakt wäre daher kein sinnvoller Ersatz für einen echten Runtime-Eingang und könnte unnötige Parameter-/EEPROM-Schreibvorgänge verursachen.

Daher:

> `MAIN:1022` eignet sich zur Kalibrierung, nicht als dynamischer externer Durchflusskanal.

---

# 9. Kann MAIN:2077 direkt beschrieben werden?

Nein, nicht über den normalen Mainboard-Modbus.

`MAIN:2077` gehört zum Statusbereich `2001–2180` und wird vom Mainboard-Statusbuilder aus dem Runtime-Durchfluss erzeugt.

Der normale Mainboard-/User-Modbus behandelt diesen Bereich als read-only.

Ein Schreiben auf `MAIN:2077` wäre daher nicht der firmware-native Einspeisepunkt und würde selbst bei einem temporären RAM-Effekt vom nächsten Status-/Regelzyklus wieder überschrieben.

---

# 10. Native externe Einspeisung durch einen eigenen 0x61-Emulator

Für einen eigenen Sensor bzw. Gateway wäre der sauberste firmware-native Ansatz:

```text
realer externer Durchflusssensor
        |
        v
ESP32 / Raspberry Pi / MCU
        |
        | interner RS485-Boardbus
        v
Modbus Slave 0x61
        |
        +-- FC03 2001..2090
        |      2047 = 1
        |      2048 = Q_m3h * 100
        |
        +-- FC10 1001..1090 annehmen/ACK
        |
        v
FoxAir Mainboard H30=3
        |
        v
0x20016F14
        |
        v
MAIN:2077
        |
        +--> Pumpen-Auto-Regelung
        +--> Mindestdurchflussprüfung
        +--> 10-min-Qualifikation
        +--> Leistungs-/Wärmemengenberechnung
```

Damit würde der externe Messwert nicht nur angezeigt, sondern an der Stelle in die Firmware gelangen, an der der Mainboard-Regler selbst seinen wirksamen Durchfluss erwartet.

Das ist gegenüber einer Manipulation von `2077` wesentlich sauberer.

---

# 11. Aber: H30=3 ist ein Architekturwechsel, kein einzelner Sensor-Schalter

Dieser Punkt ist für Tests entscheidend.

`H30=3` schaltet den internen Scheduler auf die alternative Hydraulikmodulvariante um:

```text
Unit 0x61
RX FC03 2001/90
TX FC10 1001/90
```

Die Firmware übernimmt aus der 90-Wort-Antwort neben 2047/2048 noch zahlreiche weitere Felder.

Daher darf ein Minimalemulator nicht einfach folgendes tun:

```text
alle Register = 0
nur 2047 = 1
nur 2048 = Durchfluss
```

Denn Nullwerte in anderen aktiven Hydraulikmodulfeldern könnten Funktionen, Temperaturen, Pumpen-/Ventilzustände oder Diagnoseflags beeinflussen.

Für einen sicheren Emulator müssen die anderen gelesenen Register entweder:

1. anhand eines realen 0x61-Hydraulikmoduls rekonstruiert werden,
2. durch weitere Binaryanalyse als unkritisch/Reserve bestätigt werden,
3. oder gezielt mit firmwareverträglichen Neutralwerten befüllt werden.

**Bewertung: bestätigt, Sicherheitsfolgerung aus dem Datenfluss.**

---

# 12. Anforderungen an einen späteren Testemulator

Vor einem Liveversuch sollten mindestens folgende Punkte geschlossen sein:

- vollständige Zuordnung der von V3.3 aus `HYD61:2001..2090` tatsächlich übernommenen Wörter,
- Bedeutung aller nicht-reservierten Felder neben 2047/2048,
- erwarteter Kommunikationswatchdog für Unit 0x61,
- Verhalten bei fehlender/zu später Antwort,
- notwendige Antwortzeit bei 4800 Baud,
- Inhalt und Bedeutung des vom Mainboard gesendeten FC10-Blocks `1001..1090`,
- ob der Emulator die geschriebenen Parameter nur ACKen oder intern spiegeln muss,
- Verhalten bei Wechsel `H30 normal -> 3 -> normal`,
- Auswirkungen auf reale Pumpenausgänge und Hydraulikfunktionen.

Erst danach ist ein Liveversuch an einer laufenden Wärmepumpe sinnvoll.

---

# 13. Diagnose beim späteren Emulatorversuch

Ein erfolgreicher externer Durchflusspfad sollte gleichzeitig zeigen:

```text
HYD61:2047 != 0
HYD61:2048 = gewünschter Rohwert
MAIN:2077  = HYD61:2048 + signed(MAIN:1022)
```

Beispiel bei:

```text
HYD61:2047 = 1
HYD61:2048 = 62
MAIN:1022  = 0
```

Erwartung:

```text
MAIN:2077 = 62
=> 0,62 m³/h
```

Mit:

```text
MAIN:1022 = +3
```

wäre zu erwarten:

```text
MAIN:2077 = 65
=> 0,65 m³/h
```

Die Korrelation sollte zunächst bei ausgeschaltetem Verdichter bzw. in einem hydraulisch ungefährlichen Zustand geprüft werden, bevor der Wert in die aktive Pumpenregelung einbezogen wird.

---

# 14. Abgrenzung zu MAIN:2106

Die externe Durchflussanalyse liefert keinen Hinweis darauf, dass `MAIN:2106` der Regeltimer oder ein Durchfluss-Eingaberegister wäre.

Der zentrale Mainboard-Statusbuilder erzeugt `2106` nicht wie die benachbarten normalen Statuswerte. `2107` ist im DWIN-Pfad als Kommunikationsmarker `0x5AA5` bekannt; `2106` wird dort nicht direkt ausgewertet.

Die live beobachtete ungefähr fünfminütige Pulsfolge von `2106` bleibt daher als separates, noch offenes Kommunikations-/Runtimephänomen dokumentiert.

Sie ist **nicht** die 60-s-P12-Regelperiode und **nicht** der externe Durchflusseingang.

---

# 15. Fazit

Der externe Durchfluss ist in V3.3 kein theoretischer Nebeneffekt, sondern ein echter vorgesehener Architekturpfad:

```text
H30 = 3
    -> Hydraulikmodul 0x61
    -> 2047 valid
    -> 2048 flow x100
    -> + signed MAIN:1022
    -> MAIN:2077
```

Damit ist technisch möglich, einen eigenen präzisen Durchflussmesser über einen emulierten Hydraulikmodul-Slave in die originale FoxAir-Regelung einzuspeisen.

Der entscheidende nächste Schritt ist jedoch nicht mehr die Durchflussformel, sondern die **vollständige sichere Emulation des 0x61-Hydraulikmoduls**, weil H30=3 den kompletten Hydraulikmodul-Kommunikationspfad aktiviert.
