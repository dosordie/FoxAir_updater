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

**Neu bestätigt:** Nach jeder tatsächlich übernommenen SG-Modusänderung setzt V3.3 einen festen Hold-/Umschalttimer von **10 Minuten**. `8801` selbst kann währenddessen sofort geändert und zurückgelesen werden, aber der aktive Modus (`MAIN:2133`) bleibt bis zum Ablauf des Timers auf dem zuletzt übernommenen Zustand.

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
Mode 2 -> Normalzustand / wenig PV
Mode 3 -> erhöhte Aufnahme / mittel PV
Mode 4 -> High-PV / starke Anforderung
```

---

# 4. 8801 auf dem User-Modbus

Der normale Mainboard-Slave-Dispatcher verarbeitet auch:

```text
8801–8820
```

mit FC03/FC06/FC10.

Live am untersuchten Gerät bestätigt:

- `8801` war initial `0`.
- Lesen über den User-Modbus funktioniert.
- Schreiben der Werte `0..4` funktioniert.
- Geschriebene Werte bleiben im Register stehen und sind wieder lesbar.

Damit ist `8801` auf dem direkten User-/Mainboard-Modbus praktisch bestätigt.

Für den parallelen Warmlink-/LTE-Pfad mit Slave `0x63` gilt dagegen derzeit:

- FC03 auf `8801` -> Timeout / keine Antwort.
- FC16 auf `8801` -> formal passender ACK beobachtet.
- Ein sicherer Nachweis, dass dieser LTE-FC16-ACK den Mainboardwert wirklich ändert, liegt derzeit **nicht** vor; der Zwischenstand spricht eher dagegen.

Diese beiden Buspfade müssen daher getrennt bewertet werden.

---

# 5. Fester 10-Minuten-Umschalttimer

Die Verzögerung zwischen einem geänderten `8801` und einem neuen effektiven SG-Modus ist jetzt direkt aus V3.3 rekonstruiert.

Runtime-Timer:

```text
0x20016948 + 0x24 = 0x2001696C
```

Bei jeder neu akzeptierten Mode-Umschaltung schreibt V3.3:

```text
0x04B0 = 1200
```

in diesen Timer.

Das ist für alle vier Modi identisch:

```text
Mode 1 -> aktiver Mode = 1; Timer = 1200
Mode 2 -> aktiver Mode = 2; Timer = 1200
Mode 3 -> aktiver Mode = 3; Timer = 1200
Mode 4 -> aktiver Mode = 4; Timer = 1200
```

Während der Timer größer als Null ist:

```text
Timer--
keine neue SG-Modusübernahme
```

Der gerade in `8801` stehende neue Wert wird also zwar gelesen bzw. in virtuelle Kontaktzustände umgesetzt, der **effektive Mode bleibt jedoch gesperrt**, bis der Hold-Timer abgelaufen ist.

## Warum 1200 exakt 10 Minuten sind

Die gleiche SG-Routine enthält den Mode-1-Schlafzeitzähler.

`MAIN:1335` ist dort die Schlafzeit in Minuten und wird verglichen mit:

```text
1335 * 0x78
1335 * 120
```

Da 120 SG-Zyklen genau einer Minute entsprechen, läuft die SG-Routine effektiv alle:

```text
60 s / 120 = 0,5 s
```

Damit gilt für den Umschalttimer:

```text
1200 * 0,5 s = 600 s = 10 Minuten
```

Die 10 Minuten sind damit **byte-/codebasiert bestätigt**, nicht nur aus dem beobachteten Verhalten abgeleitet.

## Praktische Konsequenz

Beispiel:

```text
2133 = 1  (Mode 1 wurde akzeptiert)
Timer wird auf 10 min gesetzt

8801 = 3
-> Registerwert ändert sich sofort
-> 2133 bleibt zunächst 1

kurz danach 8801 = 2
-> Registerwert wird 2
-> 2133 bleibt weiterhin 1

nach Ablauf der 10 min
-> der dann aktuell anliegende Wert 2 wird übernommen
-> 2133 springt direkt 1 -> 2
```

Ein zwischenzeitlich nur kurz anliegender Wert `3` muss deshalb **nie als aktiver Mode erscheinen**.

---

# 6. Änderung von 1334 setzt den Hold-Timer zurück

Ein weiterer wichtiger Firmwarebefund:

V3.3 vergleicht die aktuelle SG-Quellenauswahl mit der zuvor verwendeten Auswahl. Ändert sich die Quelle (`MAIN:1334`), werden interne SG-Zustände und insbesondere der Hold-Timer zurückgesetzt.

Sinngemäß:

```text
wenn SG-Quelle geändert:
    vorherige Quelle = neue Quelle
    10-min-Hold-Timer = 0
    interne Übergangszustände zurücksetzen
```

Damit lässt sich für gezielte Tests die 10-Minuten-Wartezeit grundsätzlich durch einen bewussten Quellenwechsel zurücksetzen, z. B.:

```text
1334 = 0
kurz warten
1334 = 3
```

Danach kann der aktuell in `8801` stehende Wert wieder neu als Mode akzeptiert werden und startet anschließend erneut seinen 10-Minuten-Hold.

Das ist primär als Test-/Diagnosewissen zu verstehen; bei laufender Anlage verändert der Quellenwechsel unmittelbar die SG-Regelung und sollte daher bewusst erfolgen.

---

# 7. Mode-1-Schlafzeit ist ein separater Timer

Die feste 10-Minuten-Umschaltsperre darf nicht mit `MAIN:1335` verwechselt werden.

`1335` steuert separat die zulässige Dauer bzw. Zeitlogik des SG Mode 1 / Schlafmodus.

Firmwareseitig existieren also mindestens zwei unterschiedliche Zeitmechanismen:

```text
10-Minuten-Hold:
    fest codiert
    nach jeder akzeptierten SG-Modusänderung

MAIN:1335:
    konfigurierbarer Minutenwert
    speziell für Mode 1 / Schlafmodus
```

---

# 8. Live-Teststand 24.08.2026

Über den User-Modbus wurden bereits folgende Funktionsreaktionen beobachtet:

```text
8801 = 1
-> effektiver Mode 1 beobachtet
-> WP im Schlafmodus, startet nicht

8801 = 4
-> effektiver Mode 4 beobachtet
-> WP startet / High-Power-Reaktion beobachtet
```

Für `8801 = 3` und `8801 = 2` wurde nach vorheriger Mode-Übernahme zunächst noch der alte effektive Modus beobachtet. Dieser Zwischenstand passt exakt zum jetzt im Binary identifizierten 10-Minuten-Hold.

Für die endgültige Livebestätigung empfiehlt sich:

```text
1. 8801 = 2 setzen und zurücklesen
2. 1334 kurz auf 0 und danach wieder auf 3 setzen
3. 2133 beobachten -> Erwartung 2
4. danach 8801 = 3 setzen
5. ohne Quellenreset muss 2133 bis zu 10 min auf 2 bleiben
6. nach Ablauf -> Erwartung 2133 = 3
```

---

# 9. Rückmeldung über MAIN:2133

`MAIN:2133` zeigt den aktiven SG-Ready-Modus:

| Wert | Bedeutung |
|---:|---|
| 0 | WP aus oder SG deaktiviert |
| 1 | SG Mode 1 / Schlafmodus |
| 2 | SG Mode 2 / wenig PV |
| 3 | SG Mode 3 / mittel PV |
| 4 | SG Mode 4 / High PV |

Die Bits 12/13 in `MAIN:2034` bleiben die physischen Eingangszustände. Bei `1334 = 3` können diese unverändert sein, obwohl `8801` einen virtuellen Zustand vorgibt.

---

# 10. Konsequenz für externe Steuerungen

Ein externer Controller sollte den 10-Minuten-Hold berücksichtigen und nicht erwarten, dass jeder Schreibzugriff auf `8801` sofort in `2133` sichtbar wird.

Empfohlen:

```text
8801 schreiben
-> 8801 zurücklesen
-> 2133 als effektiven Zustand beobachten
-> Übergang bis zu 10 min zulassen
```

Ein häufiges Umschalten innerhalb dieser 10 Minuten bringt keinen zusätzlichen Nutzen; entscheidend ist der **zu Ablaufzeitpunkt aktuell in 8801 stehende Wert**.

---

# 11. Zusammenfassung

```text
MAIN:1334 = 3
        ↓
SG-Quelle = virtueller Modbus
        ↓
ENG:CTRL:8801 = 1..4
        ↓
virtuelle SG-Kontakte werden unmittelbar erzeugt
        ↓
10-Minuten-Hold prüft, ob Moduswechsel zulässig ist
        ↓
MAIN:2133 = neuer effektiver SG-Modus
        ↓
bei erfolgreicher Übernahme Hold-Timer erneut auf 10 min
```

Damit ist nicht nur die virtuelle SG-Ready-Ansteuerung über `8801`, sondern auch ihre **feste 10-Minuten-Umschaltlogik** in V3.3 strukturell geschlossen.