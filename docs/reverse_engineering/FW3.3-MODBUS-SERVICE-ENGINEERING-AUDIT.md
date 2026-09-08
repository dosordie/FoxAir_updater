# Mainboard-Firmware V3.3 – Modbus Service-/Engineering-Audit

Stand: 8. September 2026

Diese Datei schließt die in V3.3 implementierten **nicht-normalen Modbusbereiche** außerhalb der öffentlichen Mainboard-Parameter `1001–1540` und Statusregister `2001–2180`. Ein klar markierter **V3.4-Nachtrag** ergänzt neu geschlossene DIAG-Werte, ohne V3.4-Codeadressen als V3.3-Adressen auszugeben.

Untersuchtes V3.3-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
MD5:          CEB6A4BF386FF644E23E410023E74673
```

Bewertung:

- **bestätigt** – direkt im jeweils genannten Binary geschlossen
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

V3.4 ergänzt im unveränderten DIAG-Namespace insbesondere:

```text
DIAG:6022 = Kompressor-Istfrequenz im Maschinenprofil-Diagnosepfad
DIAG:6023 = relative Verdichterlast gegen A26/T04/T02-Referenzfrequenz
```

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

**Wichtig:** Diese Matrix beschreibt den **direkten Mainboard-/Engineeringdispatcher**. Die Live-Tests zeigen, dass sie **nicht unverändert auf den Warmlink-/LTE-Pfad mit Slave `0x63` übertragen werden darf**.

---

# 4. ENG:A 5001–5090 – Engineering-Parameter-Schatten

## 4.1 Rolle

`5001–5090` ist ein kuratierter Service-/Engineering-Schatten ausgewählter aktiver Parameter.

Die zentrale V3.3-Synchronisationsroutine liegt um:

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

Die Zahl `0x63` allein reicht jedoch nicht aus, um diesen internen Forwardingpfad mit jeder manuellen Warmlink-/LTE-Anfrage gleichzusetzen.

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

Acht 16-Bit-Wörter des Device-ID-/Paketkopfs. 6001–6006 enthalten die 12-Byte-Kommunikationsmodul-ID, 6007–6008 zwei reservierte Kopfwörter. Der autoritative Puffer und sein EEPROM-/Provisionierungspfad sind in [Device-ID, EEPROM und Provisionierung](PHNIX_phnixIot4G_device_identity_block.md) dokumentiert.

## 6.2 Blocksignatur

```text
6009 = 0x0210 = 528
6010 = 0x1771 = 6001
```

**Bewertung: bestätigt.**

## 6.3 bestätigte Livewerte

| DIAG-Reg. | Quelle | Bedeutung | Sicherheit |
|---:|---|---|---|
| 6011 | `0x200164B8+0x00` | Low-Level-I/O-/Hardwarewert | Provenance V3.3 bestätigt |
| 6012 | berechnet | Betriebs-/Diagnosezustand, Werte u.a. 0/1/2/3/4/16 | Struktur V3.3 bestätigt |
| 6013 | `0x200164B8+0x06` | Low-Level-Hardwarewert | Provenance V3.3 bestätigt |
| 6014 | Bit aus `0x2001660C+0x20` | boolescher Status | Provenance V3.3 bestätigt |
| 6015 | `0x2001656C+0x00` | R-/Kennlinien-Livewert | Provenance V3.3 bestätigt |
| **6016** | Sensor-Helper | **T01 Einlasswassertemperatur** | **V3.3 bestätigt** |
| **6017** | Sensor-Helper | **T02 Auslasswassertemperatur** | **V3.3 bestätigt** |
| 6018 | konditional / `0x20016F1C` | Sensor-/Diagnosewert, bei ungültig `0x7FFF` | V3.3 bestätigt |
| **6019** | Sensor-Helper | **T04 Außentemperatur** | **V3.3 bestätigt** |
| 6020 | konditional / `0x20016F14` | Sensor-/Diagnosewert, bei ungültig `0x7FFF` | V3.3 bestätigt |
| **6022** | Kompressor-Istfrequenzpfad | **Kompressor-Istfrequenz im A26-Maschinenprofil-Diagnosepfad** | **V3.4 bestätigt** |
| **6023** | berechnet | **relative Verdichterlast in % gegen A26/T04/T02-Referenzfrequenz** | **V3.4 bestätigt** |
| 6024 | konstant `0x0284` | Block-/Softwaremetadatum | V3.3 bestätigt |
| 6025 | konstant `0x0021` | Block-/Softwaremetadatum | V3.3 bestätigt |
| 6026 | 0 | Reserve im Builder | V3.3 bestätigt |
| 6027 | 0 | Reserve im Builder | V3.3 bestätigt |
| **6040** | `0x200168C4+0x06` | **Kompressor-Istfrequenz** | **V3.3 bestätigt** |
| 6041–6043 | 0 | Reserve im Builder | V3.3 bestätigt |
| **6044** | `0x2001691C+0x0C` | **Lüfter-Istwert 1** | **V3.3 bestätigt** |
| **6045** | `0x2001691C+0x0E` | **Lüfter-Istwert 2** | **V3.3 bestätigt** |
| 6046–6047 | 0 | Reserve im Builder | V3.3 bestätigt |
| 6048 | `0x20016E88+0x02` | interner Livewert | Provenance V3.3 bestätigt |

## 6.4 V3.4: DIAG 6023 – relative Verdichterlast

V3.4 besitzt ein A26-abhängiges `7×8`-Maschinenkennfeld mit:

```text
Zeile   = T04 Außentemperaturklasse
Spalte  = T02 Auslass-/Vorlauftemperaturklasse
Ergebnis = F_ref / 100-%-Referenzfrequenz
```

Der Diagnosebuilder bildet sinngemäß:

```text
DIAG:6023 ≈ Verdichter-Istfrequenz / F_ref × 100
```

Der Last-Prozentwert selbst besitzt **keinen nachgewiesenen Rückverbrauch** in:

```text
EEV-Regelung
Lüfterregelung
COP-Berechnung
thermische/elektrische Leistungsberechnung
```

Er ist damit ein **Diagnose-/Anzeigewert**.

Wichtig ist die Trennung: `F_ref` selbst wird sehr wohl in der Verdichterregelung verwendet, um relative Hz-Grenzen zu bilden:

```text
F_limit = Prozent × F_ref / 100
```

unter anderem über `MAIN:1422` im SG-/Zusatzheizungs-Koordinationspfad.

Details und Tabellen stehen in [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md).

## 6.5 Low-Level-I/O-Bitfelder

Der hintere Teil des Blocks packt zahlreiche Einzelbits aus `0x200164B8` in Engineering-Wörter um `6073–6080`.

Damit sind diese Register funktional als:

> **Low-Level Hardware-/I/O-Diagnostic Bitfields**

klassifiziert.

## 6.6 Service-/Handshake-Status

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

Wenn `MAIN:1334 == 3`, liest V3.3 nicht die normalen physischen SG-Kontakte, sondern `ENG:CTRL:8801`.

Mapping:

```text
8801 = 1 → virtuelle Kontakte (1,0) → Mode 1
8801 = 2 → virtuelle Kontakte (0,0) → Mode 2
8801 = 3 → virtuelle Kontakte (0,1) → Mode 3
8801 = 4 → virtuelle Kontakte (1,1) → Mode 4
```

### Live-Bestätigung

Am realen Gerät über den direkten User-/Mainboard-Modbus ist Lesen/Schreiben/Rücklesen und die SG-Wirkung der Werte 1..4 bestätigt.

**Bewertung: Binary + live bestätigt.**

## 7.2 MAIN:1334 besitzt den Modus 3

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
3 = virtueller SG-Ready-Eingang über Modbus
```

**Codefunktion + Liveverhalten bestätigt.**

## 7.3 Fester 10-Minuten-Hold

Runtime-Timer:

```text
0x20016948 + 0x24 = 0x2001696C
```

Bei jeder akzeptierten SG-Modusänderung:

```text
Timer = 0x04B0 = 1200
1200 × 0,5 s = 10 Minuten
```

Während des Holds kann 8801 geändert und rückgelesen werden; `MAIN:2133` bleibt auf dem zuletzt akzeptierten Mode.

## 7.4 Änderung von MAIN:1334 setzt den Hold zurück

Binary + live bestätigt.

## 7.5 Warmlink-/LTE-Pfad 0x63 ist nicht gleichwertig

Am parallelen Warmlink-/LTE-Bus wurde beobachtet:

```text
1334 R/W -> funktioniert
2133 R   -> funktioniert
8801 FC03 -> Timeout
8801 FC16 -> formal passender ACK, aber kein belastbarer Cross-Bus-Apply
```

Für die reale 8801-Steuerung ist der direkte User-/Mainboard-Modbus der bestätigte Pfad.

## 7.6 8802–8820

Adressierbare Engineering-Control-Slots; konkrete V3.3-Laufzeitsemantik offen.

---

# 8. SPECIAL 60000 – Modbus-Adresse zurücksetzen

```text
FC06 Register 60000
→ MAIN:1024 = 1
```

Zusätzlich werden interne Provisionierungs-/Handshakezustände gelöscht und Apply-/Kommunikationsflags gesetzt.

Softwarepolicy: separate Servicefunktion.

---

# 9. SPECIAL 60010 – UID-gebundene Modbus-Adress-Provisionierung

UID-Quelle:

```text
0x1FFFF7E8
0x1FFFF7EC
0x1FFFF7F0
```

Die UID wird in `0x20016DCC` als sechs 16-Bit-Wörter abgelegt.

FC03 auf 60010 liefert die UID; FC10 akzeptiert eine neue Unit-Adresse nur nach vollständiger UID-Übereinstimmung.

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

---

# 12. Verhältnis zu anderen Modbus-Namespaces

Beispiele:

```text
MAIN:2072        öffentliche Verdichter-Istfrequenz
INV1:2102        Inverterboard-Rohregister dafür
DIAG:6040        Engineering-Spiegel derselben Istfrequenz
DIAG:6023        V3.4 relative Maschinenprofil-Lastanzeige

MAIN:2074        öffentlicher Fan-Istwert 1
INV1:2130        integrierter Driver-Rohwert
DIAG:6044        Engineering-Spiegel
```

Zusätzlich ist seit dem SG-Live-Test der **Zugriffspfad** Teil der Semantik:

```text
ENG:CTRL:8801 @ User-Modbus != 8801 @ Warmlink/LTE 0x63
```

---

# 13. Was nach diesem Audit noch offen bleibt

Kein Adressbereich und keine R/W-Klasse des direkten normalen/Engineering-Modbus ist mehr unklassifiziert.

Offen bleiben fachliche Einzelbezeichnungen für Teile von ENG:A/ENG:B, diverse DIAG-Rohwerte, Low-Level-I/O-Bits, ENG:CTRL 8802–8820 und die genauen Filter-/Proxyregeln des Warmlink-/LTE-Pfads.

Für V3.4 ist zusätzlich der originale PHNIX-Name von DIAG:6023 offen; die Rechenfunktion ist dagegen geschlossen.

---

# 14. Verwandte Dokumente

- [`FW3.4-HARDWARE-KONFIGURATION.md`](FW3.4-HARDWARE-KONFIGURATION.md)
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md)
- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
- [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
