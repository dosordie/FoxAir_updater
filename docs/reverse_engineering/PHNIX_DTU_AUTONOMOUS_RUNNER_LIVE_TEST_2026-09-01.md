# Minimaler autonomer DTU-Runner – Live-Test

Stand: 2026-09-01

## Zweck und Abgrenzung

Dieser Test belegt, dass ein kleiner Shell-Runner auf dem PHNIX-LTE-Modem nach
dem Ende der startenden ADB-Shell selbstständig weiterlaufen kann. Der Runner
führt ausschließlich einen zeitgesteuerten Status-Test aus. Er enthält
insbesondere:

- keine OTA-Funktion;
- keine Firmwaredatei und keinen Firmwarezugriff;
- keine Hooks oder Debugger-Funktion;
- keinen Eingriff in den Originaldienst `phnixIot4G`.

Die Testwerkzeuge liegen unter
[`../../devtools/dtu_autonomous_runner/`](../../devtools/dtu_autonomous_runner/):

- `dtu_autonomous_test_runner.sh` läuft auf dem Modem;
- `Start-DtuAutonomousTest.ps1` bereitet den Test von Windows aus vor, startet
  den Runner und überwacht danach ausschließlich dessen `status.json`.

## Testumgebung

Der Live-Test wurde auf folgender Plattform durchgeführt:

```text
Kernel-/Buildkennung: mdm9607-perf
Architektur:          ARMv7
Shell-Werkzeuge:      BusyBox 1.23.1 / Android /system/bin/sh
Testverzeichnis:      /data/foxair_autonomous_test
ADB-Server:           tcp:192.168.10.50:5038
```

Der PowerShell-Starter verwendet standardmäßig ADB aus
`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`. Beide Vorgaben lassen sich
bei Bedarf über `-AdbPath` und `-AdbServerSocket` überschreiben.

## Statusvertrag

Der Modem-Runner legt das Testverzeichnis an, schreibt seine PID nach
`runner.pid` und ersetzt `status.json` immer atomar über eine temporäre Datei.
Der Status hat ausschließlich diese Felder:

```json
{"state":"running","step":3,"pid":1234,"time":1788282000}
```

`time` ist die Unix-Zeit in Sekunden. Der Lauf startet mit Schritt 0,
aktualisiert anschließend 24-mal im Abstand von fünf Sekunden den Schritt und
endet mit `state=completed` und `step=24`. Ein `TERM`, `HUP` oder `INT` setzt
zuvor `state=interrupted` und `step=-1`. `runner.log` bleibt bewusst klein und
enthält nur Start, Schritte und Abschluss beziehungsweise Unterbrechung.

## Entscheidender Startmechanismus

Ein direkter Skriptstart und ein einfaches `nohup` überlebten das Ende der
ADB-Shell auf diesem Modem nicht zuverlässig. Erfolgreich war der explizit von
der Sitzung getrennte Start mit `setsid`, geschlossenen Standardeingaben und in
das Testverzeichnis umgeleiteten Ausgaben:

```sh
setsid /system/bin/sh '/data/foxair_autonomous_test/dtu_autonomous_test_runner.sh' </dev/null >'/data/foxair_autonomous_test/launcher.log' 2>&1 & sleep 2
```

Nach diesen zwei Sekunden prüft der Windows-Starter unmittelbar, ob bereits
ein gültiger Initialstatus existiert. Danach liest er im Abstand von fünf
Sekunden nur noch `status.json` per ADB. Er kontrolliert oder beendet den
Modemprozess nicht.

## Live-Nachweis der Unabhängigkeit

Im erfolgreichen Test wurde der Runner nach dem Start als Prozess mit PPID 1
beobachtet. Unabhängige, später geöffnete ADB-Shells lieferten dieselbe PID und
steigende Schritte aus derselben `status.json`.

Zusätzlich wurde die Windows-Überwachung abgebrochen, ohne den Modemprozess zu
beenden. Eine spätere neue ADB-Abfrage zeigte weiterhin dieselbe PID und einen
weiter fortgeschrittenen Schritt. Damit hing der Testlauf nach dem Start nicht
mehr von der Lebensdauer des Windows-Starters oder seiner ADB-Shell ab.

Eine reine spätere Statusabfrage ist beispielsweise:

```powershell
$env:ADB_SERVER_SOCKET = "tcp:192.168.10.50:5038"
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell "cat '/data/foxair_autonomous_test/status.json'"
```

## Ausführung

Aus PowerShell im Werkzeugverzeichnis:

```powershell
.\Start-DtuAutonomousTest.ps1
```

Der Starter prüft vor dem Aufräumen alter Teststatusdateien, ob die in
`runner.pid` genannte PID noch zu genau diesem Runner gehört. In diesem Fall
verweigert er einen zweiten parallelen Start.

Ein Abbruch der lokalen Überwachung, etwa mit `Strg+C`, ist kein Auftrag zum
Beenden des autonomen Prozesses. Der Runner läuft auf dem Modem weiter und kann
später über `status.json` erneut beobachtet werden.

## Vorsichtiger Cleanup

Vor dem Entfernen des Testverzeichnisses zuerst den terminalen Status prüfen:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell "cat '/data/foxair_autonomous_test/status.json'; cat '/data/foxair_autonomous_test/runner.pid'"
```

Nur wenn `state` bereits `completed` oder `interrupted` ist, das exakt benannte
Testverzeichnis entfernen:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell 'TEST_DIR=/data/foxair_autonomous_test; [ "$TEST_DIR" = /data/foxair_autonomous_test ] && rm -rf "$TEST_DIR"'
```

Falls der Status noch `running` ist, nicht blind eine möglicherweise
wiederverwendete PID beenden. Zuerst `/proc/<PID>/cmdline` prüfen und nur den
eindeutig als diesen Test-Runner identifizierten Prozess gezielt mit `TERM`
beenden. Danach `state=interrupted` abwarten und erst dann aufräumen.

Der dokumentierte Live-Test wurde bereits sauber beendet. Das Verzeichnis
`/data/foxair_autonomous_test` wurde vom Modem entfernt; Originaldienst und
Firmware blieben unverändert.
