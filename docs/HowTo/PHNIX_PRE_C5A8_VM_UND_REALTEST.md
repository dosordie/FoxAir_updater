# PHNIX-Generalprobe bis vor C5A8

Stand: 2026-08-24

> [!IMPORTANT]
> **Historisches Entwicklungsdokument.** Diese Datei beschreibt den Projektstand vom 24. August 2026, als der echte Firmware-Schreibpfad noch nicht freigegeben war.
>
> Inzwischen wurde **V3.3 → V3.4** auf realer Hardware vollständig und erfolgreich durchgeführt, einschließlich C5A8, Status 3, Status 5 / Board-Step 12 und anschließender C544-Version `0034`.
>
> Aussagen weiter unten wie „noch nicht implementierter Realmodus“ oder „bleiben spätere Risikostufen“ sind deshalb bewusst als historischer Entwicklungsstand zu lesen. Aktueller Endanwenderpfad: [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md). Live-Nachweis: [`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md).

## Ziel der damaligen Stufe

Diese Stufe prüfte den vollständigen Metadatenhandshake und den bereits live bestätigten Cancelpfad, ohne einen Firmwareblock zu senden:

```text
C350
→ C36E Status 1
C357
→ C36E Status 2
→ technischer Halt vor C5A8
C36A
→ C36C Status 1
→ Originaldienst Step 12
```

`C5A8` musste während des gesamten Tests exakt nullmal auftreten.

## Damaliger Sperrstatus

Der implementierte Befehl hieß:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb ./tools/phnix_ota/phnix-sim-adb \
  pre-c5a8-vm-test \
  --firmware /pfad/zur/Firmware.bin \
  --execute \
  --confirm VM-PRE-C5A8-ONLY
```

Er lief ausschließlich, wenn das Ziel die Simulator-Markierung
`/data/.phnix_ota_simulator` besaß. Auf dem echten LTE-Modem war dieser Befehl
auch mit `--execute` und richtigem Bestätigungstext gesperrt.

## Erfolgskriterien der VM

Vor dem Cancel mussten gemeinsam nachgewiesen sein:

```text
phase == pre-c5a8-hold
C350 gesendet
C36E Status 1 empfangen
C357 gesendet
C36E Status 2 empfangen
board_ota_step == 1
C5A8 gesendet == false
Mitschnitt-C5A8-Zähler == 0
SSID unverändert
Metadaten unverändert
```

Nach dem Cancel:

```text
C36A gesendet
C36C Status 1 und passende SSID
cancel_pending == false
board_ota_step == 12
Normalbetrieb bestätigt
```

## Auf der VM geprüfte Fehlerfälle

| Szenario | Erwartung | Ergebnis |
|---|---|---|
| vollständiger Handshake und Cancel | sauberer Abschluss | bestanden |
| falscher C36E-Status 1 | guarded-hold | bestanden |
| fehlender C36E-Status 2 | guarded-hold | bestanden |
| C357-Metadaten ändern sich | guarded-hold | bestanden |
| ein unerlaubtes C5A8 erscheint | guarded-hold | bestanden |
| Cancel ohne terminale Bestätigung | guarded-hold | bestanden |

Zusammen mit den damaligen Transfer-, Persistenz- und Cancel-Szenarien sowie den Unit-Tests war damit die Softwareseite bis zur damaligen Realhardwaregrenze geprüft.

## Damals noch nicht implementierter Realmodus

Zum Stand 24. August 2026 sollte der Realmodus erst nach neuer ausdrücklicher Freigabe aktiviert werden und unter anderem benötigen:

1. verifizierten Originaldienst-Build;
2. OTA_INFO mit gültiger CRC, Offset 0 und Länge 0;
3. passende Firmwaregröße, MD5, Softwarecode, Version und Vector Table;
4. kontrolliert getrennte Original-Cloud;
5. bestätigte Sendepause des originalen LTE-Modems;
6. passiven Logger für C350, C357, C36E, C36A und C36C;
7. harte Breakpoints/Guards an C5A8 und späteren Schreibphasen;
8. Bedienerbeobachtung;
9. stabile Versorgung;
10. vorbereiteten Recoveryablauf.

Diese Forderungen dokumentieren die damalige vorsichtige Teststufe. Der heutige normale Vollupdatepfad unterscheidet sich insbesondere dadurch, dass MQTT standardmäßig verbunden bleibt und der Originaldienst nach Beginn des Transfers autoritativ bleibt.

## Abbruchregeln des damaligen Realtests

Der Test sollte angehalten und nicht automatisch aufgeräumt werden, wenn:

- SSID, Softwarecode, Version, Dateigröße oder MD5 abweichen;
- C36E nicht Status 1 beziehungsweise 2 meldet;
- irgendein C5A8-Frame erreicht wird;
- ein fremdes oder widersprüchliches OTA-Frame erscheint;
- C36C Status 1 ausbleibt;
- `cancel_pending` nicht gelöscht wird;
- der Originaldienst Step 12 nicht erreicht;
- Wärmepumpe oder Bus ungewöhnliches Verhalten zeigen.

Erst der nachgewiesene Terminalzustand sollte die Wiederherstellung von Cloud, Watchdogs und Originalbetrieb erlauben.

## Bedeutung dieser historischen Teststufe

Ein erfolgreicher Realtest dieser Stufe hätte damals erstmals bewiesen, dass das Originalprogramm mit lokalen Firmwaremetadaten bis unmittelbar vor die Flash-schreibende Datenphase kommt und sich anschließend sicher abbrechen lässt.

Nicht Bestandteil dieser Stufe waren damals:

- C5A8-Schreiben in den Staging-Flash;
- vollständiger Dateitransfer;
- Promotion/Copy nach `0x08050000`;
- Boot der neuen Firmware;
- Power-Loss- oder Loader-Recovery.

Die ersten vier Punkte wurden später im vollständigen V3.3→V3.4-Live-Lauf praktisch weiter validiert; Power-Loss-/Loader-Recovery bleibt weiterhin eine eigene Risikoklasse.

## Zugehörige Dokumente

- [`PHNIX_PRE_C5A8_REALTEST_RUNBOOK.md`](PHNIX_PRE_C5A8_REALTEST_RUNBOOK.md)
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md)
- [`firmware_backup_lte.md`](firmware_backup_lte.md)
- [`PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md)
- [`PHNIX_CANCEL_PROBE_LIVE_RESULT.md`](../reverse_engineering/PHNIX_CANCEL_PROBE_LIVE_RESULT.md)
- [`phnix_ota_sender.md`](phnix_ota_sender.md)
- [`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)