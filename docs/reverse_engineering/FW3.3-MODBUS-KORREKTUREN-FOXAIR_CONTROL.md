# V3.3 – konkrete Modbus-Korrekturen für `FoxAir_Control/data`

Stand: 24. August 2026

Diese Datei ist die **umsetzbare Delta-Liste** zum ausführlichen V3.3-Modbusaudit.

Vergleichsbasis:

```text
Repository: dosordie/FoxAir_Control
Pfad:       data/
Datei:      foxair_phnix_registers.json
Blob SHA:   ff24c160813f12304b7b8c403be0287b49a84686
```

Die Datei beschreibt nur Änderungen, die aus dem V3.3-Binary bzw. aus **Binary + realem Bus-/Funktionstest** belastbar ableitbar sind. Sie ist noch kein Commit gegen `FoxAir_Control/data` selbst.

---

## 1. Sofort sichere Korrekturen

| Register | aktueller Stand | neuer Stand | Sicherheit |
|---:|---|---|---|
| 2019 Bit0 | Kompressor-Ausgang | Kompressor tatsächlich laufend / Inverter-Istfrequenz != 0 | bestätigt |
| 2019 Bit2 | Lüfter Hochgeschwindigkeitsausgang | mindestens ein Lüfter meldet tatsächliche Aktivität | bestätigt |
| 2026 | `9` | Inverter-Diagnose `INV1:2113` High-Byte | Provenance bestätigt |
| 2027 | `9` | Inverter-Diagnose `INV1:2113` Low-Byte | Provenance bestätigt |
| 2028 | `9` | Inverter-Diagnose `INV1:2118` | Provenance bestätigt |
| 2057 | Livewert, Bedeutung unbestätigt | **T35 AC Input Current** | bestätigt |
| 2071 | Kompressorfrequenz | **Kompressor-Sollfrequenz** | bestätigt |
| 2080 | Kandidat/Displaybusstatus | Inverter-/Driver-Statuswort von `INV1:2099` | Provenance bestätigt |
| 2081 | Fehler 7 | **Inverter-/Driver Fault Word 1** von `INV1:2100` | bestätigt |
| 2082 | Fehler 8 | **Inverter-/Driver Fault Word 2** von `INV1:2109` | bestätigt |
| 2109 | Reserviert | intern von V3.3 beschrieben; Semantik offen | bestätigt |
| 2117 | Reserviert | High-Wort des 32-Bit-Zählers 2117/2118 | bestätigt |
| 2119 | Reserviert | High-Wort des 32-Bit-Zählers 2119/2120 | bestätigt |
| 2121 | Reserviert | High-Wort des 32-Bit-Zählers 2121/2122 | bestätigt |
| 2123 | Reserviert | High-Wort des 32-Bit-Zählers 2123/2124 | bestätigt |
| **2133** | aktiver SG-Modus | **effektiver SG-Ready-Modus 0..4; Umschaltung unterliegt festem 10-Minuten-Hold** | **Binary + live bestätigt** |
| 2136 | berechneter x0,1-Regel-/Modulwert | **T04 / Außentemperatur, zweiter Veröffentlichungsweg** | bestätigt |
| 2137 | Spiegel von 2054 (Kandidat) | **elektrische WP-/Inverterleistung ohne zusätzlichen Leistungsanteil**, `/10 kW` | bestätigt |
| 2138 | Spiegel von 2059 (Kandidat) | **thermische WP-Leistung ohne zusätzlichen Leistungsanteil**, `/10 kW` | bestätigt |
| 2140/2141 | zwei unbekannte RAW | ein gemeinsamer 32-Bit-Wert | Struktur bestätigt |
| 2142/2143 | zwei unbekannte RAW | ein gemeinsamer 32-Bit-Wert | Struktur bestätigt |
| 2146 | Funktion unbekannt | Capability-/Statusbitfeld; V3.3-Basis `0x002C` | bestätigt |
| 2147 | Funktion unbekannt | intern befüllter signed V3.3-Wert | Provenance bestätigt |

Zusätzlich neu aufzunehmen:

| Register | neuer Stand | Sicherheit |
|---:|---|---|
| **1334** | Wert `3` = virtueller SG-Ready-Eingang über Modbus | **Binary + live bestätigt** |
| **8801** | virtueller SG-Ready-Zustand `1..4`; direkter User-Modbus R/W | **Binary + live bestätigt** |

---

## 2. Skalierungen, die jetzt von „plausibel“ auf „bestätigt“ hochgestuft werden können

### 2054

```text
MAIN:2054 = int(float[0x200161A4+0x14] × 10)
scale = 0.1 kW
```

### 2059

```text
MAIN:2059 = int(float[0x200161A4+0x18] × 10)
scale = 0.1 kW
```

### 2060

```text
MAIN:2060 = int(float[0x200161A4+0x1C] × 100)
scale = 0.01 COP
```

### 2137

```text
MAIN:2137 = int(float[0x200161A4+0x20] × 10)
```

### 2138

```text
MAIN:2138 = int(float[0x200161A4+0x10] × 10)
```

---

## 3. 2054/2059 versus 2137/2138

Die vier Register sollen in der Software künftig nicht als Spiegel behandelt werden.

V3.3 bildet:

```text
2137 = P_WP
2138 = Q_WP

2054 = P_WP + P_add
2059 = Q_WP + P_add
2060 = 2059 / 2054
```

Der zusätzliche Beitrag `P_add` stammt aus einem konfigurationsabhängigen Hilfs-/Hydraulikpfad und wird 1:1 auf elektrische Aufnahme und Wärmeleistung addiert; dies ist funktional konsistent mit einem elektrischen Zusatzheizer.

Empfohlene GUI-Namen:

```text
2054 Elektrische Gesamtleistung
2059 Thermische Gesamtleistung / Unit Capacity
2060 Gesamt-COP
2137 Elektrische WP-/Inverterleistung ohne Zusatzheizer
2138 Thermische WP-Leistung ohne Zusatzheizer
```

---

## 4. Energiezähler auf 32 Bit umstellen

Der Softwarekatalog darf die High-Wörter nicht mehr als Reserve darstellen.

```text
Elektrisch Heizen:  2117 high / 2118 low
Thermisch Heizen:   2119 high / 2120 low
Elektrisch Kühlen:  2121 high / 2122 low
Thermisch Kühlen:   2123 high / 2124 low
```

Berechnung:

```text
value32 = (high << 16) | low
```

Zusätzlich existieren:

```text
2125 / 2126
2127 / 2128
```

als zwei weitere native 32-Bit-Energiezähler.

Aufgrund der Betriebszweige sind diese **sehr wahrscheinlich**:

```text
2125/2126 = elektrische Energie Warmwasser/DHW
2127/2128 = thermische Energie Warmwasser/DHW
```

Empfehlung: 32-Bit-Kombination sofort implementierbar; DHW-Klartext bis zur Livekorrelation mit Confidence `very_likely` führen.

---

## 5. 2081 / 2082: Provenance ergänzen

### 2081

```text
remote_source = INV1:2100
role = Compressor/Inverter Driver Fault Word 1
```

Sonderfall `2081 Bit15` wird lokal vom Mainboard erzeugt, wenn Unit `0x01` nicht mehr gültig antwortet.

Besserer Text:

```text
Mainboard ↔ Inverterboard Kommunikation ausgefallen
```

### 2082

```text
remote_source = INV1:2109
role = Compressor/Inverter Driver Fault Word 2
```

Die bestehenden Bitnamen separat prüfen; kein pauschales Überschreiben.

---

## 6. 2146 als Bitfeld anlegen

Vorläufiges Schema:

```json
{
  "2146": {
    "type": "BITFIELD",
    "name": "V3.3 Capability-/Statusflags",
    "bit_map": {
      "1": "internes Flag; Bedeutung offen",
      "2": "V3.3 Basisflag; Bedeutung offen",
      "3": "V3.3 Basisflag; Bedeutung offen",
      "4": "internes Laufzeitflag; Bedeutung offen",
      "5": "V3.3 Basisflag; Bedeutung offen",
      "6": "internes Laufzeitflag; Bedeutung offen"
    }
  }
}
```

Bits 2, 3 und 5 sind in diesem V3.3-Build immer gesetzt. Normaler Basiswert:

```text
0x002C = 44
```

Der reale Mitschnitt zeigt exakt diesen Wert.

---

## 7. Neue Register 2150–2180 ergänzen

Der aktuelle aktive Katalog endet bei 2149. V3.3 broadcastet jedoch bis 2180.

Konservative Ersteinträge:

| Register | vorgeschlagener Name | Typ/Quelle |
|---:|---|---|
| 2150 | Reserve / im Hauptbuilder nicht gesetzt | RAW |
| 2151 | V3.3 Diagnose 2151 | uint8 `0x20016A44+0x14` |
| 2152 | V3.3 Diagnose 2152 | int16 `0x20016A44+0x1C` |
| 2153 | V3.3 Diagnose 2153 | int16 `0x20015EF0+0x06` |
| 2154 | V3.3 Diagnose 2154 | uint16 `0x20015EF0+0x0A` |
| 2155 | V3.3 Diagnose 2155 | uint16 `0x20015EF0+0x0C` |
| 2156 | V3.3 Diagnose 2156 | int16 `0x20015EF0+0x08` |
| 2157 | V3.3 Diagnose 2157 | uint16 `0x20015EF0+0x10` |
| 2158 | V3.3 Diagnose 2158 | uint16 `0x20015EF0+0x12` |
| 2159 | Reserve / im Hauptbuilder nicht gesetzt | RAW |
| 2160 | V3.3 Diagnose 2160 | uint16 `0x2001605C+0x66` |
| 2161 | V3.3 Diagnose 2161 | uint16 `0x20016100+0x78` |
| 2162 | V3.3 Diagnose 2162 | uint16 `0x20016100+0x66` |
| 2163 | V3.3 berechnete Prozent-/Verhältnisgröße | berechnet, auf 100 begrenzt |
| 2164 | V3.3 Diagnose 2164 | uint16 `0x2001605C+0x7A` |
| 2165 | V3.3 Diagnose 2165 | uint16 `0x20016100+0x7A` |
| 2166 | V3.3 Diagnose 2166 | int16 `0x20016100+0x46` |
| 2167–2177 | Reserve / im Hauptbuilder nicht gesetzt | RAW |
| 2178 | V3.3 Diagnose 2178 | uint16 `0x20016DB4+0x00` |
| 2179 | V3.3 Diagnose 2179 | uint16 `0x20016DB4+0x02` |
| 2180 | V3.3 Diagnose 2180 | uint16 `0x20016DB4+0x04` |

Reale Beispielwerte:

```text
2152 = 1
2164 = 450
2165 = 350
2166 = 1
```

Die Felder zunächst sichtbar/loggbar machen, aber nicht mit erfundenen Herstellerbezeichnungen versehen.

---

## 8. SG Ready / 1334 / 8801 – jetzt live bestätigt

Dieser Punkt ist seit den Tests vom 24.08.2026 kein reiner Reverse-Engineering-Kandidat mehr.

### MAIN:1334

Ergänzen:

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
3 = virtueller SG-Ready-Eingang über Modbus
```

### ENG:CTRL:8801

Neues Registermodell:

```text
Name: Virtueller SG-Ready-Zustand
Adresse: 8801 / 0x2261
Werte: 1..4
Wirksam wenn: MAIN:1334 == 3
Direkter User-Modbus: R/W live bestätigt
```

Mapping:

```text
1 -> Kontakte (1,0) -> Mode 1
2 -> Kontakte (0,0) -> Mode 2
3 -> Kontakte (0,1) -> Mode 3
4 -> Kontakte (1,1) -> Mode 4
```

Live beobachtet unter anderem:

```text
8801=1 -> Mode 1 / Schlafmodus; WP startet nicht
8801=4 -> Mode 4 / High Power; WP startet
```

### Fester 10-Minuten-Hold

Nach jeder tatsächlich akzeptierten SG-Modusänderung gilt:

```text
hold = 1200 Zyklen
SG-Zyklus = 0,5 s
=> 10 Minuten
```

Während des Holds ändert sich `8801` sofort, `MAIN:2133` bleibt aber zunächst auf dem zuletzt akzeptierten Mode. Nach Ablauf wird der dann aktuell anliegende gewünschte Zustand übernommen.

### MAIN:1334 resettiert den Hold

**Binary + live bestätigt:** Eine Änderung der SG-Quellenauswahl in `1334` setzt den laufenden 10-Minuten-Hold und zugehörige Übergangszustände zurück.

Softwarehinweis:

- `2133` ist die effektive Rückmeldung, nicht `8801` selbst.
- UI sollte einen laufenden/erwartbaren Hold erklären.
- Ein 1334-Quellenwechsel sollte nicht automatisch als Methode für schnelles Umschalten verwendet werden.

### User-Modbus und Warmlink/LTE nicht gleich behandeln

Direkter User-Modbus:

```text
8801 lesen/schreiben -> live bestätigt
```

Warmlink-/LTE, Slave `0x63`:

```text
1334 R/W -> funktioniert
2133 R   -> funktioniert
8801 FC03 -> Timeout
8801 FC16 -> ACK, tatsächlicher Apply auf User-8801 nicht bestätigt
```

Daher muss das Backend die Zugriffswege getrennt behandeln.

---

## 9. Unit-1-Remote-Reg. 2002 ebenfalls korrigieren

```text
INV1:2002
    ← 0x200162D8+0x5C
    ↔ MAIN:1343
```

Im aktuellen `FoxAir_Control`-Parameterbestand ist:

```text
MAIN:1343 = A39 / Max. Current Value
```

Damit ist das Remote-Wort funktional:

> **Maximalstrom-/Current-Limit-Vorgabe an das Inverterboard**

---

## 10. Noch nicht automatisch in FoxAir_Control ändern

Folgende Punkte bleiben bewusst Kandidaten/offen:

```text
2106 exakte Pumpenregel-Semantik
2080 fachliche Bedeutung von INV1:2099
2026–2028 fachliche Bedeutung der Rohdiagnose
2125–2128 DHW-Klartext
2140–2143 fachliche Zählerbedeutung
2146 Klartexte der einzelnen Flags
2147 fachliche Bedeutung
2151–2166 fachliche Bedeutung
2178–2180 fachliche Bedeutung
8802–8820 Engineering-Semantik
```

Wichtig ist die Trennung:

- **Provenance** kann bestätigt sein,
- während die **fachliche Herstellerbezeichnung** offen bleibt.

---

## 11. Empfohlene Reihenfolge beim späteren Software-Commit

1. sichere Namen/Descriptions korrigieren,
2. `1334 = 3` und `8801` einschließlich Werte 1..4 aufnehmen,
3. 10-Minuten-Hold und 1334-Hold-Reset in SG-UI/Logik dokumentieren,
4. User- und Warmlink-/LTE-Zugriffsrechte getrennt modellieren,
5. 2054/2059/2060 Confidence hochstufen,
6. Energiezähler 32-Bit-fähig machen,
7. 2150–2180 konservativ ergänzen,
8. Runtime-/Remote-Provenance als Metadaten hinzufügen,
9. erst danach GUI-Texte für noch offene Felder weiter verfeinern.

---

## 12. Verwandte Dokumente

- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md)
- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md)
- [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md)
- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md)