# Mainboard-Firmware V3.3 – Modbus-Statusregister 2001–2180: Audit gegen FoxAir_Control

Stand: 24. August 2026

Diese Datei dokumentiert den vollständigen Audit des öffentlichen V3.3-Statusbereichs gegen den aktuellen Wissensstand in `FoxAir_Control/data`.

Quellen:

1. V3.3-Binary `phnixIot_device_OTA` als Primärquelle,
2. `dosordie/FoxAir_Control/data`, insbesondere `foxair_phnix_registers.json`, `foxair_phnix_knowledge.json`, `foxair_phnix_display_registers.json`,
3. vorhandene Reverse-Engineering-Dokumente,
4. reale Modbus-/USART3-Mitschnitte,
5. inzwischen auch gezielte Live-Funktionstests der SG-Ready-State-Machine.

Untersuchtes Mainboard-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Größe:        287598 Byte
MD5:          CEB6A4BF386FF644E23E410023E74673
SHA-256:      6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:   0x08050000
```

Bewertung:

- **bestätigt** – direkt aus dem Binary geschlossen
- **live bestätigt** – zusätzlich am realen Gerät praktisch verifiziert
- **sehr wahrscheinlich** – Datenfluss/Struktur geschlossen, letzte Herstellerbezeichnung fehlt
- **offen** – Register wird verwendet, fachliche Bedeutung noch nicht ausreichend geschlossen

---

# 1. Ergebnis in Kurzform

Der aktuelle Datenbestand in `FoxAir_Control/data` ist bereits weit fortgeschritten. Der Audit ergibt keinen grundlegenden Registerversatz, sondern gezielte Korrekturen und V3.3-private Erweiterungen.

Wichtigste Ergebnisse:

1. **2057 = T35 / AC Input Current**.
2. **2054, 2059, 2060** haben bytegenau bestätigte Skalierungen `/10`, `/10`, `/100`.
3. **2071 = Kompressor-Sollfrequenz**, 2072 tatsächliche Betriebsfrequenz.
4. **2080 stammt direkt von INV1:2099**.
5. **2081/2082 = Inverter-/Driver-Fehlerwörter**; 2081 Bit15 wird lokal als Unit-1-Kommunikationsfehler erzeugt.
6. **2019 Bit0/Bit2 sind Ist-Rückmeldungen**, keine simplen lokalen Ausgangsbefehle.
7. **2026–2028 sind Unit-1-Diagnosefelder**.
8. **2117/2119/2121/2123 sind High-Wörter von 32-Bit-Energiezählern**.
9. **2125/2126 und 2127/2128** bilden zwei weitere 32-Bit-Energiezählerpaare, sehr wahrscheinlich DHW elektrisch/thermisch.
10. **2133 = tatsächlich aktiver SG-Ready-Modus 0..4** und unterliegt einem **festen 10-Minuten-Hold zwischen akzeptierten Modewechseln**.
11. **2136 = zweiter T04-/Außentemperaturwert**.
12. **2137/2138 sind WP-only-Leistungsgrößen**, keine simplen Spiegel von 2054/2059.
13. **2140–2143 = zwei 32-Bit-Werte**.
14. **2146 = Capability-/Statusbitfeld**, Basiswert `0x002C`.
15. V3.3 baut und broadcastet bis **2180**; 2151–2166 und 2178–2180 haben bestätigte interne Quellen.

---

# 2. Namespace-Modell

Beispiel:

```text
MAIN:2081   = öffentliches Mainboard-Fehlerwort
INV1:2100   = Remote-Reg. 2100 auf internem Inverterboard Unit 0x01
```

Datenfluss:

```text
INV1:2100
    ↓ RX-Parser
Mainboard-Runtime 0x200168C4
    ↓ Fehlerfilter
MAIN:2081
```

Dasselbe Prinzip gilt für Fan-Drive Unit 0x04, Display Unit 0x03, Hydraulikmodule und Engineeringregister.

---

# 3. Statusbuilder und Registerspiegel

Der zentrale öffentliche Statusspiegel liegt bei:

```text
0x20012788
```

Für den Hauptstatusbereich gilt:

```text
Mirror-Offset = 0x820 + 2 × (Register - 2001)
```

Der Builder erzeugt zwei 90-Wort-Blöcke:

```text
2001 … 2090
2091 … 2180
```

und verteilt diese anschließend auf dem internen USART3-Modbus per Broadcast `0x00 / FC10`.

Der reale Mitschnitt bestätigt den zweiten Block bis 2180.

---

# 4. Register 2019 – zwei wichtige Ist-Rückmeldungen

## Bit0

```text
0x200168C4 + 0x06 != 0
→ 2019 Bit0 = 1
```

Semantik:

> **Kompressor tatsächlich laufend / Inverter-Istfrequenz ungleich 0**

## Bit2

```text
0x2001691C +0x0C != 0
ODER
0x2001691C +0x0E != 0
→ 2019 Bit2 = 1
```

Semantik:

> **Mindestens ein Lüfter meldet tatsächliche Aktivität**

---

# 5. Register 2026–2028 – versteckte Inverterdiagnose

```text
INV1:2113 High-Byte → MAIN:2026
INV1:2113 Low-Byte  → MAIN:2027
INV1:2118           → MAIN:2028
```

Vorläufige Namen:

```text
2026 = Inverter-Diagnose 2113 High-Byte
2027 = Inverter-Diagnose 2113 Low-Byte
2028 = Inverter-Diagnose 2118
```

Provenance bestätigt, fachliche Rohwertsemantik offen.

---

# 6. 2042–2044 / 2057 / 2061 / 2062 – Invertertelemetrie

| MAIN | Quelle INV1 | Runtime | Bedeutung |
|---:|---:|---|---|
| 2042 | 2107 | `0x200168C4+0x10` | Kompressor-Phasenstrom |
| 2043 | 2108 | `+0x12` | DC-Bus-Spannung |
| 2044 | 2110 | `+0x16` | IPM-Temperatur |
| **2057** | **2106** | `+0x0E` | **T35 AC Input Current** |
| 2061 | 2104 | `+0x0A` | T33 IPM High Fault Temp. |
| 2062 | 2105 | `+0x0C` | T34 AC Input Voltage |

Für 2044:

```text
MAIN:2044 = (INV1:2110 - 55) × 10
```

---

# 7. 2054, 2059, 2060 – Leistung und COP

```text
MAIN:2054 = int(float[0x200161A4+0x14] × 10)
MAIN:2059 = int(float[0x200161A4+0x18] × 10)
MAIN:2060 = int(float[0x200161A4+0x1C] × 100)
```

Damit:

```text
2054 raw/10 = kW elektrische Gesamtleistung
2059 raw/10 = kW thermische Gesamtleistung
2060 raw/100 = Gesamt-COP
```

---

# 8. 2137 und 2138 – WP-only-Leistungen

V3.3 benutzt unterschiedliche Floatfelder:

```text
2137 ← 0x200161A4 + 0x20
2138 ← 0x200161A4 + 0x10
2054 ← 0x200161A4 + 0x14
2059 ← 0x200161A4 + 0x18
```

## 2137

Elektrische WP-/Inverterleistung vor Addition eines zusätzlichen Leistungsanteils:

```text
raw / 10 = kW
```

## 2138

Thermische WP-Leistung aus Volumenstrom × Delta-T × 1,163, ebenfalls vor Zusatzanteil:

```text
raw / 10 = kW
```

Zusammenhang:

```text
2137 = P_WP
2138 = Q_WP
2054 = P_WP + P_add
2059 = Q_WP + P_add
```

---

# 9. Register 2071–2073 – Soll und Ist

```text
2071 = Kompressor-Sollfrequenz
2072 = Kompressor-Ist-/Betriebsfrequenz
2073 = vom Driver gemeldete maximale zulässige Frequenz
```

2071 stammt aus:

```text
0x20016AA4 + 0x08
```

und wird als `INV1:1999` an das Inverterboard übertragen.

---

# 10. 2080–2082 – Inverterstatus und Driverfehler

```text
INV1:2099 → MAIN:2080
INV1:2100 → MAIN:2081
INV1:2109 → MAIN:2082
```

`2081 Bit15` wird vom Mainboard selbst gesetzt, wenn gültige Antworten von Unit 0x01 ausbleiben. Ein Watchdogzähler bei `0x20016F9E` läuft bis `0xF0`; anschließend wird der Kommunikationsfehler gesetzt und die Inverter-Istfrequenz auf 0 gesetzt.

---

# 11. Register 2109 – nicht Reserve

Ein separater V3.3-Pfad schreibt:

```text
0x20016EF0
→ MAIN:2109
```

Damit ist 2109 aktiv und darf nicht als sichere Reserve klassifiziert werden.

---

# 12. Energiezähler 2117–2128 – native 32-Bit-Struktur

| High | Low | Runtime-Quelle | Bedeutung |
|---:|---:|---|---|
| 2117 | 2118 | `0x200161A4+0x58` | elektrisch Heizen |
| 2119 | 2120 | `+0x60` | thermisch Heizen |
| 2121 | 2122 | `+0x54` | elektrisch Kühlen |
| 2123 | 2124 | `+0x64` | thermisch Kühlen |
| 2125 | 2126 | `+0x50` | sehr wahrscheinlich elektrisch DHW |
| 2127 | 2128 | `+0x5C` | sehr wahrscheinlich thermisch DHW |

```text
value32 = (HIGH << 16) | LOW
```

Die 32-Bit-Struktur ist bestätigt; die DHW-Bezeichnung des dritten Paars bleibt `very_likely` bis zur separaten Warmwasser-Livekorrelation.

---

# 13. MAIN:2133 – aktiver SG-Ready-Modus

`MAIN:2133` zeigt den **tatsächlich von der SG-Ready-State-Machine übernommenen Modus**:

| 2133 | Bedeutung |
|---:|---|
| 0 | WP aus oder SG deaktiviert |
| 1 | SG Mode 1 / Schlafmodus |
| 2 | SG Mode 2 / wenig PV / Normalzustand |
| 3 | SG Mode 3 / mittel PV |
| 4 | SG Mode 4 / High PV |

## 13.1 Verbindung zu MAIN:1334 und ENG:CTRL:8801

Bei:

```text
MAIN:1334 = 3
```

kommt der gewünschte Zustand aus:

```text
ENG:CTRL:8801
```

Mapping:

```text
8801=1 -> Mode 1
8801=2 -> Mode 2
8801=3 -> Mode 3
8801=4 -> Mode 4
```

Der direkte User-Modbus-Zugriff und die reale SG-Wirkung wurden am Gerät bestätigt.

## 13.2 Fester 10-Minuten-Hold

Nach jeder tatsächlich akzeptierten Modeänderung schreibt V3.3:

```text
0x2001696C = 1200
```

Die SG-State-Machine läuft alle `0,5 s`, daher:

```text
1200 × 0,5 s = 600 s = 10 Minuten
```

Während des Holds:

```text
8801 kann sofort einen neuen Sollzustand enthalten
2133 bleibt auf dem zuletzt akzeptierten Modus
```

Nach Ablauf wird der dann aktuell anliegende Sollzustand übernommen.

Damit ist `2133` bewusst **kein unmittelbares Echo eines 8801-Writes**, sondern die effektive State-Machine-Ausgabe.

## 13.3 Änderung von MAIN:1334 setzt den Hold zurück

V3.3 setzt bei Änderung der SG-Quellenauswahl den Hold-Timer und interne Übergangszustände zurück.

Dieses Verhalten wurde am 24.08.2026 **am realen Gerät getestet und bestätigt**.

Damit ist für Software wichtig:

- `2133` als effektives Feedback verwenden,
- bis zu 10 Minuten Umschaltzeit korrekt darstellen,
- Quellenwechsel über `1334` als State-Machine-Reset behandeln.

## 13.4 WP aus

Am untersuchten Gerät aktualisiert `2133` den aktiven SG-Zustand insbesondere bei eingeschalteter/aktiver WP. Bei ausgeschalteter WP ist `2133=0` bzw. die unmittelbare Mode-Rückmeldung daher kein gleichwertiger Funktionstest.

Details:

[`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)

---

# 14. Register 2136 – zweiter T04-/Außentemperaturwert

Helper `0x0808799C` schreibt nach MAIN:2136 und ist als T04/Außentemperatur bestätigt.

```text
2136 = zweiter T04-/Außentemperaturwert, x0,1 °C
```

---

# 15. Register 2140–2143 – zwei 32-Bit-Werte

```text
2140 = High 0x200161A4+0x6C
2141 = Low  0x200161A4+0x6C
2142 = High 0x200161A4+0x68
2143 = Low  0x200161A4+0x68
```

Damit sind es zwei 32-Bit-Zähler/Akkumulatoren, keine vier unabhängigen 16-Bit-Werte.

---

# 16. Register 2146 – Capability-/Statusbitfeld

Basis:

```text
Bit2 = 1
Bit3 = 1
Bit5 = 1
→ 0x002C = 44
```

Variable Bits:

```text
Bit1 ← 0x20015C68+0x10E
Bit4 ← 0x20016E3C != 0
Bit6 ← 0x20016FB2 != 0
```

Klassifikation:

> **2146 = V3.3 Capability-/Statusbitfeld**

---

# 17. Register 2147

```text
MAIN:2147 ← signed 0x20015C68+0x110
```

Aktiv befüllt, fachliche Semantik offen.

---

# 18. V3.3-Erweiterungsbereich 2150–2180

Der aktuelle `FoxAir_Control`-Katalog endet bei 2149, V3.3 erzeugt/broadcastet aber bis 2180.

| MAIN | Quelle | Typ | Live-Beispiel | Semantik |
|---:|---|---|---:|---|
| 2150 | im Hauptbuilder nicht gesetzt | – | 0 | Reserve/anderer Pfad |
| 2151 | `0x20016A44+0x14` | uint8 | 0 | offen |
| 2152 | `0x20016A44+0x1C` | int16 | 1 | offen |
| 2153 | `0x20015EF0+0x06` | int16 | 0 | offen |
| 2154 | `0x20015EF0+0x0A` | uint16 | 0 | offen |
| 2155 | `0x20015EF0+0x0C` | uint16 | 0 | offen |
| 2156 | `0x20015EF0+0x08` | int16 | 0 | offen |
| 2157 | `0x20015EF0+0x10` | uint16 | 0 | offen |
| 2158 | `0x20015EF0+0x12` | uint16 | 0 | offen |
| 2159 | im Hauptbuilder nicht gesetzt | – | 0 | Reserve/anderer Pfad |
| 2160 | `0x2001605C+0x66` | uint16 | 0 | offen |
| 2161 | `0x20016100+0x78` | uint16 | 0 | offen |
| 2162 | `0x20016100+0x66` | uint16 | 0 | offen |
| 2163 | berechnet, auf 100 begrenzt | Ratio/Prozent-artig | 0 | offen |
| 2164 | `0x2001605C+0x7A` | uint16 | **450** | offen |
| 2165 | `0x20016100+0x7A` | uint16 | **350** | offen |
| 2166 | `0x20016100+0x46` | int16 | **1** | offen |
| 2167–2177 | im Hauptbuilder nicht befüllt | – | 0 | Reserve/anderer Pfad |
| 2178 | `0x20016DB4+0x00` | uint16 | 0 | offen |
| 2179 | `0x20016DB4+0x02` | uint16 | 0 | offen |
| 2180 | `0x20016DB4+0x04` | uint16 | 0 | offen |

---

# 19. Register 2130–2132

Die vorhandenen Softwarebezeichnungen passen zur V3.3:

```text
2130 = IPM-Temperatur des externen Lüftermotorantriebs
2131 = Leistung des externen Lüftermotorantriebs
2132 = Strom des externen Lüftermotorantriebs
```

Nur Provenance ergänzen.

---

# 20. Register 2106

Der aktuelle Live-Kandidat für 2106 als zyklisches Pumpenregel-/PWM-Fenster bleibt bestehen, ist aber noch nicht vollständig statisch geschlossen.

---

# 21. Register 2111/2112 – Display-Identität

Interner Bus Unit `0x03` liefert u.a.:

```text
Softwarecode 463
Version 17 = V1.7
```

Öffentlich:

```text
2111 = 463
2112 = 17
```

Zuordnung damit bestätigt.

---

# 22. Aktionsliste für FoxAir_Control

## Sofort sicher korrigierbar

```text
2019 Bit0  → Kompressor tatsächlich laufend / Istfrequenz != 0
2019 Bit2  → mindestens ein Lüfter tatsächlich aktiv
2026       → INV1:2113 High-Byte Diagnose
2027       → INV1:2113 Low-Byte Diagnose
2028       → INV1:2118 Diagnose
2057       → T35 AC Input Current
2071       → Kompressor-Sollfrequenz
2080       → Inverter-/Driver-Statuswort INV1:2099
2081       → Driver Fault Word 1
2082       → Driver Fault Word 2
2109       → intern beschriebener V3.3-Status
2117/19/21/23 → High-Wörter der 32-Bit-Energiezähler
2133       → effektiver SG-Modus 0..4; 10-min-Hold dokumentieren
2136       → T04 Außentemperatur, zweiter Veröffentlichungsweg
2137       → elektrische WP-/Inverterleistung ohne Zusatzanteil, /10 kW
2138       → thermische WP-Leistung ohne Zusatzanteil, /10 kW
2140/2141 → 32-Bit-Paar
2142/2143 → 32-Bit-Paar
2146       → Capability-/Statusbitfeld; Basis 0x2C
2147       → intern befüllter V3.3-Wert
```

Zusätzlich muss die SG-Ready-UI wissen:

```text
MAIN:1334 = 3 aktiviert ENG:CTRL:8801
Änderung von MAIN:1334 resettiert den 10-min-Hold
```

## Neu aufnehmen

```text
2150 … 2180
```

mit den dokumentierten Runtime-Quellen und konservativen Namen.

---

# 23. Empfohlenes Datenmodell

Für jedes Register künftig mindestens:

```text
namespace
register
name
block/code
function
access
raw_type
signed
scale
unit
value_map / bit_map
runtime_source
remote_source
producer
consumer
confidence
provenance
notes
```

Für zustandsbehaftete Register wie 2133 zusätzlich sinnvoll:

```text
state_machine
transition_hold
feedback_of
backend_notes
```

---

# 24. Abschlussstatus

Der Statusbereich `2001–2180` ist strukturell geschlossen. Neu hinzugekommen ist die praktische Validierung von:

```text
MAIN:2133 als effektiver SG-Ready-Modus
10-Minuten-Hold zwischen akzeptierten SG-Moduswechseln
Reset dieses Holds bei Änderung von MAIN:1334
```

Damit ist die beobachtete Verzögerung von 2133 nicht mehr nur plausibel, sondern aus V3.3 erklärt und live bestätigt.

---

# 25. Verwandte Dokumente

- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md)