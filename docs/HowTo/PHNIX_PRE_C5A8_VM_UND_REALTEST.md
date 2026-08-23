# PHNIX-Generalprobe bis vor C5A8

Stand: 2026-08-23

## Ziel

Diese Stufe prüft den vollständigen Metadatenhandshake und den bereits live
bestätigten Cancelpfad, ohne einen Firmwareblock zu senden:

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

`C5A8` muss während des gesamten Tests exakt nullmal auftreten.

## Aktueller Sperrstatus

Der implementierte Befehl heißt:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb ./tools/phnix_ota/phnix-sim-adb \
  pre-c5a8-vm-test \
  --firmware /pfad/zur/Firmware.bin \
  --execute \
  --confirm VM-PRE-C5A8-ONLY
```

Er läuft ausschließlich, wenn das Ziel die Simulator-Markierung
`/data/.phnix_ota_simulator` besitzt. Auf dem echten LTE-Modem ist dieser
Befehl auch mit `--execute` und richtigem Bestätigungstext gesperrt.

## Erfolgskriterien der VM

Vor dem Cancel müssen gemeinsam nachgewiesen sein:

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

Zusammen mit den vorhandenen Transfer-, Persistenz- und Cancel-Szenarien sowie
den Unit-Tests ist damit die Softwareseite bis zur Realhardwaregrenze geprüft.

## Noch nicht implementierter Realmodus

Der Realmodus wird erst nach einer neuen ausdrücklichen Freigabe aktiviert.
Er benötigt zusätzlich:

1. verifizierten Originaldienst-Build;
2. OTA_INFO mit gültiger CRC, Offset 0 und Länge 0;
3. passende Firmwaregröße, MD5, Softwarecode, Version und Vector Table;
4. kontrolliert getrennte Original-Cloud;
5. bestätigte Sendepause des originalen LTE-Modems;
6. passiven Logger mit Sonderbehandlung für C350, C357, C36E, C36A und C36C;
7. harte Breakpoints/Guards an C5A8 und allen späteren Schreibphasen;
8. Bedienerbeobachtung an der Wärmepumpe;
9. stabile Versorgung für Wärmepumpe, LTE-Modem, Raspberry Pi und Logger;
10. vorbereiteten Recoveryablauf, falls C36C oder Step 12 ausbleibt.

## Abbruchregeln des späteren Realtests

Der Test bleibt angehalten und wird nicht automatisch aufgeräumt, wenn:

- SSID, Softwarecode, Version, Dateigröße oder MD5 abweichen;
- C36E nicht Status 1 beziehungsweise 2 meldet;
- irgendein C5A8-Frame erreicht wird;
- ein fremdes oder widersprüchliches OTA-Frame erscheint;
- C36C Status 1 ausbleibt;
- `cancel_pending` nicht gelöscht wird;
- der Originaldienst Step 12 nicht erreicht;
- Wärmepumpe oder Bus ungewöhnliches Verhalten zeigen.

Erst der nachgewiesene Terminalzustand erlaubt die Wiederherstellung von
Cloud, Watchdogs und Originalbetrieb.

## Bedeutung für den vollständigen Firmwaretransfer

Ein erfolgreicher Realtest dieser Stufe würde erstmals beweisen, dass das
Originalprogramm mit unseren lokalen Firmwaremetadaten bis unmittelbar vor die
Flash-schreibende Datenphase kommt und sich anschließend sicher abbrechen
lässt. Er beweist noch nicht:

- C5A8-Schreiben in den Staging-Flash;
- vollständigen Dateitransfer;
- Promotion/Copy nach `0x08050000`;
- Boot der neuen Firmware;
- Power-Loss- oder Loader-Recovery.

Diese Punkte bleiben eigene, später separat freizugebende Risikostufen.

## Zugehörige Dokumente

- [`PHNIX_PRE_C5A8_REALTEST_RUNBOOK.md`](PHNIX_PRE_C5A8_REALTEST_RUNBOOK.md)
- [`PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md)
- [`PHNIX_CANCEL_PROBE_LIVE_RESULT.md`](../reverse_engineering/PHNIX_CANCEL_PROBE_LIVE_RESULT.md)
- [`phnix_ota_sender.md`](phnix_ota_sender.md)
