# Windows-GUI: Treiber, Updateprüfung und persistente Einstellungen

Stand: 24. August 2026

> [!IMPORTANT]
> **Historisches Änderungsdokument.** Diese Datei beschreibt den Windows-GUI-Stand vom 24. August 2026 (damals v0.1.x).
>
> Aktueller Endanwenderstand ist Windows **v0.3.9**. Inzwischen wurde V3.3→V3.4 real erfolgreich durchgeführt, MQTT bleibt beim normalen Update standardmäßig verbunden, die allgemeine Experimentell-Kennzeichnung wurde entfernt und der Post-C5A8-/ADB-Reconnectpfad wurde weiterentwickelt.
>
> Für aktuelle Bedienung und Architektur siehe [`../../updater/windows/README.md`](../../updater/windows/README.md), [`PHNIX_UPDATER_ENDANWENDER.md`](PHNIX_UPDATER_ENDANWENDER.md) und [`../RELEASE_NOTES_WINDOWS_v0.3.9.md`](../RELEASE_NOTES_WINDOWS_v0.3.9.md).

Die nachfolgenden Abschnitte bleiben als historische Dokumentation der damaligen GUI-Änderungen erhalten.

## Verbindungsvoraussetzungen

Für eine direkte USB-Verbindung unter Windows zeigte die GUI die Voraussetzungen in der vorgesehenen Reihenfolge:

1. **SIMCom USB-Treiber**
   - `SIMCOM Windows USB Drivers V1.0.2`
   - Quelle: `https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip`
2. **Android SDK Platform Tools / ADB**
   - ADB wird weiterhin nicht mit dem FoxAir Updater ausgeliefert.

Der Treiberlink entspricht dem in `docs/HowTo/firmware_backup_lte.md` dokumentierten Treiber.

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
- vergleicht den Release-Tag mit der lokal eingebauten `APP_VERSION`;
- zeigt nur an, ob eine neuere Version vorhanden ist;
- bietet einen Link zur GitHub-Release-Seite an;
- lädt keine Dateien automatisch herunter;
- installiert nichts automatisch;
- beeinflusst bei Netzwerk-/GitHub-Fehlern keine ADB-, Backup- oder OTA-Funktion.

Die HTTP-/Versionslogik liegt in `updater/windows/release_check.py` und verwendet nur die Python-Standardbibliothek.

## Persistente Einstellungen

Die GUI verwendet `QSettings("FoxAir", "FoxAir Updater")`.

Damals gespeichert beziehungsweise wiederverwendet wurden unter anderem:

- ADB-Pfad;
- lokaler oder Remote-ADB-Modus;
- Raspberry-Pi-/ADB-Server-IP;
- ADB-Server-Port;
- Backup-Zielordner;
- zuletzt verwendeter ADB-Ordner;
- zuletzt verwendeter Manifest-Ordner;
- zuletzt verwendeter Firmware-Ordner.

Später kam unter anderem die persistente Einstellung **MQTT bei Update aus** hinzu.

### Historische Korrektur in v0.1.8: Remote-IP und Port

In v0.1.7 waren die Werte zwar in `QSettings` gespeichert, beim nächsten Programmstart wurden aber die Radio-/Textfeld-Signale zu früh ausgelöst. Dadurch konnte die gespeicherte Raspberry-Pi-IP mit einem leeren Feld und der gespeicherte Port mit dem Default `5038` überschrieben werden, bevor die Werte vollständig geladen waren.

v0.1.8 las zuerst alle gespeicherten Verbindungswerte ein und blockierte während des Einsetzens die Writeback-Signale. Damit blieben Remote-Modus, IP und Port über Programmstarts erhalten.

## Historische Korrektur in v0.1.8: Same-Version und Host-Run-State

Beim normalen Windows-Updatepfad kann der Controller einen `--state-dir` von der GUI erhalten. v0.1.7 startete den Controller korrekt mit diesem Pfad, suchte nach erfolgreichem Exit aber anschließend in einem anderen Wrapper-Defaultpfad nach `run-state.json`.

Dadurch konnte ein korrektes V3.3→V3.3-`same-version` nachträglich fälschlich als

```text
FEHLER: Terminaler Host-Run-State des Updates fehlt
```

mit Exit-Code 2 erscheinen.

v0.1.8 verwendete für Start und Abschlussprüfung denselben effektiven `--state-dir`. Zusätzlich wurde vor dem Start eine Momentaufnahme vorhandener `run-state.json`-Dateien erstellt. Als Abschlussbeweis zählte danach nur ein neu angelegter oder veränderter Run-State.

Der Fehler lag ausschließlich in der Windows-Host-Auswertung nach dem bereits terminal beendeten Controllerlauf und änderte nichts an C350/C357/C5A8 oder am Mainboard-Verhalten.

### Einmalige Bereinigung nach dem bekannten v0.1.7-Fall

Wenn ein damaliger Lauf nachweislich mit

```text
phase=same-version
c357_sent=false
c5a8_sent=false
state_restored=true
services-restored ok=true
```

beendet wurde und erst danach der Host-Run-State-Fehler erschien, konnte lokal der liegengebliebene Marker entfernt werden:

```powershell
Remove-Item "$env:LOCALAPPDATA\FoxAir Updater\windows-wrapper-state\original-cache\cache.pending"
```

Die historischen Verzeichnisse unter dem eigentlichen `phnix-ota-state` sollten nicht gelöscht werden; sie sind nützliche Ablaufprotokolle.

Diese manuelle Bereinigung galt ausdrücklich nur für den eindeutig bestätigten Pre-C5A8-/Same-Version-Fall. Bei einem unbekannten oder bereits begonnenen C5A8-Lauf durfte der Marker nicht blind entfernt werden.

## Sicherheitsabgrenzung dieser damaligen Änderung

Die UX-Änderung selbst führte keine neuen Befehle auf LTE-Modem oder Mainboard aus. Unverändert blieben damals insbesondere:

- `phnix_local_ota_controller.py`;
- `phnix_ota_runtime_hook`;
- C350/C357/C5A8/C371;
- Guarded-Hold-/Recovery-Entscheidungen;
- Post-C5A8-Lifecycle.

Die damals noch offene Untersuchung des USB-/ADB-Ausfalls während eines begonnenen C5A8-Transfers wurde später separat bearbeitet. Der aktuelle Updater behandelt einen Monitoringverlust nach begonnenem C5A8 so, dass der originale `phnixIot4G`-Dienst autoritativ bleibt und ein generischer Restore nicht in den laufenden Transfer eingreift.