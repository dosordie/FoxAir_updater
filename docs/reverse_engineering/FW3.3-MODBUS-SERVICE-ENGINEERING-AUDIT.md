# Mainboard-Firmware V3.3 – Modbus Service-/Engineering-Audit

Stand: 24. August 2026

Diese Datei schließt die in der V3.3 implementierten **nicht-normalen Modbusbereiche** außerhalb der öffentlichen Mainboard-Parameter `1001–1540` und Statusregister `2001–2180`.

Untersuchtes Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
MD5:          CEB6A4BF386FF644E23E410023E74673
```

Bewertung:

- **bestätigt** – direkt im Binary geschlossen
- **sehr wahrscheinlich** – Datenfluss geschlossen, Herstellerlabel nicht vollständig bekannt
- **offen** – Adresse/Quelle klar, fachliche Einzelbedeutung noch nicht geschlossen

---

# 1. Ergebnis in Kurzform

V3.3 besitzt zusätzlich zum öffentlichen Mainboard-Modbus folgende Bereiche:

| Namespace | Register | RAM-Basis | Rolle |
|---|---:|---:|---|
| `ENG:A` | 5001–5090 | `0x20015158` | Engineering-Parameter-Schatten / Serviceprofil |
| `ENG:B` | 5091–5180 | `0x2001520C` | 90-Wort-Konfigurations-/Synchronisationsfenster |
| `DIAG` | 6001–6090 | `0x200152C0` | Live-Service-/Diagnosesnapshot |
| `ENG:CTRL` | 8801–8820 | `0x20016970` | Engineering-Steuerfenster; 8801 = virtueller SG-Ready-Zustand |
| `SPECIAL` | 60000 | – | Modbus-Adresse auf 1 zurücksetzen |
| `SPECIAL` | 60010 | UID-Puffer `0x20016DCC` | UID-gebundene Modbus-Adress-Provisionierung |

Die Bereiche sind **nicht** einfach weitere öffentliche Benutzerparameter und sollten in Software separat benannt und abgesichert werden.

---

# 2. Gemeinsame Service-RAM-Struktur

Der große Engineering-/Diagnoseblock beginnt bei:

```text
0x20015158
```

Die ersten drei Fenster liegen direkt hintereinander:

```text
5001 → 0x20015158
5091 → 0x2001520C
6001 → 0x200152C0
```

Formeln:

```text
ENG:A 5001–5090:
RAM = 0x20015158 + 2*(reg-5001)

ENG:B 5091–5180:
RAM = 0x2001520C + 2*(reg-5091)

DIAG 6001–6090:
RAM = 0x200152C0 + 2*(reg-6001)
```

`8801–8820` liegt separat:

```text
8801 → 0x20016970
RAM = 0x20016970 + 2*(reg-8801)
```

**Bewertung: bestätigt.**

---

# 3. Vollständige Read-/Write-Matrix

| Bereich | FC03 | FC06 | FC10 | empfohlene Nutzung |
|---|---|---|---|---|
| MAIN 1001–1540 | ja | ja* | ja | normale Konfiguration |
| ENG:A 5001–5090 | ja | ja | ja | nur Engineering/Service |
| ENG:B 5091–5180 | ja** | nein | ja | Sync-/Transferfenster |
| DIAG 6001–6090 | ja | nein | nein | read-only Diagnose |
| ENG:CTRL 8801–8820 | ja | ja | ja | Advanced/Engineering |
| SPECIAL 60000 | – | Sonderkommando | – | Adressreset |
| SPECIAL 60010 | Sonder-Read | – | Sonder-Write | Adress-Provisionierung |

\* FC06 sperrt die sechs 10-Wort-Paketköpfe; siehe Parameter-Audit.  
\** Lesen von 5091–5180 hängt zusätzlich von einem internen Service-Statusbit ab.

**Bewertung: bestätigt.**

---

# 4. ENG:A 5001–5090 – Engineering-Parameter-Schatten

## 4.1 Rolle

Der Bereich `5001–5090` ist ein **kuratierter Service-/Engineering-Schatten ausgewählter aktiver Parameter**.

Die zentrale Synchronisationsroutine liegt um:

```text
0x080854F8 ff.
```

Sie arbeitet in zwei Richtungen.

### Normaler Spiegelbetrieb

Aktive Liveparameter aus verschiedenen V3.3-Strukturen werden in `5001–5090` kopiert, unter anderem aus:

```text
0x20016774   H-/Grundkonfiguration
0x2001656C   R-/Kennlinienblock
0x20016C6C   Pumpenparameter
0x200167A4   Timer-/Displayparameter
weitere Liveblöcke
```

Damit entsteht eine kompakte Engineering-Sicht auf wichtige Einstellungen.

### Apply-/Servicebetrieb

In einem speziellen Apply-Zustand wird die Richtung umgedreht:

```text
ENG:A 5001–5090
    ↓
aktive Live-Strukturen
```

Die Engineeringwerte werden also tatsächlich in die Regelparameter übernommen.

Damit ist `5001–5090` **kein Diagnoseblock** und auch kein zweites flaches Abbild von 1001–1540, sondern eine **reorganisierte Service-Parameteransicht**.

**Bewertung: bestätigt.**

## 4.2 Konsequenz für Software

- nicht als normale Benutzerparameter anzeigen
- lesen ist diagnostisch sinnvoll
- Schreiben kann reale Anlagenparameter verändern
- generisches „alle Register beschreibbar“-UI ist hier nicht empfehlenswert
- beim Reverse Engineering immer `ENG:A:5001` statt nur `5001` schreiben

---

# 5. ENG:B 5091–5180 – Synchronisations-/Forwardingfenster

## 5.1 Struktur

```text
5091 → 0x2001520C
90 Wörter
```

FC10-Schreiben legt die Werte zunächst in dieses Fenster und zusätzlich in einen internen Shadow-/Backupbereich.

Ein Statusflag bei:

```text
0x20015158 + 0x39A
```

fordert anschließend eine ausgehende Synchronisation an.

## 5.2 Ausgehender Transfer

Eine separate Kommunikations-State-Machine prüft dieses Flag und sendet dann:

```text
Slave: 0x63
FC:    0x10
Start: 5091
Qty:   90
Buffer: 0x2001520C
```

Danach wird das Requestflag wieder gelöscht.

Damit ist die Rolle geschlossen:

> `5091–5180` ist ein 90-Wort-Engineering-/Konfigurationsfenster, das zwischen Kommunikationsinstanzen synchronisiert bzw. an eine Unit-`0x63`-Instanz weitergereicht wird.

Die physische UART-Zuordnung dieser **ausgehenden** Unit-`0x63`-Instanz wurde in diesem Teil-Audit nicht erneut bis zum Transceiver verfolgt. Sie darf deshalb nicht allein wegen der Zahl `0x63` automatisch mit dem bekannten USART1-Service-Slavepfad gleichgesetzt werden.

**Strukturelle Rolle: bestätigt. Physischer Remote-Teilnehmer: offen.**

## 5.3 Handshake

Service-Statuswort:

```text
0x20015158 + 0x216
```

beeinflusst unter anderem die Lesefreigabe und Read-Acknowledge-Zustände der Bereiche 5001 und 5091.

`5091–5180` ist damit explizit ein **zustandsbehaftetes Transferfenster**, kein statischer Registersatz.

---

# 6. DIAG 6001–6090 – Live Engineering Diagnostic Snapshot

Der Bereich ist in V3.3 **read-only** über den normalen Modbusdispatcher.

Bei einem Read setzt die Firmware zusätzlich ein internes Diagnose-/Sessionflag:

```text
0x20015158 + 0x388 = 1
```

Der Snapshot wird aktiv aus Live-RAM aufgebaut.

## 6.1 6001–6008

```text
6001–6008 ← 0x20016B50 +0x00 … +0x0E
```

acht signed 16-Bit-Livewerte.

Die konkrete physische Benennung dieses internen Blocks ist noch nicht vollständig geschlossen.

## 6.2 Blocksignatur

```text
6009 = 0x0210 = 528
6010 = 0x1771 = 6001
```

Das ist eine typische interne Paket-/Blocksignatur.

**Bewertung: bestätigt.**

## 6.3 bestätigte Livewerte

| DIAG-Reg. | Quelle | Bedeutung | Sicherheit |
|---:|---|---|---|
| 6011 | `0x200164B8+0x00` | Low-Level-I/O-/Hardwarewert | Provenance bestätigt |
| 6012 | berechnet | Betriebs-/Diagnosezustand, Werte u.a. 0/1/2/3/4/16 | Struktur bestätigt |
| 6013 | `0x200164B8+0x06` | Low-Level-Hardwarewert | Provenance bestätigt |
| 6014 | Bit aus `0x2001660C+0x20` | boolescher Status | Provenance bestätigt |
| 6015 | `0x2001656C+0x00` | R-/Kennlinien-Livewert | Provenance bestätigt |
| **6016** | Helper `0x08087930` | **T01 Einlasswassertemperatur** | **bestätigt** |
| **6017** | Helper `0x08087966` | **T02 Auslasswassertemperatur** | **bestätigt** |
| 6018 | konditional / `0x20016F1C` | Sensor-/Diagnosewert, bei ungültig `0x7FFF` | Provenance bestätigt |
| **6019** | Helper `0x0808799C` | **T04 Außentemperatur** | **bestätigt** |
| 6020 | konditional / `0x20016F14` | Sensor-/Diagnosewert, bei ungültig `0x7FFF` | Provenance bestätigt |
| 6024 | konstant `0x0284` | Block-/Softwaremetadatum | bestätigt |
| 6025 | konstant `0x0021` | Block-/Softwaremetadatum | bestätigt |
| 6026 | 0 | Reserve im Builder | bestätigt |
| 6027 | 0 | Reserve im Builder | bestätigt |
| **6040** | `0x200168C4+0x06` | **Kompressor-Istfrequenz** | **bestätigt** |
| 6041–6043 | 0 | Reserve im Builder | bestätigt |
| **6044** | `0x2001691C+0x0C` | **Lüfter-Istwert 1** | **bestätigt** |
| **6045** | `0x2001691C+0x0E` | **Lüfter-Istwert 2** | **bestätigt** |
| 6046–6047 | 0 | Reserve im Builder | bestätigt |
| 6048 | `0x20016E88+0x02` | interner Livewert | Provenance bestätigt |

## 6.4 Low-Level-I/O-Bitfelder

Der hintere Teil des Blocks packt zahlreiche Einzelbits aus:

```text
0x200164B8
```

in Engineering-Wörter um `6073–6080`.

Der Code extrahiert unter anderem Bits aus internen Offsets:

```text
+0x16
+0x18
+0x1E
+0x20
```

und setzt/löscht daraus einzelne Bits in mehreren 16-Bit-Diagnosewörtern.

Damit sind diese Register funktional als:

> **Low-Level Hardware-/I/O-Diagnostic Bitfields**

klassifiziert.

Die vollständige elektrische Pinbelegung jedes Bits ist noch nicht benannt und bleibt bewusst `RAW bitfield with provenance`.

## 6.5 Service-/Handshake-Status im gleichen Fenster

Das Wort bei Serviceoffset `+0x216` liegt gleichzeitig innerhalb des 6001-Fensters und entspricht:

```text
DIAG:6088
```

Es wird als Service-/Handshake-Statusbitfeld verwendet:

- Read 5001 beeinflusst Bit0
- Read 5091 beeinflusst Bit1
- Bit15 kann den 5091-Read sperren

`6088` sollte daher **nicht** als gewöhnlicher physikalischer Sensorwert interpretiert werden.

---

# 7. ENG:CTRL 8801–8820

Backing RAM:

```text
0x20016970
```

Der Bereich ist per FC03, FC06 und FC10 adressierbar.

## 7.1 8801 – virtueller SG-Ready-Zustand

`8801` hat einen konkreten Laufzeitverbraucher in der SG-Ready-State-Machine um:

```text
0x08081BC0 ff.
```

Wenn die SG-Auswahl `MAIN:1334` den Wert `3` besitzt, liest V3.3 nicht die normalen physischen SG-Kontakte, sondern `ENG:CTRL:8801`.

Mapping:

```text
8801 = 1 → virtuelle Kontakte (1,0)
8801 = 2 → virtuelle Kontakte (0,0)
8801 = 3 → virtuelle Kontakte (0,1)
8801 = 4 → virtuelle Kontakte (1,1)
```

Diese beiden virtuellen Eingangszustände laufen anschließend durch dieselbe normale SG-Ready-Auswertung wie die realen Eingangsklemmen.

Damit gilt:

```text
ENG:CTRL:8801 = virtueller SG-Ready-Zustandsbefehl
```

**Bewertung: bestätigt.**

## 7.2 MAIN:1334 besitzt einen bisher fehlenden Modus 3

Der aktuelle `FoxAir_Control`-Datenstand kennt für `1334 / SG01`:

```text
0 = Aus
1 = Einfach / 1 Kontakt
2 = 2 Kontakte
```

Das Binary behandelt zusätzlich ausdrücklich:

```text
1334 == 3
```

und ersetzt dann die Hardwarekontakte durch `8801`.

Die fachlich naheliegende Bezeichnung ist:

```text
3 = SG Ready über Modbus / virtueller SG-Eingang
```

**Codefunktion bestätigt; Herstellerwortlaut „über Modbus“ sehr wahrscheinlich.**

## 7.3 8802–8820

Für diese Adressen ist der generische R/W-Dispatcher bestätigt. Im untersuchten V3.3-Binary wurde aber kein vergleichbar eindeutiger direkter Laufzeitverbraucher wie für 8801 gefunden.

Saubere Klassifikation:

```text
8802–8820 = adressierbare Engineering-Control-Slots,
             konkrete V3.3-Laufzeitsemantik offen
```

Nicht als „frei“ oder „unbenutzt“ deklarieren.

---

# 8. SPECIAL 60000 – Modbus-Adresse zurücksetzen

Der FC06-Sonderpfad erkennt:

```text
Register 60000 = 0xEA60
```

und setzt:

```text
MAIN:1024 = 1
```

Zusätzlich werden interne Provisionierungs-/Handshakezustände gelöscht und Apply-/Kommunikationsflags gesetzt.

Damit:

> **60000 ist ein Sonderkommando zum Zurücksetzen der Mainboard-Modbus-Adresse auf 1.**

**Bewertung: bestätigt.**

Softwarepolicy:

- nicht in normaler Parameterliste anbieten
- nur explizite Servicefunktion
- deutliche Warnung vor Adressänderung/Kommunikationsverlust

---

# 9. SPECIAL 60010 – UID-gebundene Modbus-Adress-Provisionierung

## 9.1 UID-Quelle

Routine:

```text
0x08050130
```

liest die STM32-Unique-ID direkt aus:

```text
0x1FFFF7E8
0x1FFFF7EC
0x1FFFF7F0
```

also 96 Bit / 12 Byte.

Die UID wird in:

```text
0x20016DCC
```

als sechs 16-Bit-Wörter abgelegt.

## 9.2 Read 60010

Ein FC03-Read auf `60010` startet den Sonderzustand und liefert nach einer internen zufälligen Antwortverzögerung die sechs UID-Wörter.

Die zufällige Verzögerung ist ein Kollisions-/Provisionierungsmechanismus; sie ist keine kryptographische Challenge.

## 9.3 Write 60010

Der FC10-Sonderpfad vergleicht **12 eingehende Datenbytes einzeln** mit der UID:

```text
UID word0 high, low
UID word1 high, low
...
UID word5 high, low
```

Nur wenn alle 12 Bytes übereinstimmen, wird der Vorgang akzeptiert.

Anschließend übernimmt V3.3 einen späteren Nutzdatenbytewert als neue:

```text
MAIN:1024 = Modbus Unit Address
```

und setzt die entsprechenden Apply-/Provisionierungsflags.

Damit:

> **60010 ist ein STM32-UID-gebundener Modbus-Adress-Setzmechanismus.**

Es handelt sich **nicht** um starke Authentifizierung: Die notwendige UID kann vorher über denselben Sonderpfad gelesen werden.

**Bewertung: bestätigt.**

---

# 10. Interne Servicezustände

Im großen Service-RAM existieren zusätzlich zustandsbehaftete Flags außerhalb der eigentlichen 90-Wort-Fenster:

| Offset ab `0x20015158` | Rolle |
|---:|---|
| `+0x216` | Service-/Handshake-Statuswort; zugleich DIAG:6088 |
| `+0x388` | wird beim Lesen von 6001–6090 gesetzt; Diagnose-/Sessionstatus |
| `+0x39A` | Requestflag für 5091→Unit-0x63-Synchronisation |
| `+0x39B` | wird in bestimmten Engineering-FC10-Pfaden gesetzt |
| `+0x3AA` | interner Apply-/Servicezustand |
| `+0x3AB` | interner Diagnose-/Gültigkeitszustand |
| `+0x3AC` | interner Diagnose-/Gültigkeitszustand |

Damit ist auch erklärt, warum Engineeringreads/-writes Nebenwirkungen auf Statusflags haben können.

---

# 11. Sicherheits-/Softwareklassifikation

| Bereich | Risiko beim Lesen | Risiko beim Schreiben | Empfehlung |
|---|---|---|---|
| 5001–5090 | gering | **hoch** – kann Liveparameter ändern | Advanced, standardmäßig read-only UI |
| 5091–5180 | gering/mittel | **hoch** – synchronisiert Konfigblock | nur Service/RE |
| 6001–6090 | gering | nicht normal schreibbar | ideal für Diagnose |
| 8801 | gering | SG-Betriebszustand kann geändert werden | nur gezielt exponieren |
| 8802–8820 | gering | unbekannte Engineeringwirkung | nicht generisch beschreibbar machen |
| 60000 | – | **sehr hoch** – Adresse wird auf 1 gesetzt | separate Serviceaktion |
| 60010 | UID-Read unkritisch | **hoch** – Unit-Adresse wird geändert | separate Provisionierungsaktion |

---

# 12. Verhältnis zu anderen Modbus-Namespaces

Diese Register gehören zum Mainboard-Service-/Engineeringdispatcher. Sie dürfen nicht mit Remote-Boardregistern verwechselt werden.

Beispiele:

```text
MAIN:2072        öffentliche Verdichter-Istfrequenz
INV1:2102        Inverterboard-Rohregister dafür
DIAG:6040        Engineering-Spiegel derselben Istfrequenz

MAIN:2074        öffentlicher Fan-Istwert 1
INV1:2130        integrierter Driver-Rohwert
DIAG:6044        Engineering-Spiegel
```

Der Namespace muss deshalb Bestandteil jeder zukünftigen maschinenlesbaren Definition sein.

---

# 13. Was nach diesem Audit noch offen bleibt

Kein **Adressbereich** und keine **R/W-Klasse** des hier untersuchten normalen/Engineering-Modbus ist mehr unklassifiziert.

Offen bleiben nur fachliche Einzelbezeichnungen für:

- Teile von ENG:A 5001–5090, obwohl deren Shadow-/Apply-Rolle geschlossen ist
- einzelne Felder von ENG:B 5091–5180
- 6001–6008 und diverse DIAG-Rohwerte
- konkrete Bitnamen der Low-Level-I/O-Bitfelder um 6073–6080
- ENG:CTRL 8802–8820

Diese Felder sind dennoch vollständig als:

```text
Adresse + Namespace + R/W-Recht + RAM-Provenance + funktionale Gruppe + Confidence
```

klassifiziert.

Damit ist der **Service-/Engineering-Modbus auf Architekturebene abgeschlossen**.

---

# 14. Verwandte Dokumente

- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
- [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
