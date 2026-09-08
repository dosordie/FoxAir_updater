# PHNIX Firmwarefamilien / Softwarecodes / Versionslinien

Stand: 2026-09-08

Diese Datei sammelt die bisher bekannten Beziehungen zwischen **Maincontroller-Softwarecode**, **Softwareversion** und mutmaßlicher **Firmware-/Controllerfamilie**. Sie ergänzt die OTA-/C544-Analyse und trennt bewusst zwischen statisch belegten Informationen aus Display-/Mainboard-Firmware, dynamisch bestätigten Daten eines realen Boards, öffentlichen Nutzerberichten und noch unbestätigten Arbeitshypothesen.

## 1. Kurzfazit

Der aktuelle Kenntnisstand zeigt deutlich, dass die PHNIX-Softwareversion `Vx.y` **nicht global über alle Gerätefamilien vergleichbar** ist.

Stattdessen gilt als belastbares Arbeitsmodell:

```text
Softwarecode / deviceSoftwareCode
        = Firmware-/Controllerfamilie bzw. Softwareprojekt

Softwareversion / deviceSoftwareVer
        = Revisionsstand innerhalb dieser Familie
```

Beispiel:

```text
82400644 V3.3
82400644 V3.4

gegenüber

82400416 V2.6
82400416 V2.8
```

`V3.3` ist damit nicht automatisch ein kompatibles oder „neueres“ Ziel für ein Gerät aus der Linie `82400416 V2.8`.

Diese Interpretation wird inzwischen von zwei Seiten direkt gestützt:

1. Das LTE-OTA-Programm akzeptiert einen Resume nur, wenn der gespeicherte Ziel-Softwarecode **bytegenau** mit dem aktuell vom Mainboard gemeldeten Softwarecode übereinstimmt. Siehe [`PHNIX_phnixIot4G_C544_softcode_resume.md`](PHNIX_phnixIot4G_C544_softcode_resume.md).
2. Die Mainboard-Firmware `82400644 V3.4` prüft beim C350-Allow-Handshake den **8-Byte-Softwarecode auf exakte Gleichheit** und danach die **4-Byte-Version auf Gleichheit/Ungleichheit**. Siehe [`FW3.4-C350-ALLOW-SOFTWARECODE-VERSION.md`](FW3.4-C350-ALLOW-SOFTWARECODE-VERSION.md).

Damit ist der Softwarecode für die untersuchte V3.4 nicht mehr nur ein indirekt abgeleiteter, sondern ein **direkt im Mainboard durchgesetzter Familien-Schlüssel**.

---

## 2. PHNIX-Schema: Code und Version sind getrennte Eigenschaften

Das Mainboard meldet im C544-Block getrennt:

```text
Hardwarecode
Hardwareversion
Softwarecode
Softwareversion
```

Für das untersuchte reale FoxAir-/PHNIX-Mainboard wurde dynamisch bestätigt:

```text
Softwarecode     = 82400644
Softwareversion  = 0033 -> V3.3
```

Die Cloud erhält daraus getrennt:

```text
deviceSoftwareCode = 82400644
deviceSoftwareVer  = V3.3
```

Damit ist bereits auf Protokollebene klar, dass die Versionsnummer allein nicht als eindeutige Firmwareidentität gedacht ist.

WarmLink zeigt den Maincontroller-Code teilweise verkürzt an, z. B.:

```text
82400644 -> SW-Code 644
82400416 -> SW-Code 416
82400539 -> SW-Code 539
```

Die Zuordnung der Kurzform zu den letzten drei Ziffern ist bei `82400644` durch Live-Daten plus WarmLink-/Forumbeobachtungen praktisch bestätigt.

---

## 3. Belege aus der DWIN-/Display-Firmware

Quelle: `DEMONS.ASM` / übersetzte Display-Firmware.

### 3.1 Unterschiedliche Softwarecodes werden als unterschiedliche Controllerzweige behandelt

Im Display-Code werden ausdrücklich unterschiedliche Maincontroller-Codes behandelt:

```text
82400416
82400539
```

Ein Kompatibilitäts-/Matching-Pfad prüft auf die Kurzwerte `416` und `539`. Andere Werte führen in diesem älteren Codepfad zur Meldung eines Maincontroller-/Display-Matchingfehlers.

Das ist ein starkes Indiz dafür, dass der Softwarecode nicht lediglich eine fortlaufende Buildnummer ist, sondern eine Controller-/Softwarefamilie identifiziert.

### 3.2 Versionsangaben sind pro Softwarecode getrennt

Im Änderungsprotokoll der Display-Firmware vom 2023-03-22 steht ausdrücklich:

```text
82400644 V2.2
82400539 V1.3
```

Dazu wurden neue Parametersätze ergänzt.

Damit existierten zu demselben Zeitpunkt mindestens zwei getrennte Maincontroller-Linien mit **unterschiedlichen Softwarecodes und eigenen Versionsständen**.

### 3.3 Weitere Versionsgrenzen für 416 und 539

Ein Kommentar beim Auslesen des Maincontroller-Softwarecodes nennt:

```text
416 V1.2 und höher
539 V1.0 und höher
```

Im Kontext bedeutet dies, dass ab diesen Versionsständen ein bestimmtes Register (`2103`) einen gültigen Wert liefert bzw. die erwartete Kommunikation verfügbar ist.

Wichtig: Daraus folgt **nicht**, dass `416 V1.2` und `539 V1.0` dieselbe Firmwarebasis besitzen. Im Gegenteil stützt die getrennte Nennung die These unterschiedlicher Softwarelinien.

### 3.4 Auch das Display selbst verwendet Code + Version getrennt

Die Display-Firmware setzt für den Line Controller einen eigenen Softwarecode:

```text
Line-Controller Softwarecode = 463
```

und führt die Display-Version separat.

Das zeigt, dass PHNIX das Schema **Softwarecode + Softwareversion** systematisch auch für andere Komponenten verwendet.

---

## 4. Beobachtete Linie 82400644 / Kurzcode 644

### 4.1 Dynamisch und statisch bestätigt

Für das im Projekt untersuchte reale Mainboard ist aus einem C544-Frame bestätigt:

| Feld | Wert |
|---|---|
| Hardwarecode | `82300314` |
| Hardwareversion | `0000` |
| Softwarecode | `82400644` |
| Softwareversion | `0033` / `V3.3` |

Zusätzlich ist die nachfolgende V3.4 inzwischen direkt aus dem Mainboard-Binary bestätigt:

```text
GL9_V3.4(1).bin
Datei-Offset 0x43020 / Flash 0x08093020:

824006440034
^^^^^^^^^^^^
82400644 + 0034
```

Damit ist für die untersuchte Firmware **`82400644 V3.4` statisch bewiesen**. Die frühere Einstufung als bloße starke Arbeitshypothese ist überholt.

### 4.2 Display-Firmware

Die DWIN-Firmware nennt bereits 2023:

```text
82400644 V2.2
```

und kennzeichnet dafür neu hinzugefügte Parameterunterstützung.

### 4.3 Öffentliche FoxAir-Berichte im Photovoltaikforum

Im Thread „FoxAIR Wärmepumpen – Erfahrungen, Meinungen & Tipps“ wurden folgende Maincontroller-Versionen genannt:

| Beobachtung | Softwarecode im selben Beleg? | Einordnung |
|---|---:|---|
| `V2.1` | **ja, SW-Code 644** | realer WarmLink-Stand, mehrfach bestätigt |
| `V1.3` | **ja, SW-Code 644** | realer WarmLink-Stand einer FoxAir |
| `V1.2` | im konkreten Beitrag nicht erneut genannt | realer älterer Firmwarestand im selben FoxAir-Thread |
| `V3.3` | im konkreten Forumsbeitrag nicht genannt | real auf PC4003-G/FoxAir per Remote-Update; zusätzlich bei unserem Board als `82400644 V3.3` dynamisch bestätigt |
| `V3.4` | im konkreten älteren Forumsbeitrag nicht genannt | real durch Remote-Update einer FoxAir GL-9-1 von V1.3 auf V3.4 bestätigt; inzwischen zusätzlich als `82400644 V3.4` direkt im Mainboard-Binary belegt |

Relevante Forumstellen:

- V2.1 mit **SW-Code 644**, Beiträge #147/#148: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=15>
- V3.3 auf Maincontroller/PC4003-G, Beitrag #468: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=47>
- weitere reale V3.3-Beobachtung, z. B. Beitrag #675: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=68>
- Remote-Update FoxAir GL-9-1 **V1.3 -> V3.4**, Beitrag #790: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=79>
- V1.3 mit **Softwarecode 644** sowie V1.2-Erwähnung, Beiträge #846/#847: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=85>

#### Neu bekannte Modellzuordnungen aus dem Forum / Feldberichten

Für folgende FoxAir-Modelle wurde inzwischen **SW-Code 644** berichtet:

```text
GL9
GL15-1
BL12-3
```

Diese Modellzuordnung stammt aus Forum-/Feldbeobachtungen und ist als solche zu kennzeichnen. Sie zeigt aber, dass `644` **nicht nur auf ein einzelnes GL9-Modell beschränkt** ist, sondern über mehrere FoxAir-Leistungs-/Modellvarianten verwendet wird.

### 4.4 Was daraus bereits geschlossen werden kann

Für die FoxAir-Beobachtungen ist `644` sehr stark mit einer gemeinsamen Maincontroller-/Firmwarelinie verknüpft. Sicher belegt sind innerhalb dieser Linie mindestens:

```text
82400644 V2.2   Display-Firmware-Referenz von 2023
82400644 V2.1   reales FoxAir/WarmLink-Gerät
82400644 V1.3   reales FoxAir/WarmLink-Gerät
82400644 V3.3   dynamisch bestätigtes Projekt-Mainboard
82400644 V3.4   direkt aus GL9_V3.4(1).bin bestätigt
```

Die Reihenfolge der numerischen Versionsstände ist dabei auffällig (`V2.2` bereits 2023, später reale Geräte mit `V2.1` und `V1.3`). Deshalb darf aus Funddatum oder Versionsnummer allein keine einfache globale Releasechronologie konstruiert werden. OEM-/Produktvarianten, Branches oder unterschiedliche Freigabestände sind möglich.

Die neuen Modellmeldungen `GL9`, `GL15-1` und `BL12-3` zeigen zusätzlich, dass die 644-Linie offenbar **modellübergreifend** eingesetzt wird. Daraus folgt jedoch noch nicht automatisch, dass jede 644-Firmware auf jedem dieser Modelle ohne weitere Hardwareprüfung austauschbar ist.

### 4.5 Mainboard-seitiger C350-Allow-Check in V3.4

Die Mainboard-Firmware `82400644 V3.4` vergleicht beim C350-Allow-Handshake:

```text
1. Softwarecode: exakt 8 Byte
2. Version:      exakt 4 Byte
```

Die Freigabelogik lautet sinngemäß:

```text
Softwarecode unterschiedlich -> REJECT
Softwarecode gleich + Version gleich -> REJECT
Softwarecode gleich + Version unterschiedlich -> ALLOW
```

Es gibt in diesem Allow-Pfad **keinen Größer-/Kleiner-Vergleich der Version**. Deshalb verhindert dieser Check auch keinen Downgrade innerhalb derselben Softwarecode-Familie.

Details und Disassembly-Fundstellen:
[`FW3.4-C350-ALLOW-SOFTWARECODE-VERSION.md`](FW3.4-C350-ALLOW-SOFTWARECODE-VERSION.md).

---

## 5. Beobachtete Linie 82400416 / Kurzcode 416

### 5.1 Display-Firmware

Die Display-Firmware kennt `82400416` ausdrücklich als eigenen Maincontroller-Code und nennt für diese Linie mindestens:

```text
416 V1.2 und höher
```

### 5.2 Externer realer Nutzerbericht vom 2026-08-27

Von einem anderen PHNIX-Nutzer wurde folgender realer Gerätestand berichtet:

```text
SW-Code 416
vorher V2.6
nach Update V2.8
```

Das Gerät ist eine PHNIX-Wärmepumpe. Die genaue Produktplattform ist derzeit nicht abschließend bekannt; es besteht die Vermutung, dass es sich um eine R32-Baureihe handeln könnte.

**Diese R32-Zuordnung ist nicht bestätigt und darf derzeit nicht als Fakt dokumentiert oder für automatische Firmwareentscheidungen verwendet werden.**

Der Nutzerbericht ist jedoch ein weiterer starker Hinweis darauf, dass `416` eine eigenständige Firmwarelinie besitzt, in der Versionsstände bis mindestens V2.8 existieren.

---

## 6. Beobachtete Linie 82400539 / Kurzcode 539

Für `539` liegen derzeit nur Belege aus der Display-Firmware vor.

Bestätigt aus dem Quelltext:

```text
82400539 V1.3
```

sowie der Kommentar:

```text
539 V1.0 und höher
```

Es liegt derzeit **kein separater realer Forums-/C544-Beleg eines 539-Gerätes** vor.

Daher ist die 539-Linie als durch Firmwarequellen belegte PHNIX-Familie zu führen, aber reale aktuelle Hardware-/Produktzuordnungen bleiben offen.

---

## 7. Vorläufige Familientabelle

| Voller Softwarecode | Kurzcode | bekannte Versionen / Hinweise | Belegstufe | Produktzuordnung |
|---|---:|---|---|---|
| `82400644` | 644 | V1.3, V2.1, V2.2, V3.3, **V3.4 bestätigt** | Display-FW + Forum + Live-C544 + Mainboard-V3.4-Binary | FoxAir-Linie; Forum/Feld: **GL9, GL15-1, BL12-3** |
| `82400416` | 416 | V1.2+, externer Realbericht V2.6 -> V2.8 | Display-FW + externer Nutzerbericht | PHNIX; genaue Baureihe offen, R32 nur Vermutung |
| `82400539` | 539 | V1.0+, V1.3 | Display-FW | Produktzuordnung offen |
| `82400463` | 463 | eigener Display-/Line-Controller-Code | Display-FW | DWIN/Line Controller, **nicht Mainboard** |

---

## 8. Bedeutung für den FoxAir Updater

Die wichtigste technische Konsequenz lautet:

> **Eine Firmware darf niemals nur anhand von `Vx.y` ausgewählt oder als kompatibel betrachtet werden.**

Mindestens erforderlich ist die Prüfung des vollständigen Maincontroller-Softwarecodes.

Konzeptionell:

```text
82400644 V1.3 -> 82400644 V3.3    gleiche Softwarefamilie
82400644 V3.3 -> 82400644 V3.4    gleiche Softwarefamilie; V3.4-Code bestätigt
82400644 V3.4 -> 82400644 V3.3    C350-Allow der V3.4 blockiert Downgrade nicht
82400416 V2.6 -> 82400416 V2.8    gleiche Softwarefamilie laut Nutzerbericht

82400416 V2.8 -> 82400644 V3.3    NICHT allein aufgrund 3.3 > 2.8 zulässig
```

Diese Trennung entspricht sowohl dem originalen LTE-OTA-Code als auch der Mainboard-V3.4-Logik:

- Beim DTU-Resume wird der Softwarecode exakt verglichen.
- Das Mainboard V3.4 verlangt im C350-Allow-Pfad ebenfalls einen exakt passenden 8-Byte-Softwarecode.
- Bei passendem Softwarecode wird die Version dort nur auf **gleich/ungleich**, nicht auf **älter/neuer**, geprüft.

### 8.1 Empfohlener Sicherheitsansatz

Für automatische Firmwareauswahl sollte derzeit mindestens geprüft werden:

```text
vollständiger Maincontroller-Softwarecode
+ aktuelle Softwareversion
+ Hardwarecode als zusätzlicher Sicherheits-/Kompatibilitätsfaktor
```

Der **Softwarecode ist damit ein harter Familien-Schlüssel**.

Ob innerhalb derselben Softwarecode-Familie jede Firmware auch über unterschiedliche Hardwarecodes und Modelle hinweg kompatibel ist, ist noch nicht bewiesen. Das ist durch die neuen 644-Modellzuordnungen (`GL9`, `GL15-1`, `BL12-3`) sogar besonders wichtig: Gleicher Softwarecode bedeutet nicht automatisch, dass Hardwareunterschiede ignoriert werden dürfen.

Der Hardwarecode sollte daher bis zu weiteren Vergleichsdaten nicht ignoriert werden.

---

## 9. Offene Punkte

1. C544/WarmLink-Daten eines realen **V3.4**-Boards weiterhin erfassen, um den jetzt statisch bewiesenen `82400644`-Code zusätzlich dynamisch nach dem Update zu bestätigen.
2. Für die gemeldeten 644-Modelle **GL9, GL15-1 und BL12-3** möglichst zusätzlich Hardwarecode, Hardwareversion, Softwareversion und exakte Modellbezeichnung sammeln.
3. Vollständigen Hardwarecode und möglichst Modell/Kältemittel des **416 V2.8**-Geräts erfassen.
4. Prüfen, ob `416` tatsächlich einer R32-Produktfamilie entspricht oder eine andere technische/OEM-Abgrenzung beschreibt.
5. Ein reales `539`-Gerät identifizieren und dessen Hardwarecode, Produktserie und aktuellen Versionsstand erfassen.
6. Weitere PHNIX-/OEM-Geräte sammeln und jeweils das Tupel dokumentieren:

```text
Hersteller/OEM
Modell
Kältemittel
Hardwarecode
Hardwareversion
Softwarecode
Softwareversion
```

7. Erst bei ausreichender Datenbasis festlegen, ob der Softwarecode eine komplette Produktreihe, eine Mainboardgeneration, ein PHNIX-Softwareprojekt oder eine Kombination daraus bezeichnet.

---

## 10. Arbeitsmodell bis zu weiteren Belegen

Derzeit sollte im Projekt folgende Terminologie verwendet werden:

```text
Softwarecode / deviceSoftwareCode
= Maincontroller-Firmwarefamilie / Softwareprojekt

Softwareversion / deviceSoftwareVer
= Revision innerhalb dieser Familie
```

Für `82400644` kann inzwischen konkreter formuliert werden:

```text
FoxAir-nahe, modellübergreifend eingesetzte Maincontroller-Firmwarefamilie;
belegt bzw. berichtet u. a. bei GL9, GL15-1 und BL12-3
```

Noch **nicht** ausreichend belegt sind dagegen starre Zuordnungen wie:

```text
644 = R290
416 = R32
539 = <bestimmtes Kältemittel/Modell>
```

Solche Zuordnungen bleiben Hypothesen, bis reale Geräteidentitäten und C544-Daten dies bestätigen.