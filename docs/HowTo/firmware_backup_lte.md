# Firmware-Backup des LTE-Modems über Micro-USB

Diese Anleitung beschreibt, wie man sich per **Micro-USB** mit dem LTE-Modem verbindet und die Firmware sowie zusätzliche Dateien mit **ADB (Android Debug Bridge, Bestandteil der Android SDK Platform Tools)** sichert.

> [!NOTE]
> Es gibt drei alternative Bedienwege:
> - **Windows – empfohlen:** FoxAir Updater mit grafischer Oberfläche;
> - **Windows – manuell:** PowerShell und direkte `adb.exe`-Befehle;
> - **Linux / Raspberry Pi:** `adb` beziehungsweise der Linux-Launcher `./foxair-updater`.
>
> Es muss **nur einer dieser Wege** verwendet werden. Die PowerShell- und Linux-Abschnitte sind Alternativen zur Windows-GUI und keine zusätzlichen notwendigen Schritte.

> [!IMPORTANT]
> Der **Windows-Backup-Pfad wurde real getestet**: ADB-Verbindung, Originalstatus und das read-only Backup der LTE-Dateien funktionieren sowohl mit lokal angeschlossenem Modem als auch über den optionalen Remote-ADB-Weg zum Raspberry Pi.
>
> Ein **echtes Firmwareupdate auf eine andere Mainboard-Version wurde mit der Windows-Version noch nicht live durchgeführt und bestätigt**. Die Update-Funktion bleibt experimentell und ist nicht Voraussetzung für das hier beschriebene Backup.

> [!NOTE]
> Die in dieser Anleitung verwendeten Backup-Funktionen **verändern nichts am LTE-Modem**. Die Windows-GUI verwendet hierfür ausschließlich `adb pull`; bei den manuellen Wegen werden dieselben Dateien ebenfalls nur vom LTE-Modem heruntergeladen/kopiert.

> [!WARNING]
> Die aus dem LTE-Modem ausgelesenen Firmware- und Datendateien **nicht öffentlich hochladen oder weiterveröffentlichen**. Sie können herstellerspezifische Software, Konfigurationsdaten oder andere nicht für die Veröffentlichung bestimmte Inhalte enthalten.

## 1. LTE-Modem öffnen und USB-Port freilegen

- Der Deckel des LTE-Modems ist **nur gesteckt** und kann vorsichtig abgenommen werden.
- Im **Micro-USB-Port** kann sich etwas Versiegelungs-/Vergussmasse von der Platine befinden.
- Diese lässt sich vorsichtig z. B. mit einer **Pinzette** entfernen.
- Dabei unbedingt darauf achten, den USB-Port, die Kontakte und die Platine nicht zu beschädigen.

### Geöffnetes LTE-Modem

Das folgende Bild zeigt das LTE-Modem mit abgenommenem Deckel und die Lage des Micro-USB-Anschlusses auf der Platine:

![Geöffnetes LTE-Modem](lte1.jpeg)

### Micro-USB-Anschluss mit Vergussmasse

Im folgenden Detailbild ist der Bereich des Micro-USB-Anschlusses zu sehen. Im Anschluss befindet sich noch Vergussmasse, die den Stecker beim Einstecken behindern kann:

![Micro-USB-Anschluss mit Vergussmasse](lte2.jpeg)

> [!CAUTION]
> Den Micro-USB-Stecker **nicht mit Gewalt einstecken**. Da sich die Vergussmasse nur schwer vollständig aus der Buchse entfernen lässt, wird beim Einstecken voraussichtlich ein gewisser Widerstand zu spüren sein und der Stecker möglicherweise nicht vollständig einrasten. Den Stecker daher nur vorsichtig und so weit wie ohne Gewalt möglich einstecken, bis das Betriebssystem die USB-Verbindung erkennt.

## 2. Windows-Treiber installieren und USB-Verbindung prüfen

Benötigt werden die SIMCom USB-Treiber:

- [SIMCOM Windows USB Drivers V1.0.2](https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip)

ZIP-Datei entpacken und die passenden Windows-Treiber installieren.

Danach das LTE-Modem über den Micro-USB-Port mit dem PC verbinden.

### Erkennung im Windows-Geräte-Manager prüfen

1. **Geräte-Manager** öffnen, z. B. über Rechtsklick auf das Windows-Startmenü → **Geräte-Manager**.
2. LTE-Modem per Micro-USB mit dem PC verbinden.
3. Beobachten, ob beim Ein- und Ausstecken neue Geräte erscheinen bzw. verschwinden.
4. Besonders unter **Anschlüsse (COM & LPT)**, **Modems**, **USB-Controller** bzw. **Andere Geräte** nach SIMCom-/Android-/ADB-Geräten suchen.
5. Wird ein Gerät mit gelbem Warnsymbol oder als unbekanntes Gerät angezeigt, ist der Treiber noch nicht korrekt installiert. In diesem Fall den SIMCom-Treiber installieren bzw. aktualisieren und das Modem erneut verbinden.

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

### Empfohlen: ADB direkt in der Windows-GUI auswählen

Die aktuelle Windows-Version des FoxAir Updaters ist als **Portable-ZIP** und als **Setup-EXE** auf der normalen GitHub-Releases-Seite verfügbar:

- [FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)

> [!NOTE]
> Die Windows-Builds sind derzeit nicht mit einem kommerziellen Code-Signing-Zertifikat signiert. Beim ersten Start kann deshalb Windows SmartScreen **„Der Computer wurde durch Windows geschützt“** anzeigen. Wenn die Datei bewusst von der oben genannten offiziellen GitHub-Releases-Seite geladen wurde, zuerst **Weitere Informationen** und danach **Trotzdem ausführen** anklicken. Bei einer Datei aus einer anderen oder unbekannten Quelle nicht einfach fortfahren.

Nach dem Start:

1. Registerkarte **Verbindung** öffnen.
2. Falls `adb.exe` nicht automatisch gefunden wird, **adb.exe auswählen…** verwenden.
3. Die zuvor entpackte `adb.exe` auswählen.
4. **ADB prüfen** anklicken.
5. Das LTE-Modem muss im Status `device` erscheinen.

Die GUI kann alternativ auch einen ADB-Server auf einem Raspberry Pi verwenden. Dafür auf dem Pi kurzfristig starten:

```bash
adb kill-server
adb -a -P 5038 nodaemon server
```

In der Windows-GUI **Remote – ADB-Server auf Raspberry Pi** auswählen, IP-Adresse und Port `5038` eintragen und **ADB prüfen** anklicken. Der Pi-Befehl bleibt im Vordergrund und wird anschließend mit **Strg+C** beendet.

### Manuelle Alternative: ADB in PowerShell prüfen

Wer die GUI nicht verwenden möchte, kann weiterhin direkt mit PowerShell arbeiten.

Im Windows Explorer den entpackten Ordner `platform-tools` öffnen. Anschließend entweder:

- in einen freien Bereich des Ordners mit **Shift + Rechtsklick** klicken und **PowerShell-Fenster hier öffnen** bzw. **Im Terminal öffnen** auswählen,
- oder oben in die Adresszeile des Explorers `powershell` eingeben und mit Enter bestätigen.

Danach sollte PowerShell bereits im richtigen Ordner stehen. Das lässt sich z. B. daran erkennen, dass die Eingabezeile ungefähr so beginnt:

```text
PS C:\platform-tools>
```

Nun prüfen, ob ADB das LTE-Modem erkennt:

```powershell
.\adb.exe devices
```

Bei funktionierender Verbindung erscheint unter `List of devices attached` eine Geräte-ID mit dem Status `device`.

Beispiel:

```text
List of devices attached
XXXXXXXXXXXX    device
```

Optional kann zusätzlich eine Shell auf dem LTE-Modem geöffnet werden:

```powershell
.\adb.exe shell
```

Mit

```text
exit
```

wird die Shell wieder verlassen.

## 4. Firmware sichern – unter Windows bevorzugt mit der GUI

Für Windows ist die grafische Backup-Funktion des FoxAir Updaters der empfohlene Weg.

### Windows-GUI

1. FoxAir Updater starten und unter **Verbindung** zuerst **ADB prüfen**.
2. Registerkarte **Backup** öffnen.
3. Gewünschten Zielordner mit **Zielordner…** auswählen.
4. Mindestens **Firmware** aktiviert lassen. Optional zusätzlich `OTA_INFO`, Statistik und `phnixIot4G` auswählen.
5. **Backup erstellen** anklicken.
6. Nach erfolgreichem Abschluss **Zielordner öffnen** verwenden, um die gesicherten Dateien direkt im Windows-Explorer zu kontrollieren.

Die Firmware wird – sofern sie seit dem letzten Download noch nicht durch einen neuen OTA-Auftrag entfernt wurde – von folgendem Pfad gelesen:

```text
/cache/phnixIot_device_OTA
```

Die GUI verwendet dafür ausschließlich `adb pull` und verändert die Quelldatei nicht.

Bei Auswahl aller vier Optionen werden folgende Dateien gesichert:

```text
phnixIot_device_OTA
phnixIot_device_OTA_INFO
phnixIot_device_statisic
phnixIot4G
```

### Manuelle PowerShell-Alternative

Nur die Firmware in den aktuellen PowerShell-Ordner kopieren:

```powershell
.\adb.exe pull /cache/phnixIot_device_OTA
```

`adb pull` kopiert die Datei lediglich vom LTE-Modem auf den PC. Die Datei auf dem LTE-Modem wird dabei nicht verändert oder gelöscht.

## 5. Zusätzliche Dateien sichern

### Windows-GUI – empfohlen

Die zusätzlichen Dateien können einfach auf der Registerkarte **Backup** mit angehakt und gemeinsam mit der Firmware heruntergeladen werden:

```text
/data/phnixIot4G
/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic
```

Nach dem Backup öffnet **Zielordner öffnen** den tatsächlich verwendeten Sicherungsordner im Explorer.

### Manuell unter Windows

```powershell
.\adb.exe pull /data/phnixIot4G
.\adb.exe pull /data/phnixIot_device_OTA_INFO
.\adb.exe pull /data/phnixIot_device_statisic
```

Die Dateien werden jeweils in den Ordner heruntergeladen, in dem PowerShell aktuell geöffnet ist.

### Komfortweg mit installiertem FoxAir-Updater unter Linux / Raspberry Pi

Wenn der FoxAir-Updater bereits installiert ist, können die Firmware aus dem LTE-Cache und alle Zusatzdateien mit einem einzigen **rein lesenden** Befehl gesichert werden:

```bash
cd ~/FoxAir_updater
./foxair-updater download
```

Der Updater legt automatisch einen Zeitstempel-Unterordner an, zum Beispiel:

```text
~/FoxAir_updater/downloaded_firmware/20260824-151100/
```

Darin werden – soweit auf dem LTE-Modem vorhanden – gespeichert:

```text
phnixIot_device_OTA
phnixIot4G
phnixIot_device_OTA_INFO
phnixIot_device_statisic
MD5SUMS.txt
SHA256SUMS.txt
README.txt
```

Quellen auf dem LTE-Modem:

```text
/cache/phnixIot_device_OTA
/data/phnixIot4G
/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic
```

Der Ordner `downloaded_firmware/` ist bewusst vom normalen Update-Eingangsordner `firmware/` getrennt und wird vom Git-Repository ignoriert.

Fehlt `/cache/phnixIot_device_OTA` bereits, meldet der Befehl dies als Warnung und sichert die übrigen vorhandenen Diagnose-/Statusdateien trotzdem.

## 6. Gesicherte Dateien prüfen

### Windows-GUI

Auf der Registerkarte **Backup** den Button **Zielordner öffnen** verwenden. Dadurch wird der eingestellte Sicherungsordner direkt im Windows-Explorer geöffnet.

Der Button **Zielordner…** dient dagegen nur der Auswahl eines Ordners. Der dabei angezeigte Dialog ist kein normaler Explorer-Dateibrowser; deshalb ist **Zielordner öffnen** für die Kontrolle nach dem Backup vorgesehen.

### Manuelle Windows-Befehle

Bei den PowerShell-Befehlen liegen die Dateien im aktuellen `platform-tools`-Ordner beziehungsweise im selbst gewählten Arbeitsordner.

### Linux / Raspberry Pi

Beim Linux-Komfortbefehl befinden sich die Dateien im erzeugten Zeitstempel-Unterordner unter `downloaded_firmware/`.

Zur Sicherheit empfiehlt es sich, die Originaldateien zunächst **unverändert zu archivieren**, bevor sie analysiert oder weiterverarbeitet werden.

> [!IMPORTANT]
> Diese Backups bitte **nicht in ein öffentliches GitHub-Repository, Forum oder einen anderen öffentlich zugänglichen Speicher hochladen**.

---

# 7. Alternative: Linux / Raspberry Pi

> [!IMPORTANT]
> Dieser Abschnitt ist ein **alternativer Weg zur Windows-GUI und zur manuellen Windows-Anleitung**. Wer das Backup bereits unter Windows durchführt, braucht diesen Abschnitt nicht zusätzlich auszuführen.

Die folgenden Schritte wurden für einen **Raspberry Pi mit Raspberry Pi OS / Debian-basiertem Linux** vorgesehen. Dort sind für das LTE-Modem in der Regel keine zusätzlichen Windows-/SIMCom-Treiber notwendig.

Wer den FoxAir-Updater bereits installiert hat, kann nach funktionierender ADB-Verbindung direkt den in Abschnitt 5 beschriebenen Komfortbefehl verwenden:

```bash
cd ~/FoxAir_updater
./foxair-updater download
```

Die folgenden manuellen Befehle bleiben als Alternative und für Systeme ohne installierten Updater dokumentiert.

## 7.1 ADB und USB-Werkzeuge installieren

Zunächst Paketlisten aktualisieren und die benötigten Pakete installieren:

```bash
sudo apt update
sudo apt install adb usbutils
```

Mit `lsusb` kann geprüft werden, ob beim Einstecken des LTE-Modems ein neues USB-Gerät erkannt wird:

```bash
lsusb
```

Anschließend prüfen, ob ADB das LTE-Modem sieht:

```bash
adb devices -l
```

Bei funktionierender Verbindung erscheint eine Geräte-ID mit dem Status `device`.

Optional kann auch eine Shell geöffnet werden:

```bash
adb shell
```

Die Shell wird mit

```text
exit
```

wieder verlassen.

## 7.2 Firmware manuell sichern

```bash
adb pull /cache/phnixIot_device_OTA
```

## 7.3 Zusätzliche Dateien manuell sichern

```bash
adb pull /data/phnixIot4G
adb pull /data/phnixIot_device_OTA_INFO
adb pull /data/phnixIot_device_statisic
```

## 7.4 Dateien vom Raspberry Pi auf einen anderen Rechner kopieren

Wer die Dateien zunächst auf einem Raspberry Pi gesichert hat, kann sie anschließend beispielsweise mit `scp` auf einen Windows- oder Linux-Rechner kopieren.

Beispiel vom Zielrechner aus:

```bash
scp -r dominik@IP_DES_RPI:~/FoxAir_updater/downloaded_firmware/ ./
```

Alternativ kann unter Windows beispielsweise WinSCP verwendet werden.

Auch hier gilt: Die ausgelesenen Originaldateien nicht öffentlich hochladen oder weiterverteilen.
