# Mainboard-Firmware V3.3 – Lüfterregelung

Stand: 23. August 2026

Diese Datei dokumentiert die statisch rekonstruierte Lüfterregelung der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3`.

Untersucht wurde dasselbe Mainboard-Image wie in den übrigen V3.3-Analysen:

```text
Größe:       287598 Byte
MD5:         CEB6A4BF386FF644E23E410023E74673
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:  0x08050000
```

Bewertungsstufen:

- **bestätigt** – direkt im Binary nachgewiesen bzw. mit Register-/Busdaten geschlossen
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

Der normale Hauptregler liegt ungefähr bei:

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

Rekonstruierte Felder:

| Struktur | Offset | Modbus | Funktion |
|---:|---:|---:|---|
| `0x2001691C` | `+0x02` | 2076 | veröffentlichter Lüfter-Zielsollwert |
| `0x2001691C` | `+0x0C` | 2074 | tatsächliche Lüfterrückmeldung 1 |
| `0x2001691C` | `+0x0E` | 2075 | tatsächliche Lüfterrückmeldung 2 |

Im Statusbuilder ungefähr um `0x0806C698` ist die Zuordnung direkt sichtbar:

```text
0x2001691C +0x0C → Register 2074
0x2001691C +0x0E → Register 2075
0x2001691C +0x02 → Register 2076
```

**Bewertung: bestätigt.**

---

## 3. Register 2076 stammt aus dem primären Lüfter-Sollkanal

Der primäre intern berechnete Lüfter-Sollwert liegt bei:

```text
0x20016F0A
```

Ein zweiter Kanal liegt unmittelbar daneben:

```text
0x20016F0C
```

Die Statuslogik übernimmt den ersten Kanal nach:

```text
0x2001691C +0x02
```

und veröffentlicht ihn damit als Register 2076.

Somit gilt:

```text
0x20016F0A = Lüfter-Sollkanal 1
0x20016F0C = Lüfter-Sollkanal 2
2076       = veröffentlichter Sollwert von Kanal 1
```

**Bewertung: bestätigt.**

---

## 4. Register 2019 Bit 2 ist kein Sollbefehl

Der Builder von Register 2019 prüft die tatsächlichen Rückmeldungen:

```text
0x2001691C +0x0C
0x2001691C +0x0E
```

Wenn mindestens einer dieser Werte ungleich `0` ist, wird gesetzt:

```text
Register 2019 Bit 2 = 1
```

Damit bedeutet Bit 2 funktional:

> Mindestens ein Lüfter liefert eine von Null verschiedene tatsächliche Drehzahl-/Aktivitätsrückmeldung.

Es ist **kein Lüfter-Enable-Befehl** und auch nicht einfach eine Kopie von Register 2076.

**Bewertung: bestätigt.**

---

## 5. Lüfterrückmeldungen kommen über den Bus

Die Werte für:

```text
0x2001691C +0x0C
0x2001691C +0x0E
```

werden in der Kommunikationsverarbeitung aus empfangenen Busdaten aktualisiert.

Damit sind 2074 und 2075 keine lokal vom Mainboard gemessenen PWM-Tachowerte, sondern Rückmeldungen eines angeschlossenen Leistungs-/Inverter-/Lüftermoduls.

Die Firmware enthält mehrere Hardware-/Plattformvarianten; die genaue Position der Rückmeldewörter innerhalb des Remote-Frames kann je nach konfiguriertem Pfad variieren. Der Datenfluss zum öffentlichen Hauptstatus ist aber eindeutig.

**Bewertung: bestätigt** für Bus-Herkunft, **sehr wahrscheinlich** für die konkrete Hardwarebezeichnung des Remote-Moduls.

---

## 6. Buspfad der Lüfter-Sollwerte

Die berechneten Sollkanäle werden vor dem ausgehenden FC10-Paket in einen Kommunikationspuffer kopiert:

```text
0x20016F0A → 0x2001233E
0x20016F0C → 0x20012340
```

Der relevante Puffer beginnt bei:

```text
0x2001232C
```

Bei der 16-Wort-Variante des Pakets beginnt die Übertragung bei Remote-Register:

```text
1999 / 0x07CF
```

Aus den Wortpositionen ergibt sich:

```text
0x2001233E → Remote-Register 2008
0x20012340 → Remote-Register 2009
```

Damit ist der Sollpfad:

```text
Lüfterregler
  ↓
0x20016F0A / 0x20016F0C
  ↓
FC10 ab Register 1999
  ↓
Wortpositionen 2008 / 2009
  ↓
Remote-/Leistungsmodul
```

Ein Konfigurationsfeld entscheidet, ob die längere 16-Wort-Variante verwendet wird; andere Plattformvarianten übertragen kürzere Frames.

Wichtig:

> Die untersuchte V3.3 steuert die Lüfter in diesem Pfad über die Buskommunikation. Es wurde kein lokaler Mainboard-PWM-Ausgang als eigentlicher Fan-Actuator dieses Reglers gefunden.

**Bewertung: bestätigt.**

---

## 7. Live-Struktur der Lüfterparameter

Der Lüfterregler benutzt einen konsolidierten Live-Parameterblock bei:

```text
0x20016A04
```

Die Hauptparameterkopie zeigt, dass dieser Block aus mehreren nicht direkt aufeinanderfolgenden Modbusparametern aufgebaut wird:

| Live-Offset | Modbusregister | beobachtete Rolle im Lüftercode |
|---:|---:|---|
| `+0x00` | 1059 | Hauptkonfiguration / Lüftermodus; sehr wahrscheinlich F01 |
| `+0x02` | 1060 | Temperaturstützpunkt einer Kennlinie |
| `+0x04` | 1062 | Temperaturstützpunkt einer Kennlinie |
| `+0x06` | 1066 | Temperaturstützpunkt alternativer Kennlinie |
| `+0x08` | 1068 | Temperaturstützpunkt alternativer Kennlinie |
| `+0x18` | 1074 | zweiter Lüfter / Doppel-Lüfter-Konfiguration bzw. Freigabe |
| `+0x0A` | 1081 | niedriger Sollwert / Plateau |
| `+0x0C` | 1083 | Sollwert / Plateau der alternativen Kennlinie |
| `+0x0E` | 1087 | weiterer Kennlinien-/Grenzwert |
| `+0x10` | 1089 | weiterer Kennlinien-/Grenzwert |
| `+0x1A` | 1101 | zusätzlicher Temperatur-/Betriebsgrenzwert |
| `+0x1C` | 1102 | Abschalt-/Untergrenze der Hauptkennlinie |
| `+0x12` | 1103 | hoher Lüfter-Sollwert / Referenz |
| `+0x14` | 1104 | hoher Sollwert / Referenz der alternativen Kennlinie |

Die Registeradressen und ihre Live-Offets sind **bestätigt**.

Die exakten Fxx-Namen aller verstreuten Parameter sollen erst dann fest benannt werden, wenn die originale Registertabelle für diesen Bereich erneut vollständig gegengeprüft ist. Die funktionale Verwendung im Code ist dagegen bereits klar.

---

## 8. Primärer Regelwert: Register 2049 = Verdampfertemperatur

Ein wichtiger offener Punkt konnte geschlossen werden.

Der Lüftercode liest seinen zentralen Temperaturwert aus:

```text
0x20015FA8 + 0x0C
```

Der Hauptstatusbuilder kopiert exakt dieses Feld nach:

```text
Register 2049
```

und Register 2049 ist in der bekannten Hauptstatusbelegung:

```text
Verdampfertemperatur
```

Damit ist bestätigt:

> Die normale Lüfterkennlinie der V3.3 wird wesentlich aus der Verdampfertemperatur gebildet.

**Bewertung: bestätigt.**

---

## 9. Hauptkennlinie: stückweise linear über Verdampfertemperatur

Ein zentraler Zweig des Lüfterreglers liegt ungefähr im Bereich:

```text
0x08060776 … 0x080608D4
```

Für diesen Modus lassen sich folgende Größen direkt benennen:

```text
T_evap = Register 2049

T_off  = fan_param +0x1C  = Register 1102
T_low  = fan_param +0x04  = Register 1062
T_high = fan_param +0x02  = Register 1060

S_low  = fan_param +0x0A  = Register 1081
S_high = fan_param +0x12  = Register 1103
```

Die Firmware bildet sinngemäß:

```text
wenn T_evap <= T_off:
    S = 0

sonst wenn T_evap <= T_low:
    S = S_low

sonst wenn T_evap >= T_high:
    S = S_high

sonst:
    S = S_low
        + (T_evap - T_low)
          × (S_high - S_low)
          / (T_high - T_low)
```

Das ist eine echte lineare Interpolation zwischen zwei Temperaturstützpunkten.

Funktional ergibt sich:

```text
Lüfter-Sollwert
  ^
  |                    ───────── S_high
  |                  /
  |                /
  |──────── S_low /
  |
  | 0
  +--------------------------------→ Verdampfertemperatur
      T_off   T_low        T_high
```

**Bewertung: bestätigt.**

---

## 10. Alternative Kennlinie

Ein zweiter Regelmodus innerhalb derselben zentralen Lüfterfunktion verwendet analog:

```text
Register 1068 / Live +0x08
Register 1066 / Live +0x06
Register 1083 / Live +0x0C
Register 1104 / Live +0x14
```

als Temperatur- und Sollwertstützpunkte.

Auch dieser Pfad interpoliert abhängig von derselben Verdampfertemperatur und benutzt damit keine völlig andere Sensorquelle.

Die Umschaltung hängt von der Lüfter-/Maschinenkonfiguration und Betriebsart ab.

**Bewertung: bestätigt** für Kennlinienstruktur und Sensorquelle; **sehr wahrscheinlich** für die exakte PHNIX-Bezeichnung der beiden Kennlinienmodi.

---

## 11. Außentemperatur als zusätzliche obere Begrenzung

Neben der Verdampfertemperatur ruft der Regler auch den bereits bekannten Außentemperatur-Helper auf:

```text
0x0808799C
```

Dieser liefert T04 / Außentemperatur.

In mehreren Außentemperaturbändern wird daraus ein zusätzlicher Lüfter-Grenzwert gebildet. Dabei verwendet der Code unter anderem die Faktoren:

```text
0.8
0.6
```

auf hohe Lüfterreferenzwerte.

Der anschließend berechnete Wert wird als obere Begrenzung benutzt:

```text
wenn AT_Limit != 0 und AT_Limit < Kennlinienwert:
    Lüfter-Soll = AT_Limit
```

Damit ist die Struktur:

```text
Verdampfertemperatur-Kennlinie
        ↓
primärer Sollwert
        ↓
Außentemperaturabhängiges Limit
        ↓
begrenzter Lüfter-Sollwert
```

Im Code sind mehrere T04-Bänder mit Stützpunkten unter anderem im Bereich um hohe positive Außentemperaturen sowie im kalten Bereich vorhanden.

Die exakte Bezeichnung der zugehörigen Engineeringparameter ist noch offen, die 0,6-/0,8-Skalierung und die Limitfunktion sind direkt nachgewiesen.

**Bewertung: bestätigt.**

---

## 12. Einfluss des Kompressorzustands

Zusätzliche Betriebsbedingungen können den normalen Kennlinienwert überschreiben bzw. auf einen definierten Anteil eines hohen Lüfterreferenzwertes setzen.

Direkt im Code vorhanden ist unter anderem:

```text
Soll = (2 × Referenz) / 3
```

Je nach Kennlinien-/Betriebszweig wird dabei eine der hohen Referenzen verwendet:

```text
Register 1103
oder
Register 1104
```

Damit reagiert die Lüftersteuerung nicht ausschließlich auf die Verdampfertemperatur, sondern besitzt besondere Verdichter-/Betriebszustände mit definierter Drehzahlvorgabe.

**Bewertung: bestätigt.**

---

## 13. Zweiter Lüfter und Kanalzuordnung

Die Firmware führt zwei Sollkanäle:

```text
Kanal 1 = 0x20016F0A
Kanal 2 = 0x20016F0C
```

Ein Parameter bei:

```text
0x20016A04 +0x18
= Register 1074
```

entscheidet in mehreren Pfaden darüber, ob Kanal 2 ebenfalls angesteuert wird.

Je nach Konfiguration/Betriebszustand kann Kanal 2:

- `0` bleiben
- den Wert von Kanal 1 übernehmen
- durch einen Sonderpfad separat gesetzt werden

Damit unterstützt dieselbe V3.3 sowohl Ein- als auch Zwei-Lüfter-Konfigurationen.

**Bewertung: bestätigt.**

---

## 14. Hauptkonfiguration Register 1059

Der Wert:

```text
0x20016A04 +0x00
= Register 1059
```

wird im Lüftercode als übergeordneter Konfigurations-/Topologiewert ausgewertet.

Beobachtete relevante Werte sind unter anderem:

```text
0
3
4
```

Bei Konfiguration `0` werden die Lüfter-Sollkanäle in den entsprechenden Pfaden auf `0` gesetzt. Werte 3/4 aktivieren dagegen konkrete Regel-/Kanalpfade.

Aufgrund der Parameterstruktur ist Register 1059 **sehr wahrscheinlich F01 / Fan-Motor-Konfiguration bzw. Fan Mode**.

Die funktionale Rolle ist bestätigt; die exakte deutsche Tabellenbezeichnung wird bis zur erneuten Gegenprüfung der Originalparameterliste bewusst nicht härter benannt.

---

## 15. Schutzübersteuerung

Die normale Kennlinie ist nicht die letzte Instanz.

Bei bestimmten internen Schutzflags in der Struktur um:

```text
0x20016E0C
```

wird während laufender Anlage der Lüfter-Sollwert direkt überschrieben.

Der Code benutzt dabei unter anderem:

```text
Soll Kanal 1 = (2 × Register-1104-Referenz) / 3
```

und lässt Kanal 2 bei vorhandener Zwei-Lüfter-Konfiguration folgen.

Damit können Schutzfunktionen eine feste, von der normalen Verdampfertemperaturkennlinie unabhängige Lüftervorgabe erzwingen.

**Bewertung: bestätigt.**

---

## 16. Abtauung überschreibt den Normalregler

Die Abtau-State-Machine schreibt direkt auf:

```text
0x20016F0A
0x20016F0C
```

und kann daher den normalen Lüfterregler vollständig übersteuern.

Je nach Defrost-State werden:

- beide Lüfter auf `0` gesetzt
- ein spezieller Abtau-Sollwert gebildet
- Kanal 2 abhängig von der Zwei-Lüfter-Konfiguration mitgeführt oder abgeschaltet

Damit gilt:

```text
Normalbetrieb
    → Verdampfertemperatur-Kennlinie + AT-Limit + Schutzlogik

Abtauung
    → eigener Defrost-Lüfterpfad
```

**Bewertung: bestätigt.**

---

## 17. Internes Fan-Command-Active-Flag

Am Ende der Sollwertbildung prüft die Firmware:

```text
0x20016F0A != 0
oder
0x20016F0C != 0
```

und setzt bzw. löscht daraufhin ein internes Flag im Bereich `0x20016E0C`.

Dieses Flag bedeutet funktional:

```text
Mainboard fordert mindestens einen Lüfter an
```

Es ist ausdrücklich **nicht identisch** mit Register 2019 Bit 2.

Unterschied:

```text
internes Command-Flag
    = Sollbefehl ungleich 0

2019 Bit 2
    = tatsächliche Lüfterrückmeldung ungleich 0
```

Das ist für Diagnose und Fehlersuche wichtig: Ein Sollbefehl kann existieren, obwohl noch keine reale Lüfterrückmeldung anliegt.

---

## 18. Register 2108 – Fan Mute Flag / verwandter Status

Im Hauptstatusbereich existiert zusätzlich Register 2108, das in älteren Display-/ASM-Unterlagen als:

```text
Lüfter-Stummschalt-Flag / Fan Mute Flag
```

bezeichnet wird.

Der V3.3-Statusbuilder erzeugt diesen Wert aus mehreren internen Lauf-/Statusbedingungen als kleinen Statuswert.

Er ist **nicht der primäre Lüfter-Sollwert**, nicht die tatsächliche Drehzahl und auch nicht die Grundlage von Register 2019 Bit 2.

Für die eigentliche Fan-Regelung sind 2074–2076 und die oben beschriebenen RAM-Kanäle die wichtigeren Anker.

**Bewertung: bestätigt** für Trennung vom Hauptregler; die vollständige semantische Bedeutung aller 2108-Zustände bleibt ein eigener kleiner Restpunkt.

---

## 19. Gesamt-Datenfluss

```text
                    T04 Außentemperatur
                           │
                           ▼
                    zusätzliches Limit
                           │
                           │
Register 2049              │
Verdampfertemperatur       │
       │                   │
       ▼                   │
stückweise lineare         │
Lüfterkennlinie ───────────┘
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
0x20016F0A / 0x20016F0C
       │
       ├────────────→ 2076 veröffentlicht Kanal 1
       │
       ▼
FC10 Remote 2008 / 2009
       │
       ▼
Leistungs-/Lüftermodul
       │
       ▼
reale Lüfter
       │
       ▼
Bus-Rückmeldung
       │
       ▼
0x2001691C +0x0C / +0x0E
       │
       ├────────→ 2074 / 2075
       │
       └────────→ 2019 Bit 2
```

---

## 20. Praktische Diagnosemöglichkeiten über Modbus

Mit den öffentlichen Registern lässt sich die Fan-Kette recht gut beobachten:

```text
2048 = Außentemperatur
2049 = Verdampfertemperatur
2074 = Lüfter 1 Ist/Rückmeldung
2075 = Lüfter 2 Ist/Rückmeldung
2076 = Lüfter Soll Kanal 1
2019 Bit 2 = mindestens ein Lüfter tatsächlich aktiv
```

Damit kann man beispielsweise unterscheiden:

### Soll vorhanden, Lüfter steht

```text
2076 > 0
2074 = 0
2075 = 0
2019 Bit 2 = 0
```

→ Mainboard fordert Lüfter an, es kommt aber keine tatsächliche Lüfterrückmeldung.

### Normaler laufender Lüfter

```text
2076 > 0
2074 > 0
2019 Bit 2 = 1
```

### Zwei-Lüfter-Betrieb

```text
2074 > 0
2075 > 0
2019 Bit 2 = 1
```

### Abtau-/Sonderzustand

2076 bzw. die tatsächlichen Lüfterwerte können bewusst von der normalen, aus 2049 erwartbaren Kennlinie abweichen, weil Defrost- und Schutzpfade direkt auf die Sollkanäle schreiben.

---

## 21. Was noch offen ist

Der Regelblock ist funktional weitgehend geschlossen. Offen bleiben vor allem die Benennungen und Varianten:

1. exakte offizielle Fxx-Namen, Min/Max/Default der verstreuten Register 1059, 1060, 1062, 1066, 1068, 1074, 1081, 1083, 1087, 1089, 1101–1104
2. exakte physikalische Einheit/Skalierung der rohen Lüfter-Soll- und Istwerte 2074–2076
3. vollständige Zuordnung aller Hardwareplattformvarianten des empfangenen und gesendeten Remote-Frames
4. vollständige semantische Auflösung von Register 2108
5. praktische Live-Gegenprobe der Kennlinie mit gleichzeitigem Log von 2048, 2049 und 2074–2076

Die Hauptarchitektur, Sensorquelle, Kennlinienform, Soll-/Ist-Trennung, Zwei-Lüfter-Unterstützung, Schutz-/Defrost-Overrides und der Buspfad sind dagegen direkt aus dem V3.3-Binary belegt.

---

## 22. Zusammenhang mit anderen Analysen

Siehe außerdem:

- `FW3.3-ERKENNTNISSE.md` – zentrale Gesamtübersicht
- `FW3.3-EEV-SMART-REGELUNG.md` – EEV-/Smart-Regelung
- `FW3.3-OELRUECKFUEHRUNG.md` – Ölrückführungszyklus und externe Rekonstruktion
