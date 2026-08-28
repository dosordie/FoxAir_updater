# Mainboard-Firmware V3.3 – Verwendung des wirksamen Wasserdurchflusses

Stand: 28. August 2026

Dieses Dokument fasst zusammen, wo der in V3.3 gebildete **wirksame Wasserdurchfluss** weiterverwendet wird. Ziel ist eine zentrale Referenz fuer alle Verbraucher des gemeinsamen Runtimewertes.

Untersuchtes Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
```

Bewertung:

- **bestaetigt** – Datenfluss im Binary direkt geschlossen
- **live bestaetigt** – zusaetzlich am realen Geraet beobachtet
- **sehr wahrscheinlich** – Datenfluss weitgehend geschlossen, letzte Herstellerbezeichnung fehlt
- **offen** – fachliche Semantik einzelner Schutzflags noch nicht vollstaendig benannt

---

# 1. Gemeinsamer autoritativer Durchflusswert

Der wirksame Durchfluss liegt in V3.3 bei:

```text
0x20016F14
```

Er wird aus einer von zwei Quellen gebildet:

```text
lokaler Pfad:
2116 PWM-Feedback
 -> H31-Kennlinie

oder H30 == 3:
HYD61:2047 valid
HYD61:2048 externer Durchfluss
```

Anschliessend wird `MAIN:1022` als signed Korrekturoffset angewendet:

```text
Basisdurchfluss
 + signed MAIN:1022
 -> wirksamer Durchfluss 0x20016F14
```

Damit sehen alle nachgelagerten Verbraucher den **korrigierten** Durchflusswert und nicht den unkorrigierten Rohwert.

---

# 2. Oeffentliche Anzeige MAIN:2077 / T39

Der gemeinsame Runtimewert wird als:

```text
MAIN:2077 / T39
raw / 100 = m3/h
```

veroeffentlicht.

Damit wirkt MAIN:1022 direkt auf die angezeigte Wasserdurchflussrate.

**Bewertung: bestaetigt.**

---

# 3. 5-s-Durchflussmittel fuer die Pumpenregelung

Die Pumpenregelung sammelt zehn Werte des wirksamen Durchflusses. Bei einer Taskperiode von 0,5 s ergibt sich:

```text
10 x 0,5 s = 5 s
```

Der Auto-PWM-Regler arbeitet damit mit einem geglaetteten Durchflusswert und nicht nur mit einem Einzelwert.

**Bewertung: bestaetigt.**

---

# 4. 10-min-Auto-PWM-Qualifikation

Vor Freigabe der eigentlichen variablen Pumpenregelung wird der wirksame Durchfluss gegen eine aus A40 gebildete Schwelle geprueft.

Sinngemaess:

```text
Ist-Durchfluss >= ca. 1,2 x A40
```

muss ueber den Qualifikationszeitraum anliegen.

Der interne Zaehler laeuft 1200 Pumpentasks:

```text
1200 x 0,5 s = 10 min
```

Damit beeinflusst MAIN:1022 unmittelbar, wann der Auto-PWM-Pfad als hydraulisch freigegeben gilt.

**Bewertung: bestaetigt.**

---

# 5. Mindestdurchfluss-Gate beim Herunterregeln

Der wirksame Durchfluss begrenzt, wie weit die automatische Pumpen-PWM abgesenkt werden darf.

Prioritaet der Mindestgrenze:

```text
wenn D22 != 0:
    Q_min = D22
sonst:
    Q_min ~= 0,8 x A40
```

Wenn der geglaettete Ist-Durchfluss an oder unter dieser Grenze liegt:

```text
positive PWM-Korrektur -> erlaubt
negative PWM-Korrektur -> gesperrt
```

Damit verhindert die Firmware, dass die Delta-T-Regelung den Volumenstrom unter ihre eigene Mindestgrenze absenkt.

**Bewertung: bestaetigt.**

---

# 6. Auto-PWM-Regelung – Rolle des Durchflusses

Der eigentliche Regelfehler stammt primaer aus:

```text
Ist-Wasserspreizung - P11
```

mit P12 als Schrittweite und zusaetzlichem Feed-Forward ueber die Kompressor-Sollfrequenz.

Der Durchfluss bestimmt dabei vor allem:

- Freigabe der variablen Regelung,
- Mindestdurchflussgrenzen,
- Sperre gegen weiteres Herunterregeln,
- hydraulische Schutz-/Plausibilitaetsentscheidungen.

Ein genauerer Durchflusswert verbessert deshalb nicht direkt den mathematischen Delta-T-Fehler, aber sehr wohl die Bedingungen, unter denen die Firmware die Pumpendrehzahl veraendern darf.

Details:

[`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md)

---

# 7. Thermische Leistungsberechnung

Der wirksame Durchfluss wird fuer die thermische Leistungsberechnung verwendet.

Prinzipiell:

```text
thermische Leistung
  ~ Wasserdurchfluss x Wasser-Delta-T x Wasserfaktor
```

Der daraus gebildete WP-only-Wert wird unter anderem als:

```text
MAIN:2138
```

veroeffentlicht. Weitere Gesamtleistungswerte bauen darauf auf, insbesondere MAIN:2059.

Damit wirkt MAIN:1022 direkt auf die von FoxAir intern berechnete thermische Leistung.

**Bewertung: bestaetigt.**

---

# 8. COP-Berechnung

Da der COP aus thermischer und elektrischer Leistung gebildet wird, beeinflusst eine Aenderung des wirksamen Durchflusses indirekt auch:

```text
MAIN:2060 / COP
```

Die elektrische Seite wird durch den Durchfluss nicht direkt veraendert; die Wirkung erfolgt ueber die neu berechnete thermische Leistung.

**Bewertung: bestaetigt ueber den geschlossenen Leistungsdatenfluss.**

---

# 9. Thermische Energie-/Waermemengenzaehler

Die thermischen Leistungswerte werden in die internen Energieakkumulatoren integriert.

Damit beeinflusst der wirksame Durchfluss indirekt die thermischen Energiezaehler fuer die verschiedenen Betriebsarten, insbesondere Heizen, Kuehlen und Warmwasser.

Der Durchflussoffset MAIN:1022 ist damit keine reine Anzeigekorrektur, sondern wirkt auf die intern von FoxAir berechnete Waermemenge.

**Bewertung: bestaetigt ueber Leistungs- und Energie-Datenfluss.**

---

# 10. Durchfluss-Schutzlogik

Neben der Auto-PWM-Mindestdurchflusslogik existiert mindestens ein weiterer zeitentprellter Schutzpfad, der denselben wirksamen Runtime-Durchfluss gegen einen konfigurierten Grenzwert prueft.

Die genaue Herstellerbezeichnung aller beteiligten Flags ist noch nicht vollstaendig geschlossen, strukturell ist die Verwendung des gemeinsamen Durchflusswertes jedoch nachgewiesen.

Wichtig:

> Diese softwarebasierte Durchflussbewertung ist vom separaten mechanischen Durchflussschalter zu unterscheiden.

Ein Offset auf MAIN:1022 kann den physisch verdrahteten mechanischen Schalter nicht uebersteuern.

**Bewertung: Verwendung bestaetigt; einzelne Schutzflag-Semantik teilweise offen.**

---

# 11. Abtau-/Defrost-Umfeld

`D22` ist als `Water Flow of Defrosting` dokumentiert und wird in V3.3 zugleich als explizite Durchflussgrenze im Pumpenregelkomplex verwendet.

Der wirksame Durchfluss ist daher auch im Defrost-/Durchfluss-Schutzumfeld relevant.

Wenn die Anlage die Umwaelzpumpe im Abtaubetrieb ohnehin zwangsweise mit 100 % betreibt, bestimmt der Durchfluss dort nicht mehr die normale P12-Pumpendrehzahlregelung. Er bleibt jedoch fuer Durchflusspruefung, Schutzlogik und hydraulische Leistungsberechnung relevant.

**Bewertung: D22-Verwendung bestaetigt; vollstaendige Prioritaetskette aller Defrost-Sonderpfade noch nicht bis auf jedes Flag benannt.**

---

# 12. Nicht vom berechneten Durchfluss abhaengig

Der physische mechanische Durchflussschalter ist ein separater Eingang.

Daher gilt:

```text
MAIN:1022 / H31 / 2077
!= mechanischer Flow-Switch
```

Auch wenn ein Offset den berechneten Durchfluss erhoeht, kann er einen real ausgelösten mechanischen Durchflussschutz nicht maskieren.

---

# 13. Zusammenfassung der bekannten Verbraucher

| Verbraucher | wirksamer Durchfluss nach MAIN:1022? | Funktion |
|---|---|---|
| MAIN:2077/T39 | ja | Anzeige/Telemetrie |
| 5-s-Durchflussmittel | ja | Glättung fuer Regelung |
| 10-min-Auto-PWM-Qualifikation | ja | hydraulische Freigabe |
| D22/A40-Mindestdurchfluss-Gate | ja | verhindert weiteres Herunterregeln |
| Auto-PWM-Schutz-/Plausibilitaetslogik | ja | Regelbegrenzung |
| thermische WP-Leistung MAIN:2138 | ja | Qdot-Berechnung |
| thermische Gesamtleistung MAIN:2059 | ja, indirekt | Gesamt-Qdot |
| COP MAIN:2060 | ja, indirekt | thermisch/elektrisch |
| thermische Energiezaehler | ja, indirekt | Integration der thermischen Leistung |
| softwarebasierte Durchflussschutzpfade | ja | Schutz/Entprellung |
| Defrost-/D22-Umfeld | ja | Durchflussgrenzen/Schutz |
| mechanischer Durchflussschalter | nein | separater Hardwareeingang |

---

# 14. Bedeutung fuer die UPM4L-Kalibrierung

Die Live-Kalibrierung mit:

```text
H31 = 1
MAIN:1022 = +36
```

trifft im typischen Bereich von etwa 45...75 % Soll-PWM den externen Waermemengenzaehler sehr gut.

Da der korrigierte Wert bereits vor allen oben genannten Verbrauchern in `0x20016F14` landet, verbessert diese Kalibrierung nicht nur MAIN:2077, sondern auch die hydraulischen Freigabe-/Mindestdurchflussentscheidungen und die thermische Leistungs-/Energierechnung im normalen Arbeitsbereich.

Messwerte und Fehlervergleich:

[`FW3.3-PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L.md`](FW3.3-PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L.md)

---

# 15. Abgrenzung P08 / MAIN:1204

`P08 / MAIN:1204` ist in der untersuchten V3.3 kein aktiver Pumpen- oder Energieparameter. Er wird vom Mainboard-Sync uebersprungen und hat keinen nachgewiesenen Einfluss auf Durchfluss, PWM, thermische Leistung, COP oder Energiezaehler.

Details:

[`FW3.3-P08-PUMPEN-NENNLEISTUNG.md`](FW3.3-P08-PUMPEN-NENNLEISTUNG.md)

---

# 16. Offene Restpunkte

Noch nicht bis auf die Herstellerbezeichnung geschlossen sind:

1. die exakte Semantik einzelner Durchflussschutz-/Overrideflags,
2. die vollstaendige Defrost-Prioritaetskette aller Sonderbedingungen,
3. alle Nebennutzungen des Durchflusswertes ausserhalb der bereits geschlossenen Regel-, Schutz-, Leistungs- und Energiepfade.

Die zentralen aktiven Verbraucher des gemeinsamen Runtime-Durchflusswertes sind jedoch dokumentiert und strukturell geschlossen.
