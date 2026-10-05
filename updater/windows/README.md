# Windows Updater

Die Windows-Version ist der empfohlene Bedienweg für den FoxAir Updater. Seit v0.4.0 wird das eigentliche Mainboard-OTA nach der Vorbereitung **autonom auf dem LTE-Modem** ausgeführt. Windows startet und überwacht den Vorgang, ist nach dem Start aber nicht mehr die Instanz, die den Transfer am Leben hält.

> [!IMPORTANT]
> Real bestätigt sind lokale und Remote-ADB-Verbindung, Backup/Diagnose, Vorprüfung, V3.3→V3.3 bis zur sicheren Gleichversionsablehnung sowie vollständige reale Mainboard-Firmwarewechsel **V3.3 → V3.4**, **V1.2 → V3.4**, Updates auf **V3.5 (`82400644 / 0035`)** und der Downgrade **V3.5 → V3.4**. Die untersuchte V3.5 stammt aus einer FoxAir BlueLine; entsprechende BlueLine- und GreenLine-Geräte mit Softwarecode `82400644` verwenden dieselbe Mainboard-Firmwarelinie und sind firmwareseitig untereinander kompatibel. Ein Firmwareupdate bleibt ein Eingriff in das Mainboard und erfolgt auf eigenes Risiko.

Öffentliche Windows-Versionen stehen als Portable-ZIP und Setup-EXE auf der GitHub-Releases-Seite bereit:

https://github.com/dosordie/FoxAir_updater/releases

## Architektur

Der produktive OTA-Pfad ist:

```text
FoxAir_Updater.exe
bzw. Source: foxair_updater_release_runtime.py
        ↓
foxair_updater_release_runtime.py
(finales Polling / automatische Diagnose)
        ↓
foxair_updater_release_product.py
(Release-UI / Archivierung / ACK / Cleanup)
        ↓
foxair_updater_runner_product.py
(Produkt-GUI / Vorprüfung / Runner)
        ↓
updater/dtu_ota/cli.py
        ↓
DTU-Runner auf dem LTE-Modem
  dtu_ota_supervisor.sh
  phnix_ota_runtime_hook
        ↓
Originaldienst phnixIot4G
        ↓
PHNIX Mainboard
```

Der Runner speichert seinen Laufzustand auf dem LTE-Modem. Nach erfolgreichem Start kann deshalb ein Windows-/ADB-Verbindungsverlust den bereits laufenden Mainboard-Transfer nicht beenden. Nach Wiederherstellung der Verbindung liest die GUI den bestehenden Lauf wieder ein; sie startet dabei keinen zweiten OTA-Vorgang.

Der alte Host-OTA-Controller ist aus dem Produktpfad entfernt. Firmwareupdate, Status, Diagnose, Recovery und Originalzustandsprüfung verwenden die gemeinsamen Komponenten unter `updater/dtu_ota`. Der Windows-Build enthält keinen `phnix_local_ota_controller*`- oder Windows-Controller-Wrapper mehr.

## ADB

ADB wird nicht mitgeliefert. Unterstützt werden:

- lokaler USB-Anschluss des LTE-Modems;
- Remote-ADB über einen Raspberry Pi;
- automatische Suche bzw. manuelle Auswahl einer `adb.exe`;
- manuelles Reconnect;
- Speicherung von ADB-Pfad, Remote-IP/Port und Backup-Ziel.

Für den empfohlenen Raspberry-Pi-Serverweg richtet der Linux-Installer den Remotezugriff bereits als systemd-Dienste ein. Auf einer frischen Installation bleiben sie zunächst deaktiviert.

Auf dem Raspberry Pi:

```bash
cd ~/FoxAir_updater
./foxair-updater remote start
./foxair-updater remote status
```

Für automatischen Start nach einem Reboot:

```bash
./foxair-updater remote enable
```

Der Raspberry Pi stellt der Windows-GUI zwei getrennte Netzwerkpfade bereit:

```text
Windows-GUI
  ├─ ADB         → Raspberry Pi :5038 → LTE-Modem
  └─ PHNIX Debug → Raspberry Pi :5039 → USB Interface 04 (read-only)
```

In der Windows-GUI wird **Remote – ADB-Server auf Raspberry Pi** gewählt, die Raspberry-Pi-IP eingetragen und Port `5038` verwendet. Der Remote-PHNIX-Debugkanal wird automatisch auf demselben Host mit **ADB-Port + 1** geöffnet, standardmäßig also TCP `5039`.

Der Debugstream ist absichtlich nur lesend und ersetzt für den FoxAir Updater einen allgemeinen COM↔TCP-Forwarder. `ser2net` ist für diesen Remoteweg nicht erforderlich. Unter Windows wird weiterhin eine lokale `adb.exe` als ADB-Client benötigt.

> [!WARNING]
> TCP 5038 und 5039 nur in einem vertrauenswürdigen lokalen Netz verwenden und nicht per Router/Portweiterleitung ins Internet freigeben.

## Firmwareupdate

Der normale Ablauf lautet:

1. Unter **Verbindung** ADB prüfen.
2. Unter **Update-Datei / Manifest** bei Bedarf ein Manifest erzeugen.
3. Unter **Firmwareupdate** die JSON-Update-Datei auswählen.
4. **Vorprüfung** ausführen.
5. Risikobestätigung aktivieren.
6. **Firmwareupdate starten**.
7. Den autonomen Lauf bis zum terminalen Ergebnis beobachten.

Die Vorprüfung kontrolliert unter anderem Manifest/Firmware-Zusammengehörigkeit, Firmwareidentität, Größe, Prüfsummen, LTE-Modem-Zustand und verfügbaren Speicherplatz. Sie sendet noch keine Firmwaredaten an das Mainboard.

### Dienstneustart vor dem Update

Unter **Erweitert** steht die Option

```text
phnixIot4G vor Firmwareupdate neu starten
```

zur Verfügung und ist standardmäßig aktiviert. Der Runner verlangt bei angefordertem Neustart einen eindeutig neuen, stabil laufenden und nicht von einem Debugger belegten Originaldienst. Danach wird der Preflight erneut durchgeführt.

### MQTT

Beim normalen Vollupdate bleibt MQTT standardmäßig verbunden. Die optionale Einstellung

```text
MQTT bei Update aus
```

ist für besondere Test-/Diagnosefälle vorgesehen und standardmäßig deaktiviert.

## Fortschritt und Sicherheitsgrenzen

Während C5A8 zeigt die GUI den Firmwaretransfer an. Wenn der serielle PHNIX-Debugkanal verfügbar ist, wird dessen Live-Fortschritt bevorzugt; der persistente Runner-Fortschritt dient als Fallback.

> [!WARNING]
> **100 % bedeutet nur, dass alle Firmwaredaten übertragen wurden.** Danach folgen Mainboard-Prüfung, Übernahme/Promotion und Abschluss.

Der bestätigte Erfolgsweg ist sinngemäß:

```text
C350
→ C36E Status 1
→ C357
→ C36E Status 2
→ C5A8 bis 100 %
→ Mainboard-Verarbeitung
→ C36E Status 3
→ Promotion
→ C36E Status 5
→ Board-Step 12
→ terminaler Erfolg
```

Ab dem ersten C5A8 darf ein generischer Host-/Monitoringfehler den autoritativen Originaldienst nicht mehr durch einen normalen Cleanup stoppen. Verliert der Host nach dieser Grenze die sichere Beobachtung, bleiben Runner-Lock und Diagnosezustand erhalten.

## Status / Wiederaufnahme

Der Button **Status prüfen** liest den persistenten Laufzustand des LTE-Modems. Ein aktiver Lauf wird dadurch nicht neu gestartet. Doppelstart und paralleles Prepare sind bei aktivem Runner-Lock gesperrt.

Bei einem LTE-/Linux-Reboot kann der Runner anhand seines persistenten Zustands zwischen einem Prozessverlust und einem echten Bootwechsel unterscheiden. Ein später fortgesetzter Mainboard-Lauf darf nicht fälschlich als Erfolg eines bereits verlorenen Host-Laufs ausgegeben werden.

## Wartung

Unter **Erweitert** können ausgewählte persistente PHNIX-Statistikzähler geprüft und gezielt geändert werden:

- DTU-OTA-Vorgänge;
- Mainboard OTA-Vorgänge;
- Dienststarts (`Power-Reset-t`);
- aktive Modem-Neustarts (`Active-Reset-t`).

Vor Änderungen wird die vollständige 128-Byte-Statistikdatei gesichert. Der Dienst wird kontrolliert neu gestartet, Datei und RAM werden anschließend verifiziert. Beim `Power-Reset-t` berücksichtigt die Wartungslogik, dass der Originaldienst den RAM-Zähler beim eigenen Start erhöht und der gewünschte Endwert danach persistent finalisiert werden muss.

## Portable- und Setup-Build

Lokaler Portable-Build aus dem Repository-Root:

```bat
updater\windows\build_windows_portable.bat
```

Setup-Build mit installiertem Inno Setup 6:

```bat
updater\windows\build_windows_setup.bat
```

Der Endanwender benötigt keine Python-Installation. Die private Python-Runtime wird in das Paket eingebettet; ADB bleibt eine externe Voraussetzung.

Der Release-Workflow wird unter GitHub Actions über **Release Windows** manuell gestartet. Er synchronisiert die Version, führt Tests und Syntaxprüfungen aus, baut Portable und Setup, prüft die enthaltenen produktiven Runner-Dateien und erzeugt anschließend Tag und GitHub Release.

## Entwicklungsstart

Für einen Quellcode-Start muss derselbe **finale Release-Einstieg** verwendet werden wie beim
PyInstaller-Build:

```bat
py -m pip install -r updater\windows\requirements-build.txt
py updater\windows\foxair_updater_release_runtime.py
```

Für wiederholte Tests nach einem Update des Repositories genügt normalerweise:

```bat
git pull
py .\updater\windows\foxair_updater_release_runtime.py
```

Damit laufen auch im Quellcode-Start die Release-Schichten für automatische Diagnose,
lokale Archivierung, ACK/Cleanup sowie die optionale DTU-Bereinigung beim
„Originalzustand wiederherstellen“. `foxair_updater_runner_product.py` bleibt die
darunterliegende Produkt-/Runner-Schicht; ein direkter Quellcode-Start dieser Datei
delegiert aus Kompatibilitätsgründen automatisch an den finalen Release-Einstieg.

Der direkte Start aus dem Repository-Root benötigt kein manuell gesetztes `PYTHONPATH`.
Die darunterliegende Produkt-Schicht ergänzt das Repository-Root nur bei einem nicht
eingefrorenen Quellcode-Start. Der gepackte PyInstaller-/Endanwender-Build bleibt davon
unberührt. Im Source-Modus wird die lokal installierte Python-Laufzeit verwendet; die
Release-/Cleanup-Logik ist dieselbe wie im gebauten Programm.

## Weitere Dokumentation

- [`../../docs/HowTo/firmware_update_windows.md`](../../docs/HowTo/firmware_update_windows.md)
- [`../../docs/HowTo/firmware_backup_lte.md`](../../docs/HowTo/firmware_backup_lte.md)
- [`../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md`](../../docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)
- [`../../docs/reverse_engineering/PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md`](../../docs/reverse_engineering/PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md)
