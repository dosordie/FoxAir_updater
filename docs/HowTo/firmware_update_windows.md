# Firmware-Update mit dem FoxAir Updater unter Windows

Stand: 1. September 2026

Diese Anleitung beschreibt **nur den normalen Firmware-Update-Ablauf für Endanwender unter Windows**.

Die Einrichtung der USB-/ADB-Verbindung zum LTE-Modem ist identisch mit dem Verbindungsweg für das Firmware-Backup und wird separat beschrieben:

**[LTE-Modem verbinden / Firmware-Backup](firmware_backup_lte.md)**

> [!CAUTION]
> Ein Firmwareupdate verändert die Firmware des Mainboards und erfolgt **auf eigenes Risiko**. Während des laufenden Updates Wärmepumpe und LTE-Modem **nicht stromlos machen** und die USB-/ADB-Verbindung nicht absichtlich trennen.
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

1. Im FoxAir Updater die Registerkarte **Firmware Update** öffnen.
2. Auf **Update-Datei…** klicken.
3. Die zum Firmwarepaket gehörende **JSON-Datei** auswählen.
4. Prüfen, ob die angezeigten Informationen zur vorgesehenen Firmware passen und die Firmwaredatei als vorhanden erkannt wird.

## 4. Vorprüfung durchführen

Auf **Vorprüfung / Dry-Run** klicken.

Die Vorprüfung kontrolliert die Voraussetzungen für das Update. Dabei wird **noch kein Firmwareupdate durchgeführt**.

Nur fortfahren, wenn die Vorprüfung erfolgreich abgeschlossen wurde.

> [!WARNING]
> Schlägt die Vorprüfung fehl, das Firmwareupdate **nicht starten**. Die Fehlermeldungen stehen im Protokoll und sollten für die weitere Analyse gesichert werden.

## 5. Firmwareupdate starten

Nach erfolgreicher Vorprüfung:

1. Den Haken bei **Risiko des Firmwareupdates verstanden.** setzen.
2. Auf **FIRMWAREUPDATE STARTEN** klicken.
3. Die zusätzliche Sicherheitsabfrage bestätigen.
4. Den Updatevorgang vollständig abwarten.

Während des Updates zeigt der FoxAir Updater den aktuellen Ablauf und den Fortschritt an.

> [!IMPORTANT]
> **100 % Firmwareübertragung bedeutet noch nicht automatisch, dass das Update vollständig abgeschlossen ist.**
>
> Nach der Übertragung verarbeitet und prüft das Mainboard die neue Firmware weiter. Erst wenn der FoxAir Updater ausdrücklich **„Firmwareupdate erfolgreich“** meldet und der normale Betriebszustand anschließend geprüft wurde, ist der Vorgang abgeschlossen.

## 6. Protokoll / Log sichern

Der FoxAir Updater führt während der Vorprüfung und des Firmwareupdates ein Protokoll. Die Meldungen stehen auch dann zur Verfügung, wenn ein Update **fehlschlägt oder geschützt abgebrochen wird**.

Nach einem Updateversuch kann das Protokoll über **Log speichern…** als Datei gesichert werden.

Das ist besonders sinnvoll:

- nach einem erfolgreichen Update als eigene Dokumentation;
- bei einer Warnung oder einem fehlgeschlagenen Update;
- wenn das Log zur Analyse an eine andere Person weitergegeben werden soll.

Bei Problemen möglichst **das vollständige Log sichern**, bevor das Protokoll geleert oder das Programm beendet wird.

## Kurzfassung

1. Update-ZIP lokal entpacken.
2. LTE-Modem verbinden und **ADB prüfen**.
3. **Firmware Update** öffnen.
4. **Update-Datei…** → JSON-Datei auswählen.
5. **Vorprüfung / Dry-Run** ausführen.
6. Nur bei erfolgreicher Vorprüfung den Haken **Risiko des Firmwareupdates verstanden.** setzen.
7. **FIRMWAREUPDATE STARTEN** anklicken und Sicherheitsabfrage bestätigen.
8. Wärmepumpe/LTE-Modem während des Vorgangs nicht stromlos machen.
9. Bis zur ausdrücklichen Meldung **Firmwareupdate erfolgreich** warten.
10. Anschließend das **Log speichern**, besonders bei Warnungen oder Fehlern.

Real erfolgreich durchgeführt: **V3.3 → V3.4** und **V1.2 (Auslieferungszustand) → V3.4**.
