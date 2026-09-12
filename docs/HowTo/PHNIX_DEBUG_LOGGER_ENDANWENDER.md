# PHNIX Debug-Dauerlogger – Anleitung für Anwender

Stand: 12. September 2026

Diese Anleitung beschreibt den PHNIX-Debuglogger für Raspberry Pi OS / Debian. Das Skript liest den Debug-Ausgang des LTE-Modems mit, schreibt einen vollständigen Rohlog und erkennt zusätzlich typische OTA-/Firmwareupdate-Ereignisse sowie Firmware-Download-URLs.

> [!IMPORTANT]
> Der Logger verändert die Firmwaredateien nicht. Er liest den Debugport passiv mit. Ohne `--no-restart` kann das Skript den Originaldienst `phnixIot4G` einmal kontrolliert neu starten, damit dessen Start-/Debugausgaben mit erfasst werden. Ein Neustart wird blockiert, wenn ein aktiver OTA-Zustand erkannt wird oder die Sicherheitsprüfung nicht zuverlässig möglich ist.

> [!WARNING]
> Die Logs können sensible Daten enthalten, z. B. IMEI/ICCID, ProductKey, DeviceSecret oder temporär gültige Download-URLs. Rohlogs und URL-Log deshalb vor einer Veröffentlichung immer prüfen und nicht ungefiltert in Foren oder öffentliche Repositories hochladen.

# Schnellstart

## 1. Voraussetzungen einmalig installieren

Der Raspberry Pi muss per USB mit dem LTE-Modem verbunden sein. `adb devices` sollte das Modem als `device` anzeigen. Die USB-/ADB-Grundinstallation ist ausführlicher in [`firmware_backup_lte.md`](firmware_backup_lte.md) beschrieben.

Für den Logger werden auf Raspberry Pi OS / Debian insbesondere `adb`, `udevadm` und `stty` benötigt. Am einfachsten einmalig installieren bzw. sicherstellen:

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

## 3. Erst einmal sicher testen – ohne Dienstneustart

```bash
./logging.sh --background --no-restart
```

Damit wird der Logger im Hintergrund gestartet, der Originaldienst `phnixIot4G` aber nicht neu gestartet.

Eine typische Ausgabe sieht ungefähr so aus:

```text
PHNIX Logger wurde im Hintergrund gestartet. PID: 4992
Statusdatei: /home/USER/FoxAir_Logs/logger_status.log
Das Terminal darf geschlossen werden; der Logger läuft weiter.

Logverzeichnis: /home/USER/FoxAir_Logs
OTA-URL-Log bereit: /home/USER/FoxAir_Logs/phnix_ota_urls.log
ADB-Verbindung OK: 0123456789ABCDEF
--no-restart aktiv: ADB-Verbindung wurde geprüft; Dienst-Neustart wird übersprungen.
Suche PHNIX-Debuginterface VID=1e0e PID=9001 IF=04 ...
PHNIX-Debugport verbunden: /dev/ttyUSB4 (...)
Serielles Logging läuft. Tagesdatei: phnix_2026-09-12.log
Dauerlogging aktiv. Hintergrundbetrieb ist vom Terminal entkoppelt.
```

`/dev/ttyUSB4` ist nur ein Beispiel. Das Skript sucht den richtigen USB-Port selbst anhand von VID/PID und USB-Interface; die Nummer kann nach einem Neustart anders sein.

## 4. Live-Anzeige verlassen

Nach `--background` wird automatisch eine Live-Anzeige geöffnet.

Mit

```text
Ctrl+C
```

wird **nur diese Anzeige beendet**. Der eigentliche Logger läuft im Hintergrund weiter.

Auch wenn das SSH-/Terminalfenster geschlossen wird, läuft der Hintergrund-Logger weiter.

## 5. Status prüfen

```bash
./logging.sh --status
```

Beispiel:

```text
PHNIX Hintergrund-Logger läuft.
PID: 4992
Debugport: /dev/ttyUSB4
Logdatei: phnix_2026-09-12.log
Zeilen heute: 0
OTA-Status: noch kein Firmware-Update erkannt.
OTA-URL-Log: phnix_ota_urls.log (bereit, noch leer)
```

Eine Rohlogdatei mit `0` Zeilen ist normal, solange noch keine Debugdaten empfangen wurden.

## 6. Live-Anzeige später wieder öffnen

```bash
./logging.sh --follow
```

`Ctrl+C` beendet wieder nur die Anzeige, nicht den Logger.

## 7. Logger beenden

```bash
./logging.sh --stop
```

Erwartete Ausgabe:

```text
Beende PHNIX Hintergrund-Logger PID 4992 ...
Hintergrund-Logger beendet. phnixIot4G wurde nicht verändert.
```

# Empfohlener Betrieb vor einem erwarteten Firmwareupdate

Für einen reinen Funktionstest ist `--background --no-restart` die vorsichtigste Variante.

Wenn der Logger für ein **bevorstehendes reales Firmwareupdate** verwendet wird und im Rohlog keine Debugzeilen erscheinen, sollte der Logger rechtzeitig **vor Beginn des Updates** neu gestartet werden:

```bash
./logging.sh --stop
./logging.sh --background
```

Ohne `--no-restart` öffnet der Logger zuerst den Debugport und startet anschließend `phnixIot4G` einmal kontrolliert neu. Dadurch können auch die Startausgaben des Originaldienstes erfasst werden.

> [!CAUTION]
> `phnixIot4G` nicht während eines bereits laufenden Firmwareupdates manuell neu starten. Das Skript besitzt dafür eigene OTA-Sicherheitsprüfungen und blockiert seinen automatischen Neustart, wenn ein aktiver OTA-Zustand erkannt wird oder die Prüfung nicht zuverlässig möglich ist.

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
| `logger_status.log` | Start-, Ereignis- und Heartbeat-Ausgabe für `--follow`. |
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
```

Anschließend wieder starten, z. B.:

```bash
./logging.sh --background --no-restart
```

oder – wenn vor einem erwarteten Update bewusst ein kontrollierter Neustart des Originaldienstes gewünscht ist:

```bash
./logging.sh --background
```

# Häufige Fragen / Probleme

## `phnix_YYYY-MM-DD.log` ist 0 Byte groß

Das kann normal sein. Die Datei wird bereits beim erfolgreichen Öffnen des Debugports angelegt. Erst wenn `phnixIot4G` Debugzeilen sendet, wächst sie.

Wenn auch vor einem erwarteten Update dauerhaft keine Debugzeilen erscheinen, den Logger rechtzeitig vor dem Update stoppen und ohne `--no-restart` neu starten.

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
./logging.sh --background            Hintergrundbetrieb + Live-Anzeige
./logging.sh --background --no-restart
./logging.sh --follow                Live-Anzeige wieder öffnen
./logging.sh --status                aktuellen Status einmalig anzeigen
./logging.sh --stop                  Hintergrund-Logger beenden
```

## Weiterführende Dokumentation

- [`firmware_backup_lte.md`](firmware_backup_lte.md) – LTE-Modem, ADB und Backup
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md) – Firmware-Updater für Anwender
- [`../reverse_engineering/`](../reverse_engineering/) – technische Reverse-Engineering-Dokumentation
