# PHNIX Debug-Dauerlogger – Anleitung für Anwender

Stand: 14. September 2026

Diese Anleitung beschreibt den PHNIX-Debuglogger für Raspberry Pi OS / Debian. Das Skript liest den Debug-Ausgang des LTE-Modems mit, schreibt einen vollständigen Rohlog und erkennt zusätzlich typische OTA-/Firmwareupdate-Ereignisse sowie Firmware-Download-URLs.

> [!IMPORTANT]
> Der Logger verändert die Firmwaredateien nicht. Er liest den Debugport passiv mit. Ohne `--no-restart` kann das Skript den Originaldienst `phnixIot4G` einmal kontrolliert neu starten und besitzt zusätzlich einen Stumm-Watchdog. Vor jedem automatischen Dienstneustart wird geprüft, ob ein Firmwareupdate aktiv oder resumierbar sein könnte. Ist die Prüfung nicht eindeutig, wird **nicht** neu gestartet.

> [!WARNING]
> Die Logs können sensible Daten enthalten, z. B. IMEI/ICCID, ProductKey, DeviceSecret oder temporär gültige Download-URLs. Rohlogs und URL-Log deshalb vor einer Veröffentlichung immer prüfen und nicht ungefiltert in Foren oder öffentliche Repositories hochladen.

# Schnellstart

## 1. Voraussetzungen einmalig installieren

Der Raspberry Pi muss per USB mit dem LTE-Modem verbunden sein. `adb devices` sollte das Modem als `device` anzeigen. Die USB-/ADB-Grundinstallation ist ausführlicher in [`firmware_backup_lte.md`](firmware_backup_lte.md) beschrieben.

Für den Logger werden auf Raspberry Pi OS / Debian insbesondere `adb`, `udevadm` und Werkzeuge aus `coreutils` benötigt. Am einfachsten einmalig installieren bzw. sicherstellen:

```bash
sudo apt update
sudo apt install -y adb udev coreutils
```

Das Skript erkennt fehlende Programme ebenfalls. Im interaktiven Vordergrund kann es die Installation nach Rückfrage anbieten. Für den späteren Hintergrundbetrieb ist es jedoch zuverlässiger, die Pakete vorher einmalig zu installieren.

## 2. Skript herunterladen

Auf dem Raspberry Pi per SSH anmelden und das Skript z. B. im Home-Verzeichnis herunterladen:

```bash
cd ~
wget -O logging.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_debug_logger/logging.sh
chmod +x logging.sh
```

Optional kann die Shell-Syntax vor dem Start geprüft werden:

```bash
bash -n ./logging.sh
```

Bei erfolgreicher Prüfung gibt dieser Befehl nichts aus.

## 3. Erst einmal sicher testen – ohne Dienstneustart

```bash
./logging.sh --background --no-restart
```

Damit wird der Logger im Hintergrund gestartet. Der Originaldienst `phnixIot4G` wird weder beim Start noch später durch den Stumm-Watchdog neu gestartet.

**Die USB-Reconnect-Selbstheilung bleibt trotzdem aktiv.** Wird das LTE-Modem kurz vom USB getrennt oder vom Kernel neu enumeriert, versucht der Logger den Debugport selbstständig neu zu öffnen.

Eine typische Ausgabe sieht ungefähr so aus:

```text
PHNIX Logger wurde im Hintergrund gestartet. PID: 4992
Statusdatei: /home/USER/FoxAir_Logs/logger_status.log
Das Terminal darf geschlossen werden; der Logger läuft weiter.

Logverzeichnis: /home/USER/FoxAir_Logs
OTA-URL-Log bereit: /home/USER/FoxAir_Logs/phnix_ota_urls.log
ADB-Verbindung OK: 0123456789ABCDEF
--no-restart aktiv: ADB-Verbindung wurde geprüft; alle Dienst-Neustarts sind deaktiviert.
Suche PHNIX-Debuginterface VID=1e0e PID=9001 IF=04 ...
PHNIX-Debugport verbunden: /dev/ttyUSB4 (...)
USB-Generation: ...
Serielles Logging läuft. Tagesdatei: phnix_2026-09-14.log
USB-Reconnect-Selbstheilung aktiv: Neu-Enumeration wird auch bei gleichem /dev/ttyUSBx erkannt.
Stumm-Watchdog: Dienstneustart deaktiviert; USB-Reconnect-Selbstheilung bleibt aktiv.
Dauerlogging aktiv. Hintergrundbetrieb ist vom Terminal entkoppelt.
```

`/dev/ttyUSB4` ist nur ein Beispiel. Das Skript sucht den richtigen USB-Port selbst anhand von VID/PID und USB-Interface; die Nummer kann nach einem Neustart oder USB-Reconnect anders sein.

## 4. Normaler Dauerbetrieb mit Stumm-Watchdog

Soll der Logger sich auch dann selbst erholen, wenn `phnixIot4G` zwar läuft, aber dauerhaft keine Debugausgaben mehr liefert, wird er **ohne** `--no-restart` gestartet:

```bash
./logging.sh --background
```

Dann gelten zusätzlich:

- kontrollierter `phnixIot4G`-Neustart beim Start, sofern die OTA-Sicherheitsprüfung ihn erlaubt;
- nach ungefähr **30 Minuten ohne neue Debugdaten** wird die OTA-Sicherheit erneut geprüft;
- nur wenn die Prüfung eindeutig unkritisch ist, wird `phnixIot4G` einmal kontrolliert neu gestartet;
- pro zusammenhängender Stummphase gibt es höchstens **einen** solchen automatischen Neustart;
- sobald wieder Debugdaten eintreffen, wird der Watchdog neu scharf geschaltet.

Es gibt bewusst **keine Neustartschleife alle 30 Minuten**.

## 5. Live-Anzeige verlassen

Nach `--background` wird automatisch eine Live-Anzeige geöffnet.

Mit

```text
Ctrl+C
```

wird **nur diese Anzeige beendet**. Der eigentliche Logger läuft im Hintergrund weiter.

Auch wenn das SSH-/Terminalfenster geschlossen wird, läuft der Hintergrund-Logger weiter.

## 6. Status prüfen

```bash
./logging.sh --status
```

Beispiel:

```text
PHNIX Hintergrund-Logger läuft.
PID: 4992
Debugport: /dev/ttyUSB4
Logdatei: phnix_2026-09-14.log
Zeilen heute: 304
Letzte Debugaktivität: 2026-09-14 10:31:12 (vor 2 min)
OTA-Status: noch kein Firmware-Update erkannt.
OTA-URL-Log: phnix_ota_urls.log (bereit, noch leer)
```

Im laufenden Hintergrundbetrieb enthält auch der Heartbeat die Zeit seit dem letzten Rohdatenempfang, z. B.:

```text
Logger aktiv | Port: /dev/ttyUSB4 | Log: phnix_2026-09-14.log | Zeilen: 304 | RX vor: 2 min
```

Eine Rohlogdatei mit `0` Zeilen ist normal, solange noch keine Debugdaten empfangen wurden.

## 7. Live-Anzeige später wieder öffnen

```bash
./logging.sh --follow
```

`Ctrl+C` beendet wieder nur die Anzeige, nicht den Logger.

## 8. Logger beenden

```bash
./logging.sh --stop
```

Erwartete Ausgabe:

```text
Beende PHNIX Hintergrund-Logger PID 4992 ...
Hintergrund-Logger beendet. phnixIot4G wurde nicht verändert.
```

# Empfohlener Betrieb vor einem erwarteten Firmwareupdate

Für einen kurzen Funktionstest ist `--background --no-restart` die konservativste Variante.

Für längeres Warten auf ein erwartetes Cloud-Firmwareupdate ist der normale Hintergrundbetrieb sinnvoll:

```bash
./logging.sh --background
```

Der Grund: Die Debugausgabe von `phnixIot4G` kann nach längerer Laufzeit verstummen. Der Stumm-Watchdog kann den Originaldienst dann nach 30 Minuten kontrolliert neu starten – **aber nur, wenn die OTA-Sicherheitsprüfung keinen aktiven oder unklaren Firmwarezustand findet**.

> [!CAUTION]
> `phnixIot4G` während eines bereits laufenden Firmwareupdates nicht manuell neu starten. Das Skript prüft vor seinen eigenen Neustarts mehrere unabhängige OTA-Indikatoren und arbeitet dabei nach dem Fail-safe-Prinzip: unklar = kein Neustart.

# Schutz vor Neustart während eines Firmwareupdates

Vor jedem automatischen Neustart von `phnixIot4G` werden mehrere Ebenen geprüft:

1. **Vom Logger erkannter OTA-Status** in `phnix_ota_state`. Ein erkannter, noch nicht abgeschlossener OTA blockiert den Neustart.
2. **OTA-Schutzmarker** des FoxAir-Updaters auf dem LTE-Modem. Vorhandene Marker blockieren den Neustart.
3. **Originale PHNIX-OTA-Persistenz** `/data/phnixIot_device_OTA_INFO`, also ein Zustand des Herstellerdienstes selbst und unabhängig vom seriellen Debugstream.

Für die originale PHNIX-Persistenz gilt insbesondere:

- Datei leer (`0` Byte) → möglicher neu gestarteter OTA-/Downloadpfad → **kein Neustart**;
- unerwartete oder nicht lesbare Datei → **kein Neustart**;
- 220-Byte-Struktur mit persistierter Firmware-Länge `> 0` → aktiver/resumierbarer Board-OTA möglich → **kein Neustart**;
- bestätigter Idle-/Abschlusszustand `Offset=0` und `Länge=0` → diese Prüfung erlaubt den Neustart.

Damit ist die Sicherheitsentscheidung nicht ausschließlich davon abhängig, dass der Debuglogger selbst den OTA-Beginn gesehen hat.

# USB-Reconnect-Selbstheilung

Ein Linux-USB-Gerät kann kurz verschwinden und danach wieder unter **dem gleichen Namen** wie `/dev/ttyUSB4` auftauchen. Ein alter Dateideskriptor kann dabei trotzdem auf dem nicht mehr existierenden USB-Endpunkt hängen bleiben.

Der Logger merkt sich deshalb zusätzlich die konkrete USB-Generation (`devnum`). Der serielle Read wird regelmäßig unterbrochen, um diese Generation zu prüfen.

Bei einem USB-Reset kann die Statusausgabe beispielsweise enthalten:

```text
WARNUNG: USB-Reconnect/Neu-Enumeration erkannt: /dev/ttyUSB4 Generation '...|4' -> '...|7'. Debugport wird neu geöffnet.
PHNIX-Debugport verbunden: /dev/ttyUSB4 (...)
USB-Generation: ...|7
```

Das funktioniert auch dann, wenn Linux vor und nach dem Reset wieder exakt `/dev/ttyUSB4` verwendet.

# Welche Dateien werden angelegt?

Standardmäßig liegen alle Dateien unter:

```text
~/FoxAir_Logs/
```

Wichtige Dateien:

| Datei | Bedeutung |
|---|---|
| `phnix_YYYY-MM-DD.log` | Vollständiger serieller PHNIX-Rohdebug mit Zeitstempeln. Wird bereits beim erfolgreichen Öffnen des Debugports angelegt und kann zunächst 0 Byte groß sein. |
| `phnix_ota_urls.log` | Erkannte Firmware-Download-URLs mit Zeitstempel und – soweit verfügbar – SoftwareCode, Version, SSID, MD5 und Dateigröße. Wird bereits beim Start angelegt und auf Schreibbarkeit geprüft. |
| `phnix_ota_state` | Letzter erkannter OTA-Zustand. Entsteht erst beim ersten erkannten OTA-Ereignis. |
| `logger_status.log` | Start-, Ereignis-, Reconnect-, Watchdog- und Heartbeat-Ausgabe für `--follow`. |
| `phnix_logger.pid` | PID-/Steuerdatei des Hintergrund-Loggers. |

Zusätzlich kann während des Betriebs eine versteckte Ready-Datei vorhanden sein. Diese dient nur der internen Prozesssteuerung.

# Was wird bei einem Firmwareupdate erkannt?

Der Logger schreibt weiterhin **jede empfangene Debugzeile** in den normalen Tages-Rohlog. Zusätzlich versucht er, wichtige OTA-Ereignisse kompakt herauszufiltern.

Bei einem typischen Update kann die Live-Anzeige z. B. so aussehen:

```text
[22:31:02] OTA | Download-URL erkannt
[22:31:05] OTA | Download gestartet - 0 %
[22:31:07] OTA | Download läuft - 28 %
[22:31:09] OTA | Download läuft - 66 %
[22:31:11] OTA | Download läuft - 100 %
[22:31:12] OTA | Download abgeschlossen
[22:31:13] OTA | MD5-Prüfung erfolgreich
[22:31:14] OTA | Firmware Update läuft
[22:36:25] OTA | Firmwareübertragung abgeschlossen - Mainboard verarbeitet Update
[22:36:30] OTA | Firmware Update erfolgreich
[22:36:31] OTA | Firmware Update fertig
```

Die verschiedenen Stufen bedeuten:

- **Download-URL erkannt** – der Originaldienst hat eine Firmware-URL ausgegeben.
- **Download gestartet / läuft** – die DTU lädt die Firmwaredatei herunter.
- **Download abgeschlossen** – der HTTP-/HTTPS-Download ist fertig.
- **MD5-Prüfung erfolgreich** – die heruntergeladene Datei wurde erfolgreich geprüft.
- **Firmware Update läuft** – die DTU überträgt Firmwaredaten an das Mainboard.
- **Firmwareübertragung abgeschlossen** – alle Firmwaredaten wurden übertragen; das Mainboard verarbeitet bzw. übernimmt das Image aber noch.
- **Firmware Update erfolgreich** – das Mainboard meldet den erfolgreichen Abschluss bzw. der terminale Erfolgsreport wird erzeugt.
- **Firmware Update fertig** – der PHNIX-OTA-Ablauf ist beendet.

> [!WARNING]
> `Download 100 %` oder auch die vollständig abgeschlossene Übertragung zum Mainboard bedeutet noch nicht automatisch, dass das Mainboard-Update erfolgreich beendet ist. Erst die späteren Erfolgs-/Abschlussmeldungen gelten als tatsächlicher Erfolg.

# Wie tolerant ist die URL-Erkennung?

Die bekannte PHNIX-Firmware-URL wird normalerweise als `otaFileDownloadAddr` ausgegeben. Der Logger erkennt mehrere Darstellungsvarianten, unter anderem:

```text
"otaFileDownloadAddr":"http://server/datei.bin"
"otaFileDownloadAddr" : "https://server/datei.bin?token=..."
otaFileDownloadAddr=http://server/datei.bin
otaFileDownloadAddr = https://server/datei.bin
```

Unterstützt werden `http://`, `https://` und `ftp://`. Hostname/IP, Port, Pfad und Query-Parameter werden mitgespeichert.

Zusätzlich existiert eine Fallback-Erkennung: Wenn PHNIX den Feldnamen in einer späteren Version ändert, versucht der Logger URLs auch in `CMD_OTA`-, `otaDeviceInfo`- oder eindeutig firmware-/upgradebezogenen Debugzeilen zu erkennen.

Normale Cloud-API-Aufrufe sollen dabei nicht als Firmware-Download-URL einsortiert werden.

Der wichtigste zusätzliche Schutz ist der vollständige Rohlog: **Die serielle Originalzeile wird unabhängig von der speziellen URL-Erkennung in `phnix_YYYY-MM-DD.log` gespeichert.** Sollte eine zukünftige PHNIX-Version eine bisher unbekannte URL-Darstellung verwenden, kann die URL deshalb trotzdem noch im Rohlog vorhanden sein.

# Status während eines Updates prüfen

Auch wenn die Live-Anzeige geschlossen wurde, kann jederzeit geprüft werden:

```bash
./logging.sh --status
```

Je nach Stand des Updates erscheinen zusätzliche Angaben, z. B.:

```text
OTA-Status: Firmware Update läuft
OTA-Zeit: 2026-09-12 22:31:14
OTA-Version: V3.4
OTA-SoftwareCode: 82400644
OTA-SSID: 0063
OTA-Download-URL erkannt: ja
OTA-URL-Log: phnix_ota_urls.log
OTA-MD5: 149A586EDE6F035B385762EA48C71605
OTA-Dateigröße: 289806 Byte
```

# Logdateien auf dem Raspberry Pi ansehen

Verzeichnis anzeigen:

```bash
ls -lh ~/FoxAir_Logs/
```

Letzte Zeilen des aktuellen Rohlogs:

```bash
tail -n 50 ~/FoxAir_Logs/phnix_$(date +%F).log
```

Rohlog live verfolgen:

```bash
tail -F ~/FoxAir_Logs/phnix_$(date +%F).log
```

Erkannte Firmware-URLs anzeigen:

```bash
cat ~/FoxAir_Logs/phnix_ota_urls.log
```

# Logdateien vom Raspberry Pi herunterladen

## Variante 1 – Windows mit WinSCP

Für viele Anwender ist WinSCP der einfachste Weg:

1. WinSCP installieren und starten.
2. Protokoll **SFTP** auswählen.
3. IP-Adresse des Raspberry Pi eintragen.
4. Mit demselben Benutzer anmelden, der auch für SSH verwendet wird.
5. Zum Verzeichnis

   ```text
   /home/BENUTZER/FoxAir_Logs/
   ```

   wechseln.
6. Gewünschte Dateien oder den kompletten Ordner auf den Windows-PC kopieren.

## Variante 2 – Windows PowerShell / Linux / macOS mit `scp`

Vom eigenen PC aus den kompletten Logordner kopieren:

```bash
scp -r BENUTZER@RASPBERRY_PI_IP:~/FoxAir_Logs ./
```

Beispiel mit einer konkreten IP:

```bash
scp -r pi@192.168.1.50:~/FoxAir_Logs ./
```

Nur die URL-Datei kopieren:

```bash
scp pi@192.168.1.50:~/FoxAir_Logs/phnix_ota_urls.log ./
```

Das Passwort ist – sofern keine SSH-Schlüssel eingerichtet wurden – dasselbe wie bei der normalen SSH-Anmeldung.

## Variante 3 – Logs vorher als Archiv zusammenpacken

Auf dem Raspberry Pi:

```bash
tar -czf ~/FoxAir_Logs_$(date +%F_%H%M).tar.gz -C ~ FoxAir_Logs
```

Danach liegt im Home-Verzeichnis eine einzelne `.tar.gz`-Datei, die z. B. per WinSCP oder `scp` heruntergeladen werden kann.

# Logger aktualisieren

Vor einem späteren Einsatz kann die aktuelle Version erneut von GitHub geladen werden.

Zuerst einen laufenden Hintergrund-Logger sauber beenden:

```bash
./logging.sh --stop
```

Danach:

```bash
cd ~
wget -O logging.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_debug_logger/logging.sh
chmod +x logging.sh
bash -n ./logging.sh
```

Anschließend wieder starten.

Mit automatischer Stumm-Erholung:

```bash
./logging.sh --background
```

Ohne jeden Dienstneustart:

```bash
./logging.sh --background --no-restart
```

# Häufige Fragen / Probleme

## `phnix_YYYY-MM-DD.log` ist 0 Byte groß

Das kann normal sein. Die Datei wird bereits beim erfolgreichen Öffnen des Debugports angelegt. Erst wenn `phnixIot4G` Debugzeilen sendet, wächst sie.

Im normalen Betrieb zeigt der Heartbeat mit `RX vor: ... min`, wie lange die letzte Debugaktivität zurückliegt. Nach 30 Minuten kann der Stumm-Watchdog – sofern sicher – den Originaldienst einmal neu starten.

## Der Logger meldet den Port weiterhin, aber es kommen keine Daten

Seit der Reconnect-Erweiterung prüft der Logger nicht mehr nur den Dateinamen `/dev/ttyUSBx`, sondern auch die USB-Generation. Ein USB-Reset mit anschließender Neu-Enumeration unter demselben Portnamen sollte deshalb erkannt und der Port neu geöffnet werden.

In `logger_status.log` erscheinen dann entsprechende Reconnect-Meldungen.

## Der Stumm-Watchdog will nicht neu starten

Das ist absichtlich möglich. Ein Dienstneustart wird unter anderem blockiert, wenn:

- `--no-restart` aktiv ist;
- der Debugport gerade physisch getrennt ist;
- ein nicht abgeschlossener OTA im Loggerzustand erkannt wurde;
- ein OTA-Schutzmarker vorhanden ist;
- die originale PHNIX-Datei `phnixIot_device_OTA_INFO` leer, nicht lesbar, unerwartet aufgebaut oder mit einer Firmware-Länge `> 0` belegt ist;
- irgendeine dieser Prüfungen kein eindeutiges Ergebnis liefert.

Im Zweifel bleibt der Originaldienst unangetastet.

## `phnix_ota_urls.log` ist leer

Auch das ist normal, solange noch keine Firmware-Download-URL erkannt wurde. Die Datei wird beim Start nur vorsorglich angelegt und auf Schreibbarkeit geprüft.

## `phnix_ota_state` fehlt

Die Datei entsteht erst, wenn das Skript tatsächlich ein OTA-Ereignis erkennt.

## Das Terminal wurde geschlossen

Bei Start mit `--background` ist das kein Problem. Der eigentliche Logger läuft vom Terminal entkoppelt weiter.

Prüfen mit:

```bash
./logging.sh --status
```

## `Ctrl+C` wurde bei `--follow` gedrückt

Auch das beendet nur die Live-Anzeige. Der Hintergrund-Logger läuft weiter.

## Der USB-Port heißt plötzlich nicht mehr `/dev/ttyUSB4`

Das ist normal. Die Nummer kann sich ändern. Das Skript verwendet keine fest konfigurierte `/dev/ttyUSBx`-Nummer, sondern sucht das PHNIX-Debuginterface anhand seiner USB-Kennung.

## Mehrere ADB-Geräte sind angeschlossen

Aus Sicherheitsgründen wählt das Skript dann nicht automatisch irgendein Gerät aus. Bei Bedarf kann das Zielgerät vor dem Start über `ADB_SERIAL` festgelegt werden:

```bash
ADB_SERIAL=0123456789ABCDEF ./logging.sh --background --no-restart
```

# Hilfe direkt im Skript

Alle verfügbaren Optionen zeigt:

```bash
./logging.sh --help
```

Kurzüberblick:

```text
./logging.sh                         Vordergrundbetrieb
./logging.sh --no-restart            Vordergrundbetrieb ohne Dienstneustart
./logging.sh --background            Hintergrundbetrieb + USB-Recovery + Stumm-Watchdog
./logging.sh --background --no-restart
                                     Hintergrundbetrieb + USB-Recovery, keine Dienstneustarts
./logging.sh --follow                Live-Anzeige wieder öffnen
./logging.sh --status                aktuellen Status einmalig anzeigen
./logging.sh --stop                  Hintergrund-Logger beenden
```

## Weiterführende Dokumentation

- [`firmware_backup_lte.md`](firmware_backup_lte.md) – LTE-Modem, ADB und Backup
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md) – Firmware-Updater für Anwender
