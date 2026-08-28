# Runtime-Helfer: Abbruch nach C36E-Status 1

## Beobachtung im Realtest

Beim Angebot von Mainboard-Firmware V3.4 bestätigte das Mainboard das C350-Angebot
mit C36E-Status `1`. Unmittelbar danach endete die GDB-Sitzung mit Exit-Code `0`.
C357 und C5A8 wurden nicht erreicht. Der Updater wechselte deshalb korrekt in den
Guarded Hold; es wurden keine Firmwaredaten übertragen.

Der passive RS485-Mitschnitt bestätigt den Ablauf bytegenau:

- `23:54:07.228`: C350-Angebot für Softwarecode `82400644`, Version `0034`,
  anschließend C350-ACK.
- `23:54:07.728`: C36E mit SSID `0063` und Status `1`, Antwortzeit 500 ms.
- In der gesamten Rohdatei: kein C357, kein C5A8 und kein C371-Block-ACK.

Damit war das Mainboard bereit für das Update, erhielt aber weder die
Transfermetadaten noch einen Firmwareblock. Spätere C37B-Frames mit Status `7`
gehören zur Geräteinformations-Bestätigung und nicht zum OTA-Datentransfer.

## Ursache

Die GDB-Batchdatei endete nach einem einzelnen `continue`. Spätere Breakpoints
setzten den Prozess in ihren Command-Listen wieder fort. Dadurch konnte der äußere
Batchbefehl als beendet gelten und GDB das Dateiende erreichen, obwohl der
OTA-Ablauf noch aktiv war. Der Exit-Code `0` belegte nur einen technisch sauberen
GDB-Exit, nicht einen terminal abgeschlossenen OTA-Lauf.

## Korrektur

Ein zweiter Realtest zeigte, dass auch ein äußerer Ereignisloop nicht genügt,
solange Breakpoints eigene `continue`-Command-Listen besitzen: Nach dem bestätigten
Status `1` traf der Dienst einen weiteren erwarteten Breakpoint in einem anderen
Thread und GDB beendete den Batchkontext erneut mit Exit-Code `0`.

Der aktive OTA-Abschnitt verwendet deshalb nun einen zentralen Dispatcher.
Breakpoints besitzen keine eigenen Fortsetzungsbefehle mehr. Ein einziges
`continue` kehrt bei jedem Ereignis zum Dispatcher zurück; dort werden Adresse,
Phase und notwendige Beobachtungsaktion ausgewertet. Ein unbekannter Stopp wird
als Fehler behandelt und niemals als OTA-Erfolg.

Zusätzlich prüft der Runtime-Helfer nach dem GDB-Ende, ob zuvor ein terminaler
OTA-Zustand geschrieben wurde. Ein Exit-Code `0` ohne terminalen Zustand ist jetzt
explizit ein Fehler.

## Abbruchgrenze

Die Fehlerbehandlung unterscheidet zwei Sicherheitsbereiche:

- **Vor C36E-Status 1:** Der Dienst wird angehalten. Cloud und Watchdogs bleiben
  gesperrt. Das Mainboard hat das Update noch nicht übernommen.
- **Ab C36E-Status 1:** Der Originaldienst bleibt aktiv und autoritativ. Ein
  Verlust der Beobachtung darf den übernommenen OTA-Ablauf nicht als vermeintliche
  Schutzmaßnahme unterbrechen. Cloud und Watchdogs bleiben zunächst gesperrt;
  automatische Wiederherstellung bleibt verboten.

Die vorhandenen Prüfungen für Dienst-Build, Firmware-Hash, Manifest, SSID,
Ausgangszustand und Restore-Grenze bleiben unverändert.

## VM-Nachweis

Mit V3.4 gegen ein simuliertes V3.3-Mainboard wurde die zuvor fehlerhafte Grenze
überschritten: C350 wurde angenommen, C357 gesendet und C5A8 begann mit korrekter
Version `0034`, Größe `289806` und MD5
`149A586EDE6F035B385762EA48C71605`. Der vollständige terminale Lauf wird vor
einem weiteren Realtest erneut geprüft.
