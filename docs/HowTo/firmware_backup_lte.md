# Firmware-Backup des LTE-Modems über Micro-USB

Stand: 29. August 2026

Diese Anleitung beschreibt, wie man sich per **Micro-USB** mit dem LTE-Modem verbindet und Firmware-/Statusdateien mit **ADB (Android Debug Bridge, Bestandteil der Android SDK Platform Tools)** sichert.

> [!NOTE]
> Es gibt drei alternative Bedienwege:
> - **Windows – empfohlen:** FoxAir Updater mit grafischer Oberfläche;
> - **Windows – manuell:** PowerShell und direkte `adb.exe`-Befehle;
> - **Linux / Raspberry Pi:** `adb` beziehungsweise der Linux-Launcher `./foxair-updater`.
>
> Es muss **nur einer dieser Wege** verwendet werden.

> [!IMPORTANT]
> Der Windows-Backup-Pfad wurde real getestet. ADB-Verbindung, Originalstatus und das read-only Backup der LTE-Dateien funktionieren sowohl mit lokal angeschlossenem Modem als auch über Remote-ADB zum Raspberry Pi.
>
> Ein vollständiger Firmwarewechsel **V3.3 → V3.4** wurde inzwischen ebenfalls erfolgreich durchgeführt; das ist für das hier beschriebene Backup jedoch **nicht erforderlich**.

> [!NOTE]
> Die Backup-Funktionen verändern nichts am LTE-Modem. Die Windows-GUI verwendet dafür ausschließlich `adb pull`; bei den manuellen Wegen werden dieselben Dateien ebenfalls nur heruntergeladen.

> [!WARNING]
> Ausgelesene Firmware- und Datendateien **nicht öffentlich hochladen oder weiterveröffentlichen**. Sie können herstellerspezifische Software, Konfigurationsdaten oder andere nicht für die Veröffentlichung bestimmte Inhalte enthalten.

## 1. LTE-Modem öffnen und USB-Port freilegen

- Der Deckel des LTE-Modems ist nur gesteckt und kann vorsichtig abgenommen werden.
- Im **Micro-USB-Port** kann sich Versiegelungs-/Vergussmasse befinden.
- Diese lässt sich vorsichtig z. B. mit einer Pinzette entfernen.
- Dabei USB-Port, Kontakte und Platine nicht beschädigen.

### Geöffnetes LTE-Modem

![Geöffnetes LTE-Modem](lte1.jpeg)

### Micro-USB-Anschluss mit Vergussmasse

![Micro-USB-Anschluss mit Vergussmasse](lte2.jpeg)

> [!CAUTION]
> Den Micro-USB-Stecker **nicht mit Gewalt einstecken**. Da sich die Vergussmasse nur schwer vollständig entfernen lässt, wird voraussichtlich ein gewisser Widerstand zu spüren sein. Den Stecker nur so weit wie ohne Gewalt möglich einstecken, bis das Betriebssystem die USB-Verbindung erkennt.

## 2. Windows-Treiber installieren und USB-Verbindung prüfen

Benötigt werden die SIMCom USB-Treiber:

- [SIMCOM Windows USB Drivers V1.0.2](https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip)

ZIP-Datei entpacken und die passenden Windows-Treiber installieren. Danach das LTE-Modem über Micro-USB mit dem PC verbinden.

### Geräte-Manager prüfen

1. **Geräte-Manager** öffnen.
2. LTE-Modem per Micro-USB verbinden.
3. Beobachten, ob beim Ein-/Ausstecken Geräte erscheinen oder verschwinden.
4. Besonders unter **Anschlüsse (COM & LPT)**, **Modems**, **USB-Controller** bzw. **Andere Geräte** nach SIMCom-/Android-/ADB-Geräten suchen.
5. Bei Warnsymbol/unbekanntem Gerät den SIMCom-Treiber installieren bzw. aktualisieren.

## 3. Android SDK Platform Tools / ADB installieren

ADB ist Bestandteil der Android SDK Platform Tools:

- [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools?hl=de#downloads)

**ADB wird aus Lizenz- und Distributionsgründen nicht mit dem FoxAir Updater mitgeliefert.**

Für Windows die ZIP-Datei herunterladen und z. B. nach

```text
C:\platform-tools
```

entpacken.

# 4. Windows – empfohlen: FoxAir Updater GUI

Die aktuelle Windows-Version ist als Portable-ZIP und Setup-EXE verfügbar:

- [FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)

Aktueller dokumentierter Stand: **v0.3.9**.

Die GUI bietet unter anderem:

- lokale ADB-Verbindung direkt per USB;
- Remote-ADB über Raspberry Pi;
- automatische/manuelle ADB-Reconnect-Funktion;
- read-only Backup per `adb pull`;
- frei wählbaren Zielordner;
- Beschreibung der Backup-Dateien;
- Button **Zielordner öffnen**.

> [!NOTE]
> Die Windows-Builds sind derzeit nicht kommerziell code-signiert. Windows SmartScreen kann deshalb beim ersten Start **„Der Computer wurde durch Windows geschützt“** anzeigen. Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite geladen wurde, **Weitere Informationen** und danach **Trotzdem ausführen** wählen.

## 4.1 ADB in der GUI einrichten

1. FoxAir Updater starten.
2. Registerkarte **Verbindung** öffnen.
3. Falls `adb.exe` nicht automatisch gefunden wird, **adb.exe auswählen…** verwenden.
4. Die zuvor entpackte `adb.exe` auswählen.
5. **ADB prüfen** anklicken.
6. Das LTE-Modem muss im Status `device` erscheinen.

Auch im Remote-Modus wird lokal unter Windows weiterhin eine `adb.exe` als Client benötigt.

## 4.2 Backup erstellen

1. Registerkarte **Backup** öffnen.
2. Zielordner mit **Zielordner…** auswählen.
3. Gewünschte Dateien auswählen.
4. **Backup erstellen** anklicken.
5. Nach erfolgreichem Abschluss **Zielordner öffnen** verwenden.

![FoxAir Updater – Backup](../DTU_2_Backup.png)

Die GUI kann folgende Dateien sichern:

| Auswahl | Quelle auf dem LTE-Modem | Bedeutung |
|---|---|---|
| Firmware | `/cache/phnixIot_device_OTA` | aktuell im LTE-Cache vorhandene OTA-/Firmwaredatei |
| OTA_INFO | `/data/phnixIot_device_OTA_INFO` | persistenter OTA-/Resume-Zustand |
| Statistik | `/data/phnixIot_device_statisic` | Betriebs-, Kommunikations-, Reset- und OTA-Zähler |
| Originaldienst `phnixIot4G` | `/data/phnixIot4G` | originale ausführbare PHNIX-LTE-Programmdatei |

Bei Auswahl aller Optionen landen im Zielordner entsprechend:

```text
phnixIot_device_OTA
phnixIot_device_OTA_INFO
phnixIot_device_statisic
phnixIot4G
```

Die Datei `/cache/phnixIot_device_OTA` ist nur vorhanden, solange sie vom originalen PHNIX-Dienst noch nicht entfernt oder durch einen späteren OTA-Auftrag ersetzt wurde.

## 4.3 Remote ADB über Raspberry Pi

Auf dem Raspberry Pi:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Danach in der Windows-GUI:

1. **Remote – ADB-Server auf Raspberry Pi** auswählen.
2. IP-Adresse eintragen.
3. Port `5038` verwenden.
4. **ADB prüfen** anklicken.

Der Pi-Befehl bleibt im Vordergrund und wird mit **Strg+C** beendet.

> [!IMPORTANT]
> Den Remote-ADB-Port nur kurzfristig und nur in einem vertrauenswürdigen lokalen Netz freigeben.

# 5. Windows – manuelle PowerShell-Alternative

Wer die GUI nicht verwenden möchte, kann direkt mit `adb.exe` arbeiten.

Im `platform-tools`-Ordner PowerShell/Terminal öffnen.

ADB prüfen:

```powershell
.\adb.exe devices
```

Bei funktionierender Verbindung erscheint eine Geräte-ID mit Status `device`.

Optional Shell öffnen:

```powershell
.\adb.exe shell
```

Beenden mit:

```text
exit
```

## 5.1 Firmware manuell sichern

```powershell
.\adb.exe pull /cache/phnixIot_device_OTA
```

## 5.2 Zusätzliche Dateien manuell sichern

```powershell
.\adb.exe pull /data/phnixIot4G
.\adb.exe pull /data/phnixIot_device_OTA_INFO
.\adb.exe pull /data/phnixIot_device_statisic
```

`adb pull` kopiert die Dateien nur vom LTE-Modem auf den PC. Die Quelldateien werden nicht verändert oder gelöscht.

# 6. Gesicherte Dateien prüfen

## Windows-GUI

Auf der Registerkarte **Backup** den Button **Zielordner öffnen** verwenden.

## Manuelle Windows-Befehle

Die Dateien liegen im aktuellen `platform-tools`-Ordner bzw. im gewählten Arbeitsordner.

Zur Sicherheit Originaldateien zunächst **unverändert archivieren**, bevor sie analysiert oder weiterverarbeitet werden.

> [!IMPORTANT]
> Backups bitte **nicht in ein öffentliches GitHub-Repository, Forum oder einen öffentlich zugänglichen Speicher hochladen**.

# 7. Alternative: Linux / Raspberry Pi

> [!IMPORTANT]
> Dieser Abschnitt ist ein alternativer Weg zur Windows-GUI und zur manuellen Windows-Anleitung. Wer das Backup bereits unter Windows durchführt, braucht ihn nicht zusätzlich auszuführen.

Unter Raspberry Pi OS / Debian sind normalerweise keine zusätzlichen SIMCom-Windows-Treiber erforderlich.

## 7.1 Komfortweg mit installiertem FoxAir Updater

```bash
cd ~/FoxAir_updater
./foxair-updater download
```

Der Updater legt einen Zeitstempel-Unterordner an, z. B.:

```text
~/FoxAir_updater/downloaded_firmware/20260829-151100/
```

Darin werden – soweit vorhanden – gespeichert:

```text
phnixIot_device_OTA
phnixIot4G
phnixIot_device_OTA_INFO
phnixIot_device_statisic
MD5SUMS.txt
SHA256SUMS.txt
README.txt
```

Fehlt `/cache/phnixIot_device_OTA`, werden die übrigen vorhandenen Dateien trotzdem gesichert.

## 7.2 ADB und USB-Werkzeuge manuell installieren

```bash
sudo apt update
sudo apt install adb usbutils
```

USB-Erkennung:

```bash
lsusb
```

ADB prüfen:

```bash
adb devices -l
```

Optional Shell:

```bash
adb shell
```

Beenden mit `exit`.

## 7.3 Firmware manuell sichern

```bash
adb pull /cache/phnixIot_device_OTA
```

## 7.4 Zusätzliche Dateien manuell sichern

```bash
adb pull /data/phnixIot4G
adb pull /data/phnixIot_device_OTA_INFO
adb pull /data/phnixIot_device_statisic
```

## 7.5 Dateien vom Raspberry Pi auf einen anderen Rechner kopieren

Beispiel vom Zielrechner aus:

```bash
scp -r dominik@IP_DES_RPI:~/FoxAir_updater/downloaded_firmware/ ./
```

Alternativ kann unter Windows z. B. WinSCP verwendet werden.

Auch hier gilt: ausgelesene Originaldateien nicht öffentlich hochladen oder weiterverteilen.

## Weiterführende Updater-Dokumentation

- [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md)
- [`FIRMWARE_MANIFEST.md`](FIRMWARE_MANIFEST.md)
- [`../RELEASE_NOTES_WINDOWS_v0.3.9.md`](../RELEASE_NOTES_WINDOWS_v0.3.9.md)