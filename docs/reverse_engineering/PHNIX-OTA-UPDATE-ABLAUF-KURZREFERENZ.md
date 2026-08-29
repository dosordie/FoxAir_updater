# PHNIX OTA Update-Ablauf – Kurzreferenz

Stand: 29. August 2026

Diese Datei fasst den aktuell bekannten und inzwischen teilweise **live bestätigten** PHNIX-/FoxAir-Mainboard-Updatepfad kompakt zusammen. Sie trennt bewusst zwischen:

- Upload der Firmwaredatei vom Host auf das LTE-Modem und
- eigentlicher Firmwareübertragung vom LTE-Modem zum Mainboard über RS485/C5A8.

> [!IMPORTANT]
> Ein per ADB auf das LTE-Modem kopiertes Firmwareimage bedeutet noch **nicht**, dass Firmwaredaten zum Mainboard geschrieben wurden. Die eigentliche Mainboard-Datenübertragung beginnt erst mit **C5A8**.

> [!NOTE]
> Der vollständige Pfad **V3.3 → V3.4** wurde auf realer Hardware erfolgreich durchgeführt. Beobachtet wurden kompletter C5A8-Transfer, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließend C544-Version `0034`.

## 1. Software-Schichten unter Windows

```text
FoxAir_Updater.exe
        │
        ▼
Windows-GUI / Statusdarstellung
        │
        ▼
phnix_windows_controller_wrapper.py
        │
        ▼
gemeinsamer phnix_local_ota_controller.py
        │
        ▼
ADB → LTE-Modem → phnixIot4G → RS485 → Mainboard
```

Der Windows-Wrapper und die GUI ergänzen Host-Sicherheitsprüfungen und Darstellung. Der eigentliche OTA-/RS485-Ablauf bleibt im gemeinsamen Controller und im Originaldienst `phnixIot4G`.

## 2. Kurz zusammengefasst

```text
Windows/Linux Host
 ↓
Manifest/Firmware prüfen
 ↓
alten LTE-Cache optional sichern
 ↓
LTE-/ADB-Preflight
 ↓
Runtime-Hook auf LTE installieren
 ↓
Firmware per ADB nach /data/phnix_local_ota/... hochladen
 ↓
lokalen HTTP-Server bereitstellen
 ↓
Original phnixIot4G kontrolliert für OTA verwenden
 ↓
C350 Versionsangebot
 ↓
C36E Status 1
 ↓
C357 Größe + MD5
 ↓
C36E Status 2
 ↓
phnixIot4G liest Firmware lokal per HTTP + MD5
 ↓
C5A8 Firmwareblöcke
 ↓
C371 ACKs
 ↓
Mainboard Staging-MD5
 ↓
C36E Status 3
 ↓
Erase + Copy + MD5 + Commit/Promotion
 ↓
C36E Status 5
 ↓
board_ota_step 12
 ↓
neue Firmware / C544-Version
```

Für die bestätigte V3.4-Datei dauerte der vollständige beobachtete Ablauf rund **35 Minuten**. Die reine C5A8-Phase dauerte **28:56 Minuten**.

## 3. Host-/Preflight

Vor einem echten Update:

1. Manifest laden.
2. Firmwaredatei analysieren.
3. Firmwareidentität und Manifest vergleichen:
   - Software-Code,
   - Display-/Wire-Version,
   - Target-SSID,
   - Dateigröße,
   - MD5,
   - SHA-256,
   - Image-Base.
4. Eventuell vorhandenen LTE-Firmware-Cache lokal sichern.
5. ADB-/LTE-Preflight durchführen:
   - ADB erreichbar,
   - richtiger `phnixIot4G`-Build,
   - Watchdogs vorhanden,
   - benötigte Werkzeuge vorhanden,
   - `OTA_INFO` plausibel,
   - kein unerwarteter Resume-Zustand,
   - genügend Speicher,
   - normaler LTE-/MQTT-Zustand.

## 4. Runtime-Helfer und Firmwarebereitstellung

Der Host kopiert den buildgebundenen Runtime-Helfer nach:

```text
/data/phnix_ota_runtime_hook
```

Die Firmware wird per ADB lokal auf dem LTE-Modem bereitgestellt, z. B.:

```text
/data/phnix_local_ota/phnixIot_device_OTA.bin
```

und dort über Loopback-HTTP angeboten:

```text
http://127.0.0.1:8081/phnixIot_device_OTA.bin
```

**Bis hierhin wurde noch keine Firmware zum Mainboard übertragen.**

## 5. MQTT während des Updates

Im aktuellen Normalbetrieb bleibt MQTT **verbunden**.

Die frühere `iptables`-Isolation ist nur noch optional (`--isolate-mqtt` / `--update-no-mqtt`, Windows: **Erweitert → MQTT bei Update aus**).

Der Originaldienst besitzt einen Rebootpfad nach mehr als 1800 Sekunden intern erkanntem Aliyun/MQTT-Offlinezustand. Wichtig: Dieser Zähler beginnt erst, nachdem der Aliyun-SDK seinen Client intern als offline bewertet. Eine stille Firewall-DROP-Sperre kann davor mehrere 180-s-Keepalive-Zyklen benötigen.

Es gibt keinen bekannten OTA-Sonderzweig, der diesen Rebootpfad während eines Mainboardupdates deaktiviert.

## 6. C350 – Firmwareangebot

C350 enthält Software-Code und angebotene Wire-Version.

Beispiel V3.4:

```text
Software-Code: 82400644
Wire-Version:   0034
```

### Gleiche Version

```text
C350
 ↓
C36E Status 0
 ↓
same-version
 ↓
STOP
```

Dann gilt:

```text
kein C357
kein C5A8
keine Firmwaredaten zum Mainboard
```

Dieser V3.3→V3.3-Pfad wurde real bestätigt.

### Neue/akzeptierte Version

```text
C350
 ↓
C36E Status 1
```

Danach folgt C357.

## 7. C357 – Dateigröße und MD5

C357 übermittelt:

```text
Dateigröße
+
MD5
```

Bei erfolgreicher Annahme:

```text
C36E Status 2
```

Der persistente OTA-Zustand wird vorbereitet.

## 8. Lokaler HTTP-/MD5-Schritt im LTE-Modem

Nach Status 2 verwendet `phnixIot4G` seinen originalen Board-OTA-Code:

```text
Loopback-HTTP-Download
→ Firmware lesen
→ MD5 prüfen
→ OTA_INFO aktualisieren
```

Erst danach beginnt C5A8.

## 9. C5A8 – eigentliche Firmwareübertragung

Bekannt für V3.3:

```text
Block-Nutzdaten: 168 Byte
Firmwaregröße:    287598 Byte
Frames:           1712
```

Schematisch:

```text
LTE / phnixIot4G          Mainboard
      │                       │
      ├──── C5A8 Block ──────►│
      │◄──── C371 ACK ────────┤
      ├──── C5A8 Block ──────►│
      │◄──── C371 ACK ────────┤
      └──── ... ─────────────►│
```

Das Mainboard schreibt zunächst in den Staging-Bereich ab ungefähr:

```text
0x080A1000
```

### 100 % Fortschritt

Wenn `offset == length`, sind alle Firmwaredaten übertragen.

> **Das ist noch nicht der terminale Firmwareerfolg.**

Der Fortschrittsbalken darf bei 100 % stehen bleiben, während das Mainboard weiterarbeitet.

## 10. C371 – Blockquittung

Jeder erfolgreich verarbeitete C5A8-Block wird mit C371 quittiert. Beim letzten Block zeigt die Abschlussquittung an, dass der vollständige Datenstrom angekommen ist.

## 11. Staging-MD5 und C36E Status 3

Nach dem letzten Firmwareblock prüft das Mainboard das Staging-Image:

```text
MD5 #1 über Staging
        │
        ├─ Fehler → C36E Status 4
        │
        └─ OK     → C36E Status 3
```

**Status 3 ist kein Fehler und kein sicherer Stopppunkt.**

Im realen V3.3→V3.4-Lauf erschien Status 3 rund **2 Sekunden nach dem letzten C5A8-Block**.

## 12. Promotion / Commit

Nach Status 3 läuft das Mainboard selbstständig weiter:

```text
Staging-Image
0x080A1000 ...
        ↓
Zielbereich löschen
0x08050000 ...
        ↓
Firmware kopieren
        ↓
MD5 #2 über Zielbereich
        ↓
Descriptor / Commit / Handoff
```

Bei Erfolg:

```text
C36E Status 5
```

Bei Fehler:

```text
C36E Status 6
```

Status 5 ist der relevante erfolgreiche Promotion-/Commit-Abschluss.

Im Live-Lauf benötigte das Mainboard vom letzten C5A8 bis Status 5 rund **5 Minuten 16 Sekunden**.

## 13. LTE-Abschluss und Board-Step 12

Der Originaldienst verarbeitet Status 5, quittiert den Boardstatus und erreicht terminal wieder:

```text
board_ota_step = 12
```

Der aktuelle Updater wertet **Status 5 / Board-Step 12** als terminalen Mainboard-Erfolg.

Nach diesem Ergebnis erhält der normale LTE-/Cloudzustand bis zu **120 Sekunden** zur Normalisierung.

## 14. Neue Firmwareidentität

Nach dem erfolgreichen Live-Lauf meldete C544:

```text
Softwarecode: 82400644
Version:       0034
```

Die erste neue C544-Versionsmeldung wurde ungefähr eine Minute nach Status 5 beobachtet.

Damit wurde der tatsächliche Start/aktive Betrieb der neuen V3.4 zusätzlich bestätigt.

## 15. Reale V3.3→V3.4-Zeiten

| Ereignis | Zeitpunkt |
|---|---|
| C350 | 00:51:18 |
| C36E Status 2 | 00:51:19 |
| erster C5A8 | 00:51:20 |
| letzter C5A8 bestätigt | 01:20:16 |
| C36E Status 3 | 01:20:18 |
| C36E Status 5 | 01:25:32 |
| Board-Step 12 / terminaler Erfolg | 01:25:34 |
| C544 Version `0034` | 01:26:33 |

Zusammenfassung:

```text
C5A8-Transfer:            ca. 28:56 min
letzter C5A8 → Status 3:  ca. 2 s
letzter C5A8 → Status 5:  ca. 5:16 min
vollständige Beobachtung: ca. 35 min
```

Die frühere technische Schätzung von 10–15 Minuten war damit deutlich zu niedrig und gilt nicht mehr als Planungswert.

## 16. Statuscodes

| C36E | Bedeutung im bekannten V3.3/Mainboardpfad |
|---:|---|
| 0 | kein Update / gleiche oder nicht akzeptierte Firmware |
| 1 | C350 akzeptiert |
| 2 | C357 akzeptiert |
| 3 | Staging vollständig + Staging-MD5 erfolgreich; Promotion läuft weiter |
| 4 | Staging-/Datenprüfung fehlgeschlagen |
| 5 | Promotion / finaler Commit erfolgreich |
| 6 | Promotion / Commit fehlgeschlagen |

## 17. Wichtigste Sicherheitsgrenze

- ADB-Upload auf das LTE-Modem ist noch kein Mainboard-Flash.
- C5A8 markiert den Beginn der eigentlichen Firmwaredatenphase.
- Vor C5A8 kann ein kontrollierter Recoverypfad zulässig sein.
- Ab dem ersten C5A8 bleibt der Originaldienst autoritativ.
- Ein Monitoring-/ADB-Fehler darf nach begonnenem Transfer keinen generischen Restore erzwingen.
- C36E Status 3 ist kein terminaler Erfolg und kein sicherer Stopppunkt.
- Erst Status 5 / Board-Step 12 ist terminaler Mainboard-Erfolg.

## 18. Evidenzgrad

**Live bestätigt für GL9 / Softwarecode `82400644`, V3.3 → V3.4:**

- C350/C36E-Handshake;
- C357;
- kompletter C5A8-Transfer;
- C371-ACKs;
- Status 3 nach Staging-Prüfung;
- selbstständige Promotionphase;
- Status 5;
- Board-Step 12;
- neue C544-Version `0034`;
- Rückkehr des normalen Betriebs.

**Statisch bzw. in Simulation zusätzlich rekonstruiert:**

- konkrete Flashbereiche;
- zweistufige MD5-Struktur;
- Copy-/Descriptor-/Commitdetails;
- Cancel-/Rollback- und Fehlerpfade.

Nicht in gleicher Tiefe live getestet sind andere Mainboardfamilien, andere Softwarecodes und reale Unterbrechungen in kritischen Flash-/Promotionphasen.

## 19. Weiterführende Dokumente

- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)
- [`PHNIX_phnixIot4G_board_ota_completion.md`](PHNIX_phnixIot4G_board_ota_completion.md)
- [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md)
- [`../HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../HowTo/PHNIX_UPDATER_ENDANWENDER.md)