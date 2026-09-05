# Mainboard-Firmware V3.4 – WW/Heizen-Umschaltung und Verdichter-Stopp

Stand: 5. September 2026

Diese Datei dokumentiert die Reverse-Engineering-Erkenntnisse zur internen Umschaltung zwischen **Warmwasser (WW)** und **Heizbetrieb** in der FoxAir-/PHNIX-Mainboard-Firmware V3.4.

Der Schwerpunkt liegt auf der Frage, ob der Verdichter beim Wechsel der hydraulischen Seite weiterläuft oder bewusst gestoppt wird, und wie dieser Stopp bis zum separaten Inverter-/Leistungsboard Unit `0x01` umgesetzt wird.

Untersuchtes Binary:

```text
Produkt-/Softwarekennung: 82400644
Firmware:                 V3.4
interne Kennung:          824006440034
Größe:                    289806 Byte
MD5:                      149A586EDE6F035B385762EA48C71605
SHA-256:                  97B4BB09BF854BDC7521278DE05354D9BB04A862DD05A864582B365D7AF5890
Imagebasis:               0x08050000
```

Vergleichsbinary V3.3:

```text
interne Kennung:          824006440033
Größe:                    287598 Byte
MD5:                      CEB6A4BF386FF644E23E410023E74673
SHA-256:                  6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
```

Bewertung in diesem Dokument:

- **bestätigt** – Datenfluss direkt im Binary geschlossen
- **stark bestätigt** – mehrere unabhängige Codepfade passen zusammen, einzelne Herstellersemantik fehlt noch
- **offen** – genaue Benennung oder reale Zeitmessung noch nicht abgeschlossen

---

# 1. Kurzfazit

Die V3.4 schaltet bei einem Wechsel **Heizen → WW** bzw. **WW → Heizen** den Verdichter **nicht nahtlos bei weiterlaufendem Inverter** auf die andere hydraulische Seite um.

Stattdessen wird beim Seitenwechsel eine eigene Übergangssequenz gestartet. Diese setzt interne Sperrtimer, welche **direkt von der Verdichter-Start/Stop-Routine abgefragt werden**.

Die rekonstruierte Kette lautet:

```text
WW ↔ Heizen Seitenwechsel
        ↓
WW-Seitenzustand ändern
        ↓
Umschalttimer setzen
  FA7 = 240
  FA8 = 10
        ↓
Verdichter-Start/Stop-Routine
        ↓
FA7 != 0 oder FA8 != 0
        ↓
STOP-Pfad
        ↓
Verdichter-Grundanforderung Bit0 = 0
        ↓
qualifizierte Verdichterfreigabe Bit1 = 0
        ↓
Inverter-Frequenzregler / Soft-Stop
        ↓
Sollfrequenz bis 0 Hz
        ↓
Unit 0x01 / FC10
Reg. 1999 = 0
Reg. 2000 = 0
        ↓
separates Inverter-/Leistungsboard stoppt Verdichter
```

Damit ist für V3.4 bestätigt:

> **Ein WW/Heizen-Seitenwechsel erzeugt bewusst eine Verdichter-Stop-Anforderung.**

Dies gilt für beide Richtungen.

---

# 2. Zwei Ebenen: Benutzermodus und tatsächlich aktive hydraulische Seite

Die Firmware trennt den eingestellten Betriebsmodus von der momentan aktiven hydraulischen Seite.

Für den kombinierten Modus `WW + Heizen` bleibt die übergeordnete Betriebsart erhalten, während intern zwischen WW-Seite und Heizseite umgeschaltet wird.

Relevante interne Struktur:

```text
0x20016E00
```

Für die untersuchten Zustände ist rekonstruiert:

```text
0x20016E00 + 1
    → Heiz-/Kühlfamilie

0x20016E00 + 3
    0 = kein WW
    1 = nur WW
    2 = WW + Raumklima kombiniert
```

Ein wichtiger Marker für die tatsächlich aktive WW-Seite liegt bei:

```text
0x2001662C Bit 7
```

Arbeitsbedeutung:

```text
Bit 7 = 1  → WW-Seite aktiv
Bit 7 = 0  → Heiz-/Klimaseite aktiv
```

**Bewertung: stark bestätigt.**

---

# 3. Übergangstimer beim WW/Heizen-Wechsel

Beim Umschalten der aktiven hydraulischen Seite setzt die Firmware mehrere interne Timer.

In diesem Dokument werden die beiden bytegroßen Timer nach ihren RAM-Endadressen kurz `FA7` und `FA8` genannt:

```text
FA7 = 0x20016FA7
FA8 = 0x20016FA8
```

Zusätzlich existiert ein weiterer hydraulischer Übergangstimer:

```text
0x20016F06
```

Typische Initialisierung beim Seitenwechsel:

```text
FA7 = 240
FA8 = 10
```

In einzelnen Zweigen zusätzlich:

```text
0x20016F06 = 240
```

Die Werte sind **unmittelbare Konstanten im Programmcode** und werden nicht aus einem normalen H-/A-/D-Parameter geladen.

Damit handelt es sich nicht um H32 oder eine vergleichbare Benutzerkonfiguration.

**Bewertung: bestätigt.**

---

# 4. Beide Umschaltrichtungen setzen die Verdichtersperre

## 4.1 Heizen → WW

Beim Eintritt auf die WW-Seite wird sinngemäß:

```text
WW-Seite aktiv setzen
FA7 = 240
FA8 = 10
weitere Übergangsflags / Timer initialisieren
```

## 4.2 WW → Heizen

Auch beim Verlassen der WW-Seite wird dieselbe Verdichtersperre aktiviert.

Ein rekonstruierter Zweig um etwa `0x0805C498` enthält sinngemäß:

```asm
MOV  #240
STRB → 0x20016FA7
...
WW-Seitenbit löschen
MOV  #10
STRB → 0x20016FA8
MOV  #240
STRH → 0x20016F06
```

Damit ist nicht nur Heizen → WW betroffen, sondern auch WW → Heizen.

**Bewertung: bestätigt.**

---

# 5. Direkte Verbindung der Umschalttimer zur Verdichter-Start/Stop-Routine

Der entscheidende Nachweis liegt in der Verdichter-Start/Stop-Logik um:

```text
0x0805ED14 ff.
```

Dort werden die beiden beim WW/Heizen-Wechsel gesetzten Timer direkt geprüft.

Rekonstruierter Ablauf:

```text
Systemfreigabe vorhanden?
    nein → STOP

FA7 prüfen
FA7 != 0 → STOP

FA8 prüfen
FA8 != 0 → STOP

weitere Verdichter-Sperrbedingungen prüfen
```

Der relevante Bereich liegt ungefähr bei:

```text
0x0805EDC4 ... 0x0805EDD8
```

und springt bei einem aktiven Timer in den Stop-Pfad bei:

```text
0x0805FF64
```

Damit ist ausgeschlossen, dass `FA7`/`FA8` lediglich Pumpen- oder Displaytimer sind.

> **Die WW/Heizen-Umschalttimer sind direkte Eingangssignale der Verdichter-Start/Stop-Entscheidung.**

**Bewertung: bestätigt.**

---

# 6. Die Sperre stoppt auch einen bereits laufenden Verdichter

Der Stop-Pfad verhindert nicht nur einen neuen Start.

Er löscht aktiv die bestehende interne Verdichteranforderung.

Um etwa:

```text
0x0805FFB2 ... 0x0805FFBC
```

wird das relevante Statusbyte gelesen und Bit 0 gelöscht:

```text
E18+3 Bit0 = 0
```

Arbeitsbedeutung:

```text
Bit0 = Verdichter-Grundanforderung
```

Damit gilt:

```text
laufender Verdichter
        +
WW/Heizen-Umschalttimer aktiv
        ↓
Verdichteranforderung wird aktiv gelöscht
```

Es handelt sich also nicht nur um eine Wiederanlaufsperre.

**Bewertung: bestätigt.**

---

# 7. Zweite Stufe: qualifizierte Verdichterfreigabe

Eine nachgeschaltete Routine um:

```text
0x0805E3A4
```

bildet aus der Grundanforderung und weiteren Betriebs-/Schutzbedingungen eine zweite Freigabestufe.

Wenn die Grundanforderung Bit0 bereits gelöscht wurde, läuft der Code zum Pfad um:

```text
0x0805E4F2
```

und löscht Bit1:

```text
E18+3 Bit1 = 0
```

Arbeitsmodell:

```text
Bit0 = grundsätzliche Verdichteranforderung
          ↓
weitere Betriebs-/Schutzqualifizierung
          ↓
Bit1 = tatsächliche Freigabe für Frequenzregelung
```

Die Inverter-Frequenzregelung prüft diese zweite Freigabe.

**Bewertung: stark bestätigt.**

---

# 8. Übergang zur separaten Inverterplatine Unit 0x01

Der Verdichter wird nicht durch ein direktes Kompressorrelais des Regelmainboards betrieben.

Das Regelmainboard berechnet eine Sollfrequenz und überträgt sie per internem Modbus an ein separates Inverter-/Leistungsboard.

Bereits für V3.3 vollständig rekonstruiert und in V3.4 wiedergefunden:

```text
Mainboard → Unit 0x01
FC10
Startregister 1999
```

sowie:

```text
Unit 0x01 → Mainboard
FC03
Startregister 2099
```

Bei H33 aktiv läuft der bekannte lange Dialog:

```text
FC10 1999, 16 Wörter
FC03 2099, 51 Wörter
```

Verwandte Grundlagen:

- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)

---

# 9. Unit-1 Register 1999 und 2000

Die finale Kompressor-Sollfrequenz liegt weiterhin bei:

```text
0x20016AAC
```

und wird als erstes Wort des FC10-Blocks nach Unit `0x01` übertragen:

```text
Remote-Reg. 1999 = Kompressor-Sollfrequenz
```

Das zweite Wort wird aus Sollfrequenz und einem weiteren Driver-Modusflag gebildet:

```text
wenn Reg. 1999 == 0:
    Reg. 2000 = 0

wenn Reg. 1999 != 0:
    Reg. 2000 = 1 oder 3
```

Damit bedeutet der endgültige Stop auf der Schnittstelle:

```text
1999 = 0
2000 = 0
```

Das separate Inverterboard erhält den Stop also als normalen Modbus-Sollwert-/Run-Befehl.

**Bewertung: bestätigt.**

---

# 10. Soft-Stop: nicht sofort von hoher Frequenz auf 0 Hz

Nach Wegfall der qualifizierten Verdichterfreigabe springt die Frequenzregelung in einen eigenen Stop-/Abregelpfad.

Relevanter Bereich:

```text
0x08075D18 ff.
```

Der Pfad wertet die vom Inverter zurückgemeldete reale Verdichterfrequenz aus.

Relevante Rückmeldung:

```text
0x200168C4 + 0x06
= 0x200168CA
```

Diese Variable ist bereits aus dem Unit-1-Protokoll bekannt als:

```text
Unit1 Reg. 2102
    ↓
Kompressor-Istfrequenz
    ↓
Mainboard Register 2072
```

Im Soft-Stop werden unter anderem die Schwellen:

```text
45 Hz
34 Hz
```

und die Sollwerte:

```text
41 Hz
30 Hz
0 Hz
```

verwendet.

Vereinfachtes Arbeitsmodell:

```text
Stop angefordert
      ↓
Istfrequenz >= 45 Hz
      → Soll 41 Hz
      ↓
Istfrequenz >= 34 Hz
      → Soll 30 Hz
      ↓
Istfrequenz < 34 Hz
      → Soll 0 Hz
```

Eine direkte Null-Schreibstelle auf die finale Sollfrequenz wurde im Bereich um:

```text
0x08075DD2
```

gefunden.

Damit stoppt das Mainboard den Inverter kontrolliert über seine Modbus-Sollfrequenz und nicht über ein separates hartes Kompressorrelais.

**Bewertung: stark bestätigt.**

---

# 11. Rekonstruierte Zeitbasis der Umschalttimer

Die Timerwerte `240`, `10` und der Soft-Stop-Unterzähler `60` sind keine direkten Sekundenwerte.

Die Zeitbasis wurde aus TIM6 und dem kooperativen Hauptscheduler rekonstruiert.

## 11.1 TIM6

Rekonstruierte Konfiguration:

```text
Systemclock: 112 MHz
TIM6 PSC:    111
TIM6 ARR:    499
```

Daraus folgt:

```text
TIM6-Interrupt ≈ 0,5 ms
```

## 11.2 Schedulerstufen

Die Firmware bildet daraus mehrere Unterzyklen:

```text
4 × TIM6-Interrupt
    → 2 ms Schedulerfreigabe

5 × Scheduler-Slot
    → 10 ms Hauptphase

50 Hauptphasen
    → 500 ms kompletter Regelzyklus
```

Die hier relevanten WW/Heizen-Timer werden einmal pro vollständigem Regelzyklus dekrementiert.

Daraus folgt:

```text
FA7 = 240
240 × 0,5 s
≈ 120 s

FA8 = 10
10 × 0,5 s
≈ 5 s
```

Der Soft-Stop-Unterzähler `60` entspricht bei derselben Zykluszeit ungefähr:

```text
60 × 0,5 s
≈ 30 s
```

**Bewertung: statisch bestätigt; reale Zeitmessung an der laufenden Anlage steht noch aus.**

---

# 12. Wahrscheinlicher zeitlicher Ablauf

Bei hoher aktueller Verdichterfrequenz ergibt sich aus der statischen Analyse ungefähr folgendes Schema:

```text
t = 0 s
WW/Heizen-Seitenwechsel erkannt
FA7 = 240
FA8 = 10
Verdichteranforderung fällt weg

        ↓
Soft-Stop des Inverters

nach einer Stop-Stufe:
Ist-Hz >= 45
→ Soll etwa 41 Hz

nach weiterer Stop-Stufe:
Ist-Hz >= 34
→ Soll etwa 30 Hz

anschließend:
→ Soll 0 Hz
→ Reg. 1999 = 0
→ Reg. 2000 = 0

parallel:
FA7 läuft bis etwa 120 s ab
```

Bei bereits niedriger Verdichterfrequenz kann 0 Hz wesentlich früher erreicht werden.

Aus dem `60`-Zähler ergibt sich eine Größenordnung von etwa 30 s pro Abregelstufe. Daraus kann bei hoher Ausgangsfrequenz ein Abregelvorgang bis in die Größenordnung von ungefähr 90 s entstehen.

Diese genaue reale Timeline ist noch durch einen Live-Mitschnitt zu bestätigen.

---

# 13. Verhältnis zum 3-Wege-Ventil und zur Hydraulik

Die WW/Heizen-State-Machine steuert nicht nur den Verdichterzustand, sondern koordiniert auch die hydraulische Seite.

Das interne WW-Seitenbit:

```text
0x2001662C Bit7
```

wird in der Hydraulik-/Ausgangslogik ausgewertet.

Die Firmware baut außerdem den realen Ausgangszustand des WW-3-Wege-Ventils in das bekannte Last-/Statuswort ein.

Aus den bereits rekonstruierten Registerbelegungen:

```text
Mainboard 2019 Bit9 = WW-3-Wege-Ventil
```

Die Displayfirmware verwendet dieses Bit zusammen mit H20, um WW- bzw. Heizseite darzustellen.

Noch nicht vollständig geschlossen ist die exakte zeitliche Reihenfolge:

```text
Verdichter-Freigabe weg
        ↓
welche Pumpe wann aus/ein?
        ↓
wann exakt schaltet 3-Wege-Ventil?
        ↓
wann wird die neue Seite hydraulisch freigegeben?
        ↓
wann nach Ablauf von FA7 erneuter Verdichterstart?
```

Dieser Teil bleibt offen und sollte mit einem Live-Trace aus Registern und internem Unit-1-Modbus ergänzt werden.

---

# 14. H32 verhindert den Verdichter-Stopp nicht

Der Parameter H32 ist die übergeordnete Umschalt-/Prioritätszeit zwischen gleichzeitig vorhandener WW- und Heizanforderung.

Er entscheidet damit sinngemäß:

```text
WW + Heizen gleichzeitig angefordert
        ↓
welche Seite hat wie lange Priorität?
        ↓
H32
        ↓
Seitenwechsel wird ausgelöst
```

Die eigentliche Verdichtersperre wird **erst danach** durch hart codierte Konstanten gesetzt:

```text
FA7 = 240
FA8 = 10
```

Die Verdichter-Start/Stop-Routine prüft diese RAM-Timer direkt.

Es wurde kein normaler H-/A-/D-Parameter gefunden, der diese Prüfung deaktiviert oder `FA7=240` verhindert.

Damit gilt nach aktuellem Stand:

> **Mit einer normalen Geräteeinstellung lässt sich der Verdichter-Stopp beim WW/Heizen-Seitenwechsel nicht deaktivieren.**

**Bewertung: stark bestätigt.**

---

# 15. V3.3 ↔ V3.4

Das V3.4-Binary ist gegenüber V3.3 um:

```text
0x8A0 = 2208 Byte
```

größer.

Große bestehende Codebereiche sind entsprechend verschoben, während die untersuchte WW/Heizen-Umschaltlogik strukturell weitgehend erhalten ist.

Der statische Vergleich zeigt für den hier relevanten Kern:

- WW-Seitenzustand wird in beiden Versionen als eigener interner Zustand behandelt,
- Übergangstimer werden beim Seitenwechsel gesetzt,
- die Verdichterregelung besitzt denselben grundsätzlichen Stop-/Freigabepfad,
- es gibt keinen Hinweis, dass V3.4 gegenüber V3.3 auf ein nahtloses Umschalten bei laufendem Verdichter umgestellt wurde.

Damit ist sehr wahrscheinlich, dass auch V3.3 beim WW/Heizen-Seitenwechsel stoppt.

Ein realer V3.3-Livetest wurde hierzu bisher nicht durchgeführt.

**Bewertung: statisch stark bestätigt, live offen.**

---

# 16. Bedeutung für die frühere V1.2-Beobachtung

Bei V1.2 wurde praktisch beobachtet, dass der Verdichter beim Wechsel:

```text
Heizen → WW
```

stoppt. Wahrscheinlich war auch die Gegenrichtung betroffen.

Die V3.4-Analyse zeigt, dass ein solcher Stopp weiterhin ausdrücklich als Teil der Zustandsmaschine vorgesehen ist.

Damit ist die frühere Beobachtung mit der heute rekonstruierten Architektur konsistent.

Ein direkter V1.2-Binaryvergleich steht allerdings noch aus.

---

# 17. Sinnvoller Live-Test zur vollständigen Verifikation

Für einen Live-Test sollten mindestens folgende Größen gleichzeitig aufgezeichnet werden:

```text
Mainboard 2012
    Gerätemodus

Mainboard 2019 Bit0
    Verdichter läuft laut Inverter-Istfrequenz

Mainboard 2019 Bit9
    WW-3-Wege-Ventil

Mainboard 2071
    Verdichter-Sollfrequenz

Mainboard 2072
    Verdichter-Istfrequenz
```

Parallel auf dem internen Unit-1-Bus:

```text
FC10 → Unit 0x01
Reg. 1999 = Sollfrequenz
Reg. 2000 = Run-/Driver-Mode

FC03 ← Unit 0x01
Reg. 2102 = Istfrequenz
```

Idealer Test:

```text
1. stabiler Heizbetrieb mit laufendem Verdichter
2. WW-Anforderung erzwingen
3. komplette Umschaltung bis erneutem Verdichterlauf aufzeichnen
4. anschließend WW → Heizen genauso aufzeichnen
```

Damit lassen sich insbesondere verifizieren:

- reale Dauer FA8,
- reale Dauer FA7,
- 41-/30-Hz-Soft-Stop-Stufen,
- Zeitpunkt des 3-Wege-Ventils,
- Pumpenreihenfolge,
- reale Stillstandszeit bis Wiederanlauf.

---

# 18. Patchbarkeit und Vorsicht

Die Verdichtersperre ist technisch patchbar, weil die Werte als unmittelbare Konstanten im Programmcode vorkommen.

Ein offensichtlicher Eingriff wäre beispielsweise eine Verkürzung von:

```text
FA7 = 240
```

auf einen kleineren Wert.

Dies sollte jedoch **nicht ohne vollständige Rekonstruktion der hydraulischen Sequenz** erfolgen.

Ein komplettes Ignorieren der Sperre könnte dazu führen, dass:

```text
Verdichter läuft noch mit hoher Leistung
        ↓
Pumpen-/Durchflusszustand ändert sich
        ↓
3-Wege-Ventil schaltet hydraulische Seite
        ↓
plötzlicher Last-/Durchflusswechsel am Kondensator
```

Die verbleibende Analyse sollte deshalb zuerst klären, warum die Firmware 120 s vorsieht und wie Pumpen, Ventil und Inverter zeitlich gekoppelt sind.

---

# 19. Offene Punkte

1. Exakte Herstellersemantik der Variablen `0x20016FA7`, `0x20016FA8` und `0x20016F06` benennen.
2. Reihenfolge von Normalpumpe, WW-Pumpe und 3-Wege-Ventil vollständig schließen.
3. Reale 120-s-/5-s-Zeitbasis mit Live-Trace verifizieren.
4. Soft-Stop 41 → 30 → 0 Hz live bestätigen.
5. Prüfen, ob die 30-s-Soft-Stop-Stufen in allen Seitenwechselzweigen identisch aktiv sind.
6. Wiederanlaufentscheidung unmittelbar nach Ablauf von FA7 vollständig kartieren.
7. Prüfen, ob zusätzliche Mindeststillstands-/Druckausgleichszeiten des Unit-0x01-Boards autonom hinzukommen.
8. V3.3 live testen.
9. V1.2-Binary zum historischen Vergleich analysieren.
10. Falls ein Patch untersucht wird: zunächst nur Timerverkürzung, nicht Stopprüfung komplett entfernen.

---

# 20. Zusammengefasste Provenance

```text
WW-/Heizanforderungen
        ↓
Prioritäts-/Seitenentscheidung
        ↓
WW-Seitenbit 0x2001662C Bit7
        ↓
FA7 = 240
FA8 = 10
        ↓
Verdichter-Start/Stop-Routine
0x0805ED14 ff.
        ↓
STOP bei FA7 != 0 oder FA8 != 0
        ↓
0x0805FF64
        ↓
E18+3 Bit0 löschen
        ↓
E18+3 Bit1 löschen
        ↓
Inverter-Frequenzregelung
        ↓
Soft-Stop anhand Istfrequenz
45 / 34 Hz Schwellen
41 / 30 / 0 Hz Sollwerte
        ↓
0x20016AAC
        ↓
Mainboard 2071
        ↓
Unit 0x01 / FC10
Reg. 1999 = Sollfrequenz
Reg. 2000 = Run-/Mode
        ↓
1999 = 0, 2000 = 0
        ↓
Inverter-/Leistungsboard
        ↓
Verdichter STOP
```

Damit ist der zentrale Zusammenhang geschlossen:

> **Die V3.4-WW/Heizen-Umschaltlogik setzt interne, hart codierte Sperrtimer. Diese Timer werden direkt von der Verdichter-Start/Stop-Routine ausgewertet und erzwingen eine Stop-Anforderung, die über den normalen internen Modbus-Sollwertpfad an das separate Inverterboard Unit `0x01` weitergegeben wird.**
