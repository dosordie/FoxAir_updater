# Linux / Raspberry Pi

Stand: 29. August 2026

Der Linux-Installer richtet den FoxAir Updater auf Raspberry Pi OS sowie anderen Debian-/Ubuntu-basierten Systemen ein. Der Linux-Weg verwendet denselben gemeinsamen OTA-Controller wie die Windows-Version.

> [!IMPORTANT]
> Der vollständige Mainboard-Firmwarewechsel **V3.3 → V3.4** wurde auf realer Hardware erfolgreich durchgeführt. Die neue Firmware wurde über C36E Status 5 / Board-Step 12 und anschließend C544-Version `0034` bestätigt.
>
> Andere Firmwarestände und Hardwarevarianten sind weiterhin nicht in gleicher Tiefe live validiert. Firmwareupdates erfolgen auf eigenes Risiko.

## Schnellinstallation

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
wget -O install.sh https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Der Installer verwendet `sudo` nur dort, wo Systemrechte benötigt werden. Standardmäßig wird nach `~/FoxAir_updater` installiert.

## Endanwender-Struktur

```text
~/FoxAir_updater/
├── firmware/          # lokale Firmware + Manifest
├── foxair-updater     # Endanwender-Launcher
├── docs/HowTo/
├── tools/phnix_ota/   # gemeinsame OTA-Werkzeuge
└── updater/           # gemeinsame Module + Linux-Installer
```

Der Ordner `firmware/` wird lokal durch den Installer erstellt und ist über `.gitignore` von Git ausgeschlossen. Er wird bei einem normalen Update des Repository-Checkouts weder hochgeladen noch gelöscht.

## Schlanker Git-Checkout

Der Installer verwendet `git sparse-checkout`. Beim Endanwender werden nur die benötigten Bereiche ausgecheckt:

```text
updater/common
updater/linux
tools/phnix_ota
docs/HowTo
```

Dateien im Projekt-Hauptverzeichnis wie `foxair-updater`, `.gitignore` und `README.md` bleiben ebenfalls verfügbar. Entwicklungsbereiche wie `devtools`, `tests`, `docs/reverse_engineering`, `updater/windows` und `firmware_manifests` erscheinen im normalen Linux-Endanwender-Checkout nicht.

## Was der Installer erledigt

- prüft `python3`, `adb`, `lsusb`, `git` und CA-Zertifikate;
- installiert fehlende Pakete auf Debian/Ubuntu/Raspberry Pi OS per `apt-get`;
- verlangt Python 3.10 oder neuer;
- installiert einen schlanken Sparse-Checkout nach `~/FoxAir_updater`;
- aktualisiert eine vorhandene Installation per `git pull --ff-only`;
- überschreibt keine lokal geänderten Projektdateien;
- erstellt `~/FoxAir_updater/firmware`;
- setzt benötigte Dateirechte;
- installiert die udev-Regel für das PHNIX-LTE-Modem `1e0e:9001`;
- lädt die udev-Regeln neu und startet ADB neu;
- prüft Controller, Manifestwerkzeug und Launcher;
- zeigt zum Abschluss `adb devices -l` und den installierten Git-Commit an.

Die USB-Regel lautet:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"
```

## Firmware bereitstellen

Firmware und Manifest werden **nicht** automatisch von GitHub geladen. Beide Dateien werden lokal nach `~/FoxAir_updater/firmware/` kopiert, zum Beispiel:

```text
~/FoxAir_updater/firmware/FW3.4.bin
~/FoxAir_updater/firmware/FW3.4.json
```

Wenn im Manifest `"firmware_file": "FW3.4.bin"` steht, sucht der Controller die Firmware im selben Verzeichnis wie das Manifest.

## Bedienung

```sh
cd ~/FoxAir_updater
```

Hilfe:

```sh
./foxair-updater --help
```

Originalzustand read-only prüfen:

```sh
./foxair-updater status
```

Dry-Run:

```sh
./foxair-updater check FW3.4.json
```

Echtes Update:

```sh
./foxair-updater update FW3.4.json --confirm
```

Restore ist ausschließlich für einen Zustand **vor begonnenem C5A8-Firmwaretransfer** vorgesehen:

```sh
./foxair-updater restore
```

Installierten Git-Stand anzeigen:

```sh
./foxair-updater version
```

Die eigentliche Sicherheitslogik bleibt im gemeinsamen `phnix_local_ota_controller.py`; der Launcher dupliziert keine OTA-Logik.

## MQTT beim normalen Vollupdate

MQTT bleibt beim normalen Vollupdate **standardmäßig verbunden**.

Die frühere MQTT-Isolierung ist nur noch ein optionaler Testmodus des Controllers (`--isolate-mqtt` beziehungsweise `--update-no-mqtt`). Sie ist für normale Updates nicht empfohlen.

Der Originaldienst besitzt einen Rebootpfad, wenn der Aliyun-MQTT-Client intern länger als 1800 Sekunden als offline gilt. Diese 1800 Sekunden starten erst, nachdem der MQTT-SDK die Verbindung intern als offline bewertet; eine stille Firewall-DROP-Sperre kann davor mehrere Keepalive-Zyklen benötigen.

Es gibt keinen bekannten OTA-Sonderzweig, der diesen Rebootpfad während eines Mainboardupdates deaktiviert.

## Fortschritt und terminaler Erfolg

Während C5A8 zeigt der Controller den persistenten `offset/length`-Fortschritt des Originaldienstes.

> [!WARNING]
> **100 % bedeutet nur, dass alle Firmwaredaten übertragen wurden.** Das Mainboard muss anschließend noch die Staging-Prüfung und Promotion/Commit-Phase abschließen.

Beim realen V3.3→V3.4-Lauf wurden beobachtet:

```text
C5A8 vollständig
→ C36E Status 3
→ Mainboard Flash/Promotion
→ C36E Status 5
→ Board-Step 12
→ C544 Version 0034
```

Gemessene Zeiten:

- C5A8-Transfer ca. **28:56 min**;
- letzter C5A8 → Status 5 ca. **5:16 min**;
- vollständiger beobachteter Ablauf bis zur ersten neuen C544-Meldung rund **35 min**.

Nach dem terminalen Mainboardergebnis wartet der Controller bis zu **120 Sekunden** auf einen wieder vollständig normalen LTE-/Cloudzustand.

## Gleichversionstest

Der Entwicklungs-/Abnahmetest für eine bereits installierte V3.3 bleibt im Launcher verfügbar:

```sh
./foxair-updater same-version FW3.3.json --confirm
```

Ein passiver Logger muss für diesen speziellen Labortest tatsächlich laufen.

Der reale V3.3→V3.3-Test endete wie erwartet vor C357/C5A8. Dieser Test ist heute ein Regressionstest des frühen Handshakes und nicht mehr die höchste erreichte Live-Teststufe.

## Manifest erzeugen

Empfohlen ist zuerst die vollständig lesende Vorschau:

```sh
./foxair-updater manifest FW3.4.bin --full --show
```

Danach kann das Manifest automatisch erzeugt werden:

```sh
./foxair-updater manifest FW3.4.bin --full
```

Alternativ können bekannte Sollwerte explizit angegeben werden:

```sh
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

Ohne `--output` wird das JSON neben der Firmware erzeugt. Größe, MD5 und SHA-256 werden vom Manifestwerkzeug berechnet.

Details:

[`../../docs/HowTo/FIRMWARE_MANIFEST.md`](../../docs/HowTo/FIRMWARE_MANIFEST.md)

## Vorhandene Installation aktualisieren

```sh
cd ~/FoxAir_updater
bash updater/linux/install.sh
```

Der Installer zieht Änderungen nur per Fast-Forward und richtet den Sparse-Checkout erneut ein. Nicht versionierte Dateien im lokalen `firmware/`-Ordner bleiben unangetastet. Es werden weder `git reset --hard` noch ein Repository-Cleanup ausgeführt.

## ADB

```sh
adb devices -l
```

Ist beim Installieren noch kein LTE-Modem angeschlossen, wird dies nur als Warnung ausgegeben. Die Softwareinstallation selbst kann trotzdem abgeschlossen werden.

## Weiterführende Dokumentation

- [`../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)
- [`../../docs/HowTo/firmware_backup_lte.md`](../../docs/HowTo/firmware_backup_lte.md)
- [`../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md`](../../docs/RELEASE_NOTES_WINDOWS_v0.3.9.md)
- Live-Bericht im vollständigen GitHub-Repository: `docs/reverse_engineering/PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`