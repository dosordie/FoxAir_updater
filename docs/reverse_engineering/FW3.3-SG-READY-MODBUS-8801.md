# Mainboard-Firmware V3.3 – SG Ready über Modbus / Register 8801

Stand: 24. August 2026

Diese Datei dokumentiert den in Firmware V3.3 implementierten und inzwischen **am realen Gerät bestätigten virtuellen SG-Ready-Eingang über Modbus**.

Untersuchtes Verhalten:

```text
MAIN:1334 / SG01 = 3
        ↓
SG-Quelle = virtueller Modbuspfad
        ↓
ENG:CTRL:8801 = 1..4
        ↓
virtuelle SG-Kontaktkombination
        ↓
SG-Ready-State-Machine
        ↓
MAIN:2133 = tatsächlich aktiver SG-Modus
```

## Kurzfazit

**Bestätigt:** V3.3 kann die vier SG-Ready-Zustände vollständig über Register `8801` vorgeben.

Voraussetzung:

```text
MAIN:1334 = 3
```

Dann werden nicht die beiden physischen SG-Kontakte als Quelle benutzt, sondern:

```text
ENG:CTRL:8801
```

Mapping:

| 8801 | virtueller Kontakt A | virtueller Kontakt B | Firmware-SG-Modus |
|---:|---:|---:|---|
| 1 | 1 | 0 | Mode 1 / Schlafmodus |
| 2 | 0 | 0 | Mode 2 / wenig PV / Normalzustand |
| 3 | 0 | 1 | Mode 3 / mittel PV |
| 4 | 1 | 1 | Mode 4 / High PV |

`8801 = 0` erzeugt keinen gültigen virtuellen Modus. Werte `>=5` werden ebenfalls nicht als gültiger SG-Zustand akzeptiert.

Zusätzlich ist bestätigt:

- `8801` ist am direkten User-/Mainboard-Modbus les- und schreibbar.
- Nach einer tatsächlich übernommenen SG-Modusänderung gilt ein fester **10-Minuten-Hold**.
- `8801` selbst ändert sich während des Holds sofort; `MAIN:2133` bleibt bis zur nächsten erlaubten Übernahme auf dem vorherigen Modus.
- **Eine Änderung von `MAIN:1334` setzt den 10-Minuten-Hold zurück. Dieses Verhalten wurde am realen Gerät getestet und bestätigt.**
- User-Modbus und Warmlink-/LTE-Modbus verhalten sich für `8801` unterschiedlich.

---

# 1. MAIN:1334 besitzt den Modus 3

Der bisherige Softwarebestand kannte für `1334 / SG01` im Wesentlichen:

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
```

Die V3.3-State-Machine behandelt zusätzlich explizit:

```text
1334 == 3
```

und wechselt dann in einen separaten virtuellen Eingangspfad.

Damit ist funktional bestätigt:

```text
3 = SG Ready über Modbus / virtueller SG-Eingang
```

Der Herstellerwortlaut ist im Binary nicht enthalten; die Funktion selbst ist eindeutig geschlossen.

---

# 2. Laufzeitpfad und RAM

SG-Runtime-Struktur:

```text
0x20016948
```

Virtuelles Engineering-Control-Fenster:

```text
0x20016970
```

Damit:

```text
8801 → 0x20016970 + 0x00
```

Der virtuelle SG-Pfad liegt ungefähr um:

```text
0x08081C72 … 0x08081CDE
```

Sinngemäßer Ablauf:

```text
wenn SG-Quelle != 3:
    physische SG-Eingänge auswerten

wenn SG-Quelle == 3:
    8801 lesen
    Wert 1..4 in zwei interne SG-Kontakte übersetzen
    dieselbe SG-Ready-State-Machine wie bei Hardwarekontakten verwenden
```

Exaktes Mapping:

```text
8801 = 1 -> A=1, B=0
8801 = 2 -> A=0, B=0
8801 = 3 -> A=0, B=1
8801 = 4 -> A=1, B=1
```

**Bewertung: bytegenau bestätigt und live funktional verifiziert.**

---

# 3. Bedeutung der vier Modi

Die vorhandenen SG-Parameter passen direkt zu den vier Firmwarezuständen:

```text
1335 SG02 -> Mode 1 Schlafmodus-Zeit
1336 SG03 -> Mode 2 Leistungswert
1337 SG04 -> Mode 3 Leistungswert
1338–1341 -> Mode 4 Sollwertanhebungen / E-Heizer-Funktion
```

Praktische Interpretation:

```text
Mode 1 -> Schlaf-/Sperrzustand
Mode 2 -> Normalzustand / wenig PV
Mode 3 -> erhöhte Aufnahme / mittel PV
Mode 4 -> High PV / starke Anforderung
```

---

# 4. User-Modbus: 8801 live bestätigt

Der normale Mainboard-Dispatcher besitzt für `8801–8820` FC03-, FC06- und FC10-Pfade.

Am realen Gerät wurde für `8801` über den direkten User-/Mainboard-Modbus bestätigt:

```text
Ausgangswert: 0
lesen:        funktioniert
schreiben:    funktioniert
Werte 0..4:   bleiben im Register stehen
Rücklesen:    funktioniert
```

Damit ist `8801` auf diesem Bus nicht nur statisch im Binary vorhanden, sondern ein real nutzbares R/W-Register.

---

# 5. Live-Funktionstest der SG-Modi

Praktisch beobachtet:

```text
8801 = 1
1334 = 3
→ effektiver Mode 1
→ WP im Schlafmodus
→ WP startet nicht
```

und:

```text
8801 = 4
1334 = 3
→ effektiver Mode 4
→ WP startet
→ erwartete High-Power-Reaktion
```

Die anschließenden Tests bestätigten auch den grundsätzlich angenommenen Umschaltpfad von `8801` auf die vier SG-Zustände.

Damit ist die Funktion:

```text
8801 -> virtueller SG-Zustand
```

**live bestätigt.**

---

# 6. Fester 10-Minuten-Umschalttimer

Die Verzögerung zwischen einer Änderung von `8801` und der Übernahme als neuer aktiver Modus ist direkt aus V3.3 rekonstruiert.

Runtime-Timer:

```text
0x20016948 + 0x24 = 0x2001696C
```

Bei jeder akzeptierten Mode-Umschaltung schreibt V3.3:

```text
0x04B0 = 1200
```

in diesen Timer.

Dies geschieht für alle vier Modi:

```text
Mode 1 -> active=1; timer=1200
Mode 2 -> active=2; timer=1200
Mode 3 -> active=3; timer=1200
Mode 4 -> active=4; timer=1200
```

Solange der Timer größer Null ist:

```text
Timer--
keine neue SG-Modusübernahme
```

Der gewünschte Wert in `8801` kann sich trotzdem sofort ändern und ist auch sofort wieder lesbar.

---

# 7. Warum 1200 exakt 10 Minuten sind

Die gleiche SG-Routine enthält die Mode-1-Schlafzeitlogik.

`MAIN:1335` ist ein Minutenwert und wird intern mit:

```text
0x78 = 120
```

multipliziert.

Damit entsprechen 120 SG-Zyklen einer Minute:

```text
60 s / 120 = 0,5 s pro SG-Zyklus
```

Für den festen Hold ergibt sich:

```text
1200 × 0,5 s = 600 s = 10 Minuten
```

Die 10 Minuten sind damit **codebasiert bestätigt**.

---

# 8. Verhalten während des Holds

Beispiel:

```text
2133 = 1
→ Mode 1 wurde gerade akzeptiert
→ 10-Minuten-Hold läuft

8801 = 3
→ 8801 ist sofort 3
→ 2133 bleibt zunächst 1

kurz danach:
8801 = 2
→ 8801 ist sofort 2
→ 2133 bleibt weiterhin 1

nach Ablauf des Holds:
→ aktuell anliegender Wert 2 wird übernommen
→ 2133 wechselt direkt 1 -> 2
```

Ein nur kurz während des Hold-Zeitraums gesetzter Zwischenwert muss daher niemals als aktiver Zustand erscheinen.

Das zunächst beobachtete scheinbar verzögerte Verhalten bei `8801 = 2/3` war damit keine fehlende Funktion von 8801, sondern die beabsichtigte Hold-Logik.

---

# 9. Änderung von MAIN:1334 setzt den Hold zurück

V3.3 vergleicht die aktuelle SG-Quellenauswahl mit der vorherigen Auswahl.

Bei einer Änderung von `MAIN:1334` werden interne Übergangszustände und insbesondere der 10-Minuten-Hold zurückgesetzt.

Sinngemäß:

```text
wenn SG-Quelle geändert:
    previous_source = new_source
    hold_timer = 0
    interne Übergangszustände zurücksetzen
```

Beispiel für Diagnosezwecke:

```text
8801 = gewünschter Zustand
1334 = 0
1334 = 3
```

Danach kann der aktuell in `8801` stehende Zustand sofort neu angenommen werden und startet anschließend wieder einen neuen 10-Minuten-Hold.

## Live-Verifikation

Dieses Verhalten wurde am 24.08.2026 am realen Gerät getestet und bestätigt:

> **Eine Änderung von `1334` setzt den laufenden 10-Minuten-Hold tatsächlich zurück.**

Damit ist dieser Punkt nicht mehr nur ein statischer Firmwarebefund, sondern praktisch verifiziert.

Für normale Automatisierung sollte dieser Reset nicht als Trick zum schnellen Hin- und Herschalten benutzt werden; er ist vor allem wichtig für Diagnose, Tests und das Verständnis der Zustandsmaschine.

---

# 10. MAIN:1335 ist ein separater Timer

Die feste 10-Minuten-Umschaltsperre darf nicht mit `MAIN:1335` verwechselt werden.

V3.3 besitzt mindestens zwei getrennte Zeitmechanismen:

```text
fester SG-Hold:
    10 Minuten
    nach jeder akzeptierten SG-Modusänderung

MAIN:1335:
    konfigurierbarer Minutenwert
    speziell für Mode 1 / Schlafmodus
```

---

# 11. Rückmeldung über MAIN:2133

`MAIN:2133` zeigt den tatsächlich aktiven SG-Modus:

| 2133 | Bedeutung |
|---:|---|
| 0 | WP aus oder SG deaktiviert |
| 1 | Mode 1 / Schlafmodus |
| 2 | Mode 2 / wenig PV |
| 3 | Mode 3 / mittel PV |
| 4 | Mode 4 / High PV |

Am untersuchten Gerät wird `2133` insbesondere bei eingeschalteter/aktiver Wärmepumpe sinnvoll aktualisiert. Bei ausgeschalteter WP eignet es sich daher nur eingeschränkt als sofortiger Testindikator.

Für die virtuelle Ansteuerung ist das ideale Paar:

```text
8801 = Sollzustand
2133 = tatsächlich übernommener Zustand
```

---

# 12. MAIN:2034 bleibt physischer Eingangszustand

Bits 12/13 von `MAIN:2034` repräsentieren die echten Hardwareklemmen.

Bei:

```text
1334 = 3
```

müssen diese Bits nicht der Vorgabe aus `8801` folgen. Die Firmware erzeugt die virtuellen Kontakte intern für die SG-State-Machine; `2034` bleibt ein Rohstatus der realen Eingänge.

---

# 13. User-Modbus versus Warmlink-/LTE-0x63

Ein wichtiger Livebefund ist die Trennung der beiden Buszugänge.

## Direkter User-/Mainboard-Modbus

Für `8801` bestätigt:

```text
FC03 / Lesen     -> funktioniert
Schreiben        -> funktioniert
0..4             -> bleiben im Register
Rücklesen        -> funktioniert
SG-Wirkung       -> bestätigt
```

## Warmlink-/LTE-Bus, Slave 0x63

Live beobachtet:

```text
1334 lesen       -> funktioniert
1334 schreiben   -> funktioniert
2133 lesen       -> funktioniert
8801 FC03        -> Timeout / keine Antwort
8801 FC16        -> formal passender ACK
```

Der FC16-ACK auf `8801` sah protokollseitig korrekt aus, beispielsweise als Antwort auf:

```text
Slave 0x63
FC16
Start 0x2261 / 8801
Qty 1
```

Der Cross-Bus-Gegencheck zeigte jedoch **keinen belastbaren Nachweis, dass dieser ACK das echte User-Modbus-Register `8801` tatsächlich verändert**.

Daher gilt derzeit:

> Für die reale SG-Ready-Steuerung über `8801` ist der direkte User-/Mainboard-Modbus bestätigt. Der Warmlink-/LTE-0x63-Pfad darf für `8801` nicht allein aufgrund des ACKs als funktionaler Schreibpfad betrachtet werden.

Damit muss die frühere pauschale Aussage „wenn 1334 über eine Schnittstelle erreichbar ist, ist dort auch 8801 vollständig erreichbar“ verworfen werden.

---

# 14. Konsequenz für externe Steuerungen

Empfohlenes Verhalten:

```text
1. MAIN:1334 = 3 setzen/konfigurieren
2. ENG:CTRL:8801 = 1..4 schreiben
3. 8801 zurücklesen
4. MAIN:2133 als effektive Rückmeldung beobachten
5. bei Änderungen den festen 10-Minuten-Hold berücksichtigen
```

Wichtig:

- nicht erwarten, dass jeder 8801-Write sofort in 2133 erscheint
- während des Holds zählt der am Ende aktuell anliegende 8801-Wert
- 1334-Änderungen resetten den Hold
- 1334-Hold-Reset nicht für schnelle normale Regelung missbrauchen
- nach Mainboard-Neustart den gewünschten Zustand erneut prüfen; keine ungetestete Persistenzannahme treffen

---

# 15. Konsequenz für FoxAir_Control

Für `data/foxair_phnix_registers.json` bzw. die UI sollte berücksichtigt werden:

## MAIN:1334 / SG01

```text
0 = Aus
1 = 1 Kontakt
2 = 2 physische Kontakte
3 = Modbus / virtueller SG-Ready-Zustand
```

## ENG:CTRL:8801

```text
Name: Virtueller SG-Ready-Zustand
Werte: 1..4
User-Modbus: R/W live bestätigt
Wirksam: nur wenn MAIN:1334 == 3
```

Zusätzliche UI-Information:

```text
SG-Moduswechsel können bis zu 10 Minuten gesperrt sein.
Eine Änderung von 1334 setzt diese Sperre zurück.
```

Für das Warmlink-/LTE-Backend darf `8801` nicht automatisch als gleichwertig zum direkten User-Modbus behandelt werden.

---

# 16. Abschlussstatus

| Punkt | Status |
|---|---|
| 1334=3 existiert | **bestätigt** |
| 8801 RAM/Dispatcher | **bestätigt** |
| 8801 Mapping 1..4 | **bestätigt** |
| 8801 User-Modbus R/W | **live bestätigt** |
| SG-Wirkung von 8801 | **live bestätigt** |
| 10-Minuten-Hold | **Binary bestätigt + live konsistent** |
| 1334-Änderung resettiert Hold | **Binary + live bestätigt** |
| 2133 als aktiver Zustand | **bestätigt** |
| LTE 0x63 FC03 auf 8801 | **nicht verfügbar / Timeout beobachtet** |
| LTE 0x63 FC16-ACK auf 8801 | **ACK bestätigt, Apply auf echtes 8801 nicht bestätigt** |

Damit ist der virtuelle SG-Ready-Modbuspfad der V3.3 einschließlich seiner Umschaltzeitlogik **strukturell und praktisch geschlossen**.