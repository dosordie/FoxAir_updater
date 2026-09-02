# PHNIX DTU OTA-Runner – Stage 1

Stand: 1. September 2026

## Zielbild

Der Windows-Updater soll den eigentlichen OTA-Vorgang künftig nicht mehr über eine dauerhaft benötigte ADB-Verbindung orchestrieren. Stattdessen wird pro Firmwareupdate ein eigenständiger, temporärer Supervisor auf dem LTE-Modem gestartet.

```text
Windows / ADB
    |
    +-- Vorprüfung / Paket vorbereiten
    +-- Runner + Firmware + Auftrag kopieren
    +-- Runner detached starten
    +-- danach nur Status / Log lesen
    +-- optional kontrollierten Abort anfordern
    +-- terminales Ergebnis bestätigen
    +-- Cleanup anfordern
                         |
                         v
                  LTE OTA-Runner
                    +-- Auftrag prüfen
                    +-- Zustand sichern
                    +-- Hook vorbereiten
                    +-- OTA auslösen
                    +-- Fortschritt überwachen
                    +-- Erfolg/Fehler verifizieren
                    +-- Recovery ausführen
                    +-- terminales Ergebnis dauerhaft ablegen
```

ADB ist nach dem Start nur noch Transport- und Beobachtungskanal. Ein ADB-Abbruch darf den Runner nicht beenden.

## Warum kein permanenter Dienst

Geplant ist ausdrücklich kein dauerhaft installierter FoxAir-Hintergrunddienst. Pro Update entsteht ein eigener Run mit eigener Run-ID. Der Supervisor wird mit `setsid` von der ADB-Sitzung getrennt gestartet und beendet sich nach einem terminalen Ergebnis selbst.

Der bereits durchgeführte Live-Test hat gezeigt, dass dieser Startmechanismus auf dem untersuchten Modem funktioniert. Ein einfaches `nohup` war dagegen nicht zuverlässig.

## Verzeichnislayout

Stage 1 verwendet bereits das geplante Grundlayout:

```text
/data/foxair_ota_runner/
    last_run_id
    active.lock/
        run_id
        pid
    runs/
        <run_id>/
            dtu_ota_supervisor_stage1.sh
            runner.pid
            status.json
            runner.log
            launcher.log
            abort.request        optional
            acknowledged        optional
```

Später kommen pro Run insbesondere Auftrag, Firmware, Runtime-Hook und Sicherungen hinzu.

## Single-Run-Schutz

Es darf niemals stillschweigend ein zweiter OTA-Runner parallel gestartet werden. Stage 1 verwendet deshalb `mkdir /data/foxair_ota_runner/active.lock` als atomaren Lock.

Ist der Lock bereits vorhanden, schlägt ein neuer Lauf terminal fehl. Ein vermeintlich verwaister Lock wird bewusst nicht automatisch gelöscht. Zuerst müssen PID, Run-ID und letzter Status geprüft werden.

## Statusvertrag

`status.json` liegt im jeweiligen Run-Verzeichnis und wird atomar über eine temporäre Datei plus `mv` ersetzt.

Beispiel:

```json
{
  "schema": "foxair-dtu-runner-v1",
  "run_id": "20260901-203000-1234",
  "state": "running",
  "phase": "autonomous-selftest",
  "terminal": false,
  "progress": 37,
  "pid": 1234,
  "ppid": 1,
  "time": 1788294600,
  "reason": "",
  "detail": "Stage-1 autonomous lifecycle self-test is running."
}
```

Geplante Zustände:

- `starting`
- `running`
- `completed`
- `failed`
- `aborted`

Ein terminaler Status wird nach Prozessende nicht gelöscht.

## Ergebnisaufbewahrung und Cleanup

Der Runner trennt terminalen Abschluss und Bereinigung absichtlich:

1. Runner schreibt einen terminalen Status und beendet sich.
2. Windows oder ein späterer ADB-Zugriff liest den Status.
3. `Ack` legt erst danach `acknowledged` an.
4. `Cleanup` ist nur erlaubt, wenn der Status terminal und bestätigt ist und der Runner nicht mehr läuft.

Damit bleiben Fehlerdiagnose und letzter Status auch dann erhalten, wenn ADB oder Windows unmittelbar nach dem Update ausfallen.

Eine automatische Altersbereinigung ist für Stage 1 absichtlich noch nicht implementiert. Für die spätere Produktionsversion ist eine konservative Garbage-Collection alter, terminaler Runs vorgesehen, ohne den letzten unbestätigten Abschlussbericht vorzeitig zu entfernen.

## Kontrollierter Abort

Stage 1 modelliert einen Abort als Datei `abort.request`. Windows beendet den Prozess nicht mit einem blinden `kill`.

Für den späteren echten OTA-Runner wird diese Regel sicherheitskritisch:

- vor der irreversiblen OTA-Grenze kann ein Abort gegebenenfalls kontrolliert ausgeführt werden;
- nach begonnenem C5A8 darf ein Abort-Request den autoritativen PHNIX-Originaldienst nicht stoppen;
- der Runner muss dann den Abort ablehnen und den laufenden Mainboardprozess weiter überwachen.

Die vorhandenen Sicherheitsregeln aus `phnix_ota_runtime_hook` bleiben maßgeblich.

## Stage 1: bewusst noch kein OTA

Die erste Umsetzung testet nur den Supervisor-Lebenszyklus. Sie greift nicht auf Firmware, `phnixIot4G`, GDB, Watchdogs oder OTA-Dateien zu.

Dateien:

```text
devtools/dtu_autonomous_runner/dtu_ota_supervisor_stage1.sh
devtools/dtu_autonomous_runner/Invoke-DtuOtaSupervisorStage1.ps1
```

Start:

```powershell
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Start
```

Detached starten und Windows-Monitoring sofort beenden:

```powershell
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Start -NoMonitor
```

Späteren Status lesen:

```powershell
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Status
```

Kontrollierten Test-Abort anfordern:

```powershell
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Abort
```

Terminales Ergebnis bestätigen und danach löschen:

```powershell
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Ack
.\Invoke-DtuOtaSupervisorStage1.ps1 -Action Cleanup
```

## Nächste Stufe nach erfolgreichem Live-Test

Wenn Stage 1 auf dem realen LTE-Modem einschließlich ADB-Abbruch, erneutem Statuslesen, Abort, Ack und Cleanup stabil funktioniert, soll Stage 2 den vorhandenen `phnix_ota_runtime_hook` als Kindprozess des Supervisors starten.

Dabei wird zunächst noch möglichst wenig Logik neu geschrieben:

1. Windows führt weiterhin die Host-seitige Firmware-/Manifestprüfung aus.
2. Windows kopiert ein bereits geprüftes Paket in das Run-Verzeichnis.
3. Der DTU-Runner prüft Größe und Hashes erneut lokal.
4. Der DTU-Runner startet den vorhandenen Runtime-Hook selbstständig.
5. Der Hook schreibt seinen technischen Status in das Run-Verzeichnis unter `/data` statt nur nach `/tmp`.
6. Der Supervisor übersetzt Hook-/OTA-Zustände in seinen dauerhaften Run-Status.
7. Windows pollt nur noch diesen Status.

Erst nachdem dieser Weg im Simulator und auf realer Hardware bestätigt ist, sollte die bisherige Windows-Orchestrierung entfernt oder stark vereinfacht werden.
