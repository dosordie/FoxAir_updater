# Linux / Raspberry Pi

Der Linux-Installer richtet den FoxAir-Updater auf Raspberry Pi OS sowie anderen
Debian-/Ubuntu-basierten Systemen ein. Die eigentlichen OTA-Werkzeuge bleiben
unter `tools/phnix_ota/`; gemeinsam genutzte Python-Module liegen unter
`updater/common/`.

## Schnellinstallation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
wget -O install.sh https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Der Installer verwendet `sudo` nur dort, wo Systemrechte benötigt werden.
Standardmäßig wird das Repository nach `~/FoxAir_updater` installiert.

## Was der Installer erledigt

- prüft `python3`, `adb`, `lsusb`, `git` und CA-Zertifikate;
- installiert fehlende Pakete auf Debian/Ubuntu/Raspberry Pi OS per `apt-get`;
- verlangt Python 3.10 oder neuer;
- klont das vollständige Repository nach `~/FoxAir_updater`;
- aktualisiert eine vorhandene Installation per `git pull --ff-only`;
- überschreibt keine lokal geänderten Projektdateien;
- setzt die benötigten lokalen Dateirechte;
- installiert die udev-Regel für das PHNIX-LTE-Modem `1e0e:9001`;
- lädt die udev-Regeln neu und startet den ADB-Server neu;
- prüft die Python-Werkzeuge mit `--help`;
- zeigt zum Abschluss `adb devices -l` und den installierten Git-Commit an.

Die USB-Regel lautet bewusst einfach:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"
```

Der Updater ist für einen kontrollierten, kurzfristigen internen Einsatz
gedacht. Deshalb ist keine zusätzliche `plugdev`-Gruppenverwaltung und kein
Logout/Login notwendig.

## Vorhandene Installation aktualisieren

Die bereits installierte `install.sh` kann gleichzeitig als Updater verwendet
werden:

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Wenn die Installation bereits aktuell ist, bleibt der Checkout unverändert.
Nicht versionierte Dateien wie lokal abgelegte Firmwaredateien werden von Git
nicht gelöscht. Der Installer führt absichtlich weder `git reset --hard` noch
ein Repository-Cleanup aus.

## Nach der Installation

ADB-Verbindung prüfen:

```sh
adb devices -l
```

Status des PHNIX-Systems prüfen:

```sh
cd ~/FoxAir_updater
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  run --check status
```

Ist beim Installieren noch kein LTE-Modem angeschlossen, wird dies nur als
Warnung ausgegeben. Die Softwareinstallation selbst gilt trotzdem als
abgeschlossen.

## Firmware

Der Installer lädt **keine Firmwaredateien und keine Firmware-Manifeste**
automatisch herunter. Firmware und Manifest bleiben bewusst getrennt vom
Updater und müssen als geprüfte Dateien bereitgestellt werden.

Auch lokale OTA-Zustände werden durch den Installer nicht verändert oder
gelöscht.

Weitere Schritte und die eigentlichen Updatebefehle stehen in
`docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`.

## Gemeinsame Architektur

Linux, Raspberry Pi und die geplante Windows-Oberfläche verwenden dieselben
Manifest- und Protokollbausteine aus `updater/common`. Firmware-spezifische
Werte sollen nicht in einem plattformspezifischen Installer dupliziert oder
hart codiert werden.
