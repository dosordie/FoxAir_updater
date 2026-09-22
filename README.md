# FoxAir Updater

Ein inoffizielles Werkzeug zum **Sichern, Prüfen und Aktualisieren der Mainboard-Firmware** von FoxAir-/PHNIX-Wärmepumpen.

Der Schwerpunkt liegt auf einer möglichst sicheren und nachvollziehbaren Bedienung unter **Windows**. Für Diagnose und Entwicklung stehen zusätzlich Linux-/Raspberry-Pi-Werkzeuge zur Verfügung.

> [!CAUTION]
> ## Firmwareupdates erfolgen auf eigenes Risiko
>
> Erfolgreich auf realer Hardware getestet wurden:
>
> - **V3.3 → V3.4**
> - **V1.2 → V3.4**
>
> Die Firmware **V3.5** ist ebenfalls bekannt und vollständig analysierbar, wurde mit dem FoxAir Updater aber noch nicht als kompletter realer Updatevorgang getestet.
>
> Die vorliegende **V3.5 stammt von einer FoxAir BlueLine (BL)**. Sie verwendet denselben Mainboard-Softwarecode **`82400644`** wie die entsprechende GreenLine-/GL-Firmware. **BlueLine und GreenLine mit diesem Softwarecode verwenden dieselbe Mainboard-Firmwarelinie; V3.5 ist daher zwischen entsprechenden BL- und GL-Geräten der `82400644`-Familie kompatibel.**
>
> Wärmepumpe und LTE-Modul während eines laufenden Firmwareupdates nicht stromlos machen.
>
> **Nutzung ausschließlich auf eigenes Risiko.** Der Ersteller übernimmt keine Gewährleistung oder Haftung für Schäden oder Folgeschäden.

FoxAir Updater ist kein offizielles FoxAir- oder PHNIX-Produkt.

Für normale Steuerung, Modbus-Auswertung und Diagnose gibt es das Schwesterprojekt **[FoxAir Control](https://github.com/dosordie/FoxAir_Control)**.

## 💙 Unterstützung

Ich entwickle dieses Tool in meiner Freizeit.  
Wenn es dir hilft, freue ich mich über eine kleine Spende:

[![Spenden via PayPal](https://img.shields.io/badge/Spenden-PayPal-blue.svg?logo=paypal)](https://www.paypal.com/paypalme/AuhuberD)

---

## Windows-Version herunterladen

Die Windows-Version ist der empfohlene Weg für Endanwender.

Sie steht als **Portable-ZIP** und **Setup-EXE** auf der Releases-Seite bereit:

**[FoxAir Updater – GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases)**

Eine separate Python-Installation ist nicht notwendig.

Für die Verbindung zum LTE-Modul wird **ADB** benötigt. ADB selbst wird aus Lizenz- und Wartungsgründen nicht mitgeliefert; die Anwendung verlinkt die offiziellen Android Platform Tools und die passende USB-/LTE-Anleitung.

> [!NOTE]
> Die Windows-Builds sind derzeit nicht mit einem kommerziellen Code-Signing-Zertifikat signiert. Windows SmartScreen kann deshalb beim ersten Start **„Der Computer wurde durch Windows geschützt“** anzeigen.
>
> Wenn die Datei bewusst von der offiziellen GitHub-Releases-Seite geladen wurde, **Weitere Informationen** und anschließend **Trotzdem ausführen** wählen.

---

## Was kann der FoxAir Updater?

Die Windows-Anwendung bietet unter anderem:

- Verbindung zum FoxAir-/PHNIX-LTE-Modul per USB;
- alternativ Verbindung über einen Raspberry Pi im Netzwerk;
- Firmware- und Diagnose-Backup vom LTE-Modul;
- Prüfung einer Firmwaredatei vor dem Update;
- automatische Prüfung von Dateigröße und Prüfsummen;
- Anzeige des Updatefortschritts;
- Fortsetzen der Statusanzeige nach einem kurzzeitigen Verbindungsverlust;
- Diagnose von LTE, SIM, Cloud-Verbindung und Mainboard;
- Export von Protokollen und Diagnosepaketen;
- erweiterte Wartungs- und Diagnosefunktionen für erfahrene Anwender.

Die Firmwaredatei wird vor dem Start geprüft. Ein Update wird nicht allein deshalb als erfolgreich betrachtet, weil die Datenübertragung 100 % erreicht hat: Das Programm wartet zusätzlich darauf, dass das Mainboard die neue Firmware vollständig geprüft und übernommen hat.

---

## Firmware-Versionen

### Aktuell real getestet

| Ausgangsversion | Zielversion | Status |
|---|---|---|
| V3.3 | V3.4 | ✅ real erfolgreich getestet |
| V1.2 | V3.4 | ✅ real erfolgreich getestet |
| V3.3 | V3.3 | ✅ gleiche Version wird korrekt abgelehnt |
| V3.4 / andere | V3.5 | ⚠️ Firmware bekannt, Update noch nicht real mit dem Updater getestet |

### V3.5: BlueLine und GreenLine

Die untersuchte V3.5 wurde von einer **FoxAir BlueLine (BL)** bezogen.

Sie besitzt:

- Mainboard-Softwarecode **`82400644`**
- Firmwareversion **V3.5**
- dieselbe Mainboard-Firmwarefamilie wie die entsprechenden FoxAir GreenLine-/GL-Geräte

Der Softwarecode `82400644` ist unter anderem bei Geräten der GL- und BL-Reihen belegt. Damit gilt für Geräte dieser Firmwarefamilie:

> **Die Mainboard-Firmware ist nicht grundsätzlich an die Bezeichnung BlueLine oder GreenLine gebunden. Entscheidend ist die gemeinsame Mainboard-Firmwarefamilie `82400644`.**

Die vorliegende V3.5 aus einer BlueLine kann deshalb auch auf entsprechenden GreenLine-/GL-Geräten derselben `82400644`-Familie verwendet werden und umgekehrt.

Bei einem unbekannten Modell sollte trotzdem immer zuerst der tatsächlich ausgelesene Mainboard-Softwarecode geprüft werden.

---

## Typischer Ablauf unter Windows

1. FoxAir Updater herunterladen und starten.
2. LTE-Modul per USB oder Remote-ADB verbinden.
3. Unter **Verbindung** prüfen, ob das Gerät erreichbar ist.
4. Optional vorher ein Backup erstellen.
5. Unter **Firmwareupdate** die Update-Datei bzw. Firmware auswählen.
6. **Vorprüfung** ausführen.
7. Nur bei erfolgreicher Vorprüfung das Firmwareupdate starten.
8. Wärmepumpe und LTE-Modul während des Updates eingeschaltet lassen.
9. Warten, bis der Updater ausdrücklich meldet, dass das Mainboard-Firmwareupdate erfolgreich abgeschlossen wurde.
10. Bei Bedarf anschließend Protokoll oder Diagnosepaket speichern.

Die ausführliche Schritt-für-Schritt-Anleitung gibt es hier:

**[Firmwareupdate unter Windows](docs/HowTo/firmware_update_windows.md)**

---

## Was passiert bei einem Verbindungsverlust?

Nach dem Start läuft der eigentliche Firmwarevorgang auf dem LTE-Modul weiter.

Ein kurzzeitiger Verlust der Windows- oder ADB-Verbindung beendet einen bereits laufenden Updatevorgang daher normalerweise nicht.

Nach Wiederherstellung der Verbindung kann über **Status prüfen** der aktuelle Zustand erneut eingelesen werden. Dadurch wird **kein zweites Firmwareupdate gestartet**.

Das LTE-Modul bzw. die Wärmepumpe sollte während eines laufenden Updates trotzdem nicht absichtlich neu gestartet oder stromlos gemacht werden.

---

## Screenshots

> [!NOTE]
> Die Screenshots zeigen den grundsätzlichen Aufbau der Windows-GUI. Einzelne Texte und Optionen können je nach Programmversion abweichen.

| Verbindung | Backup |
|---|---|
| <img src="docs/DTU_1_connect.png" width="520" alt="FoxAir Updater Verbindung"> | <img src="docs/DTU_2_Backup.png" width="520" alt="FoxAir Updater Backup"> |

| Firmwareupdate | Modem Info / LTE Diagnose |
|---|---|
| <img src="docs/DTU_3_update.png" width="520" alt="FoxAir Updater Firmwareupdate"> | <img src="docs/DTU_4_info.png" width="520" alt="FoxAir Updater Modem Info"> |

---

## Firmwaredateien

Firmwaredateien werden **nicht über dieses öffentliche GitHub-Repository verteilt**.

Der Updater lädt nicht automatisch irgendeine Mainboard-Firmware aus diesem Repository. Eine Firmwaredatei muss bewusst ausgewählt bzw. als passendes Updatepaket bereitgestellt werden.

Vor dem Update prüft der Updater unter anderem:

- Firmware-/Softwarecode;
- Firmwareversion;
- Dateigröße;
- Prüfsummen;
- Zusammengehörigkeit der ausgewählten Update-Dateien.

Die Firmwaredatei selbst wird dabei nicht verändert.

---

## Firmware-Backup

Unter Windows ist die grafische Backup-Funktion der empfohlene Weg.

Damit lassen sich die für Diagnose und Wiederherstellung interessanten Daten des LTE-Moduls sichern, ohne sie zu verändern.

Ausführliche Anleitung:

**[LTE-Modul verbinden und Firmware-Backup erstellen](docs/HowTo/firmware_backup_lte.md)**

Firmware- und Gerätedateien aus dem LTE-Modul sollten nicht ungeprüft öffentlich geteilt werden.

---

## Erweiterte Diagnose

Im Programm gibt es zusätzliche Diagnose- und Wartungsfunktionen, die für ein normales Firmwareupdate nicht benötigt werden.

Dazu gehören unter anderem:

- LTE-/SIM-Informationen;
- Cloud-/Verbindungsdiagnose;
- Mainboard-Informationen;
- LTE-DTU-Debugmonitor;
- Diagnosepaket;
- erweiterte Updateoptionen;
- Wartung ausgewählter interner Statistikzähler.

Für ein normales Update sollten diese Einstellungen unverändert bleiben.

---

## Linux / Raspberry Pi

Für erfahrene Anwender gibt es weiterhin einen Linux-/Raspberry-Pi-Weg.

Installation als normaler Benutzer:

```sh
cd ~
wget -O install.sh \
  https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/updater/linux/install.sh
bash install.sh
```

Danach stehen unter anderem folgende Befehle zur Verfügung:

```text
./foxair-updater status
./foxair-updater check MANIFEST
./foxair-updater update MANIFEST --confirm
./foxair-updater restore
./foxair-updater manifest FIRMWARE ...
./foxair-updater version
```

Für Endanwender unter Windows ist die grafische Anwendung normalerweise deutlich einfacher.

---

## Weitere Dokumentation

- **[Firmwareupdate unter Windows](docs/HowTo/firmware_update_windows.md)**
- **[Endanwender-Anleitung](docs/HowTo/PHNIX_UPDATER_ENDANWENDER.md)**
- **[LTE-Modul / Firmware-Backup](docs/HowTo/firmware_backup_lte.md)**
- **[Technische Reverse-Engineering-Dokumentation](docs/reverse_engineering/)**

Die technischen Dokumente enthalten bewusst deutlich mehr interne Details als diese README.

---

## Projektumfang

FoxAir Updater beschäftigt sich mit:

- Mainboard-Firmwareupdates;
- Firmware-Backup;
- Update- und Recovery-Verhalten;
- LTE-DTU-/PHNIX-Kommunikation;
- Firmwareanalyse und Reverse Engineering;
- Diagnose- und Validierungswerkzeugen.

Für normale Wärmepumpensteuerung, Registeranzeige und Modbus-Parametrierung ist **[FoxAir Control](https://github.com/dosordie/FoxAir_Control)** das passendere Projekt.

---

## Lizenz

Dieses Repository steht unter der **GNU General Public License v3.0**, SPDX-Kennung **`GPL-3.0-only`**.

Siehe [LICENSE](LICENSE).

Weitergabe und Änderungen sind damit erlaubt. Abgeleitete Werke müssen bei Weitergabe ebenfalls unter den Bedingungen der GPLv3 stehen und der zugehörige Quellcode muss gemäß den Lizenzbedingungen verfügbar gemacht werden.

Die GPL enthält ausdrücklich einen Gewährleistungs- und Haftungsausschluss.
