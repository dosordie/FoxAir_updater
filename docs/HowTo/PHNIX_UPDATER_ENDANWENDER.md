# PHNIX-Firmware-Updater – Anleitung für Anwender

Stand: 28. September 2026

> [!CAUTION]
> Mehrere vollständige Mainboard-Firmwarewechsel wurden auf realer FoxAir-/PHNIX-Hardware erfolgreich durchgeführt, darunter **V3.3 → V3.4**, **V1.2 → V3.4**, reale Updates auf **V3.5** sowie der Downgrade **V3.5 → V3.4**. Der jeweils aktuelle Teststand steht in der Projekt-`README.md`.
>
> Die untersuchte **V3.5 stammt von einer FoxAir BlueLine (BL)**. Für BlueLine und GreenLine (GL) mit Mainboard-Softwarecode **`82400644`** handelt es sich um dieselbe Mainboard-Firmwarelinie. Die V3.5 ist damit zwischen entsprechenden BL- und GL-Geräten dieser Firmwarefamilie kompatibel. Weitere Firmwarestände, Mainboardfamilien und Fehlerfälle sind nicht in gleicher Tiefe live validiert. Ein Firmwareupdate bleibt ein Eingriff in das Mainboard und erfolgt auf eigenes Risiko.

Diese Seite fasst den normalen Endanwenderweg zusammen. Unter Windows ist die grafische Anwendung der empfohlene Weg. Die ausführliche Schritt-für-Schritt-Anleitung für Windows steht unter:

**[`firmware_update_windows.md`](firmware_update_windows.md)**

Die USB-/ADB-Einrichtung und das Firmware-Backup sind hier beschrieben:

**[`firmware_backup_lte.md`](firmware_backup_lte.md)**

## Windows: autonomer DTU-OTA-Runner

Die aktuelle Windows-Anwendung verwendet den **autonomen DTU-OTA-Runner**. Windows führt Vorprüfung und Start aus und überwacht den Vorgang. Nach erfolgreichem Start läuft das Mainboard-OTA jedoch auf dem LTE-Modem selbstständig weiter.

Das bedeutet insbesondere:

- ein kurzzeitiger Windows-/ADB-Verbindungsverlust stoppt einen bereits gestarteten Transfer nicht;
- der gespeicherte Runner-Status kann danach wieder eingelesen werden;
- eine Statusprüfung startet keinen zweiten OTA-Vorgang;
- paralleles Prepare bzw. Doppelstart sind bei einem aktiven Runner gesperrt;
- ab der Authority-/C5A8-Grenze wird ein laufender autoritativer Mainboard-Transfer bei Monitoringverlust nicht durch normalen Cleanup gestoppt.

Der produktive Pfad ist:

```text
Windows GUI
→ updater/dtu_ota/cli.py
→ autonomer DTU-Runner
→ dtu_ota_supervisor.sh
→ phnix_ota_runtime_hook
→ Originaldienst phnixIot4G
→ Mainboard
```

## Normaler Windows-Ablauf

1. **Verbindung** öffnen und ADB prüfen.
2. Optional unter **Backup** die LTE-Dateien sichern.
3. Falls nötig unter **Update-Datei / Manifest** ein Manifest aus der Firmware erzeugen.
4. Unter **Firmwareupdate** die zum Firmwarepaket gehörende JSON-Datei auswählen.
5. **Vorprüfung** ausführen.
6. Nur nach erfolgreicher Vorprüfung die Risikobestätigung aktivieren.
7. **Firmwareupdate starten** und die Sicherheitsabfrage bestätigen.
8. Wärmepumpe und LTE-Modem während des laufenden Vorgangs nicht stromlos machen.
9. Bis zum ausdrücklich gemeldeten terminalen Erfolg warten.

## Vorprüfung

Die Vorprüfung führt noch keinen Mainboard-Transfer aus. Sie kontrolliert unter anderem:

- Manifest und zugehörige Firmwaredatei;
- Firmwareidentität, Größe, MD5 und SHA-256;
- Zustand des LTE-Modems und Originaldienstes;
- ausreichenden freien Speicher für Staging/Transfer;
- vorhandene aktive Runner-Locks bzw. bereits laufende Vorgänge.

Shell-Payloads des autonomen Runners werden beim Paketieren auf LF normalisiert und genau in dieser Form gehasht und übertragen. Dadurch ist der Runtime-Hook auch bei einem Windows-Checkout unabhängig von dessen lokalen Zeilenende-Einstellungen ausführbar.

## Dienstneustart vor dem Update

Unter **Erweitert** existiert die Option:

```text
phnixIot4G vor Firmwareupdate neu starten
```

Sie ist standardmäßig aktiviert. Ist der Neustart angefordert, akzeptiert der Runner ihn nur, wenn der alte Dienst eindeutig beendet wurde und anschließend genau ein neuer, stabiler und nicht von einem Debugger belegter Originaldienst läuft. Danach wird der Preflight erneut ausgeführt.

## MQTT während des Updates

Beim normalen Vollupdate bleibt MQTT standardmäßig verbunden.

Unter **Erweitert** kann für besondere Test-/Diagnosefälle optional

```text
MQTT bei Update aus
```

aktiviert werden. Die Option ist standardmäßig aus.

Der Originaldienst besitzt einen eigenen Rebootpfad, wenn der Aliyun-MQTT-Client intern länger als 1800 Sekunden als offline gilt. Diese 1800 Sekunden beginnen nicht zwingend bereits beim Setzen einer stillen Firewall-DROP-Regel; der SDK-Client kann den Verbindungsverlust erst nach mehreren Keepalive-Zyklen erkennen. Für normale Updates ist die verbundene MQTT-Variante deshalb der empfohlene Weg.

## Technische Sicherheitsgrenze

Wesentliche Grenze des bestätigten Mainboard-Ablaufs:

```text
C350
→ C36E Status 1
→ C357
→ C36E Status 2
→ C5A8 Firmwaretransfer
→ 100 % Transfer
→ Mainboard-Verarbeitung / Prüfung / Promotion
→ C36E Status 3
→ C36E Status 5
→ Board-Step 12
→ terminaler Erfolg
```

> [!WARNING]
> **100 % C5A8 ist noch kein erfolgreicher Abschluss.** Es bedeutet nur, dass alle Firmwaredaten übertragen wurden.

Erst **C36E Status 5 / Board-Step 12** gilt als terminaler Mainboard-Erfolg.

Vor dem ersten C5A8 kann ein kontrollierter Recovery-/Restorepfad noch zulässig sein. Nach Authority bzw. begonnenem Transfer darf ein generischer Host-/Monitoringfehler den Originaldienst nicht mehr zwangsweise zurücksetzen. Wenn die sichere Beobachtung nach dieser Grenze verloren geht, behält der Runner den aktiven Lock und die Diagnosedaten zur manuellen Beurteilung bei.

## Status nach Verbindungsverlust

Der Button **Status prüfen** liest den auf dem LTE-Modem gespeicherten Runner-Zustand. Der Vorgang wird dabei nicht neu gestartet.

Der Runner unterscheidet anhand seines persistenten Zustands und der Boot-ID zwischen einem bloßen Prozess-/Monitoringverlust und einem tatsächlichen LTE-/Linux-Reboot. Ein später wieder aufgenommener Mainboard-Lauf darf deshalb nicht einfach als eigener Erfolg eines zuvor verlorenen Runs ausgegeben werden.

## Wartung der Statistikzähler

Unter **Erweitert** können ausgewählte persistente Statistikzähler geprüft und gezielt geändert werden:

- DTU-OTA-Vorgänge;
- Mainboard OTA-Vorgänge;
- Dienststarts (`Power-Reset-t`);
- aktive Modem-Neustarts (`Active-Reset-t`).

Vor einem Schreibvorgang wird die vollständige 128-Byte-Statistikdatei gesichert. Der Originaldienst wird kontrolliert gestoppt und wieder gestartet. Danach werden persistente Datei und RAM verifiziert.

`Power-Reset-t` ist besonders: Der untersuchte Originaldienst erhöht diesen Wert bei jedem Start zunächst im RAM. Die Wartungslogik berücksichtigt diesen Start und finalisiert danach den angeforderten Endwert wieder persistent, bevor Datei und RAM abschließend geprüft werden.

## Linux / Raspberry Pi

Der Linux-/Raspberry-Pi-Weg bleibt verfügbar und verwendet für normale Mainboard-Firmwareupdates jetzt ebenfalls den **autonomen DTU-Runner**.

Installation als normaler Benutzer:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Danach stehen unter anderem zur Verfügung:

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST
./foxair-updater restore
./foxair-updater download
./foxair-updater manifest FIRMWARE ...
./foxair-updater version
```

Die vollständige Firmware-/Manifestprüfung ist beim normalen `update` immer aktiv; `--full` ist dafür nicht mehr erforderlich. Eine bereits installierte identische Firmware wird vom Mainboard-/Runner-Ablauf automatisch erkannt, daher entfällt der separate Endanwender-`same-version`-Befehl.

Nach dem Start hängt der Mainboard-OTA nicht mehr von einer dauerhaft bestehenden Raspberry-Pi-/Linux-/ADB-Verbindung ab. Der autonome DTU-Runner kann bei einem Ausfall von `phnixIot4G` den Dienst kontrolliert neu starten, das Runtime-Monitoring erneut anbinden und einen bereits begonnenen Transfer anhand des persistenten OTA-Zustands weiterführen. Zusätzlich existiert ein Stall-Recovery-Pfad für ausbleibenden C5A8-Fortschritt.

Bei `success` oder `same-version` wird zuerst ein lokales Diagnosearchiv erzeugt und verifiziert. Erst danach bestätigt der Host das terminale Ergebnis und entfernt die zu diesem Lauf gehörenden FoxAir-Updater-Daten vom LTE-Modem. Fehler- und Recovery-Daten bleiben dagegen erhalten.

### Raspberry Pi als Server für die Windows-GUI

Der Linux-Installer richtet zusätzlich einen optionalen Netzwerkzugriff ein. Auf einer frischen Installation bleibt er standardmäßig deaktiviert.

```sh
./foxair-updater remote start
./foxair-updater remote status
```

Für einen dauerhaften Start bei jedem Boot:

```sh
./foxair-updater remote enable
```

Der Raspberry Pi stellt dabei zwei getrennte Netzwerkpfade bereit:

```text
Windows-GUI
  ├─ ADB         → Raspberry Pi :5038 → LTE-Modem
  └─ PHNIX Debug → Raspberry Pi :5039 → USB Interface 04 (read-only)
```

In der Windows-GUI wird **Remote – ADB-Server auf Raspberry Pi** gewählt, die IP-Adresse des Raspberry Pi eingetragen und Port `5038` verwendet. Der PHNIX-Debugmonitor nutzt im Remote-Modus automatisch denselben Host auf **ADB-Port + 1**, also standardmäßig TCP `5039`.

Der Debugstream ist absichtlich nur lesend. Es werden keine Netzwerkdaten zurück auf den seriellen PHNIX-Port geschrieben; für diesen FoxAir-Updater-Remoteweg ist deshalb kein `ser2net` erforderlich.

> [!WARNING]
> TCP 5038 und 5039 nur in einem vertrauenswürdigen lokalen Netz verwenden und nicht per Portweiterleitung ins Internet freigeben.

Die **maßgebliche ausführliche Linux-/Raspberry-Pi-Anleitung** steht unter [`../../updater/linux/README.md`](../../updater/linux/README.md). Die Linux-Kurzangaben auf dieser Seite werden bewusst knapp gehalten.

## Real bestätigte Punkte

Real getestet bzw. bestätigt sind unter anderem:

- lokale und Remote-ADB-Verbindung;
- read-only LTE-Backup/Firmware-Download;
- Vorprüfung;
- V3.3 → V3.3 bis zur sicheren Gleichversionsablehnung ohne C5A8;
- vollständiger V3.3 → V3.4-Transfer und terminaler Abschluss;
- vollständiger V1.2 → V3.4-Versionswechsel;
- vollständiger Downgrade V3.5 → V3.4 mit terminalem Abschluss;
- V3.5 als `82400644 / 0035` bestätigt; Quelle ist eine **BlueLine (BL)**, dieselbe Firmwarelinie wird bei entsprechenden **GreenLine-/GL-Geräten** mit `82400644` verwendet; vollständige Updates auf V3.5 wurden inzwischen real erfolgreich durchgeführt;
- C36E Status 5 / Board-Step 12 als terminale Erfolgsgrenze;
- Rückkehr in den normalen LTE-/Cloudzustand;
- autonomer Runner auf realer Hardware einschließlich kontrolliertem Dienstneustart;
- Wartung der bekannten persistenten Statistikzähler.

Weitere technische Details stehen in `docs/reverse_engineering/` und in der Windows-spezifischen Dokumentation unter [`../../updater/windows/README.md`](../../updater/windows/README.md).
