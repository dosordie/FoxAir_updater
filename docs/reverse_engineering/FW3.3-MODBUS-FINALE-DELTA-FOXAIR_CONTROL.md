# V3.3 – finale Modbus-Delta-Liste für `FoxAir_Control/data`

Stand: 24. August 2026

Diese Datei fasst **alle unmittelbar software-relevanten Änderungen** aus dem abgeschlossenen V3.3-Modbusaudit einschließlich der inzwischen erfolgten Live-Verifikation von SG Ready über Register `8801` zusammen.

Vergleichsbasis:

```text
Repository: dosordie/FoxAir_Control
data/foxair_phnix_registers.json
Blob SHA: ff24c160813f12304b7b8c403be0287b49a84686
```

Die Datei ist eine Implementierungsvorlage. `FoxAir_Control/data` selbst wird durch diesen Audit nicht automatisch verändert.

---

# 1. Priorität A – sichere Korrekturen bestehender MAIN-Register

| Register | aktueller Softwarestand | V3.3-korrigierter Stand | Aktion |
|---:|---|---|---|
| 2019 Bit0 | Kompressor-Ausgang | tatsächlicher Verdichterlauf / Istfrequenz != 0 | Beschreibung korrigieren |
| 2019 Bit2 | Lüfter-Hochgeschwindigkeitsausgang | mindestens ein Lüfter meldet Istwert != 0 | Beschreibung korrigieren |
| 2026 | `9` | INV1:2113 High-Byte Diagnose | umbenennen / Provenance |
| 2027 | `9` | INV1:2113 Low-Byte Diagnose | umbenennen / Provenance |
| 2028 | `9` | INV1:2118 Diagnose | umbenennen / Provenance |
| 2054 | elektrische Leistung | **elektrische Gesamtleistung**, raw/10 kW | Skalierung bestätigen |
| 2057 | unbestätigter Livewert | **T35 AC Input Current** | Name/Typ korrigieren |
| 2059 | Wärmeleistung | **thermische Gesamtleistung**, raw/10 kW | Skalierung bestätigen |
| 2060 | COP | **Gesamt-COP**, raw/100 | Skalierung bestätigen |
| 2071 | Kompressorfrequenz | **Kompressor-Sollfrequenz** | Name korrigieren |
| 2080 | Kandidat/Displaystatus | INV1:2099 Inverter-/Driver-Status | Provenance ergänzen |
| 2081 | Fehler 7 | **Inverter-/Driver Fault Word 1** | Bitfeld/Name ersetzen |
| 2082 | Fehler 8 | **Inverter-/Driver Fault Word 2** | Bitfeld/Name ersetzen |
| 2109 | Reserviert | intern von V3.3 beschrieben | `reserved` entfernen |
| 2117 | Reserviert | Highword 32-Bit-Zähler 2117/2118 | 32-Bit-Paar modellieren |
| 2119 | Reserviert | Highword 32-Bit-Zähler 2119/2120 | 32-Bit-Paar modellieren |
| 2121 | Reserviert | Highword 32-Bit-Zähler 2121/2122 | 32-Bit-Paar modellieren |
| 2123 | Reserviert | Highword 32-Bit-Zähler 2123/2124 | 32-Bit-Paar modellieren |
| **2133** | aktiver SG-Modus | **effektiver SG-Ready-Modus 0..4; Umschaltung mit festem 10-Minuten-Hold** | Verhalten/Tooltip ergänzen |
| 2136 | unbekannter x0.1-Wert | **T04 Außentemperatur, zweiter Publikationspfad** | korrigieren |
| 2137 | Spiegel 2054 Kandidat | **reine WP-/Inverter-Eingangsleistung**, raw/10 kW | korrigieren |
| 2138 | Spiegel 2059 Kandidat | **reine thermische WP-Leistung**, raw/10 kW | korrigieren |
| 2140/2141 | zwei RAW | gemeinsamer 32-Bit-Wert | Paarmodell |
| 2142/2143 | zwei RAW | gemeinsamer 32-Bit-Wert | Paarmodell |
| 2146 | unbekannt | V3.3 Capability-/Statusbitfeld | Typ BITFIELD, Bits weiter RAW |

---

# 2. Priorität A – SG Ready über MAIN:1334 und ENG:CTRL:8801

Dieser Punkt ist inzwischen **Binary + live am realen Gerät bestätigt**.

## MAIN:1334 / SG01

Bisheriger Softwarestand:

```text
0 = Aus
1 = 1 Kontakt
2 = 2 Kontakte
```

Ergänzen:

```text
3 = SG Ready über Modbus / virtueller SG-Eingang
```

Bei `1334 = 3` benutzt die V3.3-State-Machine nicht die beiden physischen SG-Kontakte als Quelle, sondern:

```text
ENG:CTRL:8801 / 0x2261
```

## ENG:CTRL:8801

Mapping:

```text
1 → virtuelle Kontakte (1,0) → Mode 1 / Schlafmodus
2 → virtuelle Kontakte (0,0) → Mode 2 / wenig PV / Normal
3 → virtuelle Kontakte (0,1) → Mode 3 / mittel PV
4 → virtuelle Kontakte (1,1) → Mode 4 / High PV
```

Direkter User-/Mainboard-Modbus am realen Gerät:

```text
8801 initial 0
lesen -> funktioniert
0..4 schreiben -> funktioniert
Rücklesen -> funktioniert
Werte bleiben stehen
SG-Wirkung -> bestätigt
```

Explizit beobachtet:

```text
8801 = 1 -> Mode 1 / Schlafmodus; WP startet nicht
8801 = 4 -> Mode 4 / High Power; WP startet
```

Damit sollte `8801` nicht mehr nur als „Advanced-Kandidat“, sondern als **bestätigte SG-Ready-Steuerfunktion** modelliert werden.

## Fester 10-Minuten-Hold

Nach jeder tatsächlich akzeptierten SG-Modusänderung setzt V3.3 intern:

```text
0x2001696C = 0x04B0 = 1200 Zyklen
```

Die SG-Routine läuft alle ca. `0,5 s`:

```text
1200 × 0,5 s = 600 s = 10 Minuten
```

Während dieses Holds:

```text
8801 -> ändert sich sofort und ist sofort rücklesbar
2133 -> bleibt zunächst auf dem zuletzt akzeptierten SG-Modus
```

Nach Ablauf wird der dann aktuell anliegende gewünschte Zustand übernommen.

## Änderung von 1334 setzt den Hold zurück

**Binary + live bestätigt:** Ändert sich die SG-Quellenauswahl in `1334`, setzt V3.3 den laufenden 10-Minuten-Hold und zugehörige Übergangszustände zurück.

Das bedeutet für die UI/Automatisierung:

- `2133` als effektive Rückmeldung verwenden.
- Nicht jeden `8801`-Write als sofort aktive Änderung darstellen.
- Einen laufenden/erwartbaren Hold verständlich anzeigen.
- Quellenwechsel über `1334` nicht automatisch zum schnellen Umschalten missbrauchen.

## Backend-spezifische Zugriffsrechte

Diese Funktion muss außerdem **transport-/backendabhängig** modelliert werden.

Direkter User-/Mainboard-Modbus:

```text
8801 lesen/schreiben -> live bestätigt
```

Warmlink-/LTE-RS485, Slave `0x63`:

```text
1334 lesen/schreiben -> funktioniert
2133 lesen           -> funktioniert
8801 FC03            -> Timeout
8801 FC16            -> formal korrekter ACK
```

Der FC16-ACK auf `8801` hat im Cross-Bus-Gegencheck keinen belastbaren Nachweis geliefert, dass das echte User-Modbus-Register `8801` verändert wurde.

Daher:

> `8801` im Warmlink-/LTE-Backend **nicht** automatisch als gleichwertig zum direkten User-Modbus freigeben.

---

# 3. Priorität A – normaler Parameterbereich endet bei 1540

V3.3 normaler MAIN-Dispatcher:

```text
1001–1540
```

Die bislang aus Display-/Paketwissen vorhandenen:

```text
1541–1550
```

sollten nicht als normale MAIN-Parameter dargestellt werden.

Empfehlung:

```text
Namespace: DISPLAY/COMPAT
nicht MAIN:P
```

Keine automatische Schreibmöglichkeit über normalen V3.3-Mainboard-Parameterdialog anbieten.

---

# 4. Priorität A – Paketkopf-Schreibpolicy

Headerblöcke:

```text
1001–1010
1091–1100
1181–1190
1271–1280
1361–1370
1451–1460
```

V3.3 direkter Dispatcher:

```text
FC03 = lesbar
FC06 = ausdrücklich gesperrt
FC10 = technisch nicht gesperrt
```

Softwarepolicy trotzdem:

```text
read-only
```

Keinen generischen FC10-Editor hierfür anbieten.

---

# 5. Priorität B – C13–C15 / E20–E21 hochstufen

V3.3 bestätigt echte Livefelder:

| MAIN | Code | RAM | Typ | V3.3 Default |
|---:|---|---:|---|---:|
| 1348 | C13 | `0x20016C9C+1` | signed byte | 3 |
| 1349 | C14 | `+2` | signed byte | 2 |
| 1350 | C15 | `+3` | signed byte | 6 |
| 1351 | E20 | `+8` | signed byte | 1 |
| 1352 | E21 | `+9` | signed byte | 1 |

Zusätzlich:

```text
1347 C12 default 90
```

Aktion:

- `Display-Firmware Parameter` durch `V3.3-Liveparameter; fachliche Bedeutung offen` ersetzen
- `confidence/provenance` ergänzen
- keine erfundenen Funktionsnamen verwenden

---

# 6. Priorität B – neue V3.3-Parameterlücken aufnehmen

Im aktuellen Softwarekatalog fehlen reale V3.3-Livefelder insbesondere in:

```text
1381–1389
1402
1404–1405
1422–1431
1445–1448
1461–1469
1476–1477
1481
```

Empfohlene erste Aufnahmeform:

```json
{
  "name": "V3.3 interner Parameter – Bedeutung offen",
  "type": "RAW",
  "mode": "r/w",
  "confidence": "firmware_provenance_confirmed",
  "ram": "0x..."
}
```

Wichtige bekannte Ausnahmen bleiben mit ihren vorhandenen Namen:

```text
1432 P11
1433 P12
1435 P13
1436 P14
1437 D30
1438 P15
1444 P16
```

---

# 7. Priorität B – Statusbereich auf 2180 erweitern

`FoxAir_Control` besitzt derzeit technisch vor allem Definitionen bis 2149.

V3.3 baut und broadcastet:

```text
2001–2090
2091–2180
```

Deshalb `2150–2180` als V3.3-Statuskandidaten aufnehmen.

Wo die fachliche Bedeutung offen ist:

```text
Name: V3.3 Status RAW
mode: read-only
source_ram: ...
confidence: provenance_confirmed
```

---

# 8. Neue Namespaces und Zugriffspfade

Empfohlenes Datenmodell:

```text
MAIN:P       1001–1540
MAIN:S       2001–2180
ENG:A        5001–5090
ENG:B        5091–5180
DIAG         6001–6090
ENG:CTRL     8801–8820
SPECIAL      60000 / 60010
INV1         Unit 0x01 Remote
FAN4         Unit 0x04 Remote
HMI3/HMI2    Unit 0x03/0x02
WARMLINK63   gefilterter Zugriff über LTE/Service-Slave 0x63
OTA63        0xCxxx auf Service-/Warmlinkpfad
```

Zusätzlich zum Namespace muss künftig der **Zugriffspfad** Teil der Rechtebewertung sein.

---

# 9. ENG:A 5001–5090 – Softwarepolicy

Funktion:

```text
Engineering parameter shadow / apply profile
```

Direkter Dispatcher:

```text
FC03 yes
FC06 yes
FC10 yes
```

Empfehlung:

```text
visible in RE/advanced diagnostics: yes
normal writable UI: no
expert raw write: optional with explicit confirmation
```

---

# 10. ENG:B 5091–5180 – Softwarepolicy

Funktion:

```text
90-word configuration synchronization / forwarding window
```

Direkter Dispatcher:

```text
FC03 yes, state-dependent
FC06 no
FC10 yes
```

Empfehlung:

```text
advanced monitor only
kein normaler Einzelregistereditor
```

---

# 11. DIAG 6001–6090 – ideal für Diagnose

Direkter Dispatcher:

```text
FC03 yes
FC06 no
FC10 no
```

Sicher benennbare Felder:

| DIAG | Name |
|---:|---|
| 6009 | Blockmarker 0x0210 |
| 6010 | Blockstartmarker 6001 |
| 6016 | T01 Einlasswassertemperatur |
| 6017 | T02 Auslasswassertemperatur |
| 6019 | T04 Außentemperatur |
| 6040 | Kompressor-Istfrequenz |
| 6044 | Lüfter-Istwert 1 |
| 6045 | Lüfter-Istwert 2 |
| 6073–6080 | Low-Level-I/O-Diagnostic Bitfields |
| 6088 | Service-/Handshake-Status |

---

# 12. ENG:CTRL 8801–8820 – Softwarepolicy

## 8801

Empfehlung:

```text
Name: Virtual SG Ready State
Direkter User-Modbus: R/W live bestätigt
Werte: 1..4
UI: nur wirksam wenn MAIN:1334 == 3
Feedback: MAIN:2133
Hold: 10 Minuten nach akzeptiertem Modewechsel
Hold reset: bei Änderung von MAIN:1334
```

## 8802–8820

Dispatcher-R/W bestätigt, keine eindeutigen Liveverbraucher.

Empfehlung:

```text
nicht im normalen UI
keine generische Schreibfreigabe
RAW in RE-Modus möglich
```

---

# 13. SPECIAL 60000 / 60010 – nicht in normale Registerliste

## 60000

```text
FC06 → MAIN:1024 = 1
```

Benennung:

```text
Reset Mainboard Modbus Unit Address to 1
```

## 60010

```text
FC03 60010 → UID lesen
FC10 60010 → UID-Echo + neue Unit-Adresse
```

Benennung:

```text
STM32 UID / Modbus Unit Address Provisioning
```

Softwareempfehlung:

- nicht als normales Registerfeld
- eigene Serviceaktion
- Warnung vor Adressänderung/Kommunikationsverlust

---

# 14. R/W-Matrix – ausdrücklich für den direkten Dispatcher

```text
MAIN:P 1001–1540
  FC03 yes
  FC06 yes except headers
  FC10 yes

ENG:A 5001–5090
  FC03 yes
  FC06 yes
  FC10 yes

ENG:B 5091–5180
  FC03 yes/stateful
  FC06 no
  FC10 yes

DIAG 6001–6090
  FC03 yes
  FC06 no
  FC10 no

ENG:CTRL 8801–8820
  FC03 yes
  FC06 yes
  FC10 yes
```

**Nicht auf `WARMLINK63` vererben.** Rechte müssen pro Backend/Zugriffspfad hinterlegt werden.

---

# 15. Empfohlene Implementierungsreihenfolge in FoxAir_Control

1. `1334 value 3` + `8801` als bestätigte SG-Ready-Funktion ergänzen
2. 10-Minuten-Hold, `2133`-Feedback und 1334-Hold-Reset in SG-UI berücksichtigen
3. direkten User-Modbus und Warmlink-/LTE-0x63 bei Rechten getrennt modellieren
4. sichere Namens-/Skalierungskorrekturen 2019/2057/2071/2080–2082/2136–2138
5. 32-Bit-Zählerpaare korrekt modellieren
6. MAIN-Parameterende auf 1540 normieren und 1541–1550 auslagern
7. Statusbereich 2150–2180 ergänzen
8. V3.3-Liveparameter-Lücken 1381ff als RAW+Provenance aufnehmen
9. Namespace-Modell für ENG/DIAG/INV1/FAN4 etablieren
10. DIAG 6001–6090 als read-only Engineeringdiagnose integrieren
11. 5001/5091/8802ff nur im RE-/Servicebereich führen
12. 60000/60010 ausschließlich als separate Provisionierungsaktionen behandeln

---

# 16. Abschluss

Nach Umsetzung dieser Delta-Liste entspricht `FoxAir_Control/data` dem **bytegenau auditierten und an zentralen Stellen live validierten V3.3-Modbusmodell**.

Insbesondere ist SG Ready über `1334=3` + `8801` jetzt keine Hypothese mehr. Bestätigt sind:

```text
8801 User-Modbus R/W
Mapping 1..4
reale SG-Wirkung
10-Minuten-Hold
Reset des Holds durch Änderung von 1334
2133 als effektive Rückmeldung
abweichendes Verhalten des Warmlink-/LTE-0x63-Pfads
```

Die verbleibenden offenen Einzelbedeutungen sind bewusst als RAW mit Provenance klassifiziert und blockieren die Softwareintegration nicht.