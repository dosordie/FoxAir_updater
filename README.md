# FoxAir Updater

Experimentelles Firmware-Update- und Reverse-Engineering-Tool für FoxAir-/PHNIX-Wärmepumpen.

> [!CAUTION]
> ## Experimentell – echtes Versionsupdate noch nicht live validiert
>
> Dieses Projekt befindet sich im **Entwicklungs- und Teststadium**.
> Ein vollständiges Firmwareupdate von einer installierten Mainboard-Version auf
> eine andere Version wurde auf realer Hardware **noch nicht erfolgreich durchgeführt
> und bestätigt**.
>
> Der reale OTA-Ablauf wurde bislang nur mit **V3.3 → V3.3** getestet. Das Mainboard
> hat dieses Firmwareangebot erwartungsgemäß abgelehnt, weil V3.3 bereits installiert
> war. Dabei wurden keine Firmwareblöcke geschrieben.
>
> Damit ist insbesondere **nicht nachgewiesen**, dass ein echtes Update wie
> **V3.3 → V3.4** bereits sicher oder vollständig funktionsfähig ist.
>
> Bei der Verwendung kann etwas schiefgehen. Im ungünstigsten Fall können Mainboard,
> LTE-Modem oder der normale Betrieb der Wärmepumpe beeinträchtigt werden und ein
> manueller Recovery- oder Reparatureingriff erforderlich werden.
>
> **Nutzung ausschließlich auf eigenes Risiko.** Jeder Anwender muss selbst
> entscheiden, ob er dieses experimentelle Werkzeug verwendet und die möglichen
> Folgen verantworten kann. Der Ersteller übernimmt, **soweit gesetzlich zulässig**,
> keine Gewährleistung, Sachmängelhaftung oder Haftung für Schäden oder Folgeschäden,
> die aus der Verwendung oder Fehlfunktion dieses Tools entstehen.

Das Repository trennt Firmwareanalyse und Update-Werkzeuge bewusst vom Projekt
[`FoxAir_Control`](https://github.com/dosordie/FoxAir_Control), das weiterhin für
normale Steuerung, Modbus-Auswertung und Diagnose zuständig ist.

## Aktueller Stand

### Linux / Raspberry Pi

Der Linux-/Raspberry-Pi-Weg ist über einen Installer und einen einfachen Launcher nutzbar:

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST --confirm
./foxair-updater restore
./foxair-updater manifest FIRMWARE ...
./foxair-updater version
```

Für Entwicklung und Abnahme existiert zusätzlich:

```text
./foxair-updater same-version MANIFEST --confirm
```

### Windows

Zusätzlich gibt es eine **experimentelle Windows-GUI** als Portable-ZIP und Setup-EXE.
Die aktuelle Entwicklungsfassung ist **v0.1.4**.

Öffentliche Windows-Versionen werden hier bereitgestellt:

**[FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)**

> [!IMPORTANT]
> Der Windows-Pfad wurde bereits real für **ADB-Verbindung, Remote-ADB über Raspberry Pi,
> Originalstatus und read-only LTE-Backup/Firmware-Download** getestet. Diese Funktionen
> arbeiten wie vorgesehen.
>
> Ein **echtes Firmwareupdate auf eine andere Mainboard-Version wurde mit der Windows-GUI
> noch nicht live durchgeführt**. Dry-Run, Update-, Recovery- und Same-Version-Funktionen
> bleiben daher experimentell, auch wenn sie denselben gemeinsamen Controller verwenden.

Die Windows-Version refaktoriert die gemeinsame OTA-Logik bewusst nicht. Details stehen unter
[`updater/windows/README.md`](updater/windows/README.md).

Windows-Releases werden über einen separaten manuellen Actions-Workflow veröffentlicht.
Unter **Actions → Release Windows** wird nur die Zielversion eingegeben; anschließend erscheinen
Portable-ZIP und Setup-EXE auf der normalen GitHub-Releases-Seite. Die Windows-Tags verwenden
das Schema `windows-v...`.

## Linux / Raspberry Pi installieren

Als normaler Benutzer ausführen, **nicht** mit `sudo` starten:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Der Installer:

- prüft beziehungsweise installiert `python3`, `adb`, `usbutils`, `git` und CA-Zertifikate;
- verlangt Python 3.10 oder neuer;
- verwendet einen schlanken Git-Sparse-Checkout;
- richtet den USB-Zugriff für das PHNIX-LTE-Modem `1e0e:9001` ein;
- berücksichtigt ein kurzzeitig `offline` erscheinendes ADB-Gerät und versucht `adb reconnect`;
- erstellt den lokalen Firmwareordner `~/FoxAir_updater/firmware`;
- prüft Controller, Manifestwerkzeug und Launcher.

Ausführliche Updater-Anleitung:
[`docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`](docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)

Anschluss des LTE-Modems, Micro-USB, Windows-/Linux-ADB und Backup:
[`docs/HowTo/firmware_backup_lte.md`](docs/HowTo/firmware_backup_lte.md)

## Windows GUI v0.1.4

Die Windows-Version verwendet die gemeinsame OTA-Quelle weiterhin unverändert:

```text
FoxAir_Updater.exe
        ↓
private Python Runtime
        ↓
Windows-Sicherheitswrapper
        ↓
phnix_local_ota_controller_core.py
        ↑ bytegleiche Kopie von
          tools/phnix_ota/phnix_local_ota_controller.py
        ↓
extern ausgewählte adb.exe
        ↓
PHNIX LTE-Modem
```

Die zusätzliche Windows-Sicherheitshülle bildet nur die Launcher-Funktionen nach, die unter
Linux außerhalb des Controllers liegen: Full-Abgleich direkt vor einem echten Update sowie
Sicherung und Wiederherstellung eines eventuell vorhandenen LTE-Firmware-Caches. Der gemeinsame
Controller selbst wird dafür **nicht verändert oder refaktoriert**.

**ADB wird nicht mitgeliefert.** Die GUI enthält einen Link auf die offizielle Google-Seite
für Android SDK Platform Tools und erlaubt anschließend die Auswahl einer vorhandenen `adb.exe`.

Die GUI bietet unter anderem:

- lokale ADB-Verbindung oder optional Remote-ADB über einen Raspberry Pi;
- ADB-Erkennung und `adb reconnect` bei kurzzeitigem `offline`;
- **real getestetes read-only LTE-Backup/Firmware-Download per `adb pull`**;
- frei wählbaren Backup-Zielordner und **Zielordner öffnen** im Windows-Explorer;
- Originalstatus mit farbiger OK-/Fehleranzeige;
- Dry-Run;
- vollständigen, weiterhin **nicht live validierten** Update-Aufruf über den bestehenden Controller;
- Restore über den bestehenden Controller;
- Full-Firmware-/Manifest-Abgleich unmittelbar vor einem echten Update;
- Sicherung des ursprünglichen LTE-Firmware-Caches analog zum Linux-Launcher;
- Manifest-Vorschau mit der vorhandenen `--full --show`-Funktion;
- automatische Full-Manifest-Erzeugung sowie manuellen Fallback;
- Auswahl originaler Firmwaredateien auch **ohne `.bin`-Endung**;
- Gleichversionstest im Bereich „Erweitert“;
- Loganzeige, Logexport und Protokoll leeren;
- dasselbe Programmlogo wie `FoxAir_Control` für EXE, Fenster und Setup.

Beim Portable-Build werden der gemeinsame Controller, Runtime-Helfer und `updater/common/*.py`
bytegleich aus dem Repository kopiert und mit `fc /b` geprüft. Damit entsteht bewusst keine
zweite Windows-OTA-Implementierung.

### Remote ADB

Für einen Raspberry Pi mit per USB angeschlossenem LTE-Modem kann der ADB-Server kurzfristig
im lokalen LAN gestartet werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Zum Beenden auf dem Raspberry Pi **Strg+C** drücken. In der Windows-GUI werden nur IP-Adresse
und Port eingetragen. Intern setzt die GUI `ADB_SERVER_SOCKET`, sodass auch der unveränderte
gemeinsame Controller den entfernten ADB-Server nutzt.

Build-/Release-Anleitung:
[`updater/windows/README.md`](updater/windows/README.md)

## Firmware-Backup / Firmware-Download

Für Windows ist inzwischen die grafische Backup-Funktion der empfohlene Weg. Die vollständige
Anleitung einschließlich SIMCom-Treiber, ADB, Windows-GUI, manueller PowerShell-Alternative und
Linux/Raspberry Pi steht hier:

**[`docs/HowTo/firmware_backup_lte.md`](docs/HowTo/firmware_backup_lte.md)**

Die Backup-Funktion ist read-only und verwendet ausschließlich `adb pull`. Firmware- und
Datendateien aus dem LTE-Modem werden nicht automatisch veröffentlicht und dürfen insbesondere
nicht in dieses öffentliche Repository eingecheckt werden.

## Firmware bereitstellen

Firmwaredateien werden **nicht über dieses öffentliche GitHub-Repository verteilt**.
Der Installer lädt keine Mainboard-Firmware herunter.

Firmware und Manifest werden unter Linux lokal gemeinsam abgelegt, zum Beispiel:

```text
~/FoxAir_updater/firmware/FW3.4.bin
~/FoxAir_updater/firmware/FW3.4.json
```

Unter Windows können originale Firmwaredateien ohne Umbenennung über die Manifest-Registerkarte
analysiert werden. Die Datei muss keine `.bin`-Endung besitzen.

Ein Manifest kann unter Linux lokal erzeugt werden:

```sh
cd ~/FoxAir_updater
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063
```

Empfohlen ist inzwischen die Full-Variante, welche die Firmwareidentität direkt aus dem Image
liest. Unter Windows stehen **Vorschau aus Firmware (Full / Show)** und
**Manifest automatisch erzeugen (Full)** direkt in der GUI zur Verfügung.

## Repository-Struktur

```text
FoxAir_updater/
├─ docs/
│  ├─ reverse_engineering/  # Mainboard-, OTA- und LTE-Analyse
│  └─ HowTo/                # Anwender- und Testanleitungen
├─ firmware_manifests/      # geprüfte/analysierte Manifest-Metadaten
├─ updater/
│  ├─ common/               # gemeinsam genutzte Python-Module
│  ├─ linux/                # Linux-/Raspberry-Pi-Installer
│  └─ windows/              # Windows-GUI, Portable-/Setup-Build
├─ tools/phnix_ota/         # OTA-Controller, Runtime-Helfer, Manifestwerkzeug
├─ devtools/                # Simulatoren und Laborwerkzeuge
├─ tests/                   # Regressionstests
└─ foxair-updater           # einfacher Linux-Endanwender-Launcher
```

Der Linux-Installer checkt für Endanwender bewusst nur die benötigten Bereiche aus.
`devtools`, `tests`, `docs/reverse_engineering`, `updater/windows` und
`firmware_manifests` bleiben auf GitHub, erscheinen aber nicht im normalen
Linux-Endanwender-Checkout.

## Technische Sicherheitsgrenze

Der aktuelle Live-Pfad ist für genau den untersuchten Originaldienst `phnixIot4G`
ausgelegt:

```text
Build-ID: af4dcae12639bedce833ee5efa5da009777b6319
SHA-256:  7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7
```

Der Controller arbeitet fail-closed. Nicht eindeutig terminale Zustände führen zu
einem geschützten `Guarded Hold`, statt automatisch aggressiv aufzuräumen.

Der bekannte V3.3-Gleichversionstest prüft den frühen Handshake und die sichere
Ablehnung einer bereits installierten Version. Er beweist ausdrücklich nicht den
späteren C5A8-Firmware-Schreibpfad eines echten Versionswechsels.

## Projektumfang

Enthalten sind unter anderem:

- Firmware-Reverse-Engineering;
- PHNIX-LTE-Modem-/Runtime-Analyse, soweit für OTA relevant;
- OTA-/IAP-Protokollanalyse;
- Firmwareupdate-, Recovery- und Validierungswerkzeuge;
- Manifest- und Hashprüfung;
- Simulatoren, Laborwerkzeuge und Regressionstests.

Nicht Schwerpunkt dieses Repositorys sind:

- die normale FoxAir-Control-GUI;
- normale Endanwender-Steuerlogik;
- allgemeine Modbus-Werkzeuge ohne direkten Firmware-/Updater-Bezug.

## Lizenz

Dieses Repository steht unter der **GNU General Public License v3.0**,
SPDX-Kennung **`GPL-3.0-only`**.

Siehe [`LICENSE`](LICENSE).

Weitergabe und Änderungen sind damit erlaubt, abgeleitete Werke müssen bei
Weitergabe jedoch ebenfalls unter den Bedingungen der GPLv3 stehen und der
zugehörige Quellcode muss gemäß den Lizenzbedingungen verfügbar gemacht werden.

Die GPL enthält ausdrücklich einen Gewährleistungs- und Haftungsausschluss. Die
zusätzlichen technischen Warnhinweise oben bleiben davon unabhängig wichtig, weil
dieses Projekt einen experimentellen Firmware-Schreibpfad für reale Hardware enthält.
