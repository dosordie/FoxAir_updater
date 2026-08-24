# PHNIX-Gleichversionstest mit V3.3

> [!NOTE]
> Die Windows-GUI bietet den Gleichversionstest inzwischen unter **Erweitert** an und verwendet dafür weiterhin den gemeinsamen Controller. Öffentliche Windows-Versionen stehen unter [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases).
>
> Der Gleichversionstest wurde auf realer Hardware bereits im Linux-/Raspberry-Pi-Pfad bestätigt. **Unter Windows wurde dieser Test noch nicht live ausgeführt**. Dort sind bislang ADB-Verbindung, Originalstatus und Backup real bestätigt. Ein echtes Versionsupdate ist ebenfalls weiterhin ungetestet.

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
  --manifest firmware_manifests/FW3.3.json \
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

## Live-Test vom Raspberry Pi aus

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
  --manifest FW3.3.json \
  --firmware phnixIot_device_OTA.bin \
  --execute \
  --confirm PHNIX-C350-SAME-V33 \
  --logger-confirm PASSIVE-LOGGER-RUNNING \
  --state-dir phnix-ota-state
```

Die Ausgabe besteht aus JSON-Zeilen. Diese Ereignisse werden inzwischen sowohl
vom Linux-Weg als auch von der Windows-GUI verwendet. Wichtige Ereignisse sind
`preflight`, `state-backed-up`, `firmware-staged`, `same-version-status`,
`same-version-complete` und `original-state-released`.

## Windows-GUI

In der Windows-Version befindet sich der Test unter **Erweitert**. Benötigt werden:

- passendes V3.3-Manifest und die dazugehörige Firmwaredatei;
- funktionierende lokale oder Remote-ADB-Verbindung;
- ein tatsächlich laufender passiver RS485-Logger;
- aktivierte Bestätigung **Passiver RS485-Logger läuft tatsächlich**.

Die GUI verwendet dieselben Bestätigungswerte wie der bekannte Live-Test. Seit v0.1.4 sichert die Windows-Sicherheitshülle zusätzlich den ursprünglichen LTE-Firmware-Cache und stellt ihn nach einem erfolgreichen Gleichversionstest wieder her, analog zum Linux-Launcher.

> [!WARNING]
> Diese Windows-Ausführung ist noch **nicht live bestätigt**. Für den nächsten realen Windows-Test sollte weiterhin V3.3 → V3.3 verwendet werden, bevor irgendein echter Versionswechsel in Betracht gezogen wird.

Bei `guarded-hold` darf der Anwender nicht selbst Prozesse fortsetzen oder
Schutzregeln entfernen. Zuerst werden Status, Zustandsdateien und Loggerdaten
ausgewertet. Der Launcher beziehungsweise die Windows-Sicherheitshülle lässt den
Originaldienst in diesem Fall absichtlich nicht unkontrolliert weiterlaufen.
