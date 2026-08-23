# Mainboard-Firmware V3.3 – interner Modbus, Boardadressen und Antriebsboard

Stand: 24. August 2026

Diese Datei dokumentiert die interne Modbus-Kommunikationsarchitektur der PHNIX-/FoxAir-Mainboard-Firmware `82400644 / V3.3` und ordnet die im Busverkehr sichtbaren Slave-Adressen ihren funktionalen Boards zu.

Die Analyse verbindet drei Quellen:

1. das Mainboard-Binary `phnixIot_device_OTA`,
2. die statisch rekonstruierte Sende-/Empfangslogik der V3.3,
3. reale Busmitschnitte der laufenden FoxAir-Anlage.

Untersuchtes Binary:

```text
Größe:       287598 Byte
MD5:         CEB6A4BF386FF644E23E410023E74673
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:  0x08050000
```

Bewertung:

- **bestätigt** – direkt im Binary bzw. zusätzlich im realen Busverkehr nachgewiesen
- **sehr wahrscheinlich** – Datenfluss ist geschlossen, nur die genaue physische Boardbezeichnung/Revision fehlt
- **Hypothese** – plausible, aber noch nicht ausreichend geschlossene Zuordnung

---

# 1. Kurzfazit

Die V3.3 ist auf dem hier untersuchten internen Bus nicht nur Modbus-Slave, sondern betreibt einen eigenen zyklischen **Modbus-Master-Scheduler** für mehrere interne Teilnehmer.

Für die konkrete untersuchte Anlage ergibt sich:

```text
Mainboard V3.3
Modbus-Master des internen Rings
        │
        ├── 0x01  Verdichter-/Leistungs-/Inverterboard
        │         ├── Verdichter-Sollfrequenz
        │         ├── Verdichter-Telemetrie
        │         └── bei H33=1 zusätzlich Fan-Driver-Kanäle
        │
        ├── 0x03  DWIN-/Wire-Controller/HMI
        │
        ├── 0x02  zweiter/optionaler HMI-Teilnehmer
        │
        ├── 0x04  separater Fan-Motor-Driver-Pfad
        │
        └── 0x05  Hydraulikmodulpfad
                  alternativ 0x61 bei H30 == 3
```

Zusätzlich sendet das Mainboard seine öffentlichen Statusblöcke per Modbus-Broadcast `0x00`.

Die wichtigste Erkenntnis für die reale FoxAir:

> **H33 ist aktiv und heißt offiziell „Fan Motor Driver and Comp. Driver Integrated“.** Deshalb benutzt die konkrete Anlage den erweiterten Unit-`0x01`-Dialog mit 16 Sollwert- und 51 Rückmelde-Registern. Kompressor und Lüfter sind damit in dieser Hardwarekonfiguration kommunikativ auf demselben Antriebs-/Leistungsboard zusammengeführt.

Der separate Unit-`0x04`-Fan-Driver wird von der Firmware trotzdem unterstützt und zyklisch abgefragt. Im untersuchten Mitschnitt antwortet Unit `0x04` jedoch nicht.

**Bewertung: bestätigt** für H33-Weiche, Telegrammlängen und Unit-`0x01`-Datenfluss; **sehr wahrscheinlich** für die physische Beschreibung als zweites Leistungsboard, solange dessen konkrete Platinenbezeichnung/Hersteller-P/N noch nicht abgelesen wurde.

---

# 2. Zentraler Modbus-Master-Builder

Die Funktion bei:

```text
0x080695F0
```

baut die Modbus-RTU-Anfragen für den internen Scheduler.

Die Argumente lassen sich direkt rekonstruieren als:

```text
r0 = Slave-Adresse
r1 = Function Code
r2 = Datenpuffer
r3 = Startregister
Stack-Argument = Anzahl Register/Wörter
```

Unterstützt werden unter anderem:

```text
FC01
FC02
FC03
FC04
FC10
```

Die CRC-Berechnung läuft über die bereits bekannte Modbus-CRC-Routine:

```text
0x0805094E
```

Damit ist die nachfolgende Adresstabelle nicht aus Busbeobachtungen geraten, sondern direkt aus den Aufrufargumenten des Mainboardcodes abgeleitet.

**Bewertung: bestätigt.**

---

# 3. Zyklischer Kommunikations-Scheduler

Die zentrale zyklische State-Machine liegt ungefähr bei:

```text
0x08064C40 … 0x08064FC6
```

Scheduler-State:

```text
0x20016FCE
```

Sie läuft über zehn Zustände `0…9` und beginnt danach wieder bei `0`.

## 3.1 Vollständige Scheduler-Tabelle

| State | Slave | FC | Start | Anzahl | Puffer | Funktion |
|---:|---:|---:|---:|---:|---:|---|
| 0 | `0x03` | 03 | 3001 | 21 | `0x20012660` | HMI-/Display-Status lesen |
| 1 | `0x02` | 03 | 3001 | 21 | `0x20012660` | zweiter HMI-/Controller-Kanal |
| 2 | `0x00` | 10 | 2001 | 90 | `0x20011900` | Mainboard-Status 2001–2090 broadcasten |
| 3 | `0x00` | 10 | 2091 | 90 | `0x200119B4` | Mainboard-Status 2091–2180 broadcasten |
| 4 | `0x04` | 03 | 1011 | 14 | `0x200122D8` | separaten Fan-Driver lesen |
| 5 | `0x01` | 10 | 1999 | 5 oder 16 | `0x2001232C` | Verdichter-/Antriebsboard Sollwerte schreiben |
| 6 | `0x01` | 03 | 2099 | 22 oder 51 | `0x2001232C` / RX-Abbild | Verdichter-/Antriebsboard Telemetrie lesen |
| 7 | `0x05` | 03 | 2000 | 90 | `0x20012444` | Hydraulik-/Erweiterungsmodul lesen |
| 7 alt. | `0x61` | 03 | 2001 | 90 | `0x200125AC` | H30==3: alternative Modulvariante lesen |
| 8 | `0x05` | 10 | 1001 | 90 | `0x20012390` | Hydraulik-/Erweiterungsmodul schreiben |
| 8 alt. | `0x61` | 10 | 1001 | 90 | `0x200124F8` | H30==3: alternative Modulvariante schreiben |
| 9 | – | – | – | – | – | kein reguläres neues Telegramm / Zyklusabschluss |

**Bewertung: bestätigt.**

---

# 4. Unit 0x01 – Verdichter-/Leistungs-/Inverterboard

Unit `0x01` ist der am stärksten geschlossene interne Teilnehmer.

Der Mainboardcode schreibt:

```text
Slave:         0x01
FC:            0x10
Startregister: 1999 / 0x07CF
```

und liest anschließend:

```text
Slave:         0x01
FC:            0x03
Startregister: 2099 / 0x0833
```

Diese Folge ist auch im realen Mitschnitt vorhanden, einschließlich FC10-ACK und FC03-Antwort.

Damit ist Unit `0x01` **ein real vorhandener Teilnehmer der untersuchten Anlage**.

---

# 5. H33 entscheidet über integrierte Lüfteransteuerung

Der Schalter liegt in der H-Parameterstruktur bei:

```text
0x20016774 + 0x28
```

Da:

```text
0x20016774 + 0x2A = Register 1020 = H34
```

ist der unmittelbar vorhergehende Parameter:

```text
Register 1019 = H33
```

Die offizielle Parameterbezeichnung lautet:

```text
H33 = Fan Motor Driver and Comp. Driver Integrated
0 = No
1 = Yes
```

Diese Bezeichnung passt exakt zum Firmwareverhalten.

## H33 = 0

Unit `0x01` bekommt nur den kurzen Verdichterdialog:

```text
FC10 1999, 5 Wörter
FC03 2099, 22 Wörter
```

## H33 != 0

Der Dialog wird erweitert auf:

```text
FC10 1999, 16 Wörter
FC03 2099, 51 Wörter
```

In diesen Zusatzwörtern liegen die Lüfter-Soll- und Rückmeldekanäle.

## Reale Anlage

Im untersuchten Mitschnitt läuft:

```text
01 10 07 CF 00 10 ...
                 ^^^^
                 16 Wörter
```

und danach:

```text
01 03 08 33 00 33 ...
                 ^^^^
                 51 Wörter
```

Damit ist für die untersuchte FoxAir-Konfiguration praktisch bestätigt:

```text
H33 = integriert
```

und somit:

```text
Verdichterdriver + Fan-Motor-Driver
        ↓
kommunikativ gemeinsam über Unit 0x01
```

**Bewertung: bestätigt.**

---

# 6. Unit-0x01-Sollwerttelegramm ab Register 1999

Sendepuffer:

```text
0x2001232C
```

Bestätigte Felder:

| Unit-1-Register | Puffer | Quelle | Funktion |
|---:|---:|---|---|
| 1999 | `+0x00` | `0x20016AA4+0x08` | Kompressor-Sollfrequenz / Mainboard-Reg. 2071 |
| 2000 | `+0x02` | aus Sollfrequenz + internem Modusflag | Run-/Mode-Wort, Werte u. a. 0/1/3 |
| 2001 | `+0x04` | konstant 0 | noch nicht semantisch benannt |
| 2002 | `+0x06` | `0x200162D8+0x5C` | aktives Steuer-/Statuswort, Bedeutung noch offen |
| 2003 | `+0x08` | C04/Kompressormodell, ggf. `+0x083A` | Driver-/Modellcode |
| 2006 | `+0x0E` | Fan-Konfiguration | Fan-Driver-Selektor 1/2 |
| 2007 | `+0x10` | Fan-Konfiguration | zweiter Fan-Driver-Selektor 1/2 |
| 2008 | `+0x12` | `0x20016F0A` | Lüfter-Sollwert 1 |
| 2009 | `+0x14` | `0x20016F0C` | Lüfter-Sollwert 2 |
| 2010 | `+0x16` | konstant 0 | noch nicht benannt |

Die Register 2006–2010 werden nur im H33-erweiterten Pfad aufgebaut.

Die Fan-Driver-Selektoren werden aus dem ersten Wert des Fan-Parameterblocks `0x20016A04` gebildet:

```text
Fan-Konfigurationswert 3 → 1
Fan-Konfigurationswert 4 → 2
sonst                    → 1
```

Die genaue Herstellersemantik der Werte `1/2` bleibt noch offen.

---

# 7. Kompressoransteuerung über Unit 0x01

Die bekannte interne Sollfrequenz liegt bei:

```text
0x20016AA4 + 0x08
```

und wird öffentlich als:

```text
Register 2071 = Kompressor-Sollfrequenz
```

bereitgestellt.

Der Mainboardcode übernimmt genau diesen Wert als erstes Wort des Unit-`0x01`-FC10-Pakets:

```text
2071
 ↓
0x20016AA4+0x08
 ↓
Unit 0x01 / FC10 / Register 1999
 ↓
Leistungs-/Inverterboard
```

Damit ist bestätigt:

> Das V3.3-Mainboard erzeugt nicht selbst die Leistungselektronik/PWM für den Verdichter. Es berechnet die Sollfrequenz und übergibt sie digital per Modbus an Unit `0x01`.

Die eigentliche Motor-/Leistungsregelung findet damit auf dem externen Inverter-/Leistungsboard statt.

**Bewertung: bestätigt.**

---

# 8. Unit-0x01-Rückmeldungen ab Register 2099

Die Antwort wird in die interne Inverterstruktur:

```text
0x200168C4
```

übernommen.

Der Anfang des Pakets ist bytegenau zuordenbar:

| Unit-1-Reg. | internes Ziel | bekannte Bedeutung |
|---:|---:|---|
| 2099 | `0x200168C4+0x00` | noch offen |
| 2100 | `+0x02` | noch offen |
| 2101 | `+0x04` | noch offen |
| 2102 | `+0x06` | Kompressor-Istfrequenz → Mainboard-Reg. 2072 |
| 2103 | `+0x08` | maximale Inverter-/Kompressorfrequenz → Reg. 2073 |
| 2104 | `+0x0A` | noch nicht endgültig benannt |
| 2105 | `+0x0C` | AC-Eingangsspannung → Mainboard-Reg. 2062 |
| 2106 | `+0x0E` | AC-Eingangsstrom → Mainboard-Reg. 2057 |
| 2107 | `+0x10` | Kompressor-Phasenstrom → Mainboard-Reg. 2042 |
| 2108 | `+0x12` | DC-Bus-Spannung → Mainboard-Reg. 2043 |

Der reale Busmitschnitt passt dazu sehr gut: bei stillstehendem Verdichter liefert Unit `0x01` beispielsweise um 229 V am entsprechenden AC-Spannungswort und etwa 313 V DC-Bus.

**Bewertung: bestätigt.**

Wichtig für die Busanalyse:

> Die Registerzahlen `2099+` in einer Unit-`0x01`-Antwort sind **Register des Inverterboards**, nicht die gleichnamigen öffentlichen Mainboardregister. Erst der Mainboardcode überführt sie in seine eigenen öffentlichen Register.

---

# 9. H33-erweiterte Lüfterkanäle in Unit 0x01

Bei H33 aktiv wertet der RX-Pfad zusätzliche Wörter aus dem 51-Wort-Block aus.

Bestätigt sind insbesondere:

```text
Unit-1-Reg. 2130
    → 0x2001691C + 0x0C
    → Lüfter-Istwert 1
    → öffentlich Register 2074

Unit-1-Reg. 2142
    → 0x2001691C + 0x0E
    → Lüfter-Istwert 2
    → öffentlich Register 2075
```

Damit ist der vollständige Lüfterring in der integrierten Variante geschlossen:

```text
Mainboard-Lüfterregler
    ↓
0x20016F0A / 0x20016F0C
    ↓
Unit 0x01, Reg. 2008 / 2009
    ↓
integrierter Fan-Motor-Driver
    ↓
Unit 0x01, Reg. 2130 / 2142
    ↓
0x2001691C+0x0C/+0x0E
    ↓
Mainboard 2074 / 2075
```

**Bewertung: bestätigt.**

---

# 10. Erweiterte Fan-Driver-Telemetrie über Unit 0x01

Für eine bestimmte Fan-Driver-Konfiguration (`0x20016A04[0] == 4`) werden weitere Unit-`0x01`-Rückmeldungen ausgewertet.

Unter anderem:

```text
Unit-1-Reg. 2135 → internes Byte 0x200168C4+0x26
Unit-1-Reg. 2136 → 0x200168C4+0x24
Unit-1-Reg. 2123 → 0x200168C4+0x28
Unit-1-Reg. 2133 → Statusanteil 0x200168C4+0x2A
```

Daraus baut der öffentliche Mainboard-Status unter anderem:

```text
2130 = IPM-Temperatur des externen Lüftermotorantriebs
2131 = Leistung des externen Lüftermotorantriebs
2132 = Strom des externen Lüftermotorantriebs
```

Die genaue Skalierung einzelner Unit-`0x01`-Rohwerte wird noch separat benannt; die Provenance zum H33-erweiterten Inverterpaket ist geschlossen.

**Bewertung: bestätigt.**

---

# 11. Unit 0x04 – separater Fan-Motor-Driver-Pfad

Unabhängig vom H33-erweiterten Unit-`0x01`-Pfad kennt die Firmware einen weiteren Teilnehmer:

```text
Slave:         0x04
FC:            0x03
Startregister: 1011
Anzahl:        14 Wörter
Zielpuffer:    0x200122D8
```

Die Antwort wird im RX-Handler ab ungefähr:

```text
0x08065B1E
```

verarbeitet.

Die 14 Wörter entsprechen Unit-4-Registern:

```text
1011 … 1024
```

Direkt nachgewiesene Übernahmen:

| Unit-4-Reg. | internes Ziel | Funktion |
|---:|---:|---|
| 1011 | `0x2001691C+0x1E` Low-Byte | Fan-Driver-Konfiguration/Status |
| 1012 | `0x2001691C+0x14` | Konfigurations-/Modellwert |
| 1013 | `0x2001691C+0x12` | weiterer Fan-Driver-Wert |
| 1017 | `0x2001691C+0x0C` | Lüfter-Istwert 1 → 2074 |
| 1018 | `0x2001691C+0x0E` | Lüfter-Istwert 2 → 2075 |
| 1019 | `0x2001691C+0x22` Low-Byte | Status/Typ |
| 1020 | `0x2001691C+0x23` Low-Byte | Status/Typ |
| 1021 | `0x2001691C+0x06` | weiterer Drive-Wert |

Damit ist die Funktion dieses Teilnehmers als **separater Lüftermotor-Driver-Pfad** sehr stark geschlossen.

Die V3.3 unterstützt folglich mindestens zwei Fan-Kommunikationsarchitekturen:

```text
A) H33 integriert
   Lüfterkanäle über Unit 0x01 zusammen mit dem Verdichterdriver

B) separater Fan-Driver
   Rückmeldungen über Unit 0x04 / Register 1011…1024
```

Ob Unit `0x04` bei bestimmten Varianten zusätzlich oder statt des integrierten Pfads verwendet wird, hängt von der Hardwarekonfiguration ab. Eine harte gegenseitige Exklusivität wird nicht behauptet, weil die Firmware Unit `0x04` auch bei aktivem H33 weiterhin pollt.

## Reale Anlage

Im vorhandenen Mitschnitt ist regelmäßig sichtbar:

```text
04 03 03 F3 00 0E ...
```

also die Anfrage an Unit `0x04`.

Eine gültige Unit-`0x04`-Antwort wurde in diesem Mitschnitt jedoch nicht beobachtet.

Das passt dazu, dass die reale Anlage H33-integriert über Unit `0x01` arbeitet.

**Bewertung:** Polling bestätigt; konkrete Abwesenheit nur für den untersuchten Mitschnitt bestätigt.

---

# 12. Unit 0x03 – DWIN-/Wire-Controller/HMI

Die Firmware fragt zyklisch:

```text
Slave:         0x03
FC03
Start:         3001
Anzahl:        21
```

Die reale Anlage antwortet auf diesen Block.

Im Antworttelegramm wurden unter anderem beobachtet:

```text
3012 = 463  → Display-Softwarecode
3013 = 17   → Display-Softwareversion V1.7
```

Damit ist Unit `0x03` als aktives DWIN-/Wire-Controller-/HMI der untersuchten Anlage **bestätigt**.

---

# 13. Unit 0x02 – zweiter/optionaler HMI-Kanal

Unmittelbar nach Unit `0x03` sendet der Scheduler exakt dieselbe Abfrage an:

```text
Slave: 0x02
FC03
3001, 21 Wörter
```

Der gemeinsame Zielpuffer ist ebenfalls:

```text
0x20012660
```

Damit gehört Unit `0x02` eindeutig zur selben Kommunikationsklasse wie Unit `0x03`.

Die physische Funktion ist **sehr wahrscheinlich** ein zweiter/alternativer Wire-Controller bzw. HMI-Teilnehmer.

Im untersuchten Mitschnitt wird Unit `0x02` abgefragt, aber es wurde keine gültige Antwort beobachtet.

---

# 14. Broadcast 0x00 – Mainboard veröffentlicht Status

Die beiden Schedulerzustände 2 und 3 senden per FC10 an Slave `0x00`:

```text
2001 … 2090  = 90 Wörter
2091 … 2180  = 90 Wörter
```

Da `0x00` die Modbus-Broadcast-Adresse ist, gibt es hier keinen einzelnen Ziel-Slave.

Das Mainboard verteilt damit seinen kompletten öffentlichen Laufzeit-/Statusblock an alle mithörenden internen Teilnehmer:

```text
Mainboard
   │
   ├── FC10 Broadcast 2001–2090
   └── FC10 Broadcast 2091–2180
        ↓
Display / Controller / weitere Teilnehmer
```

Die Broadcasts sind im realen Mitschnitt regelmäßig sichtbar.

**Bewertung: bestätigt.**

---

# 15. Unit 0x05 / 0x61 – Hydraulik-/Erweiterungsmodulpfad

Die Auswahl wird durch:

```text
0x20016774 + 0x1C
```

bestimmt.

Dieser Parameter ist:

```text
Register 1036 = H30 = Enable Hydraulic Module
```

Die Firmware behandelt speziell den Wert:

```text
H30 == 3
```

## H30 != 3

```text
Slave 0x05
FC03 2000, 90 Wörter
FC10 1001, 90 Wörter
```

## H30 == 3

```text
Slave 0x61
FC03 2001, 90 Wörter
FC10 1001, 90 Wörter
```

Damit sind `0x05` und `0x61` keine zufälligen unabhängigen Geräte. Sie sind zwei alternative Kommunikationsvarianten desselben durch H30 gewählten Hydraulik-/Erweiterungsmodulpfads.

Die genaue physische PHNIX-Platinenbezeichnung der beiden Varianten ist noch offen.

Im Mitschnitt der untersuchten Anlage wird Unit `0x05` angesprochen; Unit `0x61` erscheint nicht. Daraus folgt nur sicher:

```text
H30 != 3
```

Eine gültige Unit-`0x05`-Antwort ist im untersuchten Ausschnitt nicht nachgewiesen.

**Funktionale Zuordnung Hydraulikmodulpfad: bestätigt. Exakte Boardrevision: offen.**

---

# 16. Unit 0x63 / 99 – nicht mit dem internen Masterring verwechseln

Aus der separaten OTA-/Warmlink-Analyse ist bekannt:

```text
Slave 0x63 = 99
```

Die Mainboard-Firmware besitzt dafür einen Slave-/Servicepfad, unter anderem für:

```text
OTA 0xCxxx
Engineering-/Servicekommunikation
internes Registerfenster 8001–8090
```

Dieser Pfad hat eine andere Rollenrichtung:

```text
LTE-/Warmlink bzw. externer Master
       ↓
Mainboard als Slave 0x63
```

Der hier dokumentierte interne Scheduler arbeitet dagegen als:

```text
Mainboard als Master
       ↓
0x01 / 0x02 / 0x03 / 0x04 / 0x05 bzw. 0x61
```

Deshalb dürfen beide Rollen nicht einfach zu einer einzigen Adresstabelle ohne Buskontext zusammengezogen werden.

**Noch offen:** Ob beide logischen Pfade auf derselben physikalischen UART-/RS485-Schnittstelle oder auf unterschiedlichen UARTs liegen. Erst die Rückverfolgung bis USART/GPIO/Transceiver kann das abschließend beantworten.

---

# 17. Aktuell beobachtete Teilnehmer der realen Anlage

Aus Binary + Mitschnitt ergibt sich für die konkrete Testanlage:

| Adresse | Schedulerfunktion | Anfrage sichtbar | Antwort sichtbar | Bewertung für reale Anlage |
|---:|---|---|---|---|
| `0x00` | Status-Broadcast | ja | keine vorgesehen | aktiv |
| `0x01` | Verdichter-/integriertes Antriebsboard | ja | **ja** | **aktiv, bestätigt** |
| `0x02` | optionaler HMI-Kanal | ja | nein | nicht belegt / nicht antwortend |
| `0x03` | DWIN-/Wire-Controller | ja | **ja** | **aktiv, bestätigt** |
| `0x04` | separater Fan-Driver | ja | nein | nicht belegt / nicht antwortend im Mitschnitt |
| `0x05` | Hydraulik-/Erweiterungsmodulpfad | ja | nicht belegt | H30-Pfad gewählt, Modulstatus offen |
| `0x61` | alternative H30-Modulvariante | nein | nein | in aktueller Konfiguration nicht gewählt |
| `0x63` | Mainboard-Slave für Service/OTA | anderer Pfad | separat bekannt | nicht Teil dieses Master-Schedulerzyklus |

---

# 18. Konsequenz für die Hardwarevermutung

Die Ausgangsvermutung war, dass ein zweites Mainboard mit Leistungselektronik Verdichter und wahrscheinlich auch Lüfter übernimmt.

Die Firmware bestätigt genau diese Architektur für H33-integrierte Geräte:

```text
Regel-Mainboard
    │
    │ Modbus
    ▼
Unit 0x01
Leistungs-/Inverterboard
    ├── Kompressorleistung
    ├── Kompressorfrequenz
    ├── DC-Bus / Ströme / Spannungen
    └── integrierte Lüfterdriver-Kanäle
```

Das Regel-Mainboard entscheidet also über:

- Sollfrequenz,
- Betriebszustand,
- Lüfter-Sollwerte,
- Schutz-/Defrost-Overrides,

aber die eigentliche elektrische Leistungsansteuerung von Verdichter und – bei H33=1 – Lüftern sitzt auf dem externen Antriebsboard.

**Bewertung: bestätigt für die Kommunikationsarchitektur; physische P/N des Boards noch offen.**

---

# 19. Diagnosemöglichkeiten nur über Modbus

Mit dieser Zuordnung kann ein passiver Mitschnitt die Boards separat überwachen.

## Antriebsboard Unit 0x01

Erwarteter Zyklus bei H33=1:

```text
01 10 07 CF 00 10 ...   FC10, 16 Wörter
01 10 07 CF 00 10 ...   ACK
01 03 08 33 00 33 ...   FC03, 51 Wörter
01 03 66 ...             Antwort
```

Fehlt die Antwort von `0x01`, obwohl das Mainboard weiter pollt, liegt eine Störung der Kommunikation zum Leistungs-/Inverterboard nahe.

## Display Unit 0x03

```text
03 03 0B B9 00 15 ...
03 03 2A ...
```

## Separater Fan-Drive Unit 0x04

```text
04 03 03 F3 00 0E ...
```

Wenn eine Gerätevariante Unit `0x04` tatsächlich besitzt, muss darauf eine 14-Wort-Antwort folgen.

Damit ist künftig auch eine automatische Board-Topologieerkennung aus einem passiven Busmitschnitt möglich.

---

# 20. Noch offene Punkte

Für einen vollständig physikalischen Schaltplan fehlen noch:

1. **USART/UART-Zuordnung des internen Schedulers**
   - welcher STM32-USART
   - TX/RX-Pins
   - RS485-Transceiver
   - DE/RE-Pin

2. **physische Boardbezeichnung von Unit 0x01**
   - Platinen-P/N
   - Herstellerbezeichnung
   - verwendeter Inverter-/Motorcontroller

3. **Unit 0x04**
   - konkrete Fan-Driver-Platine/Modell
   - vollständige Benennung 1011–1024

4. **Unit 0x05 / 0x61**
   - genaue Hydraulikmodulrevision
   - vollständige Zuordnung der 90-Wort-Blöcke

5. **Unit 0x02**
   - genaue zweite HMI-/Controller-Variante

6. **Unit 0x01 FC10/FC03 vollständig benennen**
   - Run-/Mode-Wörter
   - alle H33-Erweiterungsregister
   - Fehler-/Statusbits

7. **externer Mainboard-Slavepfad**
   - H10 „Unit address“ gegen die verschiedenen Slave-Dispatcher abgleichen
   - physische Trennung bzw. Gemeinsamkeit mit dem internen Schedulerbus beweisen

---

# 21. Verwandte Analysen

- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) – eigentliche Lüfter-Sollwertberechnung, 2074/2075/2076 und Schutzpfade
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) – Oil-Return-Frequenzanforderung vor Übergabe an Unit 0x01
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md) – zentrale Gesamtübersicht

---

# 22. Arbeitsmodell

Für weitere Boardzuordnungen gilt ab jetzt die vollständige Kette:

```text
Regelalgorithmus im Mainboard
        ↓
interne Soll-/Istvariable
        ↓
Modbus-Schedulerstate
        ↓
Slave + FC + Remote-Register
        ↓
physisches internes Board
        ↓
Remote-Antwort
        ↓
Mainboard-RX-Parser
        ↓
öffentliche Register / Schutzlogik
```

Damit lassen sich die bislang nur im Display sichtbaren Modbus-Adressen reproduzierbar auf die tatsächlichen Funktionsblöcke der Wärmepumpe zurückführen.
