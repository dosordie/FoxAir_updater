# PHNIX-Gleichversionstest mit V3.3

Dieser Test bietet dem Mainboard über den originalen `phnixIot4G`-Dienst die
bereits installierte Firmware V3.3 mit der internen Kennung `0033` an. Er darf
keine Firmwaredaten übertragen.

Der erwartete Busablauf ist:

```text
C350 (82400644 / 0033)
→ C350 Schreib-ACK
→ C36E Status 0
→ Ende
```

`C36E Status 0` bedeutet in dieser Phase: Ziel/Build wird nicht als neues
Update angenommen. Bei der bekannten Anlage ist der identische Build der
erwartete Grund. Der Test beweist keine Installation und löst keine erneute
Installation von V3.3 aus.

## Eingebaute Sicherungen

Vor dem Angebot prüft der Launcher Firmwaregröße und MD5, Originaldienst,
Build-Hash, OTA-Zustand und Supervisoren. `OTA_INFO` und Statistikdatei werden
zweifach gesichert: auf dem ausführenden Rechner und im LTE-Modem.

Während des Tests sind Cloudzugang und Supervisoren kontrolliert gesperrt.
Der Originaldienst wird an `C357` und `C5A8` überwacht. Nur die vollständige
Kette `C350 → C36E/0`, gefolgt von einer bytegleichen Wiederherstellung beider
Dateien, gibt den Dienst wieder frei.

Diese Abweichungen führen in einen Schutz-Halt:

- `C36E` meldet nicht Status 0;
- `C357` wird erreicht;
- `C5A8` wird erreicht;
- die Gerätekennung passt nicht;
- eine Zustandsdatei ist nicht bytegleich wiederhergestellt;
- ein Zeitlimit läuft ab.

## Zuerst auf der VM

```bash
cd /home/lte/phnix-ota-lab
./phnix-ota-sim start --scenario success
python3 phnix_local_ota_controller.py \
  --adb ./phnix-sim-adb \
  same-version-test \
  --firmware phnixIot_device_OTA.bin \
  --execute \
  --confirm VM-SAME-VERSION-ONLY \
  --state-dir same-version-state
```

Der erfolgreiche Abschluss enthält:

```text
"event": "same-version-complete"
"c36e_status": 0
"c357_frames": 0
"c5a8_frames": 0
"persistent_state_restored": true
```

## Später vom Raspberry Pi aus

Der Liveaufruf verwendet den regelmäßig ausgeführten MQTT-Yield-Loop bei
`0x1FE40` als Parser-Trampolin. Dieser Punkt wird unabhängig von einer neu
eintreffenden Cloudnachricht erreicht. Die Cloud wird vor dem Einsprung
gesperrt; am Haltepunkt werden UART-Leerlauf und Board-Schritt 12 erneut
geprüft. Das GDB-Skript arbeitet linear und wartet nacheinander auf Yield-Loop,
C350 und C36E. Es setzt keine im Hintergrund weiterlaufenden Breakpoint-Befehle
ein.
Der passive Logger muss bereits laufen.

```bash
python3 phnix_local_ota_controller.py \
  --adb adb \
  same-version-test \
  --firmware phnixIot_device_OTA.bin \
  --execute \
  --confirm PHNIX-C350-SAME-V33 \
  --logger-confirm PASSIVE-LOGGER-RUNNING \
  --state-dir phnix-ota-state
```

Die Ausgabe besteht aus JSON-Zeilen, damit sie gleichzeitig für Menschen und
eine spätere Windows-Oberfläche nutzbar ist. Wichtige Ereignisse sind
`preflight`, `state-backed-up`, `firmware-staged`, `same-version-status`,
`same-version-complete` und `original-state-released`.

Bei `guarded-hold` darf der Anwender nicht selbst Prozesse fortsetzen oder
Schutzregeln entfernen. Zuerst werden Status, Zustandsdateien und Loggerdaten
ausgewertet. Der Launcher lässt den Originaldienst in diesem Fall absichtlich
nicht unkontrolliert weiterlaufen.
