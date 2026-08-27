# PHNIX Firmwarefamilien / Softwarecodes / Versionslinien

Stand: 2026-08-27

Diese Datei sammelt die bisher bekannten Beziehungen zwischen **Maincontroller-Softwarecode**, **Softwareversion** und mutmaßlicher **Firmware-/Controllerfamilie**. Sie ergänzt die OTA-/C544-Analyse und trennt bewusst zwischen statisch belegten Informationen aus der Display-Firmware, dynamisch bestätigten Daten eines realen Boards, öffentlichen Nutzerberichten und noch unbestätigten Arbeitshypothesen.

## 1. Kurzfazit

Der aktuelle Kenntnisstand spricht deutlich dafür, dass die PHNIX-Softwareversion `Vx.y` **nicht global über alle Gerätefamilien vergleichbar** ist.

Stattdessen ist sehr wahrscheinlich:

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

Diese Interpretation wird auch direkt durch das LTE-OTA-Programm gestützt: `dev_otavercode_compare()` akzeptiert einen Resume nur, wenn der gespeicherte Ziel-Softwarecode **bytegenau** mit dem aktuell vom Mainboard gemeldeten Softwarecode übereinstimmt. Siehe [`PHNIX_phnixIot4G_C544_softcode_resume.md`](PHNIX_phnixIot4G_C544_softcode_resume.md).

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

Die Zuordnung der Kurzform zu den letzten drei Ziffern ist bei `82400644` durch Live-Daten plus WarmLink-Beobachtungen praktisch bestätigt.

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

### 4.1 Dynamisch bestätigt

Für das im Projekt untersuchte reale Mainboard ist bestätigt:

| Feld | Wert |
|---|---|
| Hardwarecode | `82300314` |
| Hardwareversion | `0000` |
| Softwarecode | `82400644` |
| Softwareversion | `0033` / `V3.3` |

Der Wert stammt aus einem realen C544-Frame und ist damit die derzeit stärkste Referenz für die 644-Familie.

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
| `V3.4` | im konkreten Forumsbeitrag nicht genannt | real durch Remote-Update einer FoxAir GL-9-1 von V1.3 auf V3.4 bestätigt |

Relevante Forumstellen:

- V2.1 mit **SW-Code 644**, Beiträge #147/#148: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=15>
- V3.3 auf Maincontroller/PC4003-G, Beitrag #468: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=47>
- weitere reale V3.3-Beobachtung, z. B. Beitrag #675: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=68>
- Remote-Update FoxAir GL-9-1 **V1.3 -> V3.4**, Beitrag #790: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=79>
- V1.3 mit **Softwarecode 644** sowie V1.2-Erwähnung, Beiträge #846/#847: <https://www.photovoltaikforum.com/thread/242531-foxair-w%C3%A4rmepumpen-erfahrungen-meinungen-tipps/?pageNo=85>

### 4.4 Was daraus bereits geschlossen werden kann

Für die FoxAir-/GL-Beobachtungen ist `644` sehr stark mit dieser Produkt-/Controllerlinie verknüpft. Sicher belegt sind innerhalb dieser Linie mindestens:

```text
82400644 V2.2   Display-Firmware-Referenz von 2023
82400644 V2.1   reales FoxAir/WarmLink-Gerät
82400644 V1.3   reales FoxAir/WarmLink-Gerät
82400644 V3.3   dynamisch bestätigtes Projekt-Mainboard
```

Die Reihenfolge der numerischen Versionsstände ist dabei auffällig (`V2.2` bereits 2023, später reale Geräte mit `V2.1` und `V1.3`). Deshalb darf aus Funddatum oder Versionsnummer allein keine einfache globale Releasechronologie konstruiert werden. OEM-/Produktvarianten, Branches oder unterschiedliche Freigabestände sind möglich.

Für **V3.4** ist die Firmware selbst real bestätigt, der konkrete Forumsbeitrag zeigt jedoch keinen Softwarecode. Da eine FoxAir GL-9-1 von V1.3 auf V3.4 aktualisiert wurde und V1.3 bei anderen FoxAir-Geräten als 644 bestätigt ist, ist `82400644 V3.4` eine **starke Arbeitshypothese**, aber bis zu einem C544-/WarmLink-Beleg noch nicht als vollständig bestätigt zu markieren.

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
| `82400644` | 644 | V1.3, V2.1, V2.2, V3.3; V3.4 sehr wahrscheinlich | Display-FW + Forum + Live-C544 | stark FoxAir/GL-nahe Linie |
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
82400644 V1.3 -> 82400644 V3.3    grundsätzlich gleiche Softwarefamilie
82400644 V3.3 -> 82400644 V3.4    grundsätzlich gleiche Softwarefamilie, sofern V3.4-Code bestätigt
82400416 V2.6 -> 82400416 V2.8    gleiche Softwarefamilie laut Nutzerbericht

82400416 V2.8 -> 82400644 V3.3    NICHT allein aufgrund 3.3 > 2.8 zulässig
```

Diese Trennung entspricht auch dem originalen LTE-OTA-Code: Beim Resume wird der Softwarecode mit `strcmp()` exakt verglichen. Ein anderer Softwarecode führt zum Abbruch des Resume-Pfads.

### 8.1 Empfohlener Sicherheitsansatz

Für automatische Firmwareauswahl sollte derzeit mindestens geprüft werden:

```text
vollständiger Maincontroller-Softwarecode
+ aktuelle Softwareversion
+ Hardwarecode als zusätzlicher Sicherheits-/Kompatibilitätsfaktor
```

Der **Softwarecode ist damit ein harter Familien-Schlüssel**.

Ob innerhalb derselben Softwarecode-Familie jede Firmware auch über unterschiedliche Hardwarecodes hinweg kompatibel ist, ist noch nicht bewiesen. Daher sollte der Hardwarecode bis zu weiteren Vergleichsdaten nicht ignoriert werden.

---

## 9. Offene Punkte

1. C544/WarmLink-Daten einer realen **V3.4** erfassen und prüfen, ob der Softwarecode tatsächlich `82400644` bleibt.
2. Vollständigen Hardwarecode und möglichst Modell/Kältemittel des **416 V2.8**-Geräts erfassen.
3. Prüfen, ob `416` tatsächlich einer R32-Produktfamilie entspricht oder eine andere technische/OEM-Abgrenzung beschreibt.
4. Ein reales `539`-Gerät identifizieren und dessen Hardwarecode, Produktserie und aktuellen Versionsstand erfassen.
5. Weitere PHNIX-/OEM-Geräte sammeln und jeweils das Tupel dokumentieren:

```text
Hersteller/OEM
Modell
Kältemittel
Hardwarecode
Hardwareversion
Softwarecode
Softwareversion
```

6. Erst bei ausreichender Datenbasis festlegen, ob der Softwarecode eine komplette Produktreihe, eine Mainboardgeneration, ein PHNIX-Softwareprojekt oder eine Kombination daraus bezeichnet.

---

## 10. Arbeitsmodell bis zu weiteren Belegen

Derzeit sollte im Projekt folgende Terminologie verwendet werden:

```text
Softwarecode / deviceSoftwareCode
= Maincontroller-Firmwarefamilie / Softwareprojekt (Arbeitshypothese mit starken Belegen)

Softwareversion / deviceSoftwareVer
= Revision innerhalb dieser Familie
```

Für `82400644` kann zusätzlich formuliert werden:

```text
stark mit der untersuchten FoxAir-/GL-Plattform verknüpfte Firmwarefamilie
```

Noch **nicht** ausreichend belegt sind dagegen starre Zuordnungen wie:

```text
644 = R290
416 = R32
539 = <bestimmtes Kältemittel/Modell>
```

Solche Zuordnungen bleiben Hypothesen, bis reale Geräteidentitäten und C544-Daten dies bestätigen.