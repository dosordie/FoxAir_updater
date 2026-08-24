# Windows-GUI: Treiber, Updateprüfung und persistente Einstellungen

Stand: 24. August 2026

Diese Änderung betrifft ausschließlich die Windows-Bedienoberfläche und ihre lokale Host-Konfiguration. Der PHNIX-OTA-Core, der Runtime-Hook und der RS485-/C5A8-Ablauf werden dadurch nicht verändert.

## Verbindungsvoraussetzungen

Für eine direkte USB-Verbindung unter Windows zeigt die GUI die Voraussetzungen nun in der vorgesehenen Reihenfolge:

1. **SIMCom USB-Treiber**
   - `SIMCOM Windows USB Drivers V1.0.2`
   - Quelle: `https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip`
2. **Android SDK Platform Tools / ADB**
   - ADB wird weiterhin nicht mit dem FoxAir Updater ausgeliefert.

Der Treiberlink entspricht dem bereits in `docs/HowTo/firmware_backup_lte.md` dokumentierten Treiber.

## GitHub-Updateprüfung

Die Windows-GUI prüft beim Start im Hintergrund und auf manuellen Knopfdruck das aktuelle GitHub Release von `dosordie/FoxAir_updater`.

Die Prüfung:

- liest ausschließlich die Metadaten von GitHubs `releases/latest`-API;
- vergleicht den Release-Tag, zum Beispiel `windows-v0.1.7`, mit der lokal eingebauten `APP_VERSION`;
- zeigt nur an, ob eine neuere Version vorhanden ist;
- bietet einen Link zur GitHub-Release-Seite an;
- lädt keine Dateien automatisch herunter;
- installiert nichts automatisch;
- beeinflusst bei Netzwerk-/GitHub-Fehlern keine ADB-, Backup- oder OTA-Funktion.

Die reine HTTP-/Versionslogik liegt in `updater/windows/release_check.py` und verwendet nur die Python-Standardbibliothek. Das entspricht dem einfachen Grundprinzip der Updateprüfung aus `FoxAir_Control`.

## Persistente Einstellungen

Die GUI verwendet weiterhin `QSettings("FoxAir", "FoxAir Updater")`. Es wird keine zweite Konfigurationsdatei eingeführt.

Gespeichert beziehungsweise wiederverwendet werden:

- ADB-Pfad;
- lokaler oder Remote-ADB-Modus;
- Raspberry-Pi-/ADB-Server-IP;
- ADB-Server-Port;
- Backup-Zielordner;
- zuletzt verwendeter ADB-Ordner;
- zuletzt verwendeter Manifest-Ordner;
- zuletzt verwendeter Firmware-Ordner.

Manuell geänderte Felder werden spätestens beim Verlassen des Feldes beziehungsweise beim Schließen der GUI synchronisiert.

## Sicherheitsabgrenzung

Diese Änderung führt keine neuen Befehle auf dem LTE-Modem oder Mainboard aus. Insbesondere unverändert bleiben:

- `phnix_local_ota_controller.py`;
- `phnix_ota_runtime_hook`;
- C350/C357/C5A8/C371;
- Guarded-Hold-/Recovery-Entscheidungen;
- Post-C5A8-Lifecycle.

Die noch offene Untersuchung des USB-/ADB-Ausfalls während eines begonnenen C5A8-Transfers bleibt damit weiterhin eine separate Arbeitseinheit.
