# Reverse-Engineering-Dokumentation

Stand: 1. September 2026

Dieser Ordner enthält sowohl **aktuelle technische Referenzen** als auch bewusst erhaltene **historische Arbeits-/Teststände** aus der Entwicklung des FoxAir Updaters.

> [!IMPORTANT]
> Der aktuelle Projektstand ist nicht mehr „nur rekonstruiert“: Ein vollständiger Mainboard-Firmwarewechsel **V3.3 → V3.4** wurde auf realer Hardware erfolgreich durchgeführt. Bestätigt wurden kompletter C5A8-Transfer, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließend C544-Version `0034`.

## Aktuelle Einstiegsdokumente

Für den heutigen Stand zuerst diese Dateien verwenden:

- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md) – vollständiger realer V3.3→V3.4-Lauf mit Zeitpunkten und Belegen.
- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md) – aktueller OTA-Gesamtablauf von C350 bis Status 5/C544.
- [`PHNIX_phnixIot4G_board_ota_state_machine.md`](PHNIX_phnixIot4G_board_ota_state_machine.md) – aktuelle `board_ota_step`-Einordnung mit Live-Bestätigung.
- [`PHNIX_phnixIot4G_board_ota_completion.md`](PHNIX_phnixIot4G_board_ota_completion.md) – Abschluss nach dem letzten C5A8, Status 3/5 und Step 12.
- [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md) – Watchdogs, Reset-Counter und präzise MQTT-Offline-/1800-s-Logik.
- [`PHNIX_LOCAL_OTA_LAUNCHER_BEDIENUNG.md`](PHNIX_LOCAL_OTA_LAUNCHER_BEDIENUNG.md) – technische Bedienung des aktuellen lokalen Controllers.
- [`PHNIX_DTU_AUTONOMOUS_RUNNER_LIVE_TEST_2026-09-01.md`](PHNIX_DTU_AUTONOMOUS_RUNNER_LIVE_TEST_2026-09-01.md) – isolierter Live-Nachweis eines von der startenden ADB-Shell unabhängigen Minimal-Runners auf dem DTU.

Für Endanwender ist nicht dieser Ordner, sondern [`../HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../HowTo/PHNIX_UPDATER_ENDANWENDER.md) die richtige Anleitung.

## Wichtige aktuelle Erkenntnisse in Kurzform

```text
V3.3 → V3.4 live erfolgreich
C5A8-Transfer:            ca. 28:56 min
letzter C5A8 → Status 3:  ca. 2 s
letzter C5A8 → Status 5:  ca. 5:16 min
bis neue C544-Version:    rund 35 min Gesamtbeobachtung
```

Dabei gilt:

- 100 % C5A8 bedeutet nur „alle Firmwaredaten übertragen“.
- C36E Status 3 bedeutet erfolgreiche Staging-Prüfung, nicht terminalen Erfolg.
- C36E Status 5 / Board-Step 12 ist der terminale Mainboardabschluss des bestätigten Pfads.
- MQTT bleibt beim normalen lokalen Vollupdate standardmäßig verbunden.
- Der PHNIX-1800-s-Rebootzähler startet erst, wenn der Aliyun-SDK den Client intern als offline bewertet; eine stille Firewall-DROP-Sperre startet diesen Zähler nicht zwingend sofort.
- Es wurde kein OTA-Sonderzweig gefunden, der den Cloud-Offline-Reboot während eines Mainboardupdates deaktiviert.
- Ab begonnenem C5A8 bleibt der Originaldienst autoritativ; generischer Restore ist danach absichtlich gesperrt.

## Historische Dokumente

Mehrere Dateien tragen ein Datum, einen PR-/Workchat-Bezug oder beschreiben ausdrücklich eine damalige Teststufe. Sie bleiben absichtlich erhalten, weil sie die Herleitung und Sicherheitsentscheidungen dokumentieren.

Dazu gehören insbesondere:

- `PHNIX_OTA_UPDATER_SAFETY_HARDENING_2026-08-24.md`
- `PHNIX_OTA_WORKCHAT_UEBERGABE.md`
- ältere Pre-C5A8-/Cancel-/Probe-Testpläne
- frühe Offline-Laborentwürfe im Umfeld der ersten Runtime-Hook-Entwicklung

Solche Dateien dürfen Aussagen enthalten wie „vollständiger Versionswechsel noch nicht live getestet“ oder frühere Empfehlungen zur vollständigen MQTT-Isolierung. Diese Aussagen sind im jeweiligen **historischen Entwicklungszeitpunkt** korrekt, aber nicht als heutiger Projektstatus zu lesen.

## Statische Referenzen bleiben versionsgebunden

Viele Dokumente analysieren ausdrücklich den Originaldienst mit:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

oder die Mainboard-Firmware V3.3. Diese statischen Ergebnisse werden nicht pauschal auf andere Builds oder Hardwarevarianten umgeschrieben, nur weil V3.4 inzwischen erfolgreich installiert wurde.

## Aktuelle Endanwender-/Release-Dokumentation

- [`../HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../HowTo/PHNIX_UPDATER_ENDANWENDER.md)
- [`../HowTo/FIRMWARE_MANIFEST.md`](../HowTo/FIRMWARE_MANIFEST.md)
- [`../HowTo/firmware_backup_lte.md`](../HowTo/firmware_backup_lte.md)
- [`../RELEASE_NOTES_WINDOWS_v0.3.9.md`](../RELEASE_NOTES_WINDOWS_v0.3.9.md)
- [`../../updater/windows/README.md`](../../updater/windows/README.md)

Damit sollte beim Lesen klar zwischen aktuellem Betriebsstand, statischer Reverse-Engineering-Referenz und historischem Entwicklungsprotokoll unterschieden werden.
