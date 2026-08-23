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

## Dritter Liveversuch: C350 und Gleichversion

Der migrierte Vollpfad erreichte am realen Mainboard erstmals deterministisch
C350. Der passive Logger bestätigte:

- C350-Angebot für Softwarecode `82400644`, Version `0033`, Ziel `0063`;
- gültiges C350-ACK;
- C36E Status 0;
- kein C357 und kein C5A8.

Damit funktionierte der neue `0x1FE40`-Einstieg. Der Vollhelfer besaß jedoch
noch keinen terminalen Zweig für die Gleichversionsantwort und fiel nach dem
normalen Ende des Debuggers in Guarded Hold. Der `transfer-started`-Marker war
nicht gesetzt. Das modemseitige Backup restaurierte die vom originalen
0033-Handler geleerte OTA_INFO bytegleich; danach wurden Dienst, Cloud,
Watchdogs und temporäre Dateien vollständig wiederhergestellt.

Als Korrektur überwacht der Vollpfad jetzt zusätzlich den bereits bekannten
C36E-Halt `0x1BA04`. Für Ziel `0063` und Status 0 restauriert er die Persistenz,
meldet terminal `same-version` und räumt ohne Guarded Hold auf. Status 1 wird
unverändert dem Originaldienst für C357/C5A8 überlassen. Ein neues
VM-Same-Version-Szenario prüft diesen Vertrag.

Zusätzlich wurde `--restore original` so geändert, dass es eine absichtlich
leere OTA_INFO vor der Wiederherstellung nicht zu dekodieren versucht. Ein
fehlender HTTP-PID-Datensatz wird nun durch eine streng auf
`127.0.0.1:8081` und `/data/phnix_local_ota` gefilterte Prozesssuche ersetzt.

## Vierter Liveversuch: nichtdeterministische asynchrone Injektion

Ein weiterer Lauf endete nach Parserbeginn, aber vor dem vom Logger sichtbaren
C350. GDB meldete nur Threadwechsel und verließ die asynchrone
Breakpoint-Kommandostruktur anschließend ohne terminalen Status. Nach dem
Restore und Fortsetzen des Dienstes erschien C350 verzögert; C36E meldete
wieder Status 0, C357/C5A8 blieben aus.

Der passive Mitschnitt bestätigte die verspätete Sequenz eindeutig:

- `22:31:58`: C350 für `82400644`, Version `0033`, Ziel `0063`;
- unmittelbar danach gültiges C350-ACK;
- `22:31:59`: C36E Status 0;
- weiterhin kein C357 und kein C5A8, somit keine Firmwaredatenübertragung.

Damit war nachgewiesen, dass `kein transfer-started` allein nicht bedeutet,
dass kein Parseraufruf mehr im Prozess schwebt. Zwei Korrekturen folgen daraus:

1. Unmittelbar vor `ota_code_handle` wird ein eigener `injection-started`-Marker
   gesetzt. Restore bei gesetztem Marker setzt den alten Prozess nicht einfach
   fort, sondern restauriert die Persistenz, beendet die alte Prozessinstanz
   und lässt den originalen Watchdog eine frische Instanz starten.
2. Die zustandsabhängige asynchrone Injektion am zyklischen Breakpoint wurde
   verworfen. Der Start läuft jetzt linear wie beim bereits erfolgreichen
   Gleichversionstest: `0x1FE40` → Vorbedingungen → Parser → zwingend C350 →
   zwingend erste C36E. Erst bei Status 1 wird auf die asynchrone Überwachung
   des anschließenden C357/C5A8-Volltransfers umgestellt.

Diese lineare Sequenz verhindert konkurrierende Treffer mehrerer Threads am
Yield-Breakpoint und liefert für jeden frühen Ausgang einen eindeutigen
terminalen Status.

Die alte, bereits injizierte Prozessinstanz wird beim Restore bewusst mit
`SIGKILL` beendet. Ein `SIGTERM` mit anschließendem `SIGCONT` wäre an dieser
Stelle ungeeignet: Zwischen Fortsetzen und Signalbehandlung könnte der noch
schwebende Parseraufruf erneut ein verspätetes C350 senden. Diese harte
Beendigung gilt ausschließlich vor `transfer-started`; nach beobachtetem C5A8
verweigert Restore weiterhin jeden Eingriff.
