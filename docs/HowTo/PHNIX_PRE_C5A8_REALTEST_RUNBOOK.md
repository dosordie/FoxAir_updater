# PHNIX Pre-C5A8-Realtest – vorbereitetes Runbook

Stand: 2026-08-24

> [!IMPORTANT]
> **Historisches Entwicklungsdokument.** Dieses Runbook beschreibt den Sicherheits- und Teststand vom 24. August 2026 **vor** dem ersten vollständigen Live-Firmwarewechsel.
>
> Inzwischen wurde V3.3 → V3.4 auf realer Hardware vollständig und erfolgreich durchgeführt, einschließlich C5A8, C36E Status 3, C36E Status 5 / Board-Step 12 und anschließender C544-Version `0034`.
>
> Die Aussagen weiter unten wie „nicht gestartet“, „noch ausstehend“ oder „späterer Realtest“ sind deshalb **historischer Kontext und keine aktuelle Projektstatusbeschreibung**. Für den aktuellen Endanwenderpfad siehe [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md) und den Live-Bericht [`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md).

## Status zum damaligen Stand

Der Test war vorbereitet, aber **nicht scharfgeschaltet und nicht gestartet**.
Es wurde kein neuer Helfer auf das LTE-Modem übertragen und kein Livekommando
ausgeführt. Die Logging-Software konnte unabhängig fertiggestellt werden.

## Testgrenze

Erlaubt war damals ausschließlich:

```text
C350 → C36E Status 1
C357 → C36E Status 2
HARD STOP vor dem Eintritt in C5A8
C36A → C36C Status 1
LTE-intern zurück zu Step 12
```

Verboten blieben in dieser Teststufe:

```text
C5A8-Firmwaredaten
Promotion/Copy
Bootumschaltung
Rollback
Cloud-OTA parallel zum lokalen Test
```

## Vorbereiteter lesender Preflight

Vor dem späteren Freigabetermin wurde eine Kopie von
`tools/phnix_ota/pre_c5a8_logger_checklist.example.json` ausgefüllt. Danach:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  pre-c5a8-real-plan \
  --firmware /pfad/zur/Firmware.bin \
  --logger-checklist /pfad/logger-ready.json
```

Dieser Befehl ist rein lesend. Er prüft Firmware, Originaldienst, Watchdogs,
OTA_INFO, Persistenz, Speicher und Loggerbereitschaft. Seine Ausgabe enthält
immer:

```json
"live_execution_enabled": false
```

Ein Ergebnis `ready: true` ist nur eine Bereitschaftsaussage und keine
Sendefreigabe.

## Loggerpflichten

Die ausgefüllte Checkliste musste bestätigen:

- Mitschnitt läuft bereits vor dem Test;
- Logger ist physisch und softwareseitig rein passiv;
- Rohhex und Zeitstempel sind aktiviert;
- CRC wird validiert;
- fragmentierte Frames werden zusammengesetzt;
- mehrere Frames pro Lesevorgang werden getrennt;
- ProductKey und andere Geheimnisse werden maskiert;
- C350, C357, C36E, C36A, C36C und C5A8 werden erkannt;
- jedes C5A8 löst einen kritischen Alarm aus;
- Ausgabedatei ist festgelegt und beschreibbar.

## Erwartete Referenzframes für FW3.3

C350:

```text
63 10 C3 50 00 07 0E 00 63
38 32 34 30 30 36 34 34
30 30 33 33
59 4D
```

C357:

```text
63 10 C3 57 00 13 26 00 63 00 04 63 6E
63 65 62 36 61 34 62 66 33 38 36 66 66 36 34 34
65 32 33 65 34 31 30 30 32 33 65 37 34 36 37 33
C3 65
```

C36E Status 1 und 2 im echten Vier-Byte-Wireformat:

```text
63 10 C3 6E 00 02 04 00 63 00 01 F4 99
63 10 C3 6E 00 02 04 00 63 00 02 B4 98
```

Cancel und Bestätigung:

```text
C36A  63 10 C3 6A 00 02 04 00 63 00 01 F5 6A
C36C  63 10 C3 6C 00 02 04 00 63 00 01 75 40
```

Verbotener C5A8-Anfang bei Defaultblockgröße:

```text
63 10 C5 A8 00 57 A8 00 63 ...
```

## Rollen beim damaligen Test

| Rolle | Aufgabe |
|---|---|
| Bediener | Wärmepumpe beobachten, Freigabe erteilen, bei Auffälligkeit Stop verlangen |
| Logger | ab mindestens 60 Sekunden vorher passiv aufzeichnen |
| Updater | Preflight, Cloudguard, Originaldienst-Hook, Statusausgabe |
| Recovery | bei unvollständigem Beweis Guards erhalten und Zustand auslesen |

Eine Person konnte mehrere Rollen übernehmen, Logger und Updater sollten jedoch getrennte Statusanzeigen besitzen.

## Geplanter Ablauf am damaligen Termin

1. Wärmepumpe mindestens fünf Minuten stabil im Normalbetrieb beobachten.
2. Logger starten und mindestens 60 Sekunden normalen Busverkehr aufnehmen.
3. Loggerdatei und freien Speicher kontrollieren.
4. Lesenden `pre-c5a8-real-plan` ausführen und Ergebnis archivieren.
5. Firmwaregröße/MD5 und OTA_INFO nochmals anzeigen.
6. Original-Cloud kontrolliert trennen; keine Cloud-Nachricht einspeisen.
7. Neue ausdrückliche Freigabe des Bedieners abwarten.
8. Erst dann den noch disarmten Livepfad für genau diesen Lauf aktivieren.
9. C350 und C36E Status 1 gemeinsam bestätigen.
10. C357 und C36E Status 2 gemeinsam bestätigen.
11. Am C5A8-Funktionseinstieg stoppen, bevor der Framebauer senden kann.
12. Logger muss `C5A8 count = 0` melden.
13. Cancel 0073 lokal setzen; C36A/C36C und passende SSID bestätigen.
14. `cancel_pending=0` und `board_ota_step=12` intern bestätigen.
15. Originaldienst, Watchdogs und Cloud wiederherstellen.
16. Weitere fünf Minuten Normalbetrieb und Loggerverkehr beobachten.
17. Testartefakte und Hashes dokumentieren.

## Harte Stopbedingungen der damaligen Teststufe

Kein automatisches Aufräumen, sondern `guarded-hold`, wenn:

- irgendeine Vorbedingung wechselt;
- C350/C357/SSID/MD5/Größe nicht exakt passen;
- C36E Status 1 oder 2 fehlt beziehungsweise abweicht;
- der C5A8-Einstieg nicht sicher abgefangen wird;
- der Logger irgendein C5A8 sieht;
- C36C Status 1 ausbleibt;
- LTE-intern Step 12 nicht erreicht wird;
- Logger ausfällt oder seine Datei nicht weiter wächst;
- die Wärmepumpe auffälliges Verhalten zeigt.

Bei `guarded-hold` blieben Cloud gesperrt, Watchdogs pausiert und der
Originaldienst angehalten, bis der Zustand eindeutig ausgelesen wurde.

## Damals noch ausstehender Arming-Schritt

Zum damaligen Stand sollten unmittelbar vor dem Realtest:

1. die ausgefüllte Loggercheckliste geprüft;
2. der endgültige Live-Hook nochmals gegen den Originaldienst-Hash und alle Breakpoint-Opcodes geprüft;
3. der Hook auf das LTE-Modem übertragen;
4. ein reiner Breakpoint-Installations-/Entfernungstest ausgeführt;
5. erst nach einer neuen Bedienerfreigabe der einmalige Sendebefehl freigegeben werden.

Diese Stufe wurde später durch weitere Tests und schließlich den vollständigen V3.3→V3.4-Live-Lauf überholt.

## Zugehörige Dateien

- [`PHNIX_PRE_C5A8_VM_UND_REALTEST.md`](PHNIX_PRE_C5A8_VM_UND_REALTEST.md)
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md)
- [`firmware_backup_lte.md`](firmware_backup_lte.md)
- [`../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](../reverse_engineering/PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md)
- [`../reverse_engineering/PHNIX_CANCEL_PROBE_LIVE_RESULT.md`](../reverse_engineering/PHNIX_CANCEL_PROBE_LIVE_RESULT.md)
- [`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)