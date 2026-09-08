# FW3.4 – C350-Upgradefreigabe: Softwarecode und Version

Stand: 8. September 2026

Status: **VERSIONIERT / statisch aus Mainboard-Firmware belegt**

Quelle der Analyse: Mainboard-Firmware `GL9_V3.4(1).bin` (`82400644`, Version `0034`).

Dieses Dokument ergänzt die DTU-seitige OTA-Analyse um die bislang fehlende Gegenstelle: die **C350/C36E-Freigabelogik direkt im Mainboard V3.4**.

---

## 1. Kurzfazit

Für die untersuchte Mainboard-Firmware **82400644 V3.4** ist jetzt direkt belegt:

1. C350 übermittelt dem Mainboard **Softwarecode und Version**.
2. Das Mainboard prüft den **8 Byte langen Softwarecode auf exakte Gleichheit** mit seinem eigenen Softwarecode.
3. Danach prüft es die **4 Byte lange Version auf Gleichheit/Ungleichheit**.
4. Eine Firmware wird auf dieser Stufe nur freigegeben, wenn
   - der Softwarecode identisch ist und
   - die angebotene Version von der aktuell laufenden Version abweicht.
5. Es gibt in diesem Allow-Pfad **keinen Größer-/Kleiner-Vergleich der Version**.

Damit verhindert dieser C350-Allow-Check **keinen Downgrade** innerhalb derselben Softwarecode-Familie.

Sinngemäß:

```c
if (incoming_softwarecode != own_softwarecode)
    allow = 0;
else if (incoming_version == own_version)
    allow = 0;
else
    allow = 1;

send_C36E(allow);
```

---

## 2. Eigene Firmwareidentität in V3.4

In `GL9_V3.4(1).bin` befindet sich bei Datei-Offset `0x43020`, entsprechend Flash-Adresse `0x08093020`, der ASCII-Block:

```text
824006440034
```

Aufgeteilt:

```text
82400644  0034
^^^^^^^^  ^^^^
SW-Code   Version
```

Damit ist `82400644 V3.4` **direkt aus der Mainboard-Firmware selbst bestätigt** und nicht mehr nur aus Updateverlauf oder Forum abzuleiten.

---

## 3. C350 enthält beide Identitätsfelder

Für die 644-Familie wird beim Allow-Handshake sinngemäß übertragen:

```text
SSID         = 0063
Softwarecode = 82400644
Version      = 0034 bzw. Zielversion
```

Bekannte Struktur:

```text
63 10 C3 50 00 07 0E
SS SS
softwareCode[8]
version485[4]
CRC
```

Der Empfänger erkennt C350 und setzt anschließend einen Pending-/Verarbeitungsstatus. Die eigentliche Kompatibilitätsprüfung erfolgt in einem nachgelagerten Upgrade-Handler.

---

## 4. Softwarecode-Prüfung

Der Upgrade-Handler ab ungefähr `0x080A6FB4` greift auf den eigenen Identitätsblock bei `0x08093020` zu.

Der angebotene Softwarecode wird über **8 Bytes** mit dem eigenen Softwarecode verglichen. Nur wenn alle acht Bytes übereinstimmen, wird die Versionsprüfung erreicht.

Damit ist für V3.4 direkt belegt:

> **Der Mainboard-Allow-Check behandelt den Softwarecode als harten Firmwarefamilien-Schlüssel.**

Ein abweichender Softwarecode wird bereits vor dem eigentlichen Firmwaretransfer abgelehnt.

Beispiel:

```text
Board: 82400644 V3.4
Ziel:  82400416 V2.8

=> Softwarecode unterschiedlich
=> C350-Allow abgelehnt
=> kein normaler C357/C5A8-Transferstart
```

---

## 5. Versionsprüfung

Nach erfolgreichem Softwarecode-Vergleich werden die vier Versionsbytes verglichen.

Die relevante Logik entspricht einem einfachen Gleichheitsvergleich:

```text
incoming_version == own_version
    => ablehnen

incoming_version != own_version
    => freigeben
```

In diesem Pfad wurde **keine numerische Versionsordnung** gefunden, also kein Test auf:

```text
neu > alt
neu < alt
```

und auch kein Parsen von Major-/Minor-Versionen.

Daraus folgt für den C350-Allow-Check der V3.4:

| Board | angebotenes Ziel | Ergebnis |
|---|---|---|
| `82400644 V3.4` | `82400644 V3.3` | **ALLOW** |
| `82400644 V3.4` | `82400644 V3.4` | **REJECT** |
| `82400644 V3.4` | `82400644 V3.5` | **ALLOW** |
| `82400644 V3.4` | `82400644 V9.9` | **ALLOW** auf dieser Prüfstufe |
| `82400644 V3.4` | `82400416 V2.8` | **REJECT** |

Wichtig: `ALLOW` bedeutet nur, dass **diese C350-Kompatibilitätsprüfung** den Transfer zulässt. Daraus folgt nicht automatisch, dass beliebige Firmwarestände innerhalb derselben Familie technisch sicher oder hardwarekompatibel sind.

---

## 6. C36E-Ergebnis

Nach dem Vergleich wird der resultierende Freigabestatus über C36E an die DTU zurückgegeben.

Für den hier analysierten Pfad gilt sinngemäß:

```text
C36E status = 1
    Softwarecode identisch
    UND Version unterschiedlich

C36E status = 0
    Softwarecode unterschiedlich
    ODER Version identisch
```

Damit erklärt die Mainboard-Firmware auch das zuvor live beobachtete Verhalten beim Gleichversionstest: Eine identische Zielversion wird bereits im Allow-Handshake abgewiesen.

---

## 7. Konsequenz für Up- und Downgrades

Der C350-Check unterscheidet nicht zwischen Upgrade und Downgrade.

Für ein Board mit `82400644 V3.4` sind daher auf dieser Stufe beispielsweise beide Richtungen zulässig:

```text
V3.4 -> V3.5
V3.4 -> V3.3
```

sofern der Softwarecode `82400644` identisch bleibt.

Damit ist die bisherige Annahme zu korrigieren, dass das Mainboard möglicherweise nur „neuere“ Versionen akzeptiert. Für V3.4 ist statisch belegt, dass die Allow-Logik nur **gleich / ungleich** prüft.

---

## 8. Bedeutung für den FoxAir Updater

Der Updater sollte die Mainboard-Schutzlogik nicht als einzige Kompatibilitätsprüfung betrachten.

Mindestens folgende Felder bleiben vor einem Update relevant:

```text
Softwarecode
Softwareversion
Hardwarecode
```

Der Softwarecode muss als harter Familien-Schlüssel behandelt werden. Zusätzlich sollte der Updater Downgrades weiterhin bewusst kennzeichnen bzw. absichern, obwohl das Mainboard selbst sie auf C350-Ebene nicht verhindert.

Insbesondere darf folgende Logik **nicht** verwendet werden:

```text
V3.4 > V2.8
=> Firmware ist kompatibel
```

Korrekt ist zuerst die Familienprüfung:

```text
82400644 V3.4 -> 82400644 V3.3
    gleiche Softwarefamilie; C350 erlaubt unterschiedliche Version

82400416 V2.8 -> 82400644 V3.4
    andere Softwarefamilie; C350 wird vom 82400644-V3.4-Codepfad nicht akzeptiert
```

---

## 9. Beziehung zu vorhandenen Reverse-Engineering-Dokumenten

Siehe insbesondere:

- [`PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md`](PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md) – Firmwarefamilien und bekannte Softwarecodes.
- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md) – Gesamtüberblick C350/C36E/C357/C5A8.
- [`PHNIX_C350_GLEICHVERSION_LIVE_RESULT.md`](PHNIX_C350_GLEICHVERSION_LIVE_RESULT.md) – Live-Verhalten bei gleicher Version.
- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md) – realer V3.3→V3.4-Updateablauf.
- [`PHNIX_phnixIot4G_board_is_allow_upg_handle.md`](PHNIX_phnixIot4G_board_is_allow_upg_handle.md) – DTU-seitiger Allow-Handler.

---

## 10. Belegstatus

Für **82400644 V3.4** gilt damit:

```text
Softwarecode 82400644 im Mainboard-Binary:       BEWIESEN
Version 0034 im Mainboard-Binary:                BEWIESEN
C350 enthält Softwarecode + Version:             BEWIESEN
8-Byte-Softwarecodevergleich im Mainboard:       BEWIESEN
4-Byte-Versionsvergleich im Mainboard:           BEWIESEN
Gleichversion wird abgelehnt:                    BEWIESEN
Versionsreihenfolge wird im Allow-Pfad geprüft:  NEIN
Downgrade wird im Allow-Pfad verhindert:         NEIN
```

Diese Aussagen sind **firmwareversionsgebunden an die analysierte V3.4**. Andere Mainboard-Firmwarefamilien oder ältere Firmwarestände können theoretisch eine andere Allow-Implementierung besitzen und müssen separat geprüft werden.