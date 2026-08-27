# Mainboard-Firmware V3.3 – UPM4L-Durchflusskalibrierung mit H31 und MAIN:1022

Stand: 27. August 2026

Dieses Dokument ergänzt die statische Pumpen-/PWM-Reverse-Engineering-Dokumentation um reale Messreihen an einer FoxAir mit Grundfos UPM4L und externem Wärmemengenzähler (WMZ).

Ziel ist die praktische Kalibrierung der von V3.3 aus der Pumpen-PWM-Rückmeldung abgeleiteten Wasserdurchflussrate.

Grundlagen und statischer Datenpfad:

- [`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md)
- [`FW3.3-P08-PUMPEN-NENNLEISTUNG.md`](FW3.3-P08-PUMPEN-NENNLEISTUNG.md)

## Bewertungsstufen

- **Binary bestätigt** – direkt in Mainboard-Firmware V3.3 nachgewiesen
- **live bestätigt** – am realen Gerät gemessen
- **empirische Kalibrierung** – aus realer WP-/WMZ-Vergleichsmessung abgeleitet

---

# 1. Ausgangslage

Die verwendete Grundfos UPM4L liefert auf ihrer PWM-Rückmeldung in dieser Ausführung keinen direkt linearen Durchflusswert, sondern ein pumpeninternes Leistungs-/Betriebssignal.

V3.3 interpretiert `MAIN:2116` jedoch abhängig von `H31` über feste Pumpenkennlinien als Durchfluss.

Für die beiden hier relevanten Grundfos-Kennlinien gilt näherungsweise:

```text
H31 = 1:
Q_base[m³/h] ~= 0,030 x MAIN:2116[%]

H31 = 2:
Q_base[m³/h] ~= 0,057 x MAIN:2116[%]
```

Anschließend wird `MAIN:1022` als signed Offset in 0,01 m³/h addiert:

```text
Q_eff = Q_base + signed(MAIN:1022) / 100
```

Der resultierende Wert landet im gemeinsamen Runtime-Durchfluss `0x20016F14` und wird öffentlich als `MAIN:2077 / T39` ausgegeben.

Wichtig: `MAIN:1022` wirkt nicht nur auf die Anzeige, sondern bereits vor den nachgelagerten Regel-/Leistungsfunktionen.

---

# 2. Referenzmessung H31=2 / MAIN:1022=0

Reale Messreihe:

| MAIN:2115 Soll-PWM | MAIN:2116 Feedback | FoxAir Q [m³/h] | externer WMZ Q [m³/h] | Bemerkung |
|---:|---:|---:|---:|---|
| 10 | 0 | 0,000 | 0,000 | mechanischer Durchflussschutz aktiv |
| 20 | 0 | 0,040 | 0,000 | mechanischer Durchflussschutz aktiv |
| 30 | 1 | 0,080 | 0,152 | mechanischer Durchflussschutz aktiv |
| 35 | 2 | 0,120 | 0,264 | mechanischer Durchflussschutz aktiv |
| 40 | 3 | 0,180 | 0,364 | |
| 45 | 4 | 0,260 | 0,457 | |
| 50 | 6 | 0,360 | 0,544 | |
| 55 | 8 | 0,490 | 0,629 | |
| 60 | 11 | 0,490 | 0,720 | |
| 65 | 14 | 0,820 | 0,744 | |
| 70 | 18 | 1,040 | 0,899 | |
| 75 | 22 | 1,300 | 0,979 | |
| 80 | 28 | 1,610 | 1,073 | |
| 85 | 34 | 1,970 | 1,162 | |
| 90 | 41 | 2,390 | 1,206 | |
| 95 | 42 | 2,400 | 1,255 | |
| 100 | 42 | 2,400 | 1,255 | |

Die Messreihe bestätigt die H31=2-Kennlinie qualitativ sehr gut, zeigt aber gleichzeitig, dass sie für diese konkrete UPM4L als Durchflussmodell deutlich zu steil ist.

Besonders oberhalb ca. 65–70 % Soll-PWM überschätzt FoxAir den realen Durchfluss erheblich.

Ein konstanter Offset kann diese falsche Steigung nicht über den gesamten Bereich korrigieren.

**Bewertung: live bestätigt.**

---

# 3. Kalibrierung H31=1 / MAIN:1022=+36

Getestete Einstellung:

```text
H31 = 1
MAIN:1022 = +36
```

Damit gilt näherungsweise:

```text
Q_eff[m³/h] ~= 0,030 x MAIN:2116[%] + 0,36
```

Reale Messreihe:

| MAIN:2115 Soll-PWM | MAIN:2116 Feedback | FoxAir Q [m³/h] | externer WMZ Q [m³/h] | Fehler WP-WMZ [m³/h] |
|---:|---:|---:|---:|---:|
| 40 | 3 | 0,450 | 0,363 | +0,087 |
| 45 | 4 | 0,490 | 0,455 | +0,035 |
| 50 | 6 | 0,550 | 0,547 | +0,003 |
| 55 | 8 | 0,620 | 0,637 | -0,017 |
| 60 | 11 | 0,690 | 0,719 | -0,029 |
| 65 | 14 | 0,790 | 0,809 | -0,019 |
| 70 | 18 | 0,910 | 0,893 | +0,017 |
| 75 | 22 | 1,040 | 0,987 | +0,053 |
| 80 | 28 | 1,200 | 1,080 | +0,120 |
| 85 | 34 | 1,400 | 1,163 | +0,237 |
| 90 | 41 | 1,620 | 1,241 | +0,379 |

## Ergebnis

Der Bereich etwa `45...75 %` Soll-PWM wird mit `H31=1 / 1022=+36` sehr gut getroffen.

Insbesondere:

```text
50 % Soll-PWM:
FoxAir 0,550 m³/h
WMZ    0,547 m³/h
Fehler +0,003 m³/h
```

Zwischen etwa 50 und 70 % liegt die Abweichung nur im Bereich weniger 0,01 m³/h.

Oberhalb etwa 75–80 % wird die aus dem UPM4L-Feedback gebildete Gerade wieder zunehmend zu steil. Der Offset kann nur den Arbeitspunkt verschieben, nicht die Kennliniensteigung ändern.

**Empirische Empfehlung für diese konkrete Hydraulik/Pumpe:**

```text
H31 = 1
MAIN:1022 = +36
```

für einen typischen normalen Arbeitsbereich ungefähr 45...75 % Pumpenansteuerung.

Diese Kalibrierung ist anlagenspezifisch und darf nicht ungeprüft auf andere Pumpen/Hydrauliken übertragen werden.

---

# 4. Unterer Bereich und mechanischer Durchflussschutz

Bei 40 % Soll-PWM wurden gemessen:

```text
FoxAir: 0,450 m³/h
WMZ:    0,363 m³/h
```

Der mechanische Durchflussschutz war dabei bereits sporadisch aktiv.

Durch den positiven Offset entsteht bei kleinem, aber noch ungleich null erkanntem Basisdurchfluss ein rechnerischer Sockelwert. Deshalb darf der korrigierte `MAIN:2077` im unteren Grenzbereich nicht als Ersatz für den mechanischen Durchflussschalter betrachtet werden.

Der mechanische Schutz bleibt ein separater physischer Sicherheitskanal und wird durch `MAIN:1022` nicht übersteuert.

---

# 5. Wo wirkt der Durchfluss nach MAIN:1022?

Binary bestätigt ist die Reihenfolge:

```text
PWM Feedback / externe Quelle
        ↓
Basisdurchfluss
        ↓
+ signed MAIN:1022
        ↓
0x20016F14 = wirksamer Durchfluss
        ↓
weitere Verbraucher
```

Damit sehen die nachfolgenden Verbraucher bereits den **korrigierten** Durchfluss.

## 5.1 MAIN:2077 / T39

Direkte öffentliche Anzeige des wirksamen Runtime-Durchflusses.

**Binary bestätigt.**

## 5.2 Auto-PWM – 5-s-Mittelwert

Der Pumpenregler bildet aus dem wirksamen Durchfluss ein internes Mittel über 10 Taskaufrufe.

Bei 0,5-s-Taskperiode:

```text
10 x 0,5 s = 5 s
```

Damit basiert die Durchflussseite der Auto-PWM-Regelung auf dem korrigierten Wert.

**Binary bestätigt.**

## 5.3 10-minütige Auto-PWM-Qualifikation

Vor der vollständigen Freigabe der variablen Pumpenregelung wird ein ausreichend hoher Durchfluss über ca. 10 Minuten verlangt.

Die Schwelle wird ungefähr als:

```text
Q >= 1,2 x A40
```

gebildet.

Auch hier ist `Q` bereits der korrigierte Durchfluss.

**Binary bestätigt.**

## 5.4 Mindestdurchfluss beim Herunterregeln

Für die Sperre gegen weiteres Reduzieren der Pumpen-PWM gilt:

```text
wenn D22 != 0:
    Q_min = D22
sonst:
    Q_min ~= 0,8 x A40
```

Wenn der gemittelte/korrigierte Durchfluss an oder unter dieser Grenze liegt, wird eine weitere negative PWM-Korrektur unterdrückt.

Damit kann eine bessere Durchflusskalibrierung die Auto-PWM-Regelung im realen hydraulischen Arbeitspunkt sinnvoller begrenzen.

**Binary bestätigt.**

## 5.5 Thermische Leistung

Der gemeinsame Runtime-Durchfluss wird für die thermische Leistungsberechnung zusammen mit der Wasserspreizung verwendet.

Sinngemäß:

```text
Q_therm ~ Volumenstrom x Delta-T x Wasserfaktor
```

Damit beeinflusst MAIN:1022 die von FoxAir berechnete thermische Leistung, insbesondere die WP-only-Größe `MAIN:2138` und daraus abgeleitete Gesamtgrößen.

**Binary bestätigt.**

## 5.6 COP

Da die thermische Leistung in die COP-Berechnung eingeht, wirkt eine Durchflusskorrektur indirekt auf den von FoxAir berechneten COP.

**Binary bestätigt über den Leistungsdatenpfad.**

## 5.7 Wärmemengen-/Energiezähler

Die thermischen Leistungsgrößen werden für die Wärmeenergieakkumulation verwendet. Damit beeinflusst der korrigierte Durchfluss indirekt die thermischen Energiezähler für Heizen, Kühlen und Warmwasser.

Relevante bekannte Zählerpaare:

```text
2119/2120 thermisch Heizen
2123/2124 thermisch Kühlen
2127/2128 sehr wahrscheinlich thermisch Warmwasser
```

**Binary bestätigt für Datenpfad/32-Bit-Struktur; DHW-Benennung des letzten Paars weiterhin sehr wahrscheinlich.**

## 5.8 Durchfluss-Schutzlogik

Mindestens ein separater zeitentprellter Software-Schutzpfad vergleicht den gemeinsamen Runtime-Durchfluss mit einem konfigurierten Grenzwert.

Damit kann MAIN:1022 auch Software-Schutzentscheidungen beeinflussen.

Der mechanische Durchflussschalter ist davon unabhängig.

**Binary bestätigt für die Verwendung des Runtime-Durchflusses; vollständige Herstellerbezeichnung aller Schutzflags noch offen.**

## 5.9 Abtauung

`D22` ist als `Water Flow of Defrosting` / Wasserdurchfluss beim Abtauen bekannt und wird zusätzlich im Pumpen-/Mindestdurchflusskontext benutzt.

Der gemeinsame korrigierte Durchfluss bleibt für Durchfluss-/Schutzentscheidungen im Defrost-Umfeld relevant.

Wenn die Pumpensteuerung für Abtauung unabhängig davon fest auf 100 % gestellt ist, beeinflusst der Durchfluss dort nicht mehr die eigentliche Soll-PWM-Höhe, kann aber weiterhin für Plausibilitäts-/Schutz- und Leistungsberechnungen relevant sein.

---

# 6. Wirkung auf Auto-PWM – wichtige Einordnung

Die eigentliche Delta-T-Korrektur des Auto-Reglers basiert primär auf:

```text
P11 Zielspreizung
P12 Schrittweite
Ist-Spreizung
Kompressorfrequenz-Feedforward
```

Der Durchfluss ist aber keine reine Anzeigegröße, sondern beeinflusst aktiv:

- die 10-minütige Freigabe,
- das 5-s-Mittel,
- die Mindestdurchfluss-Sperre gegen weiteres Herunterregeln,
- weitere Schutzpfade.

Damit führt eine realistischere Durchflusskalibrierung nicht zu einem anderen P11/P12-Regelgesetz, aber zu **realistischeren Freigabe-, Grenz- und Schutzentscheidungen** des Auto-PWM-Reglers.

---

# 7. P08 / MAIN:1204 – nicht zur Kalibrierung verwenden

Der Parameter `P08 / MAIN:1204` wird im DWIN als `Water Pump Rating Power` / Pumpen-Nennleistung in Watt geführt.

Die V3.3-Mainboardanalyse zeigt jedoch:

- MAIN:1204 liegt zwar im öffentlichen Parameterspiegel,
- der Pumpenparameter-Sync überspringt Register 1204 in beiden Richtungen,
- es existiert kein funktionaler Xref auf den entsprechenden Mirror-Offset,
- P08 beeinflusst weder PWM noch Durchfluss noch Leistungs-/COP-/Energiepfade.

Damit gilt für diese V3.3:

```text
P08 = 0
```

kann unverändert bleiben.

Eine Eintragung der realen Pumpen-Nennleistung verbessert die UPM4L-Durchflussberechnung nicht.

Details:

[`FW3.3-P08-PUMPEN-NENNLEISTUNG.md`](FW3.3-P08-PUMPEN-NENNLEISTUNG.md)

---

# 8. Praktische Bewertung

Für die konkrete getestete UPM4L/Hydraulik ergibt sich aktuell:

```text
H31=2 / Offset 0
-> Kennlinie deutlich zu steil
-> besonders bei hoher Pumpenleistung starke Überschätzung

H31=1 / Offset +36
-> sehr gute Übereinstimmung im normalen Bereich ca. 45...75 %
-> zunehmend positive Abweichung oberhalb ca. 75...80 %
```

Der größte Nutzen einer guten Kalibrierung liegt nicht nur in einer schöneren `2077`-Anzeige, sondern in den nachgelagerten Regel- und Bilanzierungsfunktionen:

```text
realistischeres Q
  -> realistischere Mindestdurchflussentscheidung
  -> realistischere Auto-PWM-Freigabe
  -> realistischere thermische Leistung
  -> realistischere Wärmemengen
  -> realistischere COP-Berechnung
```

---

# 9. Offene Punkte

1. Vergleich `MAIN:2138/2059` gegen die aktuelle thermische Leistung des externen WMZ bei stabilen Arbeitspunkten.
2. Langzeitvergleich der FoxAir-Wärmemengenzähler gegen den externen WMZ mit `H31=1 / 1022=+36`.
3. Verhalten/Genauigkeit während hoher Pumpenleistung >75...80 %, insbesondere Defrost.
4. Vollständige Herstellersemantik aller Software-Durchflussschutzflags.
5. Persistenz-/Schreibendurance von MAIN:1022 ist für statische Kalibrierung unkritischer als für häufige dynamische Writes, aber noch nicht vollständig geschlossen.

## Fazit

> Für die getestete Grundfos UPM4L ist `H31=1 / MAIN:1022=+36` eine empirisch sehr gute Kalibrierung des FoxAir-Durchflusswertes im normalen Betriebsbereich. Da der Offset vor dem gemeinsamen Runtime-Durchfluss angewendet wird, verbessert diese Kalibrierung nicht nur MAIN:2077, sondern wirkt auch auf die Durchflussseite der Auto-PWM-Regelung sowie auf thermische Leistungs-, COP- und Wärmemengenberechnungen.
