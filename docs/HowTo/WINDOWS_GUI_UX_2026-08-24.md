# Windows-GUI: Treiber, Updateprüfung und persistente Einstellungen

Stand: 24. August 2026

Diese Änderung betrifft ausschließlich die Windows-Bedienoberfläche, die lokale Host-Konfiguration und den Windows-Sicherheitswrapper. Der PHNIX-OTA-Core, der Runtime-Hook und der RS485-/C5A8-Ablauf werden dadurch nicht verändert.

## Verbindungsvoraussetzungen

Für eine direkte USB-Verbindung unter Windows zeigt die GUI die Voraussetzungen nun in der vorgesehenen Reihenfolge:

1. **SIMCom USB-Treiber**
   - `SIMCOM Windows USB Drivers V1.0.2`
   - Quelle: `https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip`
2. **Android SDK Platform Tools / ADB**
   - ADB wird weiterhin nicht mit dem FoxAir Updater ausgeliefert.

Der Treiberlink entspricht dem bereits in `docs/HowTo/firmware_backup_lte.md` dokumentierten Treiber.

## Windows SmartScreen

Die veröffentlichten Setup-/Portable-Builds sind derzeit **nicht mit einem kommerziellen Windows-Code-Signing-Zertifikat signiert**. Deshalb kann Windows SmartScreen beim ersten Start eine Meldung wie **„Der Computer wurde durch Windows geschützt“** anzeigen.

Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite dieses Projekts heruntergeladen wurde:

1. im SmartScreen-Fenster **Weitere Informationen** anklicken;
2. danach **Trotzdem ausführen** wählen.

Das ist kein vom Updater selbst erzeugter Fehlerdialog. Bei einer Datei aus einer anderen oder unbekannten Quelle sollte sie dagegen nicht einfach freigegeben werden.

## GitHub-Updateprüfung

Die Windows-GUI prüft beim Start im Hintergrund und auf manuellen Knopfdruck das aktuelle GitHub Release von `dosordie/FoxAir_updater`.

Die Prüfung:

- liest ausschließlich die Metadaten von GitHubs `releases/latest`-API;
- vergleicht den Release-Tag, zum Beispiel `windows-v0.1.8`, mit der lokal eingebauten `APP_VERSION`;
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

### Korrektur in v0.1.8: Remote-IP und Port

In v0.1.7 waren die Werte zwar in `QSettings` gespeichert, beim nächsten Programmstart wurden aber die Radio-/Textfeld-Signale zu früh ausgelöst. Dadurch konnte die gespeicherte Raspberry-Pi-IP mit einem leeren Feld und der gespeicherte Port mit dem Default `5038` überschrieben werden, bevor die Werte vollständig geladen waren.

v0.1.8 liest zuerst alle gespeicherten Verbindungswerte, blockiert während des Einsetzens die Writeback-Signale und aktiviert sie erst anschließend wieder. Damit bleiben Remote-Modus, IP und Port über Programmstarts erhalten.

Manuell geänderte Felder werden weiterhin spätestens beim Verlassen des Feldes beziehungsweise beim Schließen der GUI synchronisiert.

## Korrektur in v0.1.8: Same-Version und Host-Run-State

Beim normalen Windows-Updatepfad kann der Controller bereits einen `--state-dir` von der GUI erhalten. v0.1.7 startete den Controller korrekt mit diesem Pfad, suchte nach erfolgreichem Exit aber anschließend in einem anderen Wrapper-Defaultpfad nach `run-state.json`. Dadurch konnte ein korrektes V3.3→V3.3-`same-version` nachträglich fälschlich als

```text
FEHLER: Terminaler Host-Run-State des Updates fehlt
```

mit Exit-Code 2 erscheinen.

v0.1.8 verwendet für Start **und** Abschlussprüfung exakt denselben effektiven `--state-dir`. Zusätzlich wird vor dem Start eine Momentaufnahme vorhandener `run-state.json`-Dateien erstellt. Als Abschlussbeweis zählt danach nur ein neu angelegter oder veränderter Run-State; ein alter erfolgreicher Lauf kann nicht versehentlich als aktueller Abschluss verwendet werden.

Der Fehler lag ausschließlich in der Windows-Host-Auswertung nach dem bereits terminal beendeten Controllerlauf. Er ändert nichts an C350/C357/C5A8 oder am Mainboard-Verhalten.

### Einmalige Bereinigung nach dem bekannten v0.1.7-False-Positive

Wenn ein Lauf nachweislich mit

```text
phase=same-version
c357_sent=false
c5a8_sent=false
state_restored=true
services-restored ok=true
```

beendet wurde und erst danach der oben genannte Host-Run-State-Fehler erschien, kann lokal der liegengebliebene Marker entfernt werden:

```powershell
Remove-Item "$env:LOCALAPPDATA\FoxAir Updater\windows-wrapper-state\original-cache\cache.pending"
```

Die historischen Verzeichnisse unter dem eigentlichen `phnix-ota-state` sollen **nicht** gelöscht werden; sie sind nützliche Ablaufprotokolle. Auf dem LTE-Modem muss für diesen bekannten Same-Version-Fall nichts manuell gelöscht werden.

Diese manuelle Bereinigung ist ausdrücklich nur für einen eindeutig bestätigten Pre-C5A8-/Same-Version-Fall gedacht. Bei einem unbekannten oder bereits begonnenen C5A8-Lauf darf der Marker nicht blind entfernt werden.

## Sicherheitsabgrenzung

Diese Änderung führt keine neuen Befehle auf dem LTE-Modem oder Mainboard aus. Insbesondere unverändert bleiben:

- `phnix_local_ota_controller.py`;
- `phnix_ota_runtime_hook`;
- C350/C357/C5A8/C371;
- Guarded-Hold-/Recovery-Entscheidungen;
- Post-C5A8-Lifecycle.

Die noch offene Untersuchung des USB-/ADB-Ausfalls während eines begonnenen C5A8-Transfers bleibt damit weiterhin eine separate Arbeitseinheit.
