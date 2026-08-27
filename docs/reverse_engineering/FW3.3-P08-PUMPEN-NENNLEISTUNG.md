# Mainboard-Firmware V3.3 – P08 / MAIN:1204 „Pumpen-Nennleistung“

Stand: 27. August 2026

Dieses Dokument untersucht gezielt den Parameter `P08 / MAIN:1204`, der in PHNIX-/DWIN-Unterlagen als Pumpen-Nennleistung bzw. `Water Pump Rating Power` in Watt geführt wird.

Untersuchtes Mainboard-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
```

## Kurzfazit

Für die untersuchte Mainboard-Firmware V3.3 ist `MAIN:1204 / P08` **kein aktiver Regelparameter**.

Der Parameter existiert im öffentlichen 1xxx-Modbusspiegel und im DWIN-HMI weiterhin als normaler Kommunikationsparameter, wird vom Mainboard aber bewusst aus den Pumpen-Live-Strukturen ausgespart.

Es wurde im Binary weder ein direkter Transfer von `MAIN:1204` in eine Live-Runtime-Struktur noch ein funktionaler Verbraucher dieses Registerwertes gefunden.

Damit gilt für V3.3:

> `P08 / 1204` beeinflusst weder Pumpen-PWM noch Durchflussberechnung noch thermische/elektrische Leistungs- oder Energiezähler.

Die frühere Vermutung, P08 könne zur elektrischen Pumpenleistungsberechnung oder COP-Korrektur verwendet werden, ist damit für diesen Build verworfen.

---

# 1. Position im öffentlichen Parameter-Spiegel

Der Parameterbereich liegt im zentralen Modbusspiegel bei:

```text
0x20012788
```

Für MAIN:P gilt:

```text
Offset = 0x3E8 + 2 × (Register - 1001)
```

Für Register 1204 ergibt sich:

```text
0x3E8 + 2 × (1204 - 1001)
= 0x57E
```

Damit liegt `MAIN:1204` im öffentlichen Spiegel bei:

```text
0x20012788 + 0x57E
```

---

# 2. Pumpenparameter 1197–1205: 1204 wird explizit ausgelassen

Die aktive Pumpenmodus-/Timerstruktur liegt bei:

```text
0x20016C6C
```

Der Status-/Parameterbuilder überträgt:

```text
1197 <- +0x00
1198 <- +0x02
1199 <- +0x04
1201 <- +0x06
1202 <- +0x08
1203 <- +0x0A
1205 <- +0x0C
```

Bytegenau im Mirror:

```text
1197 -> Mirror +0x570
1198 -> Mirror +0x572
1199 -> Mirror +0x574
1200 -> +0x576   nicht Teil dieser Pumpenstruktur
1201 -> Mirror +0x578
1202 -> Mirror +0x57A
1203 -> Mirror +0x57C
1204 -> +0x57E   AUSGELASSEN
1205 -> Mirror +0x580
```

Entscheidend:

```text
... +0x57C
direkt danach
... +0x580
```

Es existiert an dieser Stelle **kein Store auf +0x57E**.

Damit liefert keine aktive Pumpen-Livevariable einen Wert nach MAIN:1204.

**Bewertung: bestätigt.**

---

# 3. Gegenrichtung: MAIN:1204 wird auch nicht in die Pumpen-Runtime übernommen

Beim Synchronisieren des öffentlichen Parameter-Spiegels zurück in die Pumpen-Live-Struktur liest V3.3 ebenfalls nur:

```text
Mirror +0x570 -> 0x20016C6C+0x00
Mirror +0x572 -> +0x02
Mirror +0x574 -> +0x04
Mirror +0x578 -> +0x06
Mirror +0x57A -> +0x08
Mirror +0x57C -> +0x0A
Mirror +0x580 -> +0x0C
```

Wieder wird:

```text
Mirror +0x57E / MAIN:1204
```

vollständig übersprungen.

Damit ist ausgeschlossen, dass P08 über den normalen Parameter-Sync als verstecktes Feld der Pumpenstruktur wirkt.

**Bewertung: bestätigt.**

---

# 4. Xref-Audit auf MAIN:1204

Im untersuchten V3.3-Binary wurde gezielt nach direkten Zugriffen auf den Mirror-Offset `0x57E` gesucht.

Ergebnis:

```text
kein LDRH [mirror,#0x57E]
kein STRH [mirror,#0x57E]
kein funktionaler Verbraucher mit festem Register 1204
```

Die einzige textuelle/Disassembly-Nähe zu `0x57E` ist ein Branch-Immediate und kein Datenzugriff.

Damit gibt es keinen statisch nachweisbaren Datenpfad:

```text
MAIN:1204
 -> Pumpenregelung
 -> elektrische Leistung
 -> thermische Leistung
 -> COP
 -> Energiezähler
```

**Bewertung: bestätigt für direkte Firmware-Xrefs.**

---

# 5. DWIN/HMI führt P08 weiterhin als normalen Parameter

Im DWIN-ASM existiert P08 ausdrücklich:

```text
; P08
LDWR R240,04B4H   ; Kommunikationsvariable
LDWR R242,24B4H   ; Benutzerdefinierte Einstellung
LDWR R244,34B4H   ; letzter benutzerdefinierter Wert
LDWR R246,14B4H   ; letzte Kommunikationsvariable
...
CALL Four_Variable_Communication
```

`0x04B4` entspricht dezimal:

```text
1204
```

Damit behandelt das Display P08 wie einen normalen Kommunikations-/Einstellparameter.

Das erklärt, warum P08 in Hersteller-/Displayunterlagen und Bedienoberflächen weiterhin sichtbar sein kann, obwohl die V3.3-Mainboardregelung ihn funktional nicht verwendet.

Interpretation:

> sehr wahrscheinlich Altkompatibilität bzw. ein Parameter für andere PHNIX-Plattformvarianten, der in dieser Mainboard-Firmware nicht mehr aktiv implementiert ist.

**Bewertung: DWIN-Existenz bestätigt; historische Herstellerabsicht sehr wahrscheinlich.**

---

# 6. Was passiert bei einem Modbus-Write auf 1204?

Der allgemeine direkte Mainboard-Modbusdispatcher akzeptiert den normalen 1xxx-Parameterbereich grundsätzlich über FC06/FC10.

Damit kann `MAIN:1204` im öffentlichen Parameter-Spiegel beschrieben werden.

Aber:

```text
Write MAIN:1204
   ↓
öffentlicher Mirror +0x57E
   ↓
kein Transfer in Pumpen-Live-RAM
   ↓
kein nachgewiesener Verbraucher
```

Ein Write kann daher lesbar erscheinen bzw. vom HMI synchronisiert werden, ohne eine Regelwirkung zu besitzen.

Ob der reine Spiegelwert bei allen Speicher-/Neustartpfaden dauerhaft erhalten bleibt, ist für die Funktionsfrage nebensächlich und wurde hier nicht als erforderlich geschlossen.

---

# 7. Kein Einfluss auf die Pumpen-PWM

Die aktive PWM-Regelung benutzt in V3.3 unter anderem:

```text
P10   feste/automatische PWM
P11   Ziel-Wasserspreizung
P12   Schrittweite
A40   Nenn-Wasserdurchfluss
D22   Mindest-/Abtau-Durchflussgrenze
H31   Pumpentyp / Durchflusskennlinie
1022  signed Durchfluss-Korrekturoffset
2116  gemessene Pumpen-PWM-Rückmeldung
```

`P08 / 1204` taucht in diesem Regelpfad nicht auf.

Damit gilt:

```text
P08 ändern
!= PWM-Kennlinie ändern
!= Pumpen-Sollwert ändern
!= Auto-PWM-Regelung ändern
```

---

# 8. Kein Einfluss auf die Durchflussberechnung

Die lokale Durchflussberechnung läuft über:

```text
2116 PWM-Feedback
 -> H31-Kennlinie
 -> + MAIN:1022 Offset
 -> Runtime 0x20016F14
 -> MAIN:2077
```

P08 ist kein Bestandteil dieser Gleichung.

Insbesondere wird die in Watt gedachte Pumpen-Nennleistung nicht benutzt, um aus der elektrischen Leistungsrückmeldung der Grundfos-Pumpe einen Durchfluss abzuleiten.

Das ist für UPM4L-Pumpen wichtig: Auch wenn deren PWM-Rückmeldung elektrische Pumpenleistung repräsentiert, hat V3.3 keinen P08-basierten Umrechnungsweg dafür.

---

# 9. Kein Einfluss auf elektrische Leistungs-/COP-Berechnung

Im Audit wurde kein Pfad gefunden, der P08 zu folgenden Größen führt:

```text
MAIN:2054 elektrische Gesamtleistung
MAIN:2059 thermische Gesamtleistung
MAIN:2060 COP
MAIN:2137 WP-only elektrische Leistung
MAIN:2138 WP-only thermische Leistung
2117ff Energiezähler
```

Die frühere Arbeitshypothese:

```text
P08 = Pumpen-Nennleistung
 -> elektrische Pumpenaufnahme schätzen
 -> Gesamtleistung/COP korrigieren
```

ist daher für Mainboard-Firmware V3.3 **nicht bestätigt, sondern widerlegt**.

---

# 10. Praktische Konsequenz für FoxAir V3.3

Für die untersuchte Anlage sollte P08 auf seinem bisherigen Wert bleiben:

```text
MAIN:1204 = 0
```

Eine Eingabe der tatsächlichen UPM4L-Nennleistung bringt nach aktuellem Binarybefund keinen Vorteil.

Für die Pumpen-/Durchflusskalibrierung sind stattdessen relevant:

```text
H31
MAIN:1022
P10/P11/P12
A40
D22
```

Insbesondere die empirisch kalibrierte Kombination aus passender H31-Kennlinie und `MAIN:1022` wirkt tatsächlich auf den gemeinsamen Runtime-Durchfluss und damit auf Auto-PWM, Schutz-/Mindestdurchflusslogik und thermische Leistungs-/Wärmemengenberechnung.

---

# 11. Status

| Aussage | Bewertung |
|---|---|
| P08 existiert im DWIN als Parameter 1204 | bestätigt |
| MAIN:1204 liegt im normalen Modbus-Parameterspiegel | bestätigt |
| Mirror-Offset ist `+0x57E` | bestätigt |
| Pumpenbuilder überspringt 1204 | bestätigt |
| Parameter-Sync zurück zur Pumpenstruktur überspringt 1204 | bestätigt |
| direkter funktionaler Xref auf `+0x57E` | keiner gefunden |
| Einfluss auf PWM | kein Nachweis / für V3.3 verworfen |
| Einfluss auf Durchfluss | kein Nachweis / für V3.3 verworfen |
| Einfluss auf elektrische Leistung/COP/Energie | kein Nachweis / für V3.3 verworfen |
| wahrscheinlich Alt-/Plattformkompatibilität | sehr wahrscheinlich |

## Fazit

> `P08 / MAIN:1204` ist in der FoxAir-Mainboard-Firmware V3.3 ein öffentlich sichtbarer, vom DWIN weiterhin bedienter Kompatibilitätsparameter, aber kein aktiver Pumpen- oder Energieparameter.
