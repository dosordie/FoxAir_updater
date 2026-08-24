# Linux / Raspberry Pi

Der Linux-Installer richtet den FoxAir-Updater auf Raspberry Pi OS sowie anderen
Debian-/Ubuntu-basierten Systemen ein. Für Endanwender wird nur der tatsächlich
benötigte Linux-Teil des Repositorys ausgecheckt.

## Schnellinstallation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
wget -O install.sh https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Der Installer verwendet `sudo` nur dort, wo Systemrechte benötigt werden.
Standardmäßig wird nach `~/FoxAir_updater` installiert.

## Endanwender-Struktur

Nach der Installation sieht die relevante Struktur so aus:

```text
~/FoxAir_updater/
├── firmware/          # hier Firmware + Manifest ablegen
├── foxair-updater     # einfacher Endanwender-Launcher
├── docs/HowTo/
├── tools/phnix_ota/   # interne OTA-Werkzeuge
└── updater/           # gemeinsame Module + Linux-Installer
```

Der Ordner `firmware/` wird lokal durch den Installer erstellt und ist über
`.gitignore` vollständig von Git ausgeschlossen. Er wird weder hochgeladen noch
bei einem Update verändert oder gelöscht.

## Schlanker Git-Checkout

Der Installer verwendet `git sparse-checkout`. Beim Endanwender werden nur
folgende Projektbereiche ausgecheckt:

```text
updater/common
updater/linux
tools/phnix_ota
docs/HowTo
```

Dateien im Projekt-Hauptverzeichnis wie `foxair-updater`, `.gitignore` und
`README.md` bleiben ebenfalls verfügbar. Entwicklungsbereiche wie `devtools`,
`tests`, `docs/reverse_engineering`, `updater/windows` und
`firmware_manifests` erscheinen im normalen Linux-Endanwender-Checkout nicht.
Sie bleiben weiterhin im GitHub-Repository für Entwicklung und Dokumentation
verfügbar.

## Was der Installer erledigt

- prüft `python3`, `adb`, `lsusb`, `git` und CA-Zertifikate;
- installiert fehlende Pakete auf Debian/Ubuntu/Raspberry Pi OS per `apt-get`;
- verlangt Python 3.10 oder neuer;
- installiert einen schlanken Sparse-Checkout nach `~/FoxAir_updater`;
- aktualisiert eine vorhandene Installation per `git pull --ff-only`;
- überschreibt keine lokal geänderten Projektdateien;
- erstellt den lokalen Ordner `~/FoxAir_updater/firmware`;
- setzt die benötigten lokalen Dateirechte;
- installiert die udev-Regel für das PHNIX-LTE-Modem `1e0e:9001`;
- lädt die udev-Regeln neu und startet den ADB-Server neu;
- prüft Controller, Manifestwerkzeug und Launcher;
- zeigt zum Abschluss `adb devices -l` und den installierten Git-Commit an.

Die USB-Regel lautet bewusst einfach:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"
```

Der Updater ist für einen kontrollierten, kurzfristigen internen Einsatz
gedacht. Deshalb ist keine zusätzliche `plugdev`-Gruppenverwaltung und kein
Logout/Login notwendig.

## Firmware bereitstellen

Firmware und zugehöriges Manifest werden **nicht** von GitHub geladen. Beide
Dateien werden lokal nach `~/FoxAir_updater/firmware/` kopiert, zum Beispiel:

```text
~/FoxAir_updater/firmware/FW3.4.bin
~/FoxAir_updater/firmware/FW3.4.json
```

Der Firmwarepfad ist nicht fest auf `tools/phnix_ota` codiert. Wenn im Manifest
zum Beispiel `"firmware_file": "FW3.4.bin"` steht, sucht der Controller die
Firmware automatisch im selben Verzeichnis wie das Manifest. Deshalb genügt
für den normalen Ablauf die gemeinsame Ablage beider Dateien im lokalen
`firmware/`-Ordner.

## Bedienung

In das Projektverzeichnis wechseln:

```sh
cd ~/FoxAir_updater
```

Hilfe anzeigen:

```sh
./foxair-updater --help
```

Status des Originalsystems prüfen:

```sh
./foxair-updater status
```

Dry-Run einer Firmware durchführen:

```sh
./foxair-updater check FW3.4.json
```

Wird nur ein Dateiname angegeben, sucht der Launcher das Manifest automatisch
unter `./firmware/`. Ein vollständiger Pfad ist ebenfalls möglich.

Ein echtes Update bleibt bewusst explizit bestätigt:

```sh
./foxair-updater update FW3.4.json --confirm
```

Der Entwicklungs-/Abnahmetest für die bereits installierte V3.3 wird ebenfalls
über den Launcher angeboten. Ein passiver Logger muss dabei tatsächlich laufen:

```sh
./foxair-updater same-version FW3.3.json --confirm
```

Der Launcher setzt intern die absichtlich langen Sicherheitsbestätigungen
`PHNIX-C350-SAME-V33` und `PASSIVE-LOGGER-RUNNING`; `--confirm` bleibt als
bewusste Bestätigung des Anwenders erhalten.

Originalzustand vor begonnenem Firmwaretransfer wiederherstellen:

```sh
./foxair-updater restore
```

Installierten Git-Stand anzeigen:

```sh
./foxair-updater version
```

Die eigentliche Sicherheitslogik bleibt vollständig im bestehenden
`phnix_local_ota_controller.py`; der Launcher dupliziert keine OTA-Logik.

## Manifest erzeugen

Liegt beispielsweise `FW3.4.bin` unter `~/FoxAir_updater/firmware/`, kann das
passende Manifest direkt über den Launcher erzeugt werden:

```sh
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

Ohne `--output` wird automatisch `FW3.4.json` neben der Firmware erzeugt.
`wire_version` wird aus der Display-Version abgeleitet (`V3.4` -> `0034`) und
muss nicht angegeben werden. Der Manifest-Generator berechnet Größe, MD5 und
SHA-256 selbst und validiert anschließend die Felder.

Ein eigener Ausgabepfad ist weiterhin möglich:

```sh
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063 \
  --output /tmp/FW3.4.json
```

## Vorhandene Installation aktualisieren

Die bereits installierte `install.sh` kann gleichzeitig als Updater verwendet
werden:

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Der Installer zieht neue Projektdateien nur per Fast-Forward und richtet danach
den Sparse-Checkout erneut ein. Nicht versionierte Dateien im lokalen
`firmware/`-Ordner bleiben unangetastet. Es werden absichtlich weder
`git reset --hard` noch ein Repository-Cleanup ausgeführt.

## ADB

ADB-Verbindung direkt prüfen:

```sh
adb devices -l
```

Ist beim Installieren noch kein LTE-Modem angeschlossen, wird dies nur als
Warnung ausgegeben. Die Softwareinstallation selbst gilt trotzdem als
abgeschlossen.

Weitere Details zum eigentlichen OTA-Ablauf stehen in
`docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`.
