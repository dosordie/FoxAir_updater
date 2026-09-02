# Firmware-Update mit dem FoxAir Updater unter Windows

Stand: 2. September 2026

Diese Anleitung beschreibt **nur den normalen Firmware-Update-Ablauf für Endanwender unter Windows**.

Die Einrichtung der USB-/ADB-Verbindung zum LTE-Modem ist identisch mit dem Verbindungsweg für das Firmware-Backup und wird separat beschrieben:

**[LTE-Modem verbinden / Firmware-Backup](firmware_backup_lte.md)**

> [!CAUTION]
> Ein Firmwareupdate verändert die Firmware des Mainboards und erfolgt **auf eigenes Risiko**. Während des laufenden Updates Wärmepumpe und LTE-Modem **nicht stromlos machen**.
>
> Real erfolgreich bestätigt sind inzwischen sowohl ein vollständiger Versionswechsel **V3.3 → V3.4** als auch ein direktes Update von **V1.2 (Auslieferungszustand) → V3.4**. Diese realen Tests sind keine Garantie für beliebige andere Firmwarestände oder Hardwarevarianten.

## 1. Updatepaket vorbereiten

Die für ein Update verteilte ZIP-Datei enthält normalerweise:

- die eigentliche **Firmwaredatei**;
- eine dazugehörige **Update-Datei im JSON-Format**.

Die JSON-Datei enthält die zum Update gehörenden Firmwareinformationen und Prüfdaten. Beide Dateien gehören zusammen.

1. Die erhaltene ZIP-Datei in einen **lokalen Ordner auf dem Windows-PC entpacken**.
2. Firmwaredatei und JSON-Datei im selben Ordner belassen und nicht umbenennen.

> [!IMPORTANT]
> Firmwaredateien werden **nicht über das öffentliche GitHub-Repository bereitgestellt**. Sie werden separat über die vorgesehenen Foren-/Community-Kanäle verteilt.
>
> Firmwarepakete bitte **nicht eigenständig öffentlich spiegeln, in öffentliche Repositories hochladen oder anderweitig öffentlich bereitstellen**.

## 2. Verbindung zum LTE-Modem herstellen

FoxAir Updater starten und unter **Verbindung** die ADB-Verbindung prüfen.

Das LTE-Modem muss erreichbar sein und von ADB im Status `device` erkannt werden.

Falls die Verbindung noch nicht eingerichtet ist, zuerst die separate Anleitung verwenden:

**[Firmware-Backup des LTE-Modems über Micro-USB](firmware_backup_lte.md)**

Dort sind sowohl der direkte Anschluss an einen Windows-PC als auch Remote-ADB über einen Raspberry Pi beschrieben.

## 3. Update-Datei laden

1. Im FoxAir Updater die Registerkarte **Firmwareupdate** öffnen.
2. Auf **Update-Datei…** klicken.
3. Die zum Firmwarepaket gehörende **JSON-Datei** auswählen.
4. Prüfen, ob die angezeigten Informationen zur vorgesehenen Firmware passen und die Firmwaredatei als vorhanden erkannt wird.

## 4. Vorprüfung durchführen

Auf **Vorprüfung** klicken.

Die Vorprüfung kontrolliert unter anderem Update-Datei, Prüfsummen, verfügbaren Speicherplatz und den Zustand des LTE-Modems. Dabei wird **noch keine Firmware an das Mainboard übertragen**.

Nur fortfahren, wenn **Vorprüfung erfolgreich** angezeigt wird.

> [!WARNING]
> Schlägt die Vorprüfung fehl, das Firmwareupdate **nicht starten**. Die Fehlermeldungen stehen im Protokoll und sollten für die weitere Analyse gesichert werden.

## 5. Firmwareupdate starten

Nach erfolgreicher Vorprüfung:

1. Den Haken bei **Risiko des Firmwareupdates verstanden.** setzen.
2. Auf **Firmwareupdate starten** klicken.
3. Die zusätzliche Sicherheitsabfrage bestätigen.
4. Den Updatevorgang vollständig abwarten.

Der eigentliche Updatevorgang wird nach dem Start **autonom auf dem LTE-Modem weitergeführt**. Windows liest den dort persistent gespeicherten Zustand und zeigt Ablauf und Fortschritt an.

Eine unterbrochene Windows- oder ADB-Verbindung beendet einen bereits gestarteten Updatevorgang daher nicht. Nach Wiederherstellung der Verbindung kann über **Status prüfen** der gespeicherte Stand erneut gelesen werden. Trotzdem sollten Verbindung, Wärmepumpe und LTE-Modem während eines Updates möglichst ungestört bleiben.

> [!IMPORTANT]
> **100 % Firmwareübertragung bedeutet noch nicht automatisch, dass das Update vollständig abgeschlossen ist.**
>
> Nach der Übertragung verarbeitet, prüft und übernimmt das Mainboard die neue Firmware weiter. Erst wenn der FoxAir Updater ausdrücklich **„Das Mainboard-Firmwareupdate wurde erfolgreich abgeschlossen.“** meldet, ist der Mainboard-Updatepfad terminal erfolgreich bestätigt.

Technisch wird der Erfolg erst nach der finalen Mainboard-Rückmeldung **C36E Status 5 / Board-Step 12** als abgeschlossen gewertet. Ein bloßer Verbindungsabbruch oder das Erreichen von 100 % darf nicht als Erfolg interpretiert werden.

## 6. Status und Wiederaufnahme der Anzeige

Der Updatezustand wird auf dem LTE-Modem gespeichert. Falls Windows, die GUI oder ADB während des Updates kurzzeitig nicht erreichbar sind:

1. Verbindung wiederherstellen bzw. ADB erneut verbinden.
2. Unterhalb der Updateanzeige bzw. bei den Protokoll-Schaltflächen **Status prüfen** wählen.
3. Der FoxAir Updater liest den gespeicherten Runner-Zustand erneut ein.

Dabei wird **kein zweiter Updatevorgang gestartet**.

Ein sicherer Abbruch ist nur möglich, solange noch keine Firmwareübertragung zum Mainboard begonnen hat. Nach Beginn der Firmwareübertragung bleibt der originale LTE-Dienst für den laufenden Mainboard-OTA autoritativ.

## 7. Protokoll sichern

Der FoxAir Updater führt während Vorprüfung und Firmwareupdate ein sichtbares Protokoll. Zusätzlich werden bei einem Update automatische Controller-/LTE-Protokolle im Firmwareordner unter `Logs` angelegt, soweit der Ordner beschreibbar ist.

Das sichtbare Protokoll kann über **Protokoll speichern…** als Datei gesichert werden.

Das ist besonders sinnvoll:

- nach einem erfolgreichen Update als eigene Dokumentation;
- bei einer Warnung oder einem fehlgeschlagenen Update;
- wenn Protokolle zur Analyse weitergegeben werden sollen.

Bei Problemen möglichst **die vollständigen Protokolle sichern**, bevor Daten gelöscht oder das Programm beendet werden.

## 8. Erweiterte Optionen

Unter **Erweitert** befinden sich Optionen, die im normalen Ablauf normalerweise nicht geändert werden müssen.

- **phnixIot4G vor Firmwareupdate neu starten:** Der kontrollierte Neustart des LTE-Kommunikationsdienstes kann für den Updatepfad angefordert werden. Der Runner verifiziert dabei, dass tatsächlich eine neue, einzelne und nicht von einem Debugger belegte Dienstinstanz läuft, bevor das Update fortgesetzt wird.
- **MQTT bei Update aus:** optionale Test-/Sonderfunktion. Im normalen Updatepfad bleibt MQTT verbunden.

Die Wartungsfunktionen für persistente Statistikzähler gehören **nicht** zum normalen Firmwareupdate und sollten nur gezielt verwendet werden.

## Kurzfassung

1. Update-ZIP lokal entpacken.
2. LTE-Modem verbinden und **ADB prüfen**.
3. **Firmwareupdate** öffnen.
4. **Update-Datei…** → JSON-Datei auswählen.
5. **Vorprüfung** ausführen.
6. Nur bei erfolgreicher Vorprüfung den Haken **Risiko des Firmwareupdates verstanden.** setzen.
7. **Firmwareupdate starten** anklicken und Sicherheitsabfrage bestätigen.
8. Wärmepumpe/LTE-Modem während des Vorgangs nicht stromlos machen.
9. 100 % Übertragung noch **nicht** als Abschluss betrachten.
10. Bis zur ausdrücklichen terminalen Erfolgsmeldung warten.
11. Bei Verbindungsverlust nach Wiederherstellung **Status prüfen** verwenden; dadurch wird kein zweiter OTA gestartet.
12. Anschließend bei Bedarf **Protokoll speichern…** und die automatischen Logs sichern.

Real erfolgreich durchgeführt: **V3.3 → V3.4** und **V1.2 (Auslieferungszustand) → V3.4**.
