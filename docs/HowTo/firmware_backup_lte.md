# Firmware-Backup des LTE-Modems über Micro-USB

Diese Anleitung beschreibt, wie man sich per **Micro-USB** mit dem LTE-Modem verbindet und die Firmware sowie zusätzliche Dateien mit **ADB (Android Debug Bridge, Bestandteil der Android SDK Platform Tools)** sichert.

> [!NOTE]
> Es gibt drei alternative Bedienwege:
> - **Windows – empfohlen:** FoxAir Updater mit grafischer Oberfläche;
> - **Windows – manuell:** PowerShell und direkte `adb.exe`-Befehle;
> - **Linux / Raspberry Pi:** `adb` beziehungsweise der Linux-Launcher `./foxair-updater`.
>
> Es muss **nur einer dieser Wege** verwendet werden. Die PowerShell- und Linux-Abschnitte sind Alternativen zur Windows-GUI.

> [!IMPORTANT]
> Der **Windows-Backup-Pfad wurde real getestet**. ADB-Verbindung, Originalstatus und das read-only Backup der LTE-Dateien funktionieren sowohl mit lokal angeschlossenem Modem als auch über den optionalen Remote-ADB-Weg zum Raspberry Pi.
>
> Ein echter Firmwarewechsel auf eine andere Mainboard-Version ist weiterhin experimentell und ist **nicht Voraussetzung** für das hier beschriebene Backup.

> [!NOTE]
> Die Backup-Funktionen **verändern nichts am LTE-Modem**. Die Windows-GUI verwendet dafür ausschließlich `adb pull`; bei den manuellen Wegen werden dieselben Dateien ebenfalls nur vom LTE-Modem heruntergeladen.

> [!WARNING]
> Die aus dem LTE-Modem ausgelesenen Firmware- und Datendateien **nicht öffentlich hochladen oder weiterveröffentlichen**. Sie können herstellerspezifische Software, Konfigurationsdaten oder andere nicht für die Veröffentlichung bestimmte Inhalte enthalten.

## 1. LTE-Modem öffnen und USB-Port freilegen

- Der Deckel des LTE-Modems ist **nur gesteckt** und kann vorsichtig abgenommen werden.
- Im **Micro-USB-Port** kann sich etwas Versiegelungs-/Vergussmasse von der Platine befinden.
- Diese lässt sich vorsichtig z. B. mit einer **Pinzette** entfernen.
- Dabei unbedingt darauf achten, USB-Port, Kontakte und Platine nicht zu beschädigen.

### Geöffnetes LTE-Modem

![Geöffnetes LTE-Modem](lte1.jpeg)

### Micro-USB-Anschluss mit Vergussmasse

![Micro-USB-Anschluss mit Vergussmasse](lte2.jpeg)

> [!CAUTION]
> Den Micro-USB-Stecker **nicht mit Gewalt einstecken**. Da sich die Vergussmasse nur schwer vollständig entfernen lässt, wird voraussichtlich ein gewisser Widerstand zu spüren sein. Den Stecker nur so weit wie ohne Gewalt möglich einstecken, bis das Betriebssystem die USB-Verbindung erkennt.

## 2. Windows-Treiber installieren und USB-Verbindung prüfen

Benötigt werden die SIMCom USB-Treiber:

- [SIMCOM Windows USB Drivers V1.0.2](https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip)

ZIP-Datei entpacken und die passenden Windows-Treiber installieren. Danach das LTE-Modem über den Micro-USB-Port mit dem PC verbinden.

### Erkennung im Windows-Geräte-Manager prüfen

1. **Geräte-Manager** öffnen.
2. LTE-Modem per Micro-USB mit dem PC verbinden.
3. Beobachten, ob beim Ein- und Ausstecken neue Geräte erscheinen bzw. verschwinden.
4. Besonders unter **Anschlüsse (COM & LPT)**, **Modems**, **USB-Controller** bzw. **Andere Geräte** nach SIMCom-/Android-/ADB-Geräten suchen.
5. Wird ein Gerät mit gelbem Warnsymbol oder als unbekanntes Gerät angezeigt, den SIMCom-Treiber installieren bzw. aktualisieren und das Modem erneut verbinden.

Damit lässt sich bereits vor dem ADB-Test feststellen, ob Windows die USB-Verbindung grundsätzlich erkennt.

## 3. Android SDK Platform Tools / ADB installieren

ADB ist Bestandteil der Android SDK Platform Tools:

- [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools?hl=de#downloads)

**ADB wird aus Lizenz- und Distributionsgründen nicht mit dem FoxAir Updater mitgeliefert.**

Für Windows die ZIP-Datei herunterladen und z. B. nach

```text
C:\platform-tools
```

entpacken.

---

# 4. Windows – empfohlen: FoxAir Updater GUI

Die aktuelle Windows-Version des FoxAir Updaters ist als **Portable-ZIP** und **Setup-EXE** auf der GitHub-Releases-Seite verfügbar:

- [FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)

Die Windows-GUI ist inzwischen der empfohlene Weg für Backup und Firmware-Download. Sie bietet unter anderem:

- lokale ADB-Verbindung direkt per USB;
- optional Remote-ADB über einen Raspberry Pi;
- automatische bzw. manuelle ADB-Reconnect-Funktion;
- read-only Backup per `adb pull`;
- frei wählbaren Zielordner;
- kurze Beschreibung der einzelnen Backup-Dateien;
- direkten Button **Zielordner öffnen**.

> [!NOTE]
> Die Windows-Builds sind derzeit nicht mit einem kommerziellen Code-Signing-Zertifikat signiert. Beim ersten Start kann Windows SmartScreen **„Der Computer wurde durch Windows geschützt“** anzeigen. Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite geladen wurde, **Weitere Informationen** und danach **Trotzdem ausführen** wählen.

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
2. Gewünschten Zielordner mit **Zielordner…** auswählen.
3. Gewünschte Dateien auswählen.
4. **Backup erstellen** anklicken.
5. Nach erfolgreichem Abschluss **Zielordner öffnen** verwenden.

![FoxAir Updater – Backup](../DTU_2_Backup.png)

Die GUI kann folgende Dateien sichern:

| Auswahl in der GUI | Quelle auf dem LTE-Modem | Bedeutung |
|---|---|---|
| **Firmware** | `/cache/phnixIot_device_OTA` | aktuell im LTE-Cache vorhandene OTA-/Firmwaredatei |
| **OTA_INFO** | `/data/phnixIot_device_OTA_INFO` | persistenter OTA-/Resume-Zustand |
| **Statistik** | `/data/phnixIot_device_statisic` | Betriebs-, Kommunikations-, Reset- und OTA-Zähler |
| **Originaldienst phnixIot4G** | `/data/phnixIot4G` | originale ausführbare PHNIX-LTE-Programmdatei |

Bei Auswahl aller Optionen landen im Zielordner entsprechend:

```text
phnixIot_device_OTA
phnixIot_device_OTA_INFO
phnixIot_device_statisic
phnixIot4G
```

Die Firmwaredatei unter `/cache/phnixIot_device_OTA` ist nur vorhanden, solange sie vom originalen PHNIX-Dienst noch nicht entfernt bzw. durch einen späteren OTA-Auftrag ersetzt wurde.

Die GUI liest diese Dateien ausschließlich per `adb pull`. Es werden keine Dateien auf dem LTE-Modem verändert oder gelöscht.

## 4.3 Remote ADB über Raspberry Pi

Wenn das LTE-Modem nicht direkt am Windows-PC, sondern per USB an einem Raspberry Pi hängt, kann der ADB-Server auf dem Pi kurzfristig im lokalen LAN gestartet werden:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

Danach in der Windows-GUI:

1. **Remote – ADB-Server auf Raspberry Pi** auswählen.
2. IP-Adresse des Raspberry Pi eintragen.
3. Port `5038` verwenden.
4. **ADB prüfen** anklicken.

Der Pi-Befehl bleibt im Vordergrund und wird anschließend mit **Strg+C** beendet.

> [!IMPORTANT]
> Den Remote-ADB-Port nur kurzfristig und nur in einem vertrauenswürdigen lokalen Netz freigeben.

---

# 5. Windows – manuelle PowerShell-Alternative

Wer die GUI nicht verwenden möchte, kann weiterhin direkt mit `adb.exe` arbeiten.

Im Windows Explorer den entpackten Ordner `platform-tools` öffnen und dort PowerShell bzw. Terminal starten.

Die Eingabezeile sollte ungefähr so aussehen:

```text
PS C:\platform-tools>
```

ADB-Verbindung prüfen:

```powershell
.\adb.exe devices
```

Bei funktionierender Verbindung erscheint eine Geräte-ID mit dem Status `device`:

```text
List of devices attached
XXXXXXXXXXXX    device
```

Optional kann eine Shell geöffnet werden:

```powershell
.\adb.exe shell
```

Mit

```text
exit
```

wird die Shell wieder verlassen.

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

Die Dateien werden jeweils in den Ordner heruntergeladen, in dem PowerShell aktuell geöffnet ist.

`adb pull` kopiert die Dateien lediglich vom LTE-Modem auf den PC. Die Quelldateien werden dabei nicht verändert oder gelöscht.

---

# 6. Gesicherte Dateien prüfen

## Windows-GUI

Auf der Registerkarte **Backup** den Button **Zielordner öffnen** verwenden. Dadurch wird der eingestellte Sicherungsordner direkt im Windows-Explorer geöffnet.

Der Button **Zielordner…** dient nur der Auswahl des Sicherungsordners.

## Manuelle Windows-Befehle

Bei den PowerShell-Befehlen liegen die Dateien im aktuellen `platform-tools`-Ordner beziehungsweise im selbst gewählten Arbeitsordner.

Zur Sicherheit empfiehlt es sich, die Originaldateien zunächst **unverändert zu archivieren**, bevor sie analysiert oder weiterverarbeitet werden.

> [!IMPORTANT]
> Diese Backups bitte **nicht in ein öffentliches GitHub-Repository, Forum oder einen anderen öffentlich zugänglichen Speicher hochladen**.

---

# 7. Alternative: Linux / Raspberry Pi

> [!IMPORTANT]
> Dieser Abschnitt ist ein **alternativer Weg zur Windows-GUI und zur manuellen Windows-Anleitung**. Wer das Backup bereits unter Windows durchführt, braucht diesen Abschnitt nicht zusätzlich auszuführen.

Für einen Raspberry Pi mit Raspberry Pi OS / Debian-basiertem Linux sind normalerweise keine zusätzlichen SIMCom-Windows-Treiber notwendig.

## 7.1 Komfortweg mit installiertem FoxAir Updater

Wenn der FoxAir Updater bereits installiert ist, können Firmware-Cache und Zusatzdateien mit einem einzigen rein lesenden Befehl gesichert werden:

```bash
cd ~/FoxAir_updater
./foxair-updater download
```

Der Updater legt automatisch einen Zeitstempel-Unterordner an, zum Beispiel:

```text
~/FoxAir_updater/downloaded_firmware/20260824-151100/
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

Fehlt `/cache/phnixIot_device_OTA`, meldet der Befehl dies als Warnung und sichert die übrigen vorhandenen Diagnose-/Statusdateien trotzdem.

## 7.2 ADB und USB-Werkzeuge manuell installieren

```bash
sudo apt update
sudo apt install adb usbutils
```

USB-Erkennung prüfen:

```bash
lsusb
```

ADB prüfen:

```bash
adb devices -l
```

Optional eine Shell öffnen:

```bash
adb shell
```

Die Shell wird mit

```text
exit
```

wieder verlassen.

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

Alternativ kann unter Windows beispielsweise WinSCP verwendet werden.

Auch hier gilt: Die ausgelesenen Originaldateien nicht öffentlich hochladen oder weiterverteilen.
