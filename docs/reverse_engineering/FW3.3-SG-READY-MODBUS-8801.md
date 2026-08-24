# Mainboard-Firmware V3.3 – SG Ready über Modbus / Register 8801

Stand: 24. August 2026

Diese Datei dokumentiert den in V3.3 implementierten **virtuellen SG-Ready-Eingang über den normalen Mainboard-Modbus**.

## Kurzfazit

Ja: Die Firmware kann die vier SG-Ready-Zustände vollständig per Modbus vorgeben.

Voraussetzung:

```text
MAIN:1334 / SG01 = 3
```

Dann benutzt die SG-Ready-Zustandsmaschine nicht die beiden physischen SG-Kontakte als Quelle, sondern:

```text
ENG:CTRL:8801
```

Gültige Werte:

| 8801 | interner Kontakt A | interner Kontakt B | Firmware-SG-Modus |
|---:|---:|---:|---|
| 1 | 1 | 0 | SG Mode 1 |
| 2 | 0 | 0 | SG Mode 2 |
| 3 | 0 | 1 | SG Mode 3 |
| 4 | 1 | 1 | SG Mode 4 |

`0` löscht den virtuellen Zustand; Werte `>=5` werden als ungültig behandelt und führen ebenfalls nicht zu einem gültigen virtuellen SG-Zustand.

---

# 1. MAIN:1334 besitzt einen bisher fehlenden Wert 3

Der aktuelle Softwarebestand hatte für `1334 / SG01` bisher im Wesentlichen:

```text
0 = Aus
1 = Einfach / 1 Kontakt
2 = 2 Kontakte
```

Die V3.3-Zustandsmaschine prüft jedoch ausdrücklich auf:

```text
SG source/mode == 3
```

und wechselt dann in einen separaten virtuellen Modbuspfad.

Damit ist ein vierter Konfigurationswert bestätigt:

```text
3 = SG Ready über Modbus / virtueller SG-Eingang
```

Die genaue Herstellerwortwahl ist nicht im Binary enthalten; die Funktion ist bestätigt.

---

# 2. Laufzeitpfad

Die relevante SG-Runtime-Struktur liegt bei:

```text
0x20016948
```

Der virtuelle Pfad liegt ungefähr bei:

```text
0x08081C72 … 0x08081CDE
```

Ablauf:

```text
wenn SG-Quelle != 3:
    normale physische SG-Eingänge auswerten

wenn SG-Quelle == 3:
    8801 lesen
    1..4 in zwei interne SG-Kontaktzustände übersetzen
```

Das Register 8801 liegt bei:

```text
0x20016970 + 0x00
```

Die exakt rekonstruierte Zuordnung ist:

```text
8801 = 1 -> A=1, B=0
8801 = 2 -> A=0, B=0
8801 = 3 -> A=0, B=1
8801 = 4 -> A=1, B=1
```

Diese Kombinationen werden anschließend von derselben SG-Ready-Logik verarbeitet wie die physischen Kontakte.

---

# 3. Bedeutungen der vier Firmware-SG-Modi

Die Firmwareparameter selbst verwenden bereits die Begriffe `SG Mode 1` bis `SG Mode 4`:

```text
1335 SG02 -> Mode 1 Schlafmodus-Zeit
1336 SG03 -> Mode 2 Leistungswert
1337 SG04 -> Mode 3 Leistungswert
1338–1341 -> Mode 4 Sollwertanhebungen / E-Heizer-Freigabe
```

Daher ist die Zuordnung `8801 = 1..4` zu den vier Firmware-SG-Modi direkt konsistent.

Praktische Interpretation:

```text
Mode 1 -> Sperr-/Schlafzustand
Mode 2 -> Normalzustand
Mode 3 -> erhöhte/recommended Aufnahme
Mode 4 -> starke/forced Aufnahme bzw. High-PV
```

Die physikalische SG-Ready-Normbezeichnung kann je nach Dokumentation unterschiedlich formuliert sein; entscheidend für V3.3 sind die vier oben genannten Firmware-Modi.

---

# 4. 8801 ist auf dem normalen Mainboard-/User-Modbus erreichbar

Das ist ausdrücklich **kein Register der internen Display-Slaves 0x02/0x03**.

Der normale Mainboard-Slave-Dispatcher verwendet:

```text
MAIN:1024
```

als konfigurierte Modbus-Slave-Adresse und verarbeitet in derselben State-Machine sowohl:

```text
1001–1540
2001–2180
5001–5180
6001–6090
8801–8820
```

Für 8801–8820 existieren normale Read-/Write-Zweige im Mainboard-Dispatcher.

Damit gilt:

> Wenn eine Schnittstelle bereits `MAIN:1334` und die normalen `MAIN:2xxx`-Register desselben Mainboards lesen/schreiben kann, kann sie grundsätzlich auch `8801` ansprechen.

Unterstützt:

```text
FC03 -> lesen
FC06 -> einzelnes Register schreiben
FC10 -> mehrere Register schreiben
```

Der interne Displaybus über USART3 mit Unit `0x02/0x03` ist dafür nicht erforderlich.

---

# 5. Empfohlene Testfolge

Für einen ersten kontrollierten Test:

```text
1. aktuellen Wert von MAIN:1334 lesen und merken
2. MAIN:8801 = 2 schreiben
3. MAIN:1334 = 3 schreiben
4. MAIN:8801 zurücklesen
5. MAIN:2133 beobachten
6. anschließend MAIN:8801 nacheinander auf 1/2/3/4 setzen
7. MAIN:2133 und Anlagenreaktion vergleichen
8. nach Test MAIN:1334 wieder auf den ursprünglichen Wert setzen
```

Warum zuerst `8801=2`:

```text
8801=2 -> interne Kombination 00 -> SG Mode 2
```

Das ist innerhalb der vier SG-Zustände der normale/neutrale Zustand und daher der sinnvollste Einstieg.

---

# 6. Welches Register zur Rückmeldung verwenden?

Für die effektive SG-Auswertung ist besonders interessant:

```text
MAIN:2133
```

Dieses Register bildet den effektiven SG-Ready-Modus `0..4` ab.

Die Bits 12/13 in:

```text
MAIN:2034
```

sind dagegen die **physischen SG-/Digitaleingänge**.

Bei `MAIN:1334 = 3` können diese physischen Rohbits deshalb unverändert bleiben, obwohl die Anlage intern einen durch 8801 vorgegebenen SG-Zustand verarbeitet.

Für einen Test des virtuellen Pfades deshalb primär:

```text
8801 -> Vorgabe
2133 -> effektives Ergebnis
```

und nicht nur `2034 Bit12/13` beobachten.

---

# 7. Ungültige Werte

Die V3.3 prüft den virtuellen Wert explizit.

```text
8801 = 0
```

führt nicht zu einem der vier gültigen SG-Modi und löscht/setzt den effektiven virtuellen Zustand zurück.

```text
8801 >= 5
```

wird ebenfalls nicht als gültiger SG-Zustand akzeptiert.

Damit sollte Software ausschließlich:

```text
1, 2, 3, 4
```

als auswählbare Zustände anbieten.

---

# 8. Konsequenz für FoxAir_Control

Für `data/foxair_phnix_registers.json` sollte ergänzt werden:

## MAIN:1334 / SG01

```text
0 = Aus
1 = Einfach / 1 Kontakt
2 = 2 physische Kontakte
3 = Modbus / virtueller SG-Ready-Zustand
```

## MAIN/ENG:8801

Neue Definition:

```text
Name: Virtueller SG-Ready-Zustand
R/W: FC03 / FC06 / FC10
Werte:
1 = SG Mode 1
2 = SG Mode 2
3 = SG Mode 3
4 = SG Mode 4
```

Zusätzlicher Hinweis:

```text
Nur wirksam, wenn MAIN:1334 == 3.
```

---

# 9. Sicherheits-/Prioritätsverhalten

Durch `1334 = 3` wird die SG-Quelle bewusst von den physischen Kontakten auf den Modbuswert umgeschaltet.

Daher sollte ein externer Controller bei dauerhafter Nutzung:

- den gewünschten 8801-Zustand explizit setzen,
- nach Neustarts den Zustand erneut prüfen,
- `MAIN:2133` als Rückmeldung überwachen,
- bei Ausfall des Controllers einen definierten Fallback vorsehen.

Ob `8801` selbst über einen Mainboard-Neustart persistent bleibt, ist für eine externe Automatisierung **nicht als sichere Persistenzannahme zu verwenden**; der Zustand sollte nach Neustart erneut gelesen bzw. gesetzt werden.

---

# 10. Zusammenfassung

```text
MAIN:1334 = 3
        ↓
SG-Quelle = virtueller Modbus
        ↓
MAIN/ENG:8801 = 1..4
        ↓
Firmware erzeugt virtuelle SG-Kontaktkombination
        ↓
gewöhnliche SG-Ready-Zustandsmaschine
        ↓
MAIN:2133 = effektiver SG-Modus
```

Damit lässt sich SG Ready in V3.3 vollständig ohne physisches Schalten der beiden SG-Kontakte über den normalen Mainboard-Modbus steuern.
