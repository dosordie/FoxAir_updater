# PHNIX OTA Update-Ablauf – Kurzreferenz

Stand: 25. August 2026

Diese Datei fasst den aktuell bekannten PHNIX-/FoxAir-Mainboard-Updatepfad kompakt zusammen. Sie ist als schnelle Referenz gedacht und trennt bewusst zwischen:

- **Upload der Firmwaredatei vom Host auf das LTE-Modem** und
- **eigentlicher Firmwareübertragung vom LTE-Modem zum Mainboard über RS485/C5A8**.

> [!IMPORTANT]
> Ein per ADB auf das LTE-Modem kopiertes Firmwareimage bedeutet noch **nicht**, dass Firmwaredaten zum Mainboard geschrieben wurden. Die eigentliche Mainboard-Datenübertragung beginnt erst später mit **C5A8**.

---

## 1. Software-Schichten unter Windows

```text
FoxAir_Updater.exe
        │
        ▼
foxair_updater_app.py
  └─ GUI / lesbare Statusanzeige
        │
        ▼
foxair_updater_gui.py
  └─ baut den eigentlichen Aufruf
        │
        ▼
phnix_windows_controller_wrapper.py
  └─ Windows-Sicherheitswrapper
        │
        ▼
phnix_local_ota_controller_hardened.py
        │
        ▼
phnix_local_ota_controller_core.py
  = gemeinsamer OTA-Controller
        │
        ▼
ADB → LTE-Modem → phnixIot4G → RS485 → Mainboard
```

Der Windows-Wrapper und die GUI ergänzen Host-Sicherheitsprüfungen und Darstellung. Der eigentliche OTA-/RS485-Ablauf bleibt im gemeinsamen Controller und im Originaldienst `phnixIot4G`.

---

## 2. Kurz zusammengefasst

```text
Windows GUI
 ↓
Manifest/Firmware prüfen
 ↓
alten LTE-Cache sichern
 ↓
LTE-/ADB-Preflight
 ↓
Runtime-Hook auf LTE installieren
 ↓
Firmware per ADB nach /data/phnix_local_ota/... hochladen
 ↓
lokalen HTTP-Server bereitstellen
 ↓
Original phnixIot4G kontrolliert für den OTA-Ablauf verwenden
 ↓
C350 Versionsangebot
 ↓
C36E1
 ↓
C357 Größe + MD5
 ↓
C36E2
 ↓
phnixIot4G liest Firmware lokal per HTTP + MD5
 ↓
C5A8 Firmwareblöcke
 ↓
C371 ACKs
 ↓
Mainboard Staging-MD5
 ↓
C36E3
 ↓
interner Erase + Copy + MD5
 ↓
C36E5
 ↓
Commit / Loader / neue Firmware
```

---

## 3. Reihenfolge im Detail

### 3.1 Host-/Windows-Preflight

Vor einem echten Update passiert auf dem Windows-PC zunächst:

1. Manifest laden.
2. Firmwaredatei vollständig analysieren.
3. Firmwareidentität und Manifest vergleichen, u. a.:
   - Software-Code,
   - Display-/Wire-Version,
   - Target-SSID,
   - Dateigröße,
   - MD5,
   - SHA-256,
   - Image-Base.
4. Eventuell vorhandenen LTE-Firmware-Cache unter
   `/cache/phnixIot_device_OTA`
   lokal sichern.
5. ADB-/LTE-Preflight durchführen:
   - ADB erreichbar,
   - richtiger `phnixIot4G`-Build,
   - Watchdogs vorhanden,
   - benötigte Werkzeuge vorhanden,
   - `OTA_INFO` plausibel,
   - kein aktiver Resume-Zustand,
   - genügend Speicher auf `/data` und `/cache`.

---

### 3.2 Runtime-Helfer installieren

Der Host kopiert:

```text
phnix_ota_runtime_hook
```

nach:

```text
/data/phnix_ota_runtime_hook
```

auf dem LTE-Modem.

Der Helfer wird später benutzt, um den bekannten Originaldienst `phnixIot4G` über die validierten Hook-/Breakpoint-Stellen durch den OTA-Ablauf zu führen.

---

### 3.3 Eigentliche Firmwaredatei auf das LTE-Modem hochladen

Erst jetzt wird das Firmwareimage vom PC per ADB auf das LTE-Modem übertragen.

Beispiel:

```text
PC:
phnixIot_device_OTA

        │ adb push
        ▼

LTE:
/data/phnix_local_ota/phnixIot_device_OTA.bin
```

Danach wird die Datei auf dem LTE-Modem lokal per HTTP angeboten, z. B.:

```text
http://127.0.0.1:8081/phnixIot_device_OTA.bin
```

**Wichtig:** Bis hierhin wurde noch keine Firmware zum Mainboard übertragen.

---

## 4. Mainboard-Handshake

### 4.1 C350 – Firmwareangebot

Der Originaldienst sendet über RS485 ein C350-Telegramm mit der angebotenen Firmwareidentität, insbesondere Software-Code und Version.

Für V3.3 beispielsweise:

```text
Software-Code: 82400644
Wire-Version:   0033
```

### Gleiche Version

Wenn das Mainboard die Firmware bereits installiert hat:

```text
C350
 ↓
C36E = 0
 ↓
same-version
 ↓
STOP
```

Dann gilt:

```text
kein C357
kein C5A8
keine Firmwareblöcke zum Mainboard
```

Die Firmwaredatei kann zu diesem Zeitpunkt bereits auf dem LTE-Modem liegen, wurde aber **nicht zum Mainboard übertragen**.

---

### 4.2 C36E1 – neue/akzeptierte Version

Wenn das Mainboard das angebotene Image als kompatibel und anders als die installierte Version akzeptiert:

```text
C350
 ↓
C36E = 1
```

Danach folgt C357.

---

## 5. C357 – Dateigröße und MD5

C357 übermittelt die Metadaten des vollständigen Firmwareimages:

```text
Dateigröße
+
MD5
```

Bei erfolgreicher Annahme antwortet das Mainboard:

```text
C36E = 2
```

Dabei wird der persistente OTA-Pending-Zustand im Mainboard gesetzt. Für V3.3 wurde der zugehörige EEPROM-Zustand bei `0x3F0` rekonstruiert.

---

## 6. Lokaler HTTP-Lese-/MD5-Schritt im LTE-Modem

Nach C36E2 verwendet `phnixIot4G` seinen normalen OTA-Code:

```text
lokaler HTTP-Download
http://127.0.0.1:8081/...
        │
        ▼
Firmware lesen
        │
        ▼
MD5 prüfen
        │
        ▼
OTA_INFO aktualisieren
```

Erst nach diesem Schritt beginnt die eigentliche Firmwaredatenübertragung zum Mainboard.

---

## 7. C5A8 – eigentliche Firmwareübertragung zum Mainboard

Die Firmware wird in Blöcke zerlegt und über RS485 mit C5A8 übertragen.

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
      ├──── C5A8 Block 0 ────►│
      │◄──── C371 ACK ────────┤
      │                       │
      ├──── C5A8 Block 1 ────►│
      │◄──── C371 ACK ────────┤
      │                       │
      └──── ... ─────────────►│
```

Das Mainboard schreibt die Daten zunächst in den Staging-Bereich:

```text
0x080A1000 ...
```

---

## 8. C371 – Blockquittung

Jeder erfolgreich verarbeitete C5A8-Block wird mit C371 quittiert.

Beim letzten Block signalisiert die Abschlussquittung, dass der vollständige Datenstrom angekommen ist und der LTE-Offset der Firmwarelänge entspricht.

---

## 9. Staging-MD5

Nach dem letzten Firmwareblock prüft das Mainboard das vollständige Staging-Image.

```text
MD5 #1 über Staging
        │
        ├─ Fehler → C36E4
        │
        └─ OK     → C36E3
```

**C36E3 ist noch nicht der endgültige Firmwareerfolg.**

Es bedeutet: vollständiges Image angekommen und Staging-MD5 erfolgreich.

---

## 10. Interne Promotion im Mainboard

Danach erfolgt die interne Promotion:

```text
Staging-Image
0x080A1000 ...
        │
        ▼
Zielbereich löschen
0x08050000 ...
        │
        ▼
Firmware in Zielbereich kopieren
        │
        ▼
MD5 #2 über Zielbereich
        │
        ▼
Commit / EEPROM
```

Bei Erfolg:

```text
C36E5
```

Bei Fehler:

```text
C36E6
```

**C36E5 ist der relevante erfolgreiche Promotion-/Commit-Abschluss.**

---

## 11. Loader / Handoff

Nach dem erfolgreichen Commit:

```text
phnixIot4G Erfolgsablauf
 ↓
board_ota_step → 12
 ↓
Loader / Handoff
 ↓
neue Mainboard-Firmware startet
```

Ein anschließendes C544 kann die neue Mainboard-Identität liefern. Der exakte zeitliche Ablauf dieses ersten C544 nach einem echten Versionswechsel wurde bislang noch nicht live validiert.

---

## 12. Die wichtigste Trennung

```text
ADB-Upload:
Windows-PC
  ↓
LTE-Modem /data/phnix_local_ota/...

≠

Mainboard-Firmwaretransfer:
LTE-Modem / phnixIot4G
  ↓
RS485 C5A8
  ↓
Mainboard-Staging-Flash
```

Daher gilt:

> **Eine Firmwaredatei auf dem LTE-Modem ist noch kein begonnenes Mainboard-Flashing.**
>
> Der tatsächliche Firmwaredatenpfad zum Mainboard beginnt mit den C5A8-Blöcken.

---

## 13. Statuscodes als Kurzreferenz

| C36E | Bedeutung im bekannten V3.3-Pfad |
|---:|---|
| 0 | kein Update / gleiche oder nicht akzeptierte Firmware |
| 1 | C350 akzeptiert |
| 2 | C357 akzeptiert |
| 3 | vollständiges Staging-Image + MD5 erfolgreich |
| 4 | Staging-/Datenprüfung fehlgeschlagen |
| 5 | Promotion / finaler Commit erfolgreich |
| 6 | Promotion / Commit fehlgeschlagen |

---

## 14. Sicherheitsgrenze der aktuellen Erkenntnisse

Statisch und durch bestehende Tests gut belegt sind insbesondere:

- C350/C36E-Handshake,
- C357-Größe/MD5,
- C5A8-Blockformat,
- C371-ACK-Verhalten,
- Staging-Pfad,
- zweistufige MD5-Prüfung,
- C36E3 vs. C36E5,
- Promotion-/Commit-Struktur.

Ein echter vollständiger Versionswechsel auf realer Hardware mit anschließend bestätigtem Start der neuen Firmware wurde bislang noch nicht vollständig live validiert. Diese Datei beschreibt daher den aktuell rekonstruierten und implementierten Ablauf, nicht eine bereits für alle Fehlerfälle bewiesene Recovery-Garantie.
