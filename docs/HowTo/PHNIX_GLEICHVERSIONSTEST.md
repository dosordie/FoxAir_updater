# PHNIX-Gleichversionstest mit V3.3

Stand: 29. August 2026

> [!NOTE]
> Der Gleichversionstest ist heute ein **Entwicklungs-/Abnahmewerkzeug**. Er ist nicht mehr Bestandteil der normalen Windows-Endanwender-GUI.
>
> Der Pfad wurde auf realer Hardware bestätigt. Zusätzlich wurde inzwischen auch ein vollständiger Versionswechsel **V3.3 → V3.4** erfolgreich durchgeführt. Der Gleichversionstest ist deshalb nicht mehr die höchste erreichte Live-Teststufe, bleibt aber für Regressionen des frühen Handshakes nützlich.

Dieser Test bietet dem Mainboard über den originalen `phnixIot4G`-Dienst die bereits installierte Firmware V3.3 mit der internen Kennung `0033` an. Er darf keine Firmwaredaten übertragen.

Der erwartete Busablauf ist:

```text
C350 (82400644 / 0033)
→ C350 Schreib-ACK
→ C36E Status 0
→ Ende
```

`C36E Status 0` bedeutet in dieser Phase: Ziel/Build wird nicht als neues Update angenommen. Bei der bekannten Anlage ist der identische Build der erwartete Grund.

Der Test beweist keine Neuinstallation von V3.3 und löst keine C5A8-Datenphase aus.

## Live-Bestätigung

Der V3.3→V3.3-Pfad wurde real ausgeführt. Dabei bestätigte der Ablauf:

```text
same-version
c357_sent = false
c5a8_sent = false
```

Das Mainboard erkannte die bereits installierte Firmware und beendete den Vorgang vor der Firmwaredatenphase.

Dieser Test war außerdem hilfreich, um einen früheren rein hostseitigen Windows-State-Pfadfehler aufzudecken. Dieser lag **nach** dem bereits sauber terminal beendeten Mainboardablauf und änderte nichts am tatsächlichen C350-/C36E-Verhalten.

## Eingebaute Sicherungen

Vor dem Angebot prüft der Launcher bzw. Controller unter anderem:

- Firmwaregröße und MD5;
- Originaldienst und Build-Hash;
- OTA-Zustand;
- Supervisoren/Watchdogs;
- erwartete Zielidentität.

`OTA_INFO` und Statistikdatei werden für den Test gesichert.

Der Test überwacht insbesondere, dass weder C357 noch C5A8 erreicht werden.

Diese Abweichungen führen in einen Schutz-Halt:

- `C36E` meldet nicht Status 0;
- `C357` wird erreicht;
- `C5A8` wird erreicht;
- die Gerätekennung passt nicht;
- eine Zustandsdatei ist nicht korrekt wiederhergestellt;
- ein Zeitlimit läuft ab.

## VM-/Simulatorlauf

Beispiel:

```bash
python3 phnix_local_ota_controller.py \
  --adb ./phnix-sim-adb \
  same-version-test \
  --manifest firmware_manifests/FW3.3.json \
  --firmware phnixIot_device_OTA.bin \
  --execute \
  --confirm VM-SAME-VERSION-ONLY \
  --state-dir same-version-state
```

Ein erfolgreicher Abschluss enthält sinngemäß:

```text
"event": "same-version-complete"
"c36e_status": 0
"c357_frames": 0
"c5a8_frames": 0
"persistent_state_restored": true
```

## Live-Test vom Raspberry Pi / Backend aus

Der Livepfad verwendet den originalen `phnixIot4G`-Dienst und die bekannte Parser-/Yield-Injection des Controllers.

Beispiel:

```bash
python3 phnix_local_ota_controller.py \
  --adb adb \
  same-version-test \
  --manifest FW3.3.json \
  --firmware phnixIot_device_OTA.bin \
  --execute \
  --confirm PHNIX-C350-SAME-V33 \
  --logger-confirm PASSIVE-LOGGER-RUNNING \
  --state-dir phnix-ota-state
```

Der passive Buslogger muss für diesen speziellen Labortest tatsächlich laufen.

Wichtige Ereignisse sind unter anderem:

```text
preflight
state-backed-up
firmware-staged
same-version-status
same-version-complete
original-state-released
```

## Windows

Frühere Windows-Versionen stellten den Gleichversionstest zeitweise separat unter **Erweitert** bereit.

Im aktuellen Endanwenderstand v0.3.9 ist dieser separate Test **nicht mehr in der normalen GUI sichtbar**. Der normale Firmware-Update-Pfad selbst wurde jedoch real mit V3.3→V3.3 bis zur Gleichversionsablehnung geprüft.

Für weitere Regressionstests bleibt die Backend-/Labfunktion erhalten. Endanwender sollen für normale Updates den regulären Firmware-Update-Dialog verwenden und nicht den Labortest nachbauen.

## Verhältnis zum echten Versionswechsel

Der Gleichversionstest validiert:

- frühen C350-Handshake;
- Erkennung einer bereits installierten Version;
- sicheren Abschluss ohne C357/C5A8;
- Restore-/Cleanup-Verhalten dieses speziellen Testpfads.

Er validiert nicht selbst:

- C5A8-Datenübertragung;
- Staging-MD5;
- Mainboard-Promotion;
- Status 5;
- Boot einer neuen Firmware.

Diese späteren Schritte wurden inzwischen separat durch den realen **V3.3→V3.4-Live-Lauf** bestätigt:

[`../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](../reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)

## Bei `guarded-hold`

Bei einem `guarded-hold` nicht selbst Prozesse fortsetzen, Schutzregeln entfernen oder einen neuen Updateauftrag starten. Zuerst Status, Zustandsdateien und Loggerdaten auswerten und danach den vorgesehenen Recoverypfad verwenden.