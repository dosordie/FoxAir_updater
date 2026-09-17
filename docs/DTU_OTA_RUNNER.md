# DTU OTA Runner – aktueller Architektur- und Sicherheitsstand

Stand: 17. September 2026

Der Umbau auf den autonomen DTU-Runner ist abgeschlossen. Diese Datei ersetzt die frühere Entwicklungs-Roadmap unter `docs/dev/DTU_OTA_RUNNER_ROADMAP.md` und beschreibt nur noch den produktiven Stand sowie die dauerhaft relevanten Sicherheitsgrenzen.

## Architektur

Der Mainboard-OTA wird nach dem Start vollständig auf dem PHNIX-LTE-Modem ausgeführt:

```text
Windows-GUI / Host-CLI
        │
        ├─ prepare / start
        ├─ status / log
        ├─ abort-request
        ├─ ack / cleanup
        │
        ▼
/data/foxair_ota_runner/
        │
        ▼
DTU OTA Supervisor
        │
        ├─ Paket, Firmware, Hook und Originaldienst prüfen
        ├─ exklusiven Run-Lock verwalten
        ├─ persistenten Status führen
        ├─ Runtime-Hook starten und überwachen
        └─ terminales Ergebnis / Recovery klassifizieren
        │
        ▼
phnix_ota_runtime_hook
        │
        └─ C350 / C36E / C357 / C5A8 / Abschlusssequenz
```

Ein gestarteter OTA hängt nicht von einer dauerhaft bestehenden Windows-, USB-, ADB- oder Remote-ADB-Verbindung ab. Die GUI ist nur Client des persistenten Runner-Zustands und enthält keine eigene C350/C36E/C357/C5A8- oder Recoverylogik.

## Persistenter und flüchtiger Zustand

Persistente Runner-Daten liegen unter:

```text
/data/foxair_ota_runner/
```

Dort werden unter anderem Run-ID, Paketidentität, `status.json`, Logs, Fortschritt, `boot_id`, Lock- und Lifecycle-Daten gehalten.

Flüchtiger Runtime-Hook-Zustand liegt unter:

```text
/tmp/phnix_ota_hook
```

Dazu gehören GDB-/GDBServer-PIDs, Watchdog-PIDs und temporäre Transfer-/Authority-Marker. Das Design setzt ausdrücklich nicht voraus, dass `/tmp` einen Reboot überlebt.

## Readiness vor dem Hook

Vor Start des Runtime-Hooks muss genau eine stabile und ungetracete `phnixIot4G`-Instanz vorhanden sein. Der Supervisor prüft den lokalen Laufzeitstatus direkt über `/proc/<pid>/mem` und verlangt zweimal hintereinander:

- `dtu_run_step == 11` (`0x98903`)
- `dtu_sta == 4` (`0x98904`)
- `board_ota_step == 12` (`0x98A94`)
- UART-Sendeflag `== 0` (`0x930DC`)

Die Prüfung wartet maximal 120 Sekunden und schlägt bei PID-Wechsel, Tracing, nicht lesbarem Zustand oder Timeout fail-closed fehl. Eine aktive MQTT-Verbindung ist keine Voraussetzung für diesen lokalen Readiness-Gate.

## Sicherheitsinvarianten

1. Maximal ein aktiver OTA-Run pro DTU.
2. Host-/ADB-Verlust beendet einen gestarteten OTA nicht.
3. Nach validiertem Autoritätsübergang bleibt `phnixIot4G` autoritativ.
4. Nach Beginn der Firmwareübertragung ist kein generischer Restore zulässig.
5. 100 % C5A8 ist noch kein terminaler Erfolg.
6. Erfolg wird erst nach der validierten Mainboard-Abschlusssequenz mit finalem Board-Step 12 gesetzt.
7. PID-Werte allein rechtfertigen niemals Kill oder Cleanup; Prozessidentität wird geprüft.
8. Statusdateien werden atomar aktualisiert.
9. Unklare Zustände werden fail-closed behandelt.
10. `abort-request` darf nach dem Point-of-no-return keinen unsicheren Abbruch erzwingen.
11. Ein Dry-Run startet weder GDB-Attach noch C350.
12. Der Supervisor verwendet keinen Busy-Loop; normales Polling bleibt leichtgewichtig.

## Terminalstatus und Hook-Ende

Der Runtime-Hook schreibt seinen Terminalstatus persistent. Da der Hook unmittelbar nach dem Schreiben enden kann, liest der Supervisor den Terminalstatus nach dem Child-Ende nochmals frisch ein. Dadurch wird ein bereits gespeicherter Erfolg nicht fälschlich als `hook_monitor_lost` / `original-service-active-unmonitored` klassifiziert.

Am eigentlichen Mainboard-Protokoll C350/C36E/C357/C5A8 wurde dafür nichts geändert.

## Verwaiste Runs und Cleanup

Ein nichtterminaler `active.lock` bedeutet nicht automatisch, dass noch ein OTA läuft. Der Lock kann nach einem abgestürzten oder verlorenen Supervisor zurückbleiben – mit oder ohne DTU-Reboot.

Ein Bootwechsel ist deshalb nur noch ein zusätzlicher Hinweis auf einen verwaisten Lauf, aber keine Voraussetzung für Cleanup. Entscheidend sind die aktuellen Live-Prüfungen:

- kein OTA-Supervisor, Runtime-Hook, GDB oder GDBServer läuft;
- keine aktiven Transfer-/Injection-/Authority-Marker vorhanden;
- `OTA_INFO` ist gültig und zeigt keinen plausibel unvollständigen Board-Transfer.

Für die beiden Board-Transferzähler in `OTA_INFO` gilt beim Cleanup:

- `offset=0`, `length=0`: normaler Ruhezustand;
- `0 <= offset < length`: fortsetzbarer/unvollständiger Transfer, Cleanup bleibt gesperrt;
- `offset == length > 0`: vollständig übertragener historischer Zustand, blockiert den Cleanup nicht;
- inkonsistente Werte bleiben fail-closed gesperrt.

Damit können verwaiste nichtterminale Runner-Daten auch im selben DTU-Boot entfernt werden, wenn keine Live-Komponente mehr aktiv ist und kein unvollständiger Transfer erkennbar ist. Ein tatsächlich laufender Helper oder ein partieller Resume-Zustand blockiert weiterhin.

## Cleanup und Diagnose-Retention

Erfolgreiche bzw. Same-Version-Läufe werden lokal diagnostisch archiviert und können danach vom LTE-Modem entfernt werden. Fehler- und `recovery-required`-Zustände behalten ihre Diagnosedaten standardmäßig.

Die Option **„Danach alle FoxAir-Updater-Dateien vom LTE-Modem entfernen“** entfernt nur bekannte FoxAir-Updater-Arbeitsdaten und Runner-Verzeichnisse. Nicht gelöscht werden insbesondere:

- `/data/phnixIot4G`
- `/cache/phnixIot_device_OTA`
- `/data/phnixIot_device_OTA_INFO`
- `/data/phnixIot_device_statisic`

Das Diagnosepaket nimmt die originale 220-Byte-Datei `/data/phnixIot_device_OTA_INFO` standardmäßig unverändert mit auf und legt zusätzlich eine kleine JSON-Auswertung der Board-Transferzähler ab. Firmware und Statistik-Binärdaten bleiben ausgeschlossen.

Nach bereits erfolgtem Auto-Cleanup behandelt **„Update-Status lesen“** einen fehlenden `last_run_id` als normalen Zustand und nicht als Firmwareupdate-Fehler.

## Verifizierter Stand

Der autonome Runner wurde auf realer FoxAir-/PHNIX-Hardware mit vollständigen Mainboard-Firmwarewechseln eingesetzt. Erfolgreich dokumentiert sind unter anderem V3.3 → V3.4 und V1.2 → V3.4.

Zusätzlich wurden im Simulator und auf realer DTU unter anderem verifiziert:

- detached Start des Supervisors;
- Wiederanbindung nach ADB-Verlust;
- Same-Version-Pfad;
- vollständige C350/C36E/C357/C5A8-Sequenz;
- 100 % Transfer ohne vorzeitigen Terminalstatus;
- finale Erfolgsklassifizierung erst nach Mainboard-Abschluss;
- kontrollierter Service-Neustart;
- Reboot-/orphaned-run-Klassifizierung;
- stale Lock / fremde PID ohne falschen Kill;
- Cleanup mit Ack und Diagnose-Retention.

## Produktiver Code

Der produktive Backendpfad liegt unter:

```text
updater/dtu_ota/
```

Die Windows-Oberfläche verwendet diesen Backendvertrag. Test-, QEMU- und Simulatorpfade bleiben davon getrennt.

Die frühere Stage-basierte Entwicklungsroadmap ist damit abgeschlossen und wird nicht weitergeführt. Neue konkrete Fehler oder Erweiterungen sollen direkt als Issue/PR und in der jeweils betroffenen permanenten Dokumentation beschrieben werden.
