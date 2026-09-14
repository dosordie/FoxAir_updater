# PHNIX Debug-Dauerlogger – Anleitung für Anwender

Stand: 14. September 2026

Der Logger liest den Debug-Ausgang des PHNIX-LTE-Modems mit, schreibt einen Rohlog und erkennt wichtige OTA-/Firmwareupdate-Ereignisse sowie Firmware-Download-URLs.

> [!IMPORTANT]
> Der Logger verändert keine Firmwaredateien. Im normalen Betrieb kann er `phnixIot4G` kontrolliert neu starten, wenn längere Zeit keine Debugdaten mehr kommen. Vor jedem Neustart wird geprüft, ob ein Firmwareupdate aktiv sein könnte. Bei unklarem Zustand wird **nicht** neu gestartet.

> [!WARNING]
> Die Logs können sensible Daten enthalten, z. B. IMEI/ICCID, ProductKey, DeviceSecret oder temporär gültige Download-URLs. Vor einer Veröffentlichung immer prüfen.

# Schnellstart

## 1. Voraussetzungen

Der Raspberry Pi muss per USB mit dem LTE-Modem verbunden sein. `adb devices` sollte das Modem als `device` anzeigen.

Benötigte Pakete:

```bash
sudo apt update
sudo apt install -y adb udev coreutils
```

## 2. Logger herunterladen

```bash
cd ~
wget -O logging.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_debug_logger/logging.sh
chmod +x logging.sh
bash -n ./logging.sh
```

Wenn `bash -n` nichts ausgibt, ist die Shell-Syntax in Ordnung.

## 3. Sicherer Test ohne Dienstneustart

```bash
./logging.sh --background --no-restart
```

Damit läuft der Logger im Hintergrund, startet `phnixIot4G` aber niemals neu.

Die automatische USB-Wiederverbindung bleibt aktiv. Wird das Modem kurz getrennt oder vom Kernel neu eingebunden, öffnet der Logger den Debugport selbstständig wieder.

## 4. Normaler Dauerbetrieb

```bash
./logging.sh --background
```

Im normalen Betrieb gilt:

- `phnixIot4G` wird beim Start einmal kontrolliert neu gestartet, sofern der OTA-Schutz dies erlaubt;
- nach **15 Minuten ohne neue Debugdaten** wird die OTA-Sicherheit erneut geprüft;
- nur bei eindeutig unkritischem Zustand wird `phnixIot4G` einmal neu gestartet;
- pro zusammenhängender Stummphase gibt es höchstens einen automatischen Neustart;
- sobald wieder Daten eintreffen, wird der Watchdog neu scharf geschaltet.

Es gibt keine Neustartschleife alle 15 Minuten.

# Live-Anzeige und Status

Nach `--background` öffnet sich automatisch eine Live-Anzeige.

`Ctrl+C` beendet **nur die Anzeige**. Der Logger läuft im Hintergrund weiter.

Später wieder öffnen:

```bash
./logging.sh --follow
```

Einmaligen Status anzeigen:

```bash
./logging.sh --status
```

Typische Statuszeile:

```text
[2026-09-14 11:44:48] Logger aktiv | /dev/ttyUSB4 | phnix_2026-09-14.log | 338 Zeilen | letzte Daten vor: 0 min
```

Bei getrennter USB-Verbindung steht dort entsprechend `USB getrennt`.

Die Live-Anzeige verwendet Farben:

- **grün**: Erfolg / verbunden / URL erkannt
- **gelb**: Warnung
- **rot**: Fehler

Die Logdateien selbst enthalten keine Farbcodes.

Farben lassen sich bei Bedarf abschalten:

```bash
NO_COLOR=1 ./logging.sh --background
```

# Logger beenden

```bash
./logging.sh --stop
```

Dabei wird nur der Logger beendet. `phnixIot4G` bleibt unangetastet.

# Schutz während eines Firmwareupdates

Vor jedem automatischen Neustart prüft der Logger mehrere OTA-Hinweise:

1. den vom Logger erkannten OTA-Status;
2. vorhandene OTA-Schutzmarker;
3. den originalen PHNIX-OTA-Zustand auf dem LTE-Modem.

Wichtig:

- aktiver oder fortsetzbarer OTA → **kein Neustart**;
- unklarer oder nicht lesbarer Zustand → **kein Neustart**;
- bestätigter Idle-Zustand → Neustart erlaubt;
- leere oder fehlende `OTA_INFO` allein bedeutet noch nicht automatisch OTA. Fehlen zusätzlich Firmware-Cache und weitere OTA-Hinweise, kann dies ein normaler Erstzustand sein.

> [!CAUTION]
> `phnixIot4G` während eines bereits laufenden Firmwareupdates nicht manuell neu starten.

# USB-Wiederverbindung

Der Logger erkennt auch einen kurzen USB-Reset, wenn Linux danach wieder denselben Portnamen wie `/dev/ttyUSB4` verwendet.

Typische Meldung:

```text
WARNUNG: USB-Verbindung wurde neu aufgebaut. Debugport wird neu geöffnet.
Debugport verbunden: /dev/ttyUSB4
```

Die konkrete `/dev/ttyUSBx`-Nummer muss nicht fest eingestellt werden. Der Logger sucht den passenden PHNIX-Debugport selbst.

# Dateien

Standardmäßig liegen alle Dateien unter:

```text
~/FoxAir_Logs/
```

| Datei | Bedeutung |
|---|---|
| `phnix_YYYY-MM-DD.log` | vollständiger serieller Rohlog |
| `phnix_ota_urls.log` | erkannte Firmware-Download-URLs und Metadaten |
| `phnix_ota_state` | letzter erkannter OTA-Zustand |
| `logger_status.log` | Start-, Status-, Watchdog-, Restart- und USB-Meldungen |
| `phnix_logger.pid` | PID-Datei des Hintergrund-Loggers |

Ein automatischer Restart steht ebenfalls in `logger_status.log`, inklusive alter und neuer PID.

# Erkannte OTA-Ereignisse

Bei einem Firmwareupdate kann die Live-Anzeige z. B. melden:

```text
OTA | Download-URL erkannt
OTA | Download gestartet - 0 %
OTA | Download läuft - 66 %
OTA | Download abgeschlossen
OTA | MD5-Prüfung erfolgreich
OTA | Firmware Update läuft
OTA | Firmwareübertragung abgeschlossen - Mainboard verarbeitet Update
OTA | Firmware Update erfolgreich
OTA | Firmware Update fertig
```

`Download 100 %` bedeutet noch nicht automatisch, dass das Mainboard-Update erfolgreich abgeschlossen ist. Entscheidend sind die späteren Erfolgs-/Abschlussmeldungen.

Die erkannte URL wird zusätzlich in `phnix_ota_urls.log` gespeichert.

# Logs ansehen

Dateien anzeigen:

```bash
ls -lh ~/FoxAir_Logs/
```

Letzte Zeilen des Rohlogs:

```bash
tail -n 50 ~/FoxAir_Logs/phnix_$(date +%F).log
```

Rohlog live verfolgen:

```bash
tail -F ~/FoxAir_Logs/phnix_$(date +%F).log
```

Erkannte Firmware-URLs:

```bash
cat ~/FoxAir_Logs/phnix_ota_urls.log
```

Status-/Restart-Log:

```bash
tail -n 100 ~/FoxAir_Logs/logger_status.log
```

# Logs herunterladen

Unter Windows ist WinSCP per SFTP meist am einfachsten. Das Logverzeichnis liegt unter:

```text
/home/BENUTZER/FoxAir_Logs/
```

Alternativ per `scp`:

```bash
scp -r BENUTZER@RASPBERRY_PI_IP:~/FoxAir_Logs ./
```

# Logger aktualisieren

Zuerst beenden:

```bash
./logging.sh --stop
```

Dann aktuelle Version laden:

```bash
cd ~
wget -O logging.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/phnix_debug_logger/logging.sh
chmod +x logging.sh
bash -n ./logging.sh
```

Danach wieder starten:

```bash
./logging.sh --background
```

# Häufige Fragen

## Die Tagesdatei ist 0 Byte groß

Das kann direkt nach dem Start normal sein. Die Datei wird angelegt, bevor die erste Debugzeile empfangen wurde.

## Der Port ist verbunden, aber es kommen keine Daten

Im normalen Betrieb greift nach 15 Minuten der Stumm-Watchdog. Vor dem Neustart wird immer der OTA-Schutz geprüft.

## Der Watchdog startet `phnixIot4G` nicht neu

Das ist möglich und beabsichtigt, z. B. wenn:

- `--no-restart` aktiv ist;
- USB gerade getrennt ist;
- ein OTA läuft oder noch nicht abgeschlossen ist;
- ein OTA-Schutzmarker vorhanden ist;
- der OTA-Zustand nicht sicher beurteilt werden kann.

Im Zweifel wird nicht neu gestartet.

## `phnix_ota_urls.log` ist leer

Dann wurde noch keine Firmware-Download-URL erkannt.

## Das Terminal wurde geschlossen

Bei Start mit `--background` läuft der Logger weiter.

Prüfen mit:

```bash
./logging.sh --status
```

## Mehrere ADB-Geräte sind angeschlossen

Dann wird aus Sicherheitsgründen keines automatisch gewählt. Das Zielgerät kann festgelegt werden:

```bash
ADB_SERIAL=0123456789ABCDEF ./logging.sh --background
```

# Befehle im Überblick

```text
./logging.sh                         Vordergrundbetrieb
./logging.sh --no-restart            Vordergrund ohne Dienstneustart
./logging.sh --background            Hintergrund + USB-Recovery + 15-Minuten-Watchdog
./logging.sh --background --no-restart
                                     Hintergrund + USB-Recovery, keine Dienstneustarts
./logging.sh --follow                Live-Anzeige öffnen
./logging.sh --status                Status anzeigen
./logging.sh --stop                  Logger beenden
./logging.sh --help                  Hilfe anzeigen
```

## Weiterführende Dokumentation

- [`firmware_backup_lte.md`](firmware_backup_lte.md) – LTE-Modem, ADB und Backup
- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md) – Firmware-Updater für Anwender
