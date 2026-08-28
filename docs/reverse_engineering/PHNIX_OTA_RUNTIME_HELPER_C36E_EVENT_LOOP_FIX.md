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

Der aktive OTA-Abschnitt besitzt nun einen expliziten Ereignisloop. Jeder erwartete
Breakpoint erhöht einen Ereigniszähler. Kehrt GDB ohne ein solches Ereignis zum
Loop zurück, wird dies als unerwarteter Debugger-Stopp behandelt und nicht als
OTA-Erfolg.

Zusätzlich prüft der Runtime-Helfer nach dem GDB-Ende, ob zuvor ein terminaler
OTA-Zustand geschrieben wurde. Ein Exit-Code `0` ohne terminalen Zustand ist jetzt
explizit ein Fehler.

## Abbruchgrenze

Die Fehlerbehandlung unterscheidet zwei Sicherheitsbereiche:

- **Vor dem ersten C5A8-Block:** Der Dienst wird angehalten. Cloud und Watchdogs
  bleiben gesperrt. In diesem Bereich wurde noch keine Firmware übertragen.
- **Ab dem ersten C5A8-Block:** Der Originaldienst bleibt aktiv und
  autoritativ. Ein Verlust der Beobachtung darf den laufenden Firmwaretransfer
  nicht als vermeintliche Schutzmaßnahme unterbrechen. Cloud und Watchdogs bleiben
  zunächst gesperrt; automatische Wiederherstellung bleibt verboten.

Die vorhandenen Prüfungen für Dienst-Build, Firmware-Hash, Manifest, SSID,
Ausgangszustand und Restore-Grenze bleiben unverändert.

## VM-Nachweis

Mit V3.4 gegen ein simuliertes V3.3-Mainboard wurde die zuvor fehlerhafte Grenze
überschritten: C350 wurde angenommen, C357 gesendet und C5A8 begann mit korrekter
Version `0034`, Größe `289806` und MD5
`149A586EDE6F035B385762EA48C71605`. Der vollständige terminale Lauf wird vor
einem weiteren Realtest erneut geprüft.
