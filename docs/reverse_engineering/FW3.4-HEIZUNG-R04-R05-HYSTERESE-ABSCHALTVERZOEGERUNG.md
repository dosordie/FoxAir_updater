# Mainboard-Firmware V3.4 – Heizungs-Hysterese R04/R05 und Abschaltverzögerung

Stand: 13. September 2026

Diese Datei dokumentiert die Reverse-Engineering-Erkenntnisse zur normalen temperaturgeführten Ein-/Ausschaltlogik im **Heizbetrieb** der FoxAir-/PHNIX-Mainboard-Firmware V3.4.

Der Schwerpunkt liegt auf `R04`/`R05`, insbesondere auf Register `1161 / R05`, und auf der Frage, ob das Überschreiten von `Heiz-Soll + R05` den Verdichter unmittelbar stoppt oder ob die Firmware die Stop-Bedingung zuerst zeitlich qualifiziert.

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

Bewertung in diesem Dokument:

- **bestätigt** – Datenfluss direkt im V3.4-Binary geschlossen
- **stark bestätigt** – Codepfad und Zeitbasis passen zusammen; reale Stoppzeit noch nicht mit Stoppuhr verifiziert
- **offen** – genaue reale Zusatzzeit bis `0 Hz` bzw. einzelne Sensorsemantik noch nicht separat live vermessen

> Firmwareadressen in diesem Dokument gelten für V3.4. Sie dürfen nicht ungeprüft auf V3.3 oder andere Versionen übertragen werden.

---

# 1. Kurzfazit

`1161 / R05` ist weiterhin die obere Heizungs-Abschalthysterese.

Die Grundbedingung lautet sinngemäß:

```text
T_wirksam >= Heiz-Soll + R05
    -> rohe Heizanforderung = AUS
```

Die Wärmepumpe löscht daraus aber **nicht im selben Moment die endgültige Verdichterfreigabe**.

Zwischen der rohen Thermostatentscheidung und der qualifizierten Betriebsfreigabe sitzt in V3.4 ein fester Persistenz-/Entprellfilter. Die Stop-Bedingung muss über mehrere aufeinanderfolgende Auswertungen bestehen bleiben.

Aus Scheduler und Zählerlogik ergibt sich für den normalen Lauf eine wirksame Verzögerung von ungefähr:

```text
ca. 17 ... 18 s
```

bevor die interne Freigabe fällt.

Wichtig:

- diese Zeit ist **kein normaler Modbus-/R-/P-/D-Parameter**,
- der Grenzwert `20` des Filters ist als unmittelbare Konstante im Code enthalten,
- bis der Inverter anschließend tatsächlich `0 Hz` meldet, kann durch nachgelagerte Verdichter-/Soft-Stop-Logik noch zusätzliche Zeit vergehen.

Damit ist die Aussage „bei `Soll + R05` stoppt der Verdichter sofort“ für V3.4 zu grob.

---

# 2. Register und Live-Struktur

Der öffentliche R-/Temperaturkurvenblock liegt in V3.4 weiterhin in der bekannten Live-Struktur ab:

```text
0x2001656C
```

Für den Anfang des Blocks gilt:

```text
1157 -> +0x00
1158 -> +0x02
1159 -> +0x04
1160 -> +0x06   R04
1161 -> +0x08   R05
```

Damit liegt `1161 / R05` live bei:

```text
0x20016574
```

Die Synchronisation von Register `1161` in dieses Feld und die spätere Verwendung dieses Feldes in der Heizungsentscheidung sind im V3.4-Binary direkt nachweisbar.

**Bewertung: bestätigt.**

---

# 3. Abschaltbedingung mit R05

Der relevante Heizungs-Thermostatpfad liegt ungefähr um:

```text
0x0805F4EC ... 0x0805F534
```

Rekonstruierter Ablauf:

```text
R05 laden
wirksamen Heiz-Temperaturwert laden
Heiz-Soll + R05 bilden
vergleichen

wenn Temperatur >= Heiz-Soll + R05:
    rohe Heizanforderung = 0
```

Markante Stellen:

```text
0x0805F4EC   R05 / Live-Feld laden
0x0805F526   wirksamen Temperaturwert holen
0x0805F52C   Heiz-Soll + R05 bilden
0x0805F530   Vergleich
0x0805F534   rohe Heizanforderung auf AUS setzen
```

Sinngemäß:

```c
if (T >= heating_target + R05) {
    raw_heat_request = 0;
}
```

Beispiel:

```text
Heiz-Soll = 35,0 °C
R05       =  1,0 K

Stop-Bedingung ab etwa:
36,0 °C
```

Die genaue physische Sensorbenennung des in diesem Pfad verwendeten Temperaturhelpers sollte getrennt von der Hysterese-Mechanik betrachtet werden. Für die Regelinterpretation ist es der wirksame Heiz-/Wasser-Temperaturwert; in der aktuellen FoxAir-Zuordnung entspricht dies der Auslass-/Vorlauftemperatur.

**Bewertung: bestätigt für Vergleich und R05-Datenfluss; Sensorbezeichnung als physische Zuordnung separat zu behandeln.**

---

# 4. Wiedereinschalten mit R04

Die Gegenseite der Hysterese benutzt separat `R04`.

Sinngemäß:

```text
T_wirksam <= Heiz-Soll - R04
    -> rohe Heizanforderung = EIN
```

Damit bilden `R04` und `R05` keine einzelne symmetrische Hysterese, sondern zwei getrennte Schaltschwellen:

```text
EIN-Schwelle: Heiz-Soll - R04
AUS-Schwelle: Heiz-Soll + R05
```

Auch die EIN-Seite läuft anschließend durch die Zustandsqualifizierung und ist damit nicht nur ein nackter Einzelvergleich.

**Bewertung: bestätigt.**

---

# 5. Persistenzfilter zwischen Thermostat und endgültiger Freigabe

Nach der rohen Heizanforderung folgt um etwa:

```text
0x0805FEC0 ff.
```

eine weitere Zustandsqualifizierung.

Dabei wird ein signed Zähler im Verdichter-/Regelstrukturblock verwendet. Im stabilen EIN-Zustand ist er bis ungefähr `+20` gesättigt. Liegt anschließend dauerhaft eine Stop-Anforderung an, läuft der Zähler schrittweise in die negative Richtung.

Vereinfacht:

```text
stabil EIN
Counter = +20

R05-Stop-Bedingung bleibt aktiv
        ↓
+20 -> ... -> 0 -> -1 -> -2 -> ... -> -20
        ↓
erst nach ausreichender negativer Persistenz:
qualifizierte Betriebs-/Verdichterfreigabe löschen
```

Markante Konstanten/Operationen:

```text
0x0805FEE6   Vergleich mit +0x14  (= +20)
0x0805FF3C   Vergleich mit -0x14  (= -20)
0x0805FF4E   Freigabebit 0 löschen
```

Entscheidend ist:

> Der Wert `20` wird hier direkt als Codekonstante verwendet. In diesem Pfad wird kein separater einstellbarer Zeitparameter geladen.

Es wurde insbesondere kein R-/P-/D-/A-Parameter gefunden, der diese Persistenzdauer unmittelbar ersetzt.

**Bewertung: bestätigt.**

---

# 6. Zeitbasis und resultierende Abschaltverzögerung

Die Thermostat-/Qualifizierungslogik wird nicht in jedem CPU-Hauptschleifendurchlauf wirksam weitergezählt, sondern durch die Firmware-Zeitbasis periodisch ausgeführt.

Für V3.4 ergibt die Rückverfolgung des Schedulers für diesen Pfad ungefähr:

```text
Auswertungsintervall ~0,78 s
```

Zusammen mit der festen Zählerqualifizierung ergibt sich vom ersten erkannten dauerhaften Überschreiten der R05-Schwelle bis zum Löschen der qualifizierten Freigabe ungefähr:

```text
~17,1 s aus der Code-/Scheduler-Rekonstruktion
praktisch etwa 17 ... 18 s
```

Da das reale Überschreiten zwischen zwei Auswertungen auftreten kann, ist eine kleine zusätzliche Abtastunsicherheit zu erwarten.

Diese Zeitangabe ist **binary-/schedulerbasiert**. Eine gezielte Live-Messung mit gleichzeitigem Logging von Auslasstemperatur, Sollwert, R05, interner Anforderung und Verdichterfrequenz wäre sinnvoll, um die reale Zeit auf der GL9 exakt zu bestätigen.

**Bewertung: stark bestätigt, noch nicht separat per Stoppuhr/Live-Trace verifiziert.**

---

# 7. Was bedeutet „Abschalten“ genau?

Es müssen drei Ebenen getrennt werden:

```text
1. Temperaturvergleich
   T >= Soll + R05
        ↓
2. rohe Heizanforderung = 0
        ↓
3. Persistenzfilter / qualifizierte Freigabe
   nach ca. 17 ... 18 s dauerhaftem Stop-Wunsch
        ↓
4. nachgelagerte Verdichter-/Inverterlogik
   Sollfrequenz absenken / Soft-Stop
        ↓
5. Unit 0x01 erhält schließlich 0-Hz-/Stop-Vorgabe
        ↓
6. gemeldete Istfrequenz fällt auf 0 Hz
```

Deshalb kann zwischen dem Überschreiten von `Soll + R05` und dem physisch stehenden Verdichter mehr Zeit liegen als nur der hier dokumentierte Persistenzfilter.

Für den Mainboard→Inverter-Pfad siehe:

- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md)
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md)

---

# 8. Abgrenzung zu anderen Abschaltursachen

Diese Erkenntnis betrifft ausdrücklich die **normale Heizungs-Sollwertabschaltung über R05**.

Nicht damit verwechseln:

- Schutzabschaltungen wegen zu hoher Wasser-/Auslasstemperatur,
- Fehler-/Alarmabschaltungen,
- WW↔Heizen-Seitenwechsel,
- Durchfluss-/Pumpenschutz,
- Abtau-State-Machine,
- Ölrückführung,
- Invertereigene Schutzgrenzen.

Insbesondere der WW↔Heizen-Wechsel besitzt in V3.4 eine **eigene** Stop-Ursache mit `FA7`/`FA8` und ist separat dokumentiert:

- [`FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md`](FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md)

R05 und die FA7/FA8-Umschaltsperre sind also zwei unterschiedliche Mechanismen, die beide letztlich in Richtung Verdichterfreigabe wirken können.

---

# 9. Einstellbarkeit

Für die normale Heizungsabschaltung sind derzeit folgende Stellgrößen zu unterscheiden:

```text
R04
    Wiedereinschalt-Differenz unterhalb des Heiz-Sollwerts

R05 / Register 1161
    Abschalt-Differenz oberhalb des Heiz-Sollwerts

interner Persistenzfilter
    ca. 17 ... 18 s
    fest im Code über Zählergrenzen +/-20
    kein normaler Einstellparameter gefunden
```

Damit kann über `R05` die **Temperaturschwelle**, aber nach aktuellem Reverse-Engineering nicht die nachgeschaltete **Zeitqualifizierung** verändert werden.

---

# 10. Praktische Konsequenz für Taktverhalten

Kurze Temperaturspitzen oberhalb von:

```text
Heiz-Soll + R05
```

müssen in V3.4 nicht zwangsläufig einen Verdichterstopp erzeugen. Fällt die Stop-Bedingung vor Ablauf der Persistenz wieder weg, kann die Zustandsqualifizierung zurücklaufen, bevor die endgültige Freigabe gelöscht wurde.

Für die Praxis bedeutet das:

> `R05` bestimmt primär **wie weit die Auslass-/Vorlauftemperatur über das Heiz-Soll steigen darf**. Die Firmware verlangt zusätzlich eine zeitlich anhaltende Stop-Bedingung, bevor der qualifizierte Betriebszustand tatsächlich auf AUS wechselt.

Das reduziert die Empfindlichkeit gegenüber sehr kurzen Überschwingern, ersetzt aber keine echte einstellbare Mindestlaufzeit.

---

# 11. Noch offene Punkte / sinnvolle Live-Tests

Für eine vollständige Live-Verifikation wären besonders nützlich:

1. `R05` bewusst klein einstellen und bei konstanter Last die Zeit von `T >= Soll + R05` bis zur fallenden Sollfrequenz messen.
2. Prüfen, ob ein kurzes Unterschreiten der Stop-Schwelle den Persistenzzähler vollständig oder schrittweise zurücknimmt.
3. Dasselbe für die R04-EIN-Seite messen.
4. V2.1, V3.3 und V3.4 vergleichen, ob Zählergrenzen und Schedulerintervall identisch sind.
5. Zeit zwischen fallender qualifizierter Mainboard-Freigabe und tatsächlichem `2071 = 0` / `2072 = 0 Hz` separat bestimmen.

---

# 12. Kompaktform

```text
V3.4 Heizen:

R05 = Register 1161
R05 live = 0x20016574

AUS-Rohbedingung:
T >= Heiz-Soll + R05

EIN-Rohbedingung:
T <= Heiz-Soll - R04

Danach:
fester Persistenz-/Entprellfilter
Grenzen etwa +20 / -20
Auswertung ~0,78 s

=> qualifizierte Abschaltung nach ungefähr 17 ... 18 s
   dauerhaft anstehender Stop-Bedingung

Zeit nicht als normaler Modbus-Parameter gefunden.
Danach kann der Inverter-Soft-Stop bis real 0 Hz weitere Zeit benötigen.
```
