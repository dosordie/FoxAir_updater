# FoxAir Updater Windows v0.3.9 – Release Notes

Stand: 29. August 2026

## Kurzfassung

Version **0.3.9** ist der erste Windows-Release, bei dem ein echter Mainboard-Firmwarewechsel mit dem FoxAir Updater auf realer Hardware vollständig durchgeführt und anschließend unabhängig bestätigt wurde.

Der reale Test aktualisierte eine FoxAir/PHNIX GL9 von **Mainboard-Firmware V3.3 auf V3.4**. Der vollständige C5A8-Firmwaretransfer, die anschließende Mainboard-Verarbeitung bis **C36E Status 5 / Board-Step 12** sowie die danach gemeldete Firmwareversion **V3.4** wurden beobachtet.

Der Updater wird deshalb nicht mehr als „experimentell“ bezeichnet. Ein Firmwareupdate bleibt dennoch ein Eingriff in das Mainboard und erfolgt weiterhin auf eigenes Risiko. Andere Firmwarestände und Hardwarevarianten sind noch nicht vollständig live validiert.

---

## Was ist neu gegenüber Windows v0.3.3?

### MQTT bleibt während eines normalen Updates verbunden

Der wichtigste technische Unterschied ist das Verhalten der LTE-/Cloud-Verbindung während eines Mainboard-Updates.

Bisher wurde MQTT vorsorglich während des Updates per Firewall isoliert. Das hat sich beim realen V3.3→V3.4-Lauf als unnötiges zusätzliches Risiko erwiesen, weil die Firmwareübertragung allein knapp 29 Minuten benötigt und das Mainboard danach noch mehrere Minuten für Prüfung, Flash/Promotion und Abschluss braucht.

Ab v0.3.9 gilt deshalb:

- **Standard:** MQTT bleibt während des Mainboard-Updates verbunden.
- Der originale `phnixIot4G`-Dienst behält damit seinen normalen Cloud-/MQTT-Zustand.
- Die optionale alte Isolation bleibt für spezielle Tests verfügbar.
- Kommandozeile: `--isolate-mqtt` beziehungsweise Alias `--update-no-mqtt`.
- Windows-GUI: unter **Erweitert** die Option **„MQTT bei Update aus“**.
- Die Einstellung der Checkbox wird gespeichert.

Hintergrund: Der Originaldienst besitzt einen eigenen Cloud-Offline-/Resetmechanismus. Der 1800-s-Zähler beginnt erst, nachdem der Aliyun-MQTT-SDK die Verbindung intern tatsächlich als offline bewertet; eine stille Paketblockade per `iptables DROP` muss deshalb nicht exakt nach 30 Minuten zum Reboot führen. Dennoch ist eine absichtlich getrennte MQTT-Verbindung für einen langen Firmwaretransfer ein vermeidbares Risiko.

### Abschluss des Updates wird realistischer bewertet

Der reale Lauf hat gezeigt, dass **100 % Fortschritt nur bedeutet, dass alle Firmwaredaten per C5A8 an das Mainboard übertragen wurden**.

Danach arbeitet das Mainboard noch selbstständig weiter.

Der Updater berücksichtigt jetzt deutlicher:

1. Firmwaredaten vollständig übertragen – 100 %
2. Staging-Prüfung / `C36E Status 3`
3. Mainboard-Flash-/Promotionphase
4. `C36E Status 5` / `board_ota_step = 12`
5. Prüfung des normalen LTE-/Cloudzustands

Erst **Status 5 / Board-Step 12** gilt als terminaler erfolgreicher Mainboardabschluss.

### Mehr Zeit für die Rückkehr des normalen LTE-Betriebs

Nach dem terminalen Mainboardergebnis prüft der Controller weiterhin den Originalzustand des LTE-Moduls.

Da beim Live-Test MQTT unmittelbar nach Status 5 noch nicht sofort wieder in `netstat` sichtbar war, erhält der normale Runtime-Zustand nun ein **120-Sekunden-Fenster**.

Geprüft werden dabei unter anderem:

- originaler `phnixIot4G`-Dienst aktiv
- erwartete Original-SHA256 des Dienstes
- Watchdogs aktiv
- MQTT/Cloud verbunden
- temporärer Update-Helfer entfernt

Damit wird ein erfolgreich abgeschlossenes Mainboard-Update nicht mehr vorschnell als Fehler gewertet, nur weil der LTE-/MQTT-Zustand wenige Sekunden später noch nicht vollständig normalisiert ist.

### Windows-Oberfläche nicht mehr als „experimentell“ bezeichnet

Nach dem erfolgreichen Live-Update wurde die bisherige Experimentell-Kennzeichnung aus der Windows-Oberfläche entfernt.

Stattdessen zeigt die GUI einen sachlichen Risikohinweis:

> **Firmwareupdate – Nutzung auf eigenes Risiko**

Der Hinweis stellt klar:

- V3.3 → V3.4 wurde real erfolgreich getestet.
- Andere Firmwarestände und Hardwarevarianten sind noch nicht vollständig getestet.
- Ein Firmwareupdate kann bei Fehlern zum Ausfall des Geräts führen.

Auch Fenstertitel, Bestätigungsdialog und weitere Benutzertexte wurden entsprechend angepasst.

### Meldungen während des Updates angepasst

Die Statusmeldungen wurden an den neuen MQTT-Standard und den real beobachteten Ablauf angepasst.

Insbesondere wird nicht mehr vorausgesetzt, dass MQTT während eines normalen Updates getrennt und anschließend neu verbunden werden muss.

Nach dem Mainboardabschluss wird neutral der normale **LTE-/Cloudzustand geprüft**.

Der Fortschrittsbalken bleibt nach dem vollständigen Firmwaretransfer bei 100 %, während die nachfolgende Mainboard-Verarbeitung als eigene Phase weiterläuft.

---

## Was wurde auf realer Hardware bestätigt?

Der V3.3→V3.4-Lauf wurde auf einer realen FoxAir/PHNIX GL9 durchgeführt.

Verwendete Mainboard-Firmware:

| Feld | Wert |
|---|---|
| Softwarecode | `82400644` |
| Ziel-SSID | `0063` |
| Ausgangsversion | `V3.3` / `0033` |
| Zielversion | `V3.4` / `0034` |
| Firmwaregröße | `289806` Byte |
| MD5 | `149A586EDE6F035B385762EA48C71605` |
| SHA-256 | `97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890` |

Gemessener Ablauf:

| Ereignis | Zeitpunkt |
|---|---|
| C350 Firmwareangebot | 00:51:18 |
| C36E Status 2 | 00:51:19 |
| erster C5A8-Firmwareblock | 00:51:20 |
| letzter C5A8-Firmwareblock bestätigt | 01:20:16 |
| C36E Status 3 | 01:20:18 |
| C36E Status 5 | 01:25:32 |
| terminaler Erfolg / Board-Step 12 | 01:25:34 |
| C544 meldet V3.4 / `0034` | 01:26:33 |

Damit wurden live bestätigt:

- Annahme des Firmwareangebots durch das Mainboard
- vollständige C5A8-Datenübertragung
- Persistenz/Fortschritt über `phnixIot_device_OTA_INFO`
- Übergang auf C36E Status 3 nach dem letzten Datenblock
- anschließende selbstständige Mainboard-Verarbeitung
- C36E Status 5 als erfolgreicher Abschluss
- terminaler `board_ota_step = 12`
- Rückkehr des normalen Mainboard-/Warmlink-Verkehrs
- neue Mainboardversion **V3.4** über C544/Geräteinfo
- Originaldienst `phnixIot4G` blieb im kritischen Übertragungs- und Flashfenster derselbe Prozess
- normaler LTE-/MQTT-Betrieb stellte sich nach dem Update wieder her

### Reale Laufzeiten

Die gemessenen Zeiten sind für weitere Tests wichtig:

- reine C5A8-Firmwareübertragung: **ca. 28 min 56 s**
- letzter Datenblock → C36E Status 3: **ca. 2 s**
- letzter Datenblock → C36E Status 5: **ca. 5 min 16 s**
- vollständiger beobachteter Ablauf bis zur ersten V3.4-C544-Meldung: **rund 35 Minuten**

Damit ist bestätigt, dass 100 % im Fortschrittsbalken nicht mit dem Ende des gesamten Firmwareupdates gleichgesetzt werden darf.

---

## Sicherheitsverhalten

Die bereits vorhandenen Schutzmechanismen bleiben erhalten.

Insbesondere:

- Vor dem Firmwarestart werden Firmwaredatei und Manifest geprüft.
- Nach Beginn des ersten C5A8-Firmwareblocks ist ein automatisches Restore absichtlich gesperrt.
- Ab diesem Zeitpunkt bleibt der originale PHNIX-Dienst für den OTA-Ablauf autoritativ.
- `C36E Status 3` ist kein sicherer Stopp-/Restorepunkt.
- Bei Verlust der ADB-Beobachtung nach begonnenem C5A8 darf der laufende Mainboardprozess nicht durch einen generischen Restore unterbrochen werden.
- Der normale Originalzustand des LTE-Moduls kann read-only geprüft werden.

Das Firmwaremanifest bindet unter anderem Softwarecode, Version, Ziel-SSID, Größe, MD5 und SHA256 an die ausgewählte Firmwaredatei.

---

## Was ist weiterhin nicht vollständig live geprüft?

Der erfolgreiche Test bestätigt den konkreten Pfad **FoxAir/PHNIX GL9, Softwarecode `82400644`, V3.3 → V3.4**.

Daraus folgt nicht automatisch, dass jede PHNIX-/FoxAir-Hardware und jede Firmwarekombination identisch reagiert.

Noch nicht in gleicher Tiefe live bestätigt sind insbesondere:

- andere Mainboard-Softwarecodes
- andere Hardwarevarianten
- beliebige ältere oder neuere Firmwarekombinationen
- Verhalten bei realen Unterbrechungen während kritischer Flash-/Promotionphasen
- gleichzeitige aktive Cloud-OTA-Kommandos während eines lokalen Updates

Deshalb bleibt ein Firmwareupdate trotz erfolgreichem Live-Test ein Vorgang mit Ausfallrisiko.

---

## Windows-Paket

FoxAir Updater Windows v0.3.9 wird als Setup und portable Variante veröffentlicht:

- `FoxAir_Updater_Setup_v0.3.9.exe`
- `FoxAir_Updater_Portable_v0.3.9.zip`

SHA-256 der veröffentlichten Release-Artefakte:

| Datei | SHA-256 |
|---|---|
| `FoxAir_Updater_Setup_v0.3.9.exe` | `F007D52373EF3B2CF87FAF6E338BCBD21B476534832B752AAAB72A85BC960B61` |
| `FoxAir_Updater_Portable_v0.3.9.zip` | `7815630504CD0F16946B40085EA4BFE6E6FAFABC80FBA04931D2A5FC101E0887` |

### Hinweise für Windows

- Die Builds sind derzeit nicht kommerziell code-signiert. Windows SmartScreen kann deshalb beim ersten Start einen Hinweis anzeigen.
- ADB wird aus Lizenz-/Distributionsgründen nicht mitgeliefert.
- Die GUI verweist auf die offiziellen Android Platform Tools sowie den passenden SIMCom-USB-Treiber.
- Lokaler ADB-Betrieb und Remote-ADB über einen Raspberry Pi werden weiterhin unterstützt.

---

## Technische Referenzen

Ausführliche technische Details zum erfolgreichen Live-Lauf:

- `docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`
- `docs/reverse_engineering/PHNIX_phnixIot4G_watchdogs_reset_counters.md`
- `docs/reverse_engineering/PHNIX_phnixIot4G_ota_full_path.md`
- `docs/reverse_engineering/PHNIX_phnixIot4G_board_ota_state_machine.md`

Vergleich der veröffentlichten Windows-Tags:

- Basis: `windows-v0.3.3`
- Release: `windows-v0.3.9`

---

## Zusammenfassung

Windows v0.3.9 markiert den Übergang vom ausschließlich abgesicherten Test-/Gleichversionspfad zu einem **real erfolgreich ausgeführten Mainboard-Firmwareupdate**.

Die wichtigsten Änderungen sind:

1. V3.3 → V3.4 auf realer GL9 erfolgreich durchgeführt und als V3.4 bestätigt.
2. MQTT bleibt beim normalen Update standardmäßig verbunden.
3. Optionale MQTT-Isolation bleibt unter **Erweitert → MQTT bei Update aus** verfügbar.
4. 100 % bedeutet nur Ende des Firmwaretransfers; Status 5 / Board-Step 12 ist der eigentliche Mainboardabschluss.
5. Nach dem Abschluss erhält der LTE-/MQTT-Runtimezustand bis zu 120 Sekunden zur Normalisierung.
6. Die Windows-GUI wird nicht mehr als „experimentell“ bezeichnet; der verbleibende Firmware-Risiko-Hinweis bleibt bewusst bestehen.

**Firmwareupdates weiterhin nur mit passender, eindeutig identifizierter Firmware und passendem Manifest durchführen.**
