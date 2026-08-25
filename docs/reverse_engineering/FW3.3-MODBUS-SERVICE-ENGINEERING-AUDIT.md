# Mainboard-Firmware V3.3 – Modbus Service-/Engineering-Audit

Stand: 24. August 2026

Diese Datei schließt die in V3.3 implementierten **nicht-normalen Modbusbereiche** außerhalb der öffentlichen Mainboard-Parameter `1001–1540` und Statusregister `2001–2180`.

Untersuchtes Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
MD5:          CEB6A4BF386FF644E23E410023E74673
```

Bewertung:

- **bestätigt** – direkt im Binary geschlossen
- **live bestätigt** – am realen Gerät praktisch verifiziert
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
| `ENG:CTRL` | 8801–8820 | `0x20016970` | Engineering-Steuerfenster; **8801 = virtueller SG-Ready-Zustand** |
| `SPECIAL` | 60000 | – | Modbus-Adresse auf 1 zurücksetzen |
| `SPECIAL` | 60010 | UID-Puffer `0x20016DCC` | UID-gebundene Modbus-Adress-Provisionierung |

Neu live bestätigt:

```text
MAIN:1334 = 3
ENG:CTRL:8801 = 1..4
→ reale virtuelle SG-Ready-Steuerung
```

Zusätzlich ist ein fester **10-Minuten-Hold** zwischen akzeptierten SG-Moduswechseln bestätigt; eine Änderung von `MAIN:1334` setzt diesen Hold zurück.

Die Bereiche sind nicht einfach weitere öffentliche Benutzerparameter und sollten in Software separat benannt und abgesichert werden.

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

# 3. Read-/Write-Matrix des direkten Mainboard-Engineeringdispatchers

| Bereich | FC03 | FC06 | FC10 | empfohlene Nutzung |
|---|---|---|---|---|
| MAIN 1001–1540 | ja | ja* | ja | normale Konfiguration |
| ENG:A 5001–5090 | ja | ja | ja | nur Engineering/Service |
| ENG:B 5091–5180 | ja** | nein | ja | Sync-/Transferfenster |
| DIAG 6001–6090 | ja | nein | nein | read-only Diagnose |
| ENG:CTRL 8801–8820 | ja | ja | ja | Advanced/Engineering |
| SPECIAL 60000 | – | Sonderkommando | – | Adressreset |
| SPECIAL 60010 | Sonder-Read | – | Sonder-Write | Adress-Provisionierung |

\* FC06 sperrt die sechs 10-Wort-Paketköpfe.  
\** Lesen von 5091–5180 hängt zusätzlich von einem internen Service-Statusbit ab.

**Wichtig:** Diese Matrix beschreibt den **direkten Mainboard-/Engineeringdispatcher**. Die Live-Tests zeigen, dass sie **nicht unverändert auf den Warmlink-/LTE-Pfad mit Slave `0x63` übertragen werden darf**. Für `8801` ist genau diese Asymmetrie praktisch nachgewiesen.

---

# 4. ENG:A 5001–5090 – Engineering-Parameter-Schatten

## 4.1 Rolle

`5001–5090` ist ein kuratierter Service-/Engineering-Schatten ausgewählter aktiver Parameter.

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

### Apply-/Servicebetrieb

In einem speziellen Apply-Zustand wird die Richtung umgedreht:

```text
ENG:A 5001–5090
    ↓
aktive Live-Strukturen
```

Damit ist `5001–5090` kein Diagnoseblock, sondern eine reorganisierte Service-Parameteransicht mit echter Änderungswirkung.

**Bewertung: bestätigt.**

## 4.2 Konsequenz für Software

- nicht als normale Benutzerparameter anzeigen
- lesen ist diagnostisch sinnvoll
- Schreiben kann reale Anlagenparameter verändern
- generisches „alle Register beschreibbar“-UI ist nicht empfehlenswert
- immer `ENG:A:5001` statt nur `5001` dokumentieren

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

Danach wird das Requestflag gelöscht.

Damit ist die Rolle geschlossen:

> `5091–5180` ist ein 90-Wort-Engineering-/Konfigurationsfenster, das zwischen Kommunikationsinstanzen synchronisiert bzw. an eine Unit-`0x63`-Instanz weitergereicht wird.

Die Zahl `0x63` allein reicht jedoch nicht aus, um diesen internen Forwardingpfad mit jeder manuellen Warmlink-/LTE-Anfrage gleichzusetzen. Die aktuellen 8801-Tests zeigen gerade, dass auf dem realen `0x63`-Zugriff zusätzliche Filter-/Gatewaylogik existiert.

## 5.3 Handshake

Service-Statuswort:

```text
0x20015158 + 0x216
```

beeinflusst unter anderem die Lesefreigabe und Read-Acknowledge-Zustände der Bereiche 5001 und 5091.

`5091–5180` ist damit explizit ein zustandsbehaftetes Transferfenster.

---

# 6. DIAG 6001–6090 – Live Engineering Diagnostic Snapshot

Der Bereich ist in V3.3 über den direkten Engineeringdispatcher **read-only**.

Bei einem Read setzt die Firmware zusätzlich:

```text
0x20015158 + 0x388 = 1
```

Der Snapshot wird aktiv aus Live-RAM aufgebaut.

## 6.1 6001–6008

```text
6001–6008 ← 0x20016B50 +0x00 … +0x0E
```

Acht 16-Bit-Wörter des Device-ID-/Paketkopfs. 6001–6006 enthalten die
12-Byte-Kommunikationsmodul-ID, 6007–6008 zwei reservierte Kopfwörter. Dieser
Diagnosebereich ist nur ein read-only Live-Spiegel; der autoritative Puffer und
sein EEPROM-/Provisionierungspfad sind in
[Device-ID, EEPROM und Provisionierung](PHNIX_phnixIot4G_device_identity_block.md)
dokumentiert.

## 6.2 Blocksignatur

```text
6009 = 0x0210 = 528
6010 = 0x1771 = 6001
```

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

Der hintere Teil des Blocks packt zahlreiche Einzelbits aus `0x200164B8` in Engineering-Wörter um `6073–6080`.

Damit sind diese Register funktional als:

> **Low-Level Hardware-/I/O-Diagnostic Bitfields**

klassifiziert.

## 6.5 Service-/Handshake-Status

Das Wort bei Serviceoffset `+0x216` entspricht:

```text
DIAG:6088
```

Es wird als Service-/Handshake-Statusbitfeld verwendet:

- Read 5001 beeinflusst Bit0
- Read 5091 beeinflusst Bit1
- Bit15 kann den 5091-Read sperren

`6088` ist kein gewöhnlicher physikalischer Sensorwert.

---

# 7. ENG:CTRL 8801–8820

Backing RAM:

```text
0x20016970
```

Der Bereich ist im **direkten** Engineeringdispatcher per FC03, FC06 und FC10 adressierbar.

## 7.1 8801 – virtueller SG-Ready-Zustand

`8801` hat einen konkreten Laufzeitverbraucher in der SG-Ready-State-Machine um:

```text
0x08081BC0 ff.
```

Wenn `MAIN:1334 == 3`, liest V3.3 nicht die normalen physischen SG-Kontakte, sondern `ENG:CTRL:8801`.

Mapping:

```text
8801 = 1 → virtuelle Kontakte (1,0) → Mode 1
8801 = 2 → virtuelle Kontakte (0,0) → Mode 2
8801 = 3 → virtuelle Kontakte (0,1) → Mode 3
8801 = 4 → virtuelle Kontakte (1,1) → Mode 4
```

Damit:

```text
ENG:CTRL:8801 = virtueller SG-Ready-Zustandsbefehl
```

### Live-Bestätigung

Am realen Gerät über den direkten User-/Mainboard-Modbus:

```text
8801 initial 0
lesen -> funktioniert
0..4 schreiben -> funktioniert
Rücklesen -> funktioniert
Wert bleibt stehen
```

Reale Funktionsreaktionen:

```text
8801=1 -> Mode 1 / Schlafmodus; WP startet nicht
8801=4 -> Mode 4 / High Power; WP startet
```

Die grundsätzliche SG-Wirkung des Registers wurde praktisch bestätigt.

**Bewertung: Binary + live bestätigt.**

## 7.2 MAIN:1334 besitzt den Modus 3

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
3 = virtueller SG-Ready-Eingang über Modbus
```

Bei Wert 3 werden die Hardwarekontakte als SG-Quelle durch `8801` ersetzt.

**Codefunktion + Liveverhalten bestätigt; exakter Herstellerwortlaut offen.**

## 7.3 Fester 10-Minuten-Hold

Runtime-Timer:

```text
0x20016948 + 0x24 = 0x2001696C
```

Bei jeder akzeptierten SG-Modusänderung:

```text
Timer = 0x04B0 = 1200
```

Die gleiche Routine zeigt über `1335 * 120`, dass 120 Zyklen einer Minute entsprechen. Damit:

```text
1200 × 0,5 s = 10 Minuten
```

Während des Holds:

```text
8801 kann sofort geändert und rückgelesen werden
MAIN:2133 bleibt auf dem zuletzt akzeptierten Mode
```

Nach Ablauf wird der aktuell anliegende gewünschte Zustand übernommen.

## 7.4 Änderung von MAIN:1334 setzt den Hold zurück

V3.3 setzt bei Änderung der SG-Quellenauswahl den Hold-Timer und interne Übergangszustände zurück.

Dieses Verhalten ist inzwischen **Binary + live bestätigt**.

Ein kontrollierter Test kann daher z. B.:

```text
8801 = gewünschter Zustand
1334 = 0
1334 = 3
```

verwenden, um den aktuellen 8801-Wert neu annehmen zu lassen. Nach der Annahme startet wieder ein neuer 10-Minuten-Hold.

Für normalen Automatikbetrieb ist dies nicht als Schnellumschaltmechanismus gedacht.

## 7.5 Warmlink-/LTE-Pfad 0x63 ist nicht gleichwertig

Am parallelen Warmlink-/LTE-Bus wurde beobachtet:

```text
1334 R/W -> funktioniert
2133 R   -> funktioniert
8801 FC03 -> Timeout
8801 FC16 -> formal passender ACK
```

Der FC16-ACK auf `8801` konnte im Cross-Bus-Test nicht als tatsächliche Änderung des direkten User-Modbus-Registers 8801 bestätigt werden.

Daraus folgt:

> Die direkte Dispatcher-R/W-Matrix von `8801–8820` darf **nicht** automatisch auf den `0x63`-Warmlink-/LTE-Zugriff übertragen werden.

Für die reale 8801-Steuerung ist derzeit der direkte User-/Mainboard-Modbus der bestätigte Pfad.

## 7.6 8802–8820

Für diese Adressen ist der generische R/W-Dispatcher bestätigt. Im untersuchten V3.3-Binary wurde jedoch kein direkter Laufzeitverbraucher wie für 8801 gefunden.

```text
8802–8820 = adressierbare Engineering-Control-Slots,
             konkrete V3.3-Laufzeitsemantik offen
```

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

> **60000 ist ein Sonderkommando zum Zurücksetzen der Mainboard-Modbus-Adresse auf 1.**

Softwarepolicy:

- nicht in normaler Parameterliste anbieten
- nur explizite Servicefunktion
- deutliche Warnung vor Adressänderung/Kommunikationsverlust

---

# 9. SPECIAL 60010 – UID-gebundene Modbus-Adress-Provisionierung

## 9.1 UID-Quelle

Routine `0x08050130` liest die STM32-Unique-ID aus:

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

FC03 auf `60010` startet einen Sonderzustand und liefert nach einer internen zufälligen Antwortverzögerung die sechs UID-Wörter.

## 9.3 Write 60010

Der FC10-Sonderpfad vergleicht 12 eingehende Datenbytes einzeln mit der UID. Nur bei vollständiger Übereinstimmung wird der Vorgang akzeptiert.

Anschließend übernimmt V3.3 einen späteren Nutzdatenbytewert als neue:

```text
MAIN:1024 = Modbus Unit Address
```

Damit:

> **60010 ist ein STM32-UID-gebundener Modbus-Adress-Setzmechanismus.**

Es handelt sich nicht um starke Authentifizierung, weil die UID vorher gelesen werden kann.

---

# 10. Interne Servicezustände

| Offset ab `0x20015158` | Rolle |
|---:|---|
| `+0x216` | Service-/Handshake-Statuswort; zugleich DIAG:6088 |
| `+0x388` | beim Lesen von 6001–6090 gesetzt; Diagnose-/Sessionstatus |
| `+0x39A` | Requestflag für 5091→Unit-0x63-Synchronisation |
| `+0x39B` | wird in bestimmten Engineering-FC10-Pfaden gesetzt |
| `+0x3AA` | interner Apply-/Servicezustand |
| `+0x3AB` | interner Diagnose-/Gültigkeitszustand |
| `+0x3AC` | interner Diagnose-/Gültigkeitszustand |

---

# 11. Sicherheits-/Softwareklassifikation

| Bereich | Risiko beim Lesen | Risiko beim Schreiben | Empfehlung |
|---|---|---|---|
| 5001–5090 | gering | **hoch** – kann Liveparameter ändern | Advanced, standardmäßig read-only UI |
| 5091–5180 | gering/mittel | **hoch** – synchronisiert Konfigblock | nur Service/RE |
| 6001–6090 | gering | nicht normal schreibbar | ideal für Diagnose |
| **8801** | gering | SG-Betriebszustand kann geändert werden | gezielt exponieren; 10-min-Hold beachten |
| 8802–8820 | gering | unbekannte Engineeringwirkung | nicht generisch beschreibbar machen |
| 60000 | – | **sehr hoch** – Adresse wird auf 1 gesetzt | separate Serviceaktion |
| 60010 | UID-Read unkritisch | **hoch** – Unit-Adresse wird geändert | separate Provisionierungsaktion |

Für `8801` zusätzlich:

```text
Direkter User-Modbus: bestätigt
Warmlink/LTE 0x63: nicht als gleichwertiger R/W-Pfad behandeln
```

---

# 12. Verhältnis zu anderen Modbus-Namespaces

Diese Register gehören zum Mainboard-Service-/Engineeringkontext. Sie dürfen nicht mit Remote-Boardregistern verwechselt werden.

Beispiele:

```text
MAIN:2072        öffentliche Verdichter-Istfrequenz
INV1:2102        Inverterboard-Rohregister dafür
DIAG:6040        Engineering-Spiegel derselben Istfrequenz

MAIN:2074        öffentlicher Fan-Istwert 1
INV1:2130        integrierter Driver-Rohwert
DIAG:6044        Engineering-Spiegel
```

Zusätzlich ist seit dem SG-Live-Test der **Zugriffspfad** Teil der Semantik:

```text
ENG:CTRL:8801 @ User-Modbus  !=  8801 @ Warmlink/LTE 0x63
```

---

# 13. Was nach diesem Audit noch offen bleibt

Kein Adressbereich und keine R/W-Klasse des direkten normalen/Engineering-Modbus ist mehr unklassifiziert.

Offen bleiben nur fachliche Einzelbezeichnungen für:

- Teile von ENG:A 5001–5090
- einzelne Felder von ENG:B 5091–5180
- diverse DIAG-Rohwerte jenseits des identifizierten Kopfes 6001–6008
- konkrete Bitnamen der Low-Level-I/O-Bitfelder um 6073–6080
- ENG:CTRL 8802–8820
- genaue interne Filter-/Proxyregeln des Warmlink-/LTE-0x63-Pfads jenseits der live getesteten Register

`8801` gehört **nicht mehr** zu den offenen Funktionen.

Damit ist der Service-/Engineering-Modbus auf Architekturebene abgeschlossen; die SG-Ready-Funktion über 8801 ist zusätzlich praktisch validiert.

---

# 14. Verwandte Dokumente

- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
- [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
