# PHNIX Cancel-Probe – Live-Ergebnis am Mainboard

Stand: 2026-08-23

## Ergebnis

Der begrenzte Originaldienst-Test mit lokal eingespeistem Cloud-Code `0073`
war erfolgreich. Das LTE-Modem verwendete seinen eigenen RS485-Anschluss; der
separate ser2net-Zugang war nicht Sender und wurde nicht benötigt.

Beobachtete Zustandsfolge:

```text
Ausgang:  board_ota_step=12, cancel_pending=0, uart_send_flag=0
0073:     board_ota_step=7,  cancel_pending=1
Abschluss board_ota_step=12, cancel_pending=0, uart_send_flag=0
```

Damit ist dynamisch bestätigt, dass das echte Mainboard den frühen
Cancelpfad beantwortet und der Originaldienst anschließend seinen terminalen
Schritt 12 erreicht.

## Sicherheitsrahmen

- kein `0033` eingespeist;
- keine Firmwaredatei verwendet;
- Cloud während des Testfensters per Mobilfunkschnittstelle blockiert;
- beide Watchdogs während der Debug-Abschnitte pausiert;
- Ausgangszustand OTA_INFO: Offset 0, Länge 0;
- Endzustand OTA_INFO: Offset 0, Länge 0;
- keine C350-, C357- oder C5A8-Phase gestartet;
- vor der Injektion Dienst angehalten, TX-Flag 0 bestätigt und eine Sekunde
  Sendepause eingehalten.

Der Test schreibt über C36A den frühen Mainboard-OTA-/EEPROM-Abbruchzustand
zurück. Er war deshalb bewusst als begrenzter Mainboard-Schreibtest eingestuft,
nicht als rein lesender Test.

## Auffälligkeiten des Testwerkzeugs

Der ursprünglich vorgesehene Breakpoint `0x1FDAC` ist kein zyklischer
Leerlaufpunkt; ohne Cloudereignis wurde er nicht erreicht. Die lokale
Handler-Injektion per GDB benötigte außerdem die Original-ELF-Zuordnung. Beim
ersten Funktionsaufruf wechselte ein anderer Thread bereits in die
Cancel-State-Machine. Dadurch brach GDB seine Ausdrucksauswertung ab, obwohl
der Handler vollständig den Zustand `step 7 / cancel_pending 1` gesetzt hatte.

Der abgesicherte Halt funktionierte dabei wie vorgesehen. Der bereits gesetzte
Cancelzustand wurde danach unter fortbestehender Cloud- und Watchdog-Sperre
kontrolliert ausgeführt. Nach 15 Sekunden lag der eindeutige Terminalzustand
`step 12 / cancel_pending 0` vor.

Für weitere automatisierte Läufe sperrt der Runtime-Helfer den Scheduler
während des lokalen Handler-Aufrufs. Der spezielle Resume-Pfad bleibt für
einen nachweislich vorhandenen Zustand `step 7 / cancel_pending 1` erhalten.

## Wiederhergestellter Originalzustand

Nach dem Erfolg wurden bestätigt:

- Originaldienst zunächst mit PID 27255 und `TracerPid: 0` fortgesetzt;
- der originale Watchdog startete den Dienst anschließend einmal regulär neu;
  Endkontrolle: PID 25140, `TracerPid: 0`, 15 Threads und unveränderte
  Dienst-SHA-256
  `7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7`;
- beide ursprünglichen `helloworld`-Watchdogs laufen;
- keine aktive Testsitzung;
- keine verbliebene MQTT-Firewallregel;
- OTA_INFO Offset 0 und Länge 0;
- MQTT-Verbindung wieder `ESTABLISHED` auf TCP-Port 1883;
- keine Testdatei wurde als Firmware installiert oder übertragen.

## Aussagegrenze

Bestätigt ist ausschließlich der frühe Cancel- und Rückkehrpfad. Der Test
belegt weder die Sicherheit noch die Funktionsfähigkeit von C350, C357, C5A8,
Firmware-Promotion oder Boot/Recovery. Ein echter Firmwaretransfer bleibt eine
separate, ausdrücklich freizugebende Risikostufe.
