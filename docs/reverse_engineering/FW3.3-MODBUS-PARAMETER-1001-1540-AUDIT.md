# Mainboard-Firmware V3.3 – Modbus-Parameter 1001–1540

Stand: 24. August 2026

Diese Datei dokumentiert den strukturellen Audit des kompletten öffentlichen Parameterbereichs der Mainboard-Firmware `82400644 / V3.3`.

Verglichen wurde gegen den aktuellen Softwarestand in `dosordie/FoxAir_Control/data`, insbesondere `foxair_phnix_registers.json` und `foxair_phnix_knowledge.json`. Primärquelle für Verhalten und Adressierung ist das untersuchte V3.3-Binary.

## Bewertungsstufen

- **bestätigt** – direkt im V3.3-Binary nachgewiesen
- **sehr wahrscheinlich** – Datenfluss geschlossen, Herstellerbezeichnung noch nicht vollständig belegt
- **offen** – Register/Struktur existiert, fachliche Bedeutung noch nicht belastbar benannt

---

# 1. Protokollbereich und zentraler Spiegel

Der normale öffentliche Mainboard-Parameterbereich ist in V3.3:

```text
1001–1540
```

Der zentrale Modbus-Spiegel liegt bei:

```text
0x20012788
```

Für Register 1001–1540 gilt:

```text
RAM = 0x20012788 + 0x3E8 + 2 × (Register - 1001)
```

**Wichtig:** Die in älteren Display-/Paketdaten vorhandenen Register `1541–1550` gehören in dieser V3.3 **nicht** mehr zum normalen Mainboard-FC03/FC06-Bereich. Sie sind deshalb als Display-/Kompatibilitäts-/Paketnamespace zu behandeln und nicht als normale V3.3-Mainboardparameter.

---

# 2. R/W-Verhalten: FC03, FC06 und FC10 sind nicht identisch

## FC03

`1001–1540` ist vollständig lesbar.

## FC06

FC06 akzeptiert den Parameterbereich, schließt aber sechs Paketkopfblöcke ausdrücklich aus:

```text
1001–1010
1091–1100
1181–1190
1271–1280
1361–1370
1451–1460
```

Diese Blöcke sollen in Software deshalb weiterhin als **read-only Paket-/Blockköpfe** behandelt werden.

## FC10

Der FC10-Pfad akzeptiert technisch den kompletten Bereich `1001–1540` und wiederholt die FC06-Sperre der Paketköpfe **nicht**.

Damit gilt:

| Bereich | FC03 | FC06 | FC10 | empfohlene Softwarepolicy |
|---|---|---|---|---|
| normale Parameter | ja | ja | ja | R/W |
| Paketköpfe s. oben | ja | nein | technisch ja | **read-only** |

Die asymmetrische Implementierung ist **bestätigt**. Dass FC10 die Paketköpfe technisch beschreiben kann, ist kein Grund, dies in `FoxAir_Control` freizugeben.

Für einen FC10-Schreibvorgang auf Register `1012` mit genau einem Wort existiert zusätzlich ein unmittelbarer Apply-/Modus-Hook bei `0x080839A4`.

---

# 3. Architektur: kein flaches Parameterarray

V3.3 hält die Parameter nicht nur im Modbusspiegel. Die Firmware synchronisiert die Register blockweise in eigene Live-Strukturen. Das erlaubt eine wesentlich belastbarere Zuordnung als allein aus Displaytabellen.

Die wichtigsten Live-Strukturen sind:

| Funktionsgruppe | Live-RAM | Hauptregister |
|---|---:|---|
| H-/Grundkonfiguration | `0x20016774` | 1018ff, 1020, 1024, 1027ff, 1032ff, 1041, 1045, 1048, 1224–1226 |
| A-/allgemeine Regelparameter | `0x20016744` | 1037–1064, 1215 |
| Lüfter | `0x20016A04` | 1059ff, 1074, 1081/83/87/89, 1101–1104 |
| Zonen-/Mischer | `0x20016894` | 1069–1090, 1134/35, 1357/58 |
| Abtauparameter | `0x200166A0` | 1105–1130 + 1047 |
| EEV | `0x200169E4` | 1131ff, 1142ff, 1200, 1206 |
| R-/Temperaturkurven | `0x2001656C` | 1157–1177, 1192/95/96, 1228–1238, 1476 |
| Pumpenmodus/-Timer | `0x20016C6C` | 1197–1205 |
| Zusatzblock | `0x20016C7C` | 1152–1156, 1022 |
| Kompressor C | `0x20016B20` | 1217–1223, 1227, 1209–1211 |
| Silent-Timer | `0x20016B68` | 1244–1249 + 1141 |
| Systemzeit | `0x20016D90` | 1250–1255 |
| ältere Timer-/Displaylogik | `0x200167A4` | 1256–1270, 1239–1243, 1025/26, 1216 |
| neue 6-Timer-Struktur | `0x200162D8` | 1281–1325, 1343, 1356 |
| Rücklauf-/Zirkulationspumpentimer | `0x20016C8C` | 1326–1332 |
| SG Ready | `0x20016CAC` | 1334–1341 |
| C12/C13/C14/C15/E20/E21 + Erweiterungen | `0x20016C9C` | 1342–1352, 1402, 1437 |
| Factory Test | `0x20016C10` | 1371–1380 |
| neuer V3.3-Erweiterungsblock | `0x20016278` | 1381ff, 1404, 1429, 1431–1438, 1444–1448, 1462–1467 |
| zusätzlicher V3.3-Optionsblock | `0x20016A24` | 1422–1430, 1477, 1481 |

**Bewertung: bestätigt.**

---

# 4. Blockweise Registerzuordnung

## 4.1 H-/Grundkonfiguration `0x20016774`

Bestätigte direkte Felder:

```text
1018 -> +0x04
1019 -> +0x28
1020 -> +0x2A   H34 ERP-Testmodus
1021 -> +0x06
1023 -> +0x08
1024 -> +0x0A   Unit Address / Modbus-Adresse
1027 -> +0x0C
1028 -> +0x0E
1029 -> +0x10
1030 -> +0x12
1032 -> +0x14
1033 -> +0x16
1034 -> +0x18
1035 -> +0x1A
1036 -> +0x1C
1041 -> +0x1E
1045 -> +0x26
1048 -> +0x2C
1224 -> +0x20
1225 -> +0x22
1226 -> +0x24
```

Weitere Sonderfelder:

- 1014 aus `0x20016E4C+1`
- 1015/1016 aus `0x20016D9C`
- 1022 aus `0x20016C7C+0x0C`
- 1047 aus `0x200166A0+0x34`
- 1011, 1012, 1013, 1017 und 1046 laufen über Sonder-/Steuerlogik und sind nicht nur einfache Backcopy-Felder.

## 4.2 A-Parameter `0x20016744`

```text
1037 +0x00   1038 +0x02   1039 +0x04   1040 +0x06
1052 +0x08   1053 +0x0A   1042 +0x10   1054 +0x12
1043 +0x14   1044 +0x16   1055 +0x18   1056 +0x1A
1057 +0x1C   1051 +0x20   1049 +0x22   1050 +0x24
1063 +0x26   1064 +0x28   1031 +0x2A   1215 +0x2C
```

## 4.3 Lüfter `0x20016A04`

```text
1059 +0x00   1060 +0x02   1062 +0x04   1066 +0x06
1068 +0x08   1081 +0x0A   1083 +0x0C   1087 +0x0E
1089 +0x10   1103 +0x12   1104 +0x14   1074 +0x18
1101 +0x1A   1102 +0x1C
```

Die funktionale Lüfterregelung ist separat in `FW3.3-LUEFTERREGELUNG.md` dokumentiert.

## 4.4 Zone/Mischer `0x20016894`

```text
1069 +0x00 byte
1080 +0x01 byte
1070 +0x02
1071 +0x04
1072 +0x06
1073 +0x08
1075 +0x0A
1076 +0x0C
1077 +0x0E
1078 +0x10
1079 +0x12
1358 +0x14 byte
1082 +0x16 signed
1084 +0x18 signed
1090 +0x1A signed
1134 +0x1C signed
1135 +0x1E signed
1357 +0x20 signed
1085 +0x22 signed
1088 +0x24 signed
```

## 4.5 Abtauung `0x200166A0`

`1105–1130` bilden einen zusammenhängenden D-Parameterblock in 2-Byte-Schritten ab `+0x00`. Zusätzlich liegt Register 1047 bei `+0x34`.

Damit ist die strukturelle D01ff-Zuordnung in V3.3 geschlossen.

## 4.6 EEV `0x200169E4`

```text
1131 +0x00   1132 +0x02   1133 +0x04   1137 +0x06
1138 +0x08   1139 +0x0A   1140 +0x0C   1143 +0x0E
1144 +0x10   1147 +0x12   1148 +0x14   1149 +0x16
1200 +0x18   1142 +0x1A   1206 +0x1C
```

Zusätzlich:

- 1141 aus `0x20016B68+0x12`
- 1145 aus `0x20016F16`

Die Smart-/Auto-Regelung ist in `FW3.3-EEV-SMART-REGELUNG.md` dokumentiert.

## 4.7 R-/Kurvenblock `0x2001656C`

```text
1157–1177 -> +0x00 … +0x28
1192 -> +0x2A
1476 -> +0x2E
1195 -> +0x30
1196 -> +0x32
1228 -> +0x34
1229 -> +0x36
1230 -> +0x38
1231 -> +0x3A
1232 -> +0x3C
1234 -> +0x3E
1235 -> +0x40
1236 -> +0x42
1233 -> +0x44
1237 -> +0x46
1238 -> +0x48
1207 -> +0x4A
1208 -> +0x4C
```

## 4.8 Pumpenmodus/-Timer `0x20016C6C`

```text
1197 +0x00
1198 +0x02
1199 +0x04
1201 +0x06
1202 +0x08
1203 +0x0A
1205 +0x0C
```

Register 1204/P08 wird über eine abweichende Struktur/Sonderlogik geführt.

## 4.9 Kompressor C `0x20016B20`

```text
1218 C01 +0x00
1219 C02 +0x02
1220 C03 +0x04
1221 C04 +0x06
1222 C05 +0x08
1223 C06 +0x0A
1227 C10 +0x0C
1217 C11 +0x0E byte
1209     +0x10
1210     +0x12
1211     +0x14
```

C03, C10 und C11 sind bereits funktional in der Kompressorregelung nachgewiesen.

## 4.10 Silent-Timer `0x20016B68`

```text
1244 +0x0C byte
1245 +0x0D byte
1246 +0x0E byte
1247 +0x0F byte
1248 +0x10 byte
1249 +0x11 byte
1141 +0x12
```

## 4.11 Zeit/Timer

Systemzeit `0x20016D90`:

```text
1250 +0x00
1251 +0x02
1252 +0x04
1253 +0x06
1254 +0x08
1255 +0x0A
```

Alte Timer-/Displaystruktur `0x200167A4`:

```text
1268 +0x00
1269 +0x02
1270 +0x04
1256–1267 +0x06 … +0x1C
1239 +0x1E
1240 +0x20
1241 +0x22
1242 +0x24
1243 +0x26
1025 +0x28
1026 +0x2A
1216 +0x2C
```

Neue 6-Timer-Struktur `0x200162D8`:

- 1281–1325 liegen in dieser Struktur
- 1356/H42 liegt bei `+0x5A`
- 1343/A39 liegt signed bei `+0x5C`

## 4.12 SG Ready `0x20016CAC`

```text
1334 SG01 +0x00
1335 SG02 +0x02
1336 SG03 +0x04
1337 SG04 +0x06
1341 SG08 +0x08
1339 SG06 +0x0A
1340 SG07 +0x0C
```

Zusätzlich:

- 1338/SG05 aus `0x20016DFC+0x00` byte
- 1333 aus `0x20016DFC+0x02`

---

# 5. C12–C15 / E20–E21: in V3.3 echte aktive Parameter

Der Liveblock liegt bei:

```text
0x20016C9C
```

Bestätigte Zuordnung:

| Register | Bezeichnung aus aktuellem Softwarestand | Liveoffset | Typ |
|---:|---|---:|---|
| 1347 | C12 | `+0x00` | byte |
| 1348 | C13 | `+0x01` | signed byte |
| 1349 | C14 | `+0x02` | signed byte |
| 1350 | C15 | `+0x03` | signed byte |
| 1342 | A38 | `+0x04` | byte |
| 1345 | H40 | `+0x05` | byte |
| 1346 | H41 | `+0x06` | signed 16 bit |
| 1351 | E20 | `+0x08` | signed byte |
| 1352 | E21 | `+0x09` | signed byte |
| 1344 | A40 | `+0x0A` | 16 bit |
| 1402 | V3.3-Erweiterung | `+0x0C` | byte |
| 1437 | D30 | `+0x0D` | byte |

Bei ungültiger/fehlender Parametrierung initialisiert V3.3 den Block unter anderem mit:

```text
C12 = 90
C13 = 3
C14 = 2
C15 = 6
E20 = 1
E21 = 1
H41 = 66
```

Damit sind **C13–C15 und E20/E21 definitiv keine bloßen Display-Platzhalter**. Ihre genaue Herstellerfunktion ist noch offen, ihre Existenz, Breite, Signedness, Defaultwerte und Live-RAM-Zuordnung sind bestätigt.

---

# 6. Factory-Testblock 1371–1380

Live-RAM:

```text
0x20016C10
```

Bestätigt:

```text
1371 +0x04 byte   Factory Test Mode
1372 +0x06 byte
1373 +0x07 byte
1375 +0x09 byte
1380 +0x08 byte
1374 +0x0A 16 bit
1376 +0x0C signed
1377 +0x0E
1378 +0x10
1379 +0x12
```

Die bereits in `FoxAir_Control` vorhandenen Factory-Test-Bezeichnungen für 1371–1380 passen strukturell zur V3.3.

---

# 7. V3.3-Erweiterungsblock ab 1381

Der aktuelle `FoxAir_Control`-Katalog besitzt in diesem Bereich große Lücken. V3.3 befüllt jedoch nachweislich zahlreiche Felder.

## `0x20016278`

Bestätigte Registerquellen:

```text
1381 -> +0x48
1382 -> +0x4A
1383 -> +0x4C
1384 -> +0x4E
1385 -> +0x50
1386 -> +0x52
1387 -> +0x36
1388 -> +0x3A
1389 -> +0x38
1404 -> +0x2E byte
1429 -> +0x2F byte
1431 -> +0x11 byte
1432 -> +0x00 byte   P11
1433 -> +0x01 byte   P12
1435 -> +0x04        P13
1436 -> +0x06        P14
1438 -> +0x02 byte   P15
1444 -> +0x03 byte   P16
1445 -> +0x08
1446 -> +0x0A
1447 -> +0x0C
1448 -> +0x0E
1462 -> +0x54 byte
1463 -> +0x55 byte
1464 -> +0x56
1465 -> +0x58
1466 -> +0x5A
1467 -> +0x5C byte
```

Die Felder `1387–1389` werden in temperatur-/zustandsabhängiger Regelung benutzt; `1462–1467` werden als zusammengehöriger Parametersatz an Laufzeitlogik übergeben. Die exakten Herstellerlabels sind noch offen.

## `0x20016A24`

```text
1422 -> +0x00 byte
1423 -> +0x01 byte
1424 -> +0x02 byte
1425 -> +0x03 byte
1426 -> +0x04 byte
1430 -> +0x05 byte
1427 -> +0x06 signed
1477 -> +0x0B byte
1481 -> +0x0C byte
```

Diese Felder sind echte V3.3-Laufzeitparameter. Unter anderem wird `+0x0C` als Feature-/Freigabebedingung ausgewertet; `+0x0B` beeinflusst einen berechneten Soll-/Grenzwert.

Weitere bestätigte V3.3-Felder:

```text
1405 -> 0x20016F38 signed
1461 -> 0x20016F18 signed
1476 -> 0x2001656C+0x2E
```

**Folge für FoxAir_Control:** Diese Adressen sollten nicht länger implizit als „nicht existent“ behandelt werden. Wo der Herstellername noch fehlt, ist ein neutraler V3.3-Kandidat mit RAM-Provenance sinnvoller als eine erfundene Bezeichnung.

---

# 8. Adressierbar, aber ohne geschlossenen V3.3-Livepfad

Nach Abzug der Paketköpfe sind folgende Slots im öffentlichen Protokoll adressierbar, besitzen aber im untersuchten Backcopy-/Livepfad keinen gleichartigen direkten Treffer:

```text
1011, 1012, 1013, 1017, 1046,
1058, 1061, 1065, 1067, 1086,
1136, 1146, 1150, 1151,
1178, 1179, 1180,
1191, 1193, 1194, 1204,
1293,
1359, 1360,
1390–1401, 1403, 1406–1421, 1428, 1434,
1439–1443, 1449, 1450,
1468, 1470–1475, 1478–1480,
1482–1540
```

Das bedeutet **nicht automatisch „unbenutzt“**. Ein Teil davon besitzt Sonderlogik oder transformierte Datenpfade. Für den großen Schwanz `1482–1540` wurde jedoch bisher kein direkter Live-Backcopy-Verbraucher gefunden.

Saubere Klassifikation:

- **Protokolladresse bestätigt**
- **direkter Liveparameter nicht bestätigt**
- bis zum Nachweis nicht als frei nutzbaren Parameter deklarieren.

---

# 9. Wichtigste Deltas zu `FoxAir_Control/data`

1. `1541–1550` aus dem normalen Mainboard-Namespace herauslösen; V3.3 FC03/FC06 endet bei 1540.
2. Paketköpfe softwareseitig read-only lassen, obwohl FC10 sie technisch schreiben kann.
3. C13/C14/C15/E20/E21 von „Displayparameter unbekannt“ auf **echter V3.3-Liveparameter, Semantik offen** hochstufen.
4. Für C13/C14/C15/E20/E21 Breite/Signedness und V3.3-Defaults ergänzen.
5. V3.3-Felder `1381–1389`, `1402`, `1404/1405`, `1422–1431`, `1445–1448`, `1461–1469`, `1476/1477`, `1481` in den Wissenskatalog aufnehmen – zunächst mit neutraler Provenance, wenn das Herstellerlabel noch offen ist.
6. 1024 ausdrücklich als Ziel des speziellen 60000/60010-Modbus-Adressmechanismus dokumentieren; Details stehen im Service-/Engineering-Audit.

---

# 10. Ergebnis

Der öffentliche Parameterbereich ist damit **strukturell vollständig auditiert**:

- FC03-Bereich: geschlossen
- FC06-Rechte: geschlossen
- FC10-Rechte: geschlossen
- Paketkopf-Ausnahmen: geschlossen
- zentraler Spiegel: geschlossen
- große Live-Strukturen: geschlossen
- aktive V3.3-Erweiterungsfelder: identifiziert
- Sonder-/Lückenfelder: explizit getrennt

Noch offen sind bei einem Teil der neu identifizierten Felder ausschließlich die **Herstellerbezeichnungen bzw. die letzte fachliche Semantik**, nicht mehr ihre Existenz oder Modbus-Provenance.
