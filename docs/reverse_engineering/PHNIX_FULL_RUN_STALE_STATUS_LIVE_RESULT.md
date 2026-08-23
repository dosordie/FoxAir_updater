# Vollupdate-Start: veralteter Statusdatensatz

Stand: 2026-08-23

## Beobachtung am realen LTE-Modem

Ein mit V3.3 gestarteter Vollupdate-Test endete unmittelbar nach `hook-start`
mit `terminal OTA state: stopped`. Der passive Buslogger sah kein C350, C357
oder C5A8. Die anschließend gelesene Laufzeitphase des neu gestarteten Helfers
war erst `attaching`.

## Ursache

Der Vollupdatepfad löschte `/tmp/phnix_ota_status.json` vor dem Start nicht. Der
Controller konnte deshalb den terminalen `stopped`-Datensatz eines vorherigen
Laufs lesen, während der neue Helfer seine erste Statusmeldung noch nicht
geschrieben hatte. Der Gleichversionstest besaß diese Absicherung bereits.

## Sicherer Ausgang

Es war noch kein Parserauftrag injiziert und kein OTA-Frame gesendet worden.
Nach dem kontrollierten Entfernen von GDB/GDB-Server und der Laufzeitguards
wurden bestätigt:

- Originaldienst `/data/phnixIot4G` läuft, `TracerPid: 0`;
- unveränderter Service-SHA-256;
- beide `helloworld`-Watchdogs laufen;
- keine MQTT-iptables-Regeln mehr vorhanden;
- MQTT-Verbindung wieder `ESTABLISHED`;
- OTA_INFO und Statistik stimmen mit den bekannten Ausgangshashes überein.

## Korrektur

Der Vollupdatecontroller entfernt die alte Statusdatei jetzt unmittelbar vor
dem Start des neuen Runtime-Helfers. Damit kann kein terminaler Datensatz eines
früheren Laufs als Ergebnis des neuen Laufs interpretiert werden.

Ein VM-Regressionstest legt vor dem Start absichtlich
`{"phase":"stopped","terminal":true}` ab und verlangt anschließend trotzdem
den vollständigen simulierten Ablauf bis 100 Prozent und Board-Step 12.

## Zweiter Liveversuch und neue Sperre

Nach Korrektur der Statusdatei erreichte der Vollupdate-Helfer nur die
Attach-Phase. Sein alter Einsprung `0x1FDAC` wurde nicht erreicht; der
Start-Watchdog wechselte deshalb vor jeder Parserinjektion in Guarded Hold. Der
Buslogger bestätigte erneut null OTA-Frames. Dienst, Debugger, Cloudguards,
Watchdogs und Persistenz wurden kontrolliert in den Originalzustand versetzt.

`0x1FDAC` ist nur der einmalige Übergang nach der MQTT-Initialisierung. Der
erfolgreiche Gleichversionstest verwendet dagegen den zyklisch erreichbaren
MQTT-Yield-Punkt `0x1FE40` mit UART-Leerlauf- und Board-Step-12-Prüfung.

Der Vollupdate-Helfer wurde anschließend auf diesen bewährten zyklischen
Startpfad migriert. Er prüft am Halt `0x1FE40` zusätzlich UART-Leerlauf und
Board-Step 12, bevor er den lokalen Auftrag an `ota_code_handle` übergibt.
Außerdem wurden ein zuvor fehlendes modemseitiges Persistenzbackup und ein
`transfer-started`-Marker ergänzt. Letzterer verhindert, dass eine generische
Wiederherstellung eine bereits laufende C5A8-Übertragung unterbricht.
