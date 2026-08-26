# PHNIX-Traffic-Tracer: Live-Erkenntnisse vom 26.08.2026

## Status

Der GDB-basierte Traffic-Tracer ist ein **experimenteller Forschungsstand**. Er ist noch nicht für den regulären Endnutzerbetrieb freigegeben. Der Trace verändert die Programmdatei nicht und erzeugt keine eigenen MQTT-, HTTP- oder RS485-Nachrichten. Das Anhalten einzelner Threads durch Software-Breakpoints kann den laufenden Originaldienst jedoch beeinflussen.

## Live bestätigt

- Die geprüfte `phnixIot4G`-Build-ID und die hinterlegten Hook-Adressen passen zum untersuchten LTE-Modem.
- Ein einzelner Hook `mqtt_tx_update` wurde live getroffen. Das Ereignis enthielt eine Nutzdatenlänge von 189 Byte und einen gültigen Prozesszeiger.
- Ereignisse werden mit echten Zeilenumbrüchen in die Rohdatei geschrieben und können fortlaufend abgeholt werden.
- Pro Lauf ist nur ein ausgewählter Hook aktiv. Das begrenzt Breakpoint-Dichte und Eingriffsdauer.
- Ein Host-seitig gehaltener ADB-Prozess überwacht den Lauf. Bei Verbindungsabbruch oder nach Ablauf der Maximaldauer beendet der Helfer den Trace.
- Während des Trace werden die beiden Original-Watchdogs kontrolliert angehalten. Vor ihrer Freigabe prüft der Helfer direkt über `/proc`, dass kein Tracer mehr am Originaldienst hängt.
- Stop ist wiederholbar; veraltete Marker werden erkannt und bereinigt.

Beobachtetes Live-Ereignis:

```text
FOX|hook_hit|mqtt_tx_update|len=189|ptr=0x920dc
```

## Offener sicherheitsrelevanter Punkt

Obwohl der Kernel nach dem Beenden `TracerPid: 0`, einen lebenden Prozess und keinen aktiven Debugger meldete, wurde `phnixIot4G` bei Live-Tests etwa 30 bis 50 Sekunden später neu gestartet. Der unmittelbare Detach ist damit technisch bestätigt, die zeitverzögerte interne Folge des Ptrace-Eingriffs aber noch nicht beherrscht.

Der Trace darf deshalb derzeit nicht parallel zu einem Firmwareupdate oder einem anderen kritischen Vorgang eingesetzt werden. Nach jedem Versuch müssen Dienst-PID, Cloudverbindung und Watchdogs über einen ausreichend langen Beobachtungszeitraum geprüft werden.

## Verworfen: GDB Non-Stop Mode

Der vorhandene `gdbserver` 7.8.1 unterstützt den getesteten Non-Stop-Ablauf nicht zuverlässig und brach mit einer internen Assertion ab:

```text
queue_stop_reply_callback: Assertion 'thread->last_status.kind != TARGET_WAITKIND_IGNORE' failed
```

Diese Variante ist daher kein sicherer Lösungsweg für das Zielgerät.

## Empfehlung für die weitere Entwicklung

Für eine dauerhaft nebenwirkungsarme Diagnose sollte der Netzwerkverkehr möglichst außerhalb von `phnixIot4G` erfasst werden, beispielsweise über eine native ARM-Paketaufzeichnung am Mobilfunkinterface. Der GDB-Tracer bleibt nützlich, um einzelne interne Aufrufstellen zu bestätigen, sollte aber bis zur Klärung des verzögerten Neustarts nur kurzzeitig und beaufsichtigt verwendet werden.
