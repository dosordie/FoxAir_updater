# Linux / Raspberry Pi

Stand: 28. September 2026

Der Linux-/Raspberry-Pi-Weg verwendet für normale Mainboard-Firmwareupdates denselben **autonomen DTU-Runner** wie die Windows-Version. Der Raspberry Pi bzw. Linux-Rechner ist nur noch Host für Vorbereitung, Start, Statusanzeige und lokale Archivierung. Nach dem Start läuft der eigentliche OTA-Vorgang persistent auf dem LTE-Modem weiter.

> [!IMPORTANT]
> Mehrere Firmwarestände und Hardwarekonfigurationen wurden real mit dem FoxAir Updater getestet, einschließlich vollständiger Firmwarewechsel bis V3.5. Nicht jede denkbare Hardware-/Firmwarekombination und nicht jeder Fehlerfall ist in gleicher Tiefe live validiert. Firmwareupdates erfolgen auf eigenes Risiko.

## Schnellinstallation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
wget -O install.sh https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Bei der interaktiven Erstinstallation kann zusätzlich der integrierte Windows-
Remotezugriff aktiviert werden. Direkt erzwingen lässt er sich mit:

```sh
bash install.sh --remote-access
```

Dabei werden zwei systemd-Dienste eingerichtet:

- **TCP 5038:** Remote-ADB-Server;
- **TCP 5039:** ausschließlich lesender PHNIX-Debugstream.

Der Debugstream findet den SIMCom-Port anhand **VID 1e0e / PID 9001 /
USB-Interface 04** automatisch. Eine feste Zuordnung wie `/dev/ttyUSB4` ist
nicht erforderlich.

Standardmäßig wird nach `~/FoxAir_updater` installiert. Der Installer verwendet `sudo` nur für Systempakete und die udev-Regel.

## Installierte Struktur

```text
~/FoxAir_updater/
├── firmware/              # lokale Firmware + Manifest
├── downloaded_firmware/   # manuell geladene LTE-/Firmwaredateien
├── logs/                  # Update-Logs + automatische DTU-Diagnosearchive
├── foxair-updater         # Endanwender-Launcher
├── updater/common/        # gemeinsamer Transport/Manifest-Core
├── updater/dtu_ota/       # autonomer DTU-Runner
├── updater/linux/         # Linux-Host-Orchestrierung
├── tools/phnix_ota/       # Manifest- und Runtime-Profil-Werkzeuge
└── docs/HowTo/
```

Der Installer verwendet `git sparse-checkout`. Entwicklungsbereiche wie `devtools`, `tests`, `docs/reverse_engineering` und `updater/windows` werden beim normalen Linux-Endanwender-Checkout nicht benötigt.

## Architektur

Der produktive Linux-Updatepfad ist:

```text
./foxair-updater update MANIFEST
        ↓
automatische vollständige Firmware-/Manifestprüfung
        ↓
updater/linux/autonomous_update.py
        ↓
DtuOtaClient / updater/dtu_ota
        ↓
dtu_ota_supervisor.sh auf dem LTE-DTU
        ↓
phnix_ota_runtime_hook
        ↓
phnixIot4G
        ↓
Mainboard
```

Nach `start` ist der Host nicht mehr dafür verantwortlich, den OTA am Leben zu halten. USB-, ADB- oder Host-Verbindungsverlust beendet einen bereits gestarteten Mainboard-Transfer nicht.

Der autonome Runner übernimmt insbesondere:

- persistenten Run-/Statuszustand auf dem LTE-Modem;
- kontrollierten Neustart von `phnixIot4G` vor dem Update;
- Readiness-Prüfung des Originaldienstes;
- C350/C36E/C357/C5A8 und Abschlussüberwachung;
- Wiederanbindung des Runtime-Monitorings;
- direkten kontrollierten Neustart von `phnixIot4G` nach einem Dienst-Crash;
- Wiederaufnahme anhand des persistenten PHNIX-OTA-Offsets;
- 20-Minuten-Stall-Recovery;
- maximal drei automatische Recovery-Vorgänge pro OTA-Lauf.

MQTT bleibt beim normalen Vollupdate verbunden.

## Firmware bereitstellen

Firmware und Manifest lokal nach `~/FoxAir_updater/firmware/` kopieren, zum Beispiel:

```text
~/FoxAir_updater/firmware/FW3.5.bin
~/FoxAir_updater/firmware/FW3.5.json
```

Der im Manifest angegebene Firmwaredateiname wird im selben Verzeichnis und anschließend im lokalen `firmware/`-Ordner gesucht.

## Bedienung

```sh
cd ~/FoxAir_updater
```

Hilfe:

```sh
./foxair-updater --help
```

### Status

```sh
./foxair-updater status
```

Der Status wird aus dem persistenten autonomen DTU-Lauf gelesen. Wurde ein erfolgreicher Lauf nach einem früheren Host-/ADB-Verlust inzwischen terminal, führt `status` ebenfalls den sicheren Abschluss **Diagnose → ACK → Cleanup** aus.

### Vorprüfung

```sh
./foxair-updater check FW3.5.json
```

Die Firmware wird lokal vollständig gegen das Manifest geprüft. Danach wird ein DTU-Paket hochgeladen und der autonome DTU-Preflight ausgeführt. Es werden dabei weder GDB noch C350 noch ein Mainboard-OTA gestartet. Nach erfolgreicher Vorprüfung werden die ausschließlich vorbereiteten Testdaten wieder vom LTE-Modem entfernt.

### Firmwareupdate

```sh
./foxair-updater update FW3.5.json
```

Vor dem Start erfolgt eine interaktive Bestätigung.

Für einen bewusst nicht-interaktiven Aufruf bleibt möglich:

```sh
./foxair-updater update FW3.5.json --confirm
```

`--full` ist beim Update **nicht mehr erforderlich und nicht mehr vorgesehen**. Die vollständige Firmware-/Manifestprüfung läuft immer zwingend.

Ein separater `same-version`-Befehl ist ebenfalls nicht mehr erforderlich. Meldet das Mainboard, dass bereits dieselbe Firmware installiert ist, erkennt der autonome Runner das automatisch und beendet den Lauf sicher ohne C357/C5A8-Firmwareübertragung.

### Automatischer Abschluss

Bei terminalem `success` oder `same-version`:

```text
terminales Ergebnis
→ lokales FoxAir_DTU_Logs_<run-id>.zip erzeugen
→ ZIP verifizieren
→ Ergebnis auf dem DTU bestätigen (ACK)
→ gespeicherte Daten dieses OTA-Laufs vom DTU entfernen
```

Die Archive und Host-Logs liegen unter:

```text
~/FoxAir_updater/logs/
```

Kann das Diagnosearchiv nicht sicher lokal erstellt und verifiziert werden, erfolgt **kein ACK und kein Cleanup**. Die Daten bleiben auf dem LTE-Modem erhalten.

Bei `failed`, `runner-lost`, `recovery-required` oder vergleichbaren Fehlerzuständen wird ein Diagnosepaket gespeichert, die DTU-Daten werden aber absichtlich **nicht automatisch gelöscht**.

Das normale per-run Cleanup entfernt keine originalen PHNIX-Dateien. Insbesondere bleiben erhalten:

- `/data/phnixIot4G`
- `/cache/phnixIot_device_OTA`
- `/data/phnixIot_device_OTA_INFO`
- `/data/phnixIot_device_statisic`

## Host-/ADB-Verlust während des Updates

Wird die Host-Verbindung unterbrochen, meldet die CLI, dass nur das Monitoring verloren wurde. Der autonome DTU-Lauf arbeitet weiter.

Nach Wiederherstellung der Verbindung:

```sh
./foxair-updater status
```

Es wird kein zweiter OTA gestartet.

## Firmware-/LTE-Dateien manuell sichern

```sh
./foxair-updater download
```

Die Dateien landen unter:

```text
~/FoxAir_updater/downloaded_firmware/<Zeitstempel>/
```

Dieser Befehl ist read-only gegenüber den gelesenen PHNIX-Dateien.

## Restore

```sh
./foxair-updater restore
```

`restore` verwendet den gemeinsamen Originalzustands-Core und denselben geprüften Runtime-Hook wie der autonome Runner. Der Aufruf ist ausschließlich für einen eindeutig sicheren Zustand **vor Übernahme des Firmwaretransfers durch den Originaldienst** vorgesehen. Ein aktiver autonomer Runner sowie `transfer_started` oder `original_service_owns` sperren den Restore fail-closed. Ein laufender autonomer OTA wird stattdessen ausschließlich über dessen Runner-/Abort-Pfad behandelt.

## Manifest erzeugen

Die Option `--full` bleibt beim **Manifest-Werkzeug** weiterhin sinnvoll und hat nichts mit dem früheren Update-Schalter zu tun:

```sh
./foxair-updater manifest FW3.5.bin --full --show
./foxair-updater manifest FW3.5.bin --full
```

Ohne `--output` wird das Manifest neben der Firmware erzeugt.

## Installation aktualisieren

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Der Installer aktualisiert nur per Fast-Forward. Lokale Firmwaredateien, Downloads und Logs bleiben erhalten.

## Remotezugriff für Windows

Der Raspberry Pi kann den Windows-Updater direkt mit beiden benötigten
Netzwerkpfaden versorgen:

```text
Windows
  ├─ ADB            → Raspberry Pi :5038 → LTE-Modem/ADB
  └─ PHNIX Debug    → Raspberry Pi :5039 → USB Interface 04 (read-only)
```

Verwaltung:

```sh
./foxair-updater remote status
./foxair-updater remote start
./foxair-updater remote stop
./foxair-updater remote restart
./foxair-updater remote enable
./foxair-updater remote disable
```

`enable` aktiviert beide Dienste auch für den nächsten Systemstart. `start`
startet sie nur für die aktuelle Sitzung.

Der Debugstream auf TCP 5039 ist bewusst **kein allgemeiner virtueller COM-Port**:
Netzwerkdaten werden niemals zurück auf den seriellen PHNIX-Port geschrieben.
Für den FoxAir-Updater ist deshalb kein `ser2net` erforderlich. Falls außerhalb
des Updaters ein echter bidirektionaler COM↔TCP-/RFC2217-Adapter gebraucht wird,
kann ser2net weiterhin separat verwendet werden.

Wenn der Remote-ADB-Dienst aktiv ist, verwendet auch
`./foxair-updater` lokal automatisch den ADB-Server auf
`127.0.0.1:5038`. Dadurch konkurriert kein zusätzlicher ADB-Server auf TCP
5037 um dasselbe USB-Modem.

> [!WARNING]
> Remote-ADB ist nur für ein vertrauenswürdiges LAN vorgesehen. TCP 5038 und
> TCP 5039 nicht per Router/Portweiterleitung ins Internet freigeben.

## ADB

```sh
adb devices -l
```

Ist beim Installieren noch kein LTE-Modem angeschlossen, ist das nur eine Warnung. Die Softwareinstallation selbst kann trotzdem abgeschlossen werden.

## Weiterführende Dokumentation

- [Projekt-README](../../README.md)
- [Endanwender-Anleitung](../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)
- [Firmware-Manifest](../../docs/HowTo/FIRMWARE_MANIFEST.md)
- [LTE-/Firmware-Backup](../../docs/HowTo/firmware_backup_lte.md)
- [DTU OTA Runner](../../docs/DTU_OTA_RUNNER.md)
