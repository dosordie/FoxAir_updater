# DTU OTA Runner – Roadmap für den vollständigen Umbau

> **Temporäre Entwicklungsdokumentation**
>
> Diese Datei dient ausschließlich als Arbeits-/Umbauplan im Branch `DTU_runner`.
> Nach Abschluss des Umbaus, Übernahme der dauerhaften Erkenntnisse in die normale
> Dokumentation und erfolgreicher Abnahme soll `docs/dev/` wieder gelöscht werden.

Stand: 1. September 2026

## 1. Zielbild

Der bisherige OTA-Ablauf wird so umgebaut, dass der **kritische Updatevorgang vollständig
auf dem PHNIX-LTE-Modem ausgeführt und überwacht wird**.

Windows/ADB übernimmt danach nur noch:

1. Vorprüfung und Paketvorbereitung;
2. Upload von Runner, Hook, Auftrag und Firmware;
3. Start eines detached OTA-Runners;
4. read-only Status- und Logabfrage;
5. optional einen kontrollierten Abort-Request;
6. Bestätigung eines terminalen Ergebnisses (`ack`);
7. kontrollierte Bereinigung (`cleanup`).

Nach erfolgreichem Start des Runners darf ein Verlust von Windows, ADB, USB oder des
Remote-ADB-Servers den laufenden OTA-Vorgang **nicht mehr beeinflussen**.

Zielarchitektur:

```text
Windows GUI / CLI
      │
      ├─ Firmware + Manifest lokal prüfen
      ├─ Runner + Hook + Auftrag + Firmware kopieren
      ├─ detached starten
      │
      └─ nur noch lesen / kontrollierte Requests schreiben
                           │
                           ▼
                 DTU OTA Supervisor
                   ├─ Auftrag erneut prüfen
                   ├─ exklusiven Run übernehmen
                   ├─ persistenten Run-Zustand führen
                   ├─ Originalzustand sichern
                   ├─ Runtime-Hook starten
                   ├─ Hook/OTA lokal überwachen
                   ├─ Fortschritt persistieren
                   ├─ Recovery lokal entscheiden
                   ├─ terminales Ergebnis persistieren
                   └─ auf Ack/Cleanup warten
                           │
                           ▼
                 phnix_ota_runtime_hook
                   ├─ Originaldienst verifizieren
                   ├─ C350 auslösen
                   ├─ C357/C5A8 beobachten
                   ├─ Transfergrenze markieren
                   ├─ Status 3 / 5 beobachten
                   └─ Step 12 / terminales Ergebnis
```

## 2. Warum `/data` für den Supervisor und `/tmp` für den Hook?

Die beiden Pfade haben bewusst unterschiedliche Aufgaben.

### `/tmp`: flüchtiger Runtime-Zustand

Der vorhandene Runtime-Hook verwendet `/tmp/phnix_ota_hook` unter anderem für:

- `helper.pid`;
- `gdb.pid` / `gdbserver.pid`;
- generierte GDB-Skripte;
- `watchdogs.pids`;
- Marker wie `run.active`, `transfer-started`, `injection-started` und
  `original-service-owns`;
- weitere Daten, die direkt an **aktuell laufende Prozesse** gekoppelt sind.

Das ist sinnvoll. Nach einem Modem-Neustart sind diese PIDs, Debuggerprozesse und
Prozessbeziehungen ohnehin ungültig. Dieser Zustand soll daher **nicht als dauerhafte
Wahrheit** behandelt werden.

### `/data`: dauerhafter übergeordneter Run-Zustand

Der neue Supervisor benötigt dagegen Informationen, die auch nach Verlust der
ADB-Verbindung noch vorhanden sein müssen:

- Run-ID;
- Auftrag / Paketidentität;
- letzte bekannte OTA-Phase;
- letzter Fortschritt;
- Zeitpunkt der letzten Aktivität;
- ob C5A8 bereits begonnen hat;
- ob der Originaldienst bereits autoritativ ist;
- terminales Ergebnis;
- Fehlergrund;
- Recovery-Ergebnis;
- Log;
- Acknowledgement durch Windows;
- Cleanup-Status.

Diese Daten gehören deshalb unter `/data/foxair_ota_runner/`.

Wichtig: Das Design darf **nicht darauf angewiesen sein, dass `/tmp` einen Modem-Reboot
überlebt**. Ob und in welchem Umfang ein laufender OTA nach einem kompletten DTU-Reboot
fortgesetzt werden kann, wird separat untersucht. Der persistente `/data`-Status soll
aber in jedem Fall genug Informationen enthalten, um nach einem Neustart sicher zu
erkennen, welcher Run zuletzt aktiv war und an welcher Sicherheitsgrenze er stand.

Die Persistenz von `/data` über einen realen Modem-Reboot wird vor Nutzung einer
Restart-Recovery-Funktion nochmals explizit auf Hardware bestätigt.

## 3. Sicherheitsinvarianten des neuen Designs

Diese Regeln gelten während des gesamten Umbaus und dürfen nicht durch Komfortfunktionen
aufgeweicht werden:

1. **Maximal ein aktiver OTA-Run pro DTU.**
2. Ein ADB-Abbruch beendet niemals automatisch einen gestarteten OTA-Run.
3. Nach begonnenem C5A8 bleibt der originale `phnixIot4G`-Dienst autoritativ.
4. Ein generischer Restore ist nach begonnenem C5A8 weiterhin verboten.
5. `100 %` C5A8 ist kein terminaler Erfolg.
6. Terminaler Erfolg bleibt an die bestätigte Mainboard-Abschlusssequenz gebunden.
7. Ein alter PID-Wert allein darf niemals zum Kill eines Prozesses verwendet werden.
8. Vor Prozessaktionen wird `/proc/<pid>/cmdline` bzw. die tatsächliche Identität geprüft.
9. Statusdateien werden atomar ersetzt, nie halb geschrieben.
10. Terminale Diagnoseinformationen werden nicht automatisch unmittelbar gelöscht.
11. Windows darf den Runner nach dem Start nicht als Child-Prozess besitzen oder über
    die Lebensdauer einer ADB-Shell kontrollieren.
12. Ein nicht eindeutig klassifizierbarer Zustand wird fail-closed behandelt.
13. OTA-Protokollentscheidungen bleiben zentral und dürfen nicht gleichzeitig in
    Windows und auf dem DTU unterschiedlich implementiert werden.

## 4. Geplantes Dateisystem auf dem DTU

Zielstruktur:

```text
/data/foxair_ota_runner/
├── version
├── active.lock/
│   ├── run_id
│   ├── pid
│   └── started_at
├── last_run_id
└── runs/
    └── <RUN-ID>/
        ├── request.json
        ├── package.json
        ├── status.json
        ├── result.json
        ├── runner.pid
        ├── runner.log
        ├── launcher.log
        ├── hook.log
        ├── hook-status.json
        ├── state/
        │   ├── ota_info.backup
        │   ├── ota_info.sha256
        │   └── weitere notwendige Sicherungen
        ├── payload/
        │   ├── firmware.bin
        │   ├── runtime_hook
        │   └── ota-command.json
        ├── abort.request          optional
        ├── acknowledged           optional
        └── cleanup.pending        optional
```

Die konkrete Struktur kann während Stage 2 noch vereinfacht werden. Entscheidend ist
die Trennung zwischen:

- persistentem Supervisorstatus in `/data`;
- flüchtigem Hook-/Debuggerzustand in `/tmp`.

## 5. Statusvertrag

Der Supervisor erhält ein eigenes, versionsgebundenes Statusschema.

Beispiel:

```json
{
  "schema": "foxair-dtu-ota-run-v1",
  "run_id": "20260901-203000-4711",
  "state": "running",
  "phase": "c5a8",
  "terminal": false,
  "progress": 37.4,
  "offset": 108360,
  "length": 289806,
  "transfer_started": true,
  "original_service_authoritative": true,
  "recovery": "not-required",
  "reason": "",
  "detail": "",
  "runner_pid": 1234,
  "service_pid": 5678,
  "updated_at": 1788290000
}
```

Terminaler Fehler beispielsweise:

```json
{
  "schema": "foxair-dtu-ota-run-v1",
  "run_id": "20260901-203000-4711",
  "state": "failed",
  "phase": "precondition",
  "terminal": true,
  "progress": 0,
  "transfer_started": false,
  "original_service_authoritative": false,
  "recovery": "completed",
  "reason": "service_pid_changed",
  "detail": "Expected original service identity no longer matches",
  "updated_at": 1788290030
}
```

### Pflichtfelder

Mindestens:

- `schema`
- `run_id`
- `state`
- `phase`
- `terminal`
- `updated_at`
- `transfer_started`
- `original_service_authoritative`
- `recovery`

Fortschrittsfelder sind phasenabhängig.

## 6. Zustandsmodell des Supervisors

Vorgesehene grobe Zustände:

```text
prepared
  ↓
starting
  ↓
preflight
  ↓
hook-starting
  ↓
waiting-for-acceptance
  ↓
c350
  ↓
c357
  ↓
c5a8
  ↓
mainboard-processing
  ↓
terminal-verification
  ├─ success
  ├─ failed
  └─ recovery-required
```

Zusätzliche Supervisorzustände:

```text
aborted-before-transfer
recovery-running
recovery-completed
guarded-hold
reboot-detected
orphaned-run
```

Nicht jeder Zustand muss später als sichtbarer GUI-Text erscheinen. Intern sollen sie
aber eindeutig sein.

## 7. Stage 0 – bereits erfolgreich nachgewiesen

Bereits erledigt im Branch `DTU_runner`:

- Minimalrunner auf `/data` kopiert;
- Start via `setsid /system/bin/sh ... &`;
- Runner läuft nach Ende der ADB-Shell mit PPID 1 weiter;
- Status kann von unabhängigen späteren ADB-Sitzungen gelesen werden;
- Abbruch der Windows-Überwachung beeinflusst den Runner nicht;
- Testprozess kontrolliert beendet und Testverzeichnis entfernt.

Dieser Nachweis ist die Grundlage für den weiteren Umbau.

## 8. Stage 1 – production-shaped Supervisor ohne OTA

Aktueller Entwicklungsstand im Branch.

Ziel: Lebenszyklus und Schnittstellen real auf dem DTU testen, **ohne Firmware,
Originaldienst, GDB oder OTA anzufassen**.

Funktionen:

- Run-ID;
- atomarer `status.json`;
- Single-Run-Lock;
- persistentes Run-Verzeichnis;
- detached Start;
- begrenztes Log;
- Statusabfrage über beliebig neue ADB-Sitzungen;
- kontrolliertes `abort.request`;
- terminaler Status bleibt erhalten;
- explizites `ack`;
- Cleanup erst nach terminal + ack.

### Stage-1-Abnahmetests auf echter Hardware

- [ ] Normaler Lauf bis `completed`.
- [ ] ADB/Windows während des Laufs vollständig trennen; Runner läuft weiter.
- [ ] Spätere neue ADB-Sitzung liest dieselbe Run-ID und fortgeschrittenen Status.
- [ ] Zweiter paralleler Start wird sicher verweigert.
- [ ] `abort.request` führt kontrolliert zu `aborted`, nicht zu blindem Prozess-Kill.
- [ ] Terminalstatus bleibt nach Prozessende vorhanden.
- [ ] `ack` löscht noch keine Diagnose.
- [ ] `cleanup` vor terminal wird verweigert.
- [ ] `cleanup` ohne ack wird verweigert.
- [ ] `cleanup` nach terminal + ack entfernt ausschließlich das richtige Run-Verzeichnis.
- [ ] Stale-/fremde PID wird nicht beendet.

Erst nach erfolgreicher Hardwareabnahme weiter mit Stage 2.

## 9. Stage 2 – Supervisor + Runtime-Hook, noch ohne echten Firmwaretransfer

Ziel: Der DTU-Supervisor startet und überwacht den bestehenden Runtime-Hook selbst.
Windows ist nur noch Beobachter.

Noch keine echte Firmwareübertragung.

Schritte:

- [ ] vorhandenen `phnix_ota_runtime_hook` als Child des Supervisors starten;
- [ ] Hookstatus in ein Run-spezifisches Ziel schreiben;
- [ ] Hook-PID und tatsächliche Prozessidentität überwachen;
- [ ] Hookstatus in das persistente Supervisor-Schema übersetzen;
- [ ] Hook-Log dauerhaft dem Run zuordnen;
- [ ] `/tmp`-Marker ausschließlich als lokale Runtime-Signale behandeln;
- [ ] verlorene/ungültige `/tmp`-Marker nicht als persistente Wahrheit interpretieren;
- [ ] Read-only `verify` / attach-test als erster Child-Workflow;
- [ ] absichtlicher ADB-Abbruch während Hook-Lauf;
- [ ] absichtliches Beenden des Windows-Monitors ohne Auswirkung auf Hook/Supervisor;
- [ ] kontrolliertes Ende und persistentes Ergebnis.

## 10. Stage 3 – Paketformat und doppelte lokale Verifikation

Vor einem echten OTA muss das komplette Updatepaket auf dem Modem erneut geprüft werden.

Windows prüft bereits vor dem Upload. Der Supervisor prüft danach **noch einmal lokal auf
dem DTU**, damit zwischen Hostprüfung und Nutzung keine ungeprüfte Datei liegt.

`package.json` bzw. `request.json` enthält mindestens:

- Firmwaredateiname;
- Größe;
- MD5;
- SHA-256;
- Softwarecode;
- Display-Version;
- Wire-Version;
- Target SSID;
- erwartete Runtime-Hook-Version / Hash;
- erwartete `phnixIot4G`-Build-ID / SHA-256;
- Run-ID;
- gewünschter Modus;
- Sicherheitsbestätigung des Hosts.

Abnahmepunkte:

- [ ] falscher Firmwarehash → terminale Ablehnung vor Serviceeingriff;
- [ ] falscher Hookhash → terminale Ablehnung;
- [ ] falscher Servicebuild → terminale Ablehnung;
- [ ] unvollständiges Paket → terminale Ablehnung;
- [ ] falsche Run-ID / Paketzuordnung → terminale Ablehnung;
- [ ] ausreichend freier Speicher wird lokal geprüft.

## 11. Stage 4 – Pre-C5A8-Orchestrierung auf das DTU verschieben

Ziel: Der Supervisor übernimmt die heute noch vom Windows-Controller gesteuerten
Schritte bis zur Annahme des OTA-Auftrags.

Zu verschieben bzw. lokal auszuführen:

- [ ] Originaldienst prüfen;
- [ ] erwartete Serviceidentität prüfen;
- [ ] MQTT-/Cloudzustand prüfen;
- [ ] Watchdogs prüfen;
- [ ] OTA_INFO prüfen;
- [ ] keinen aktiven Resume-Zustand bestätigen;
- [ ] persistenten Ausgangszustand sichern;
- [ ] Firmware lokal auf dem DTU bereitstellen;
- [ ] lokalen HTTP-/Stagingpfad vorbereiten;
- [ ] OTA-Command erzeugen/verifizieren;
- [ ] Hook starten;
- [ ] C350 auslösen;
- [ ] C36E-Annahme klassifizieren;
- [ ] Same-Version-/Precondition-Ablehnung lokal und terminal behandeln.

Bis hierhin bleibt Recovery vor C5A8 weiterhin zulässig, sofern der bestehende
Sicherheitscontroller dies erlaubt.

## 12. Stage 5 – echter C5A8-Transfer autonom auf dem DTU

Erst nach Abnahme der vorherigen Stufen.

Ziel: Ein kompletter echter Firmwaretransfer läuft nach dem detached Start ohne weitere
aktive Windows-Steuerung.

Wesentliche Punkte:

- [ ] erster C5A8 setzt persistent `transfer_started=true`;
- [ ] gleichzeitig persistent `original_service_authoritative=true` setzen, sobald die
      bestehende Sicherheitslogik diese Grenze bestätigt;
- [ ] Fortschritt regelmäßig aus OTA_INFO/Hookstatus übernehmen;
- [ ] Fortschritt atomar unter `/data` persistieren;
- [ ] Windows-Ausfall hat keinerlei Einfluss;
- [ ] Remote-ADB-Ausfall hat keinerlei Einfluss;
- [ ] USB-Verlust hat keinerlei Einfluss;
- [ ] Hook-/Debuggerfehler nach Autoritätsübergang darf den Originaldienst nicht
      generisch stoppen;
- [ ] keine automatische Restore-Funktion nach begonnenem Transfer;
- [ ] Watchdog-/Dienstentscheidungen bleiben identisch zur heute validierten Logik.

Erster echter Test möglichst mit bereits bekannter/validierter Kombination und
vollständiger externer serieller Beobachtung.

## 13. Stage 6 – terminale Mainboardverifikation lokal abschließen

Der Supervisor muss den Run selbst terminal klassifizieren können.

Erfolg nur bei der bereits validierten Abschlusslogik, insbesondere nicht nur wegen
`100 %` oder `promotion-committed`.

Zu übernehmen:

- [ ] Transfer vollständig;
- [ ] Mainboard-Verarbeitungsphase;
- [ ] Hersteller-Erfolgsmeldung;
- [ ] Status 5 / Step 12 entsprechend der bestehenden Sicherheitslogik;
- [ ] finalen normalen Zustand prüfen, soweit lokal zuverlässig möglich;
- [ ] `result.json` schreiben;
- [ ] `status.json` terminal setzen;
- [ ] Run-Lock freigeben;
- [ ] Diagnose-/Ergebnisdateien behalten.

Windows darf danach nur noch das bereits terminale Ergebnis anzeigen.

## 14. Stage 7 – Recovery und kontrollierter Abort

Abort-Semantik muss phasenabhängig sein.

### Vor OTA-Injection / vor C5A8

Ein kontrollierter Abort kann ggf.:

- Hook sauber beenden;
- Persistent State zurückspielen;
- Watchdogs/Dienst normalisieren;
- temporäre Ressourcen schließen;
- terminal `aborted` schreiben.

### Nach begonnenem C5A8

`abort.request` darf **keinen generischen Abbruch** auslösen.

Stattdessen beispielsweise:

```json
{
  "state": "running",
  "phase": "c5a8",
  "terminal": false,
  "abort_requested": true,
  "abort_allowed": false,
  "reason": "original_service_authoritative"
}
```

Der Runner überwacht weiter bis zu einem sicheren terminalen Ergebnis.

### Notfallabbruch

Ein echter Force-/Emergency-Eingriff darf nur separat, explizit und mit zusätzlichen
Bestätigungen implementiert werden. Er ist **nicht** Teil des normalen Endanwenderpfads.

## 15. Stage 8 – Verhalten bei Modem-Reboot / Prozessverlust

Dies ist getrennt von einfachem ADB-Verlust zu behandeln.

Zuerst reale Tests ohne OTA:

- [ ] bleibt `/data/foxair_ota_runner` nach DTU-Reboot erhalten?
- [ ] bleiben atomar geschriebene Statusdateien konsistent?
- [ ] wie werden `setsid`-Prozesse bei Modem-Reboot beendet? (erwartet: komplett beendet)
- [ ] welche Init-/Watchdogmechanismen starten `phnixIot4G` neu?

Danach Recovery-Klassifizierung definieren.

Nach Reboot niemals alte `/tmp`-PIDs/Marker blind weiterverwenden.

Der Supervisorstatus in `/data` muss genug Informationen enthalten, um mindestens zu
klassifizieren:

- Run war noch vor C5A8;
- Run hatte C5A8 bereits begonnen;
- Originaldienst war autoritativ;
- letzter bekannter Offset / Phase;
- Run war bereits terminal.

Ob ein OTA nach echtem DTU-Reboot automatisch fortgesetzt werden darf, wird **nicht
vorab angenommen**. Das wird erst nach gezielter Analyse entschieden.

## 16. Stage 9 – Windows-Controller auf dünnen Client reduzieren

Erst nachdem der DTU-Pfad real abgenommen ist.

Windows-Kommandos bzw. interne Operationen werden auf folgende Semantik reduziert:

```text
prepare
install
start
status
log
abort-request
ack
cleanup
```

Windows darf nach `start` keine sicherheitskritische Prozesssteuerung mehr besitzen.

GUI-Aufgaben:

- [ ] Run-ID anzeigen;
- [ ] persistenten DTU-Status regelmäßig lesen;
- [ ] ADB-Ausfall nur als Monitoringverlust darstellen;
- [ ] nach Reconnect denselben Run weiter anzeigen;
- [ ] niemals automatisch einen zweiten Run starten;
- [ ] terminale Ergebnisse als Popup anzeigen;
- [ ] Log abrufbar machen;
- [ ] Ack/Cleanup getrennt behandeln;
- [ ] bei nicht terminalem Zustand Buttons für neuen OTA/Dry-Run sperren.

Die bisherige serielle Windows-Fallbacklogik kann erst entfernt oder vereinfacht werden,
wenn der autonome DTU-Pfad mindestens gleichwertig real validiert ist.

## 17. Stage 10 – Simulator an die neue Architektur anpassen

Der Simulator soll dieselbe Host↔Runner-Schnittstelle abbilden.

Zu simulieren:

- [ ] normaler Erfolg;
- [ ] Same-Version;
- [ ] Fehler vor C5A8;
- [ ] ADB-Verlust während C5A8;
- [ ] ADB-Reconnect bei laufendem Transfer;
- [ ] `promotion-committed` ohne terminalen Erfolg;
- [ ] späterer `success + terminal=true`;
- [ ] Hook-Prozessverlust vor C5A8;
- [ ] Hook-/Monitoringverlust nach C5A8;
- [ ] Runner-Abbruch;
- [ ] stale lock;
- [ ] kaputte Statusdatei;
- [ ] Modem-Reboot-Simulation / persistenter letzter Run.

Insbesondere soll der bekannte aktuelle Fall vermieden werden, bei dem die GUI
„Abschlusskontrolle läuft“ anzeigt, aber kein weiterer automatischer terminaler Zustand
mehr geliefert wird.

## 18. Stage 11 – automatisches Reattach-/Statuspolling in Windows

Bis zur vollständigen DTU-Umstellung bzw. auch danach sinnvoll:

Wenn ADB wieder erreichbar ist, der Run aber noch nicht terminal ist:

- [ ] automatisches read-only Polling, z. B. alle 5–10 Sekunden;
- [ ] bei `terminal=true` sauber beenden;
- [ ] bei erneutem ADB-Verlust wieder Monitoringverlust anzeigen;
- [ ] nach sinnvoller lokalen UI-Frist keine falsche Aussage „Kontrolle läuft“ stehen
      lassen, wenn tatsächlich nicht weiter gepollt wird;
- [ ] keine OTA-Aktion aus diesem Polling heraus auslösen.

## 19. Stage 12 – Cleanup- und Retention-Modell

Terminale Ergebnisse dürfen nicht sofort verschwinden.

Vorgesehenes Modell:

1. Runner schreibt terminales `status.json` und `result.json`.
2. Windows liest das Ergebnis.
3. Windows setzt explizit `acknowledged`.
4. Erst danach darf ein normaler Cleanup Payload/temporäre Dateien löschen.
5. Ein kleiner Abschlussbericht kann länger erhalten bleiben.

Zusätzlich optional:

- automatische Payload-Bereinigung nach z. B. 24 Stunden;
- terminale `result.json` länger behalten;
- maximal N alte Runs archivieren;
- Logs größenbegrenzt halten.

Keine automatische Bereinigung eines **nicht terminalen** Runs allein aufgrund seines
Alters.

## 20. Stage 13 – Failover-, Stromausfall- und Chaos-Tests

Vor Endanwenderfreigabe gezielt testen:

- [ ] Windows-Prozess beenden;
- [ ] Windows-PC herunterfahren;
- [ ] Remote-ADB-Server stoppen;
- [ ] USB-Verbindung trennen;
- [ ] ADB `offline`;
- [ ] ADB reconnect;
- [ ] Runner-Child/Hook vor C5A8 beenden;
- [ ] Hook nach C5A8 verlieren;
- [ ] Statusdatei während Schreiben lesen;
- [ ] Log voll / Speicher knapp;
- [ ] unerwarteter Service-PID-Wechsel;
- [ ] Watchdog-PID-Wechsel;
- [ ] MQTT kurzfristig weg;
- [ ] bewusst langsamer C5A8-Transfer;
- [ ] Statuspolling minutenlang aussetzen;
- [ ] erneuter Host verbindet sich an denselben Run;
- [ ] zweiter Startversuch während aktivem Run;
- [ ] DTU-Reboot vor C5A8;
- [ ] DTU-Reboot nach C5A8 nur nach vorher definierter sicherer Teststrategie.

## 21. Stage 14 – produktive Integration und Altpfad entfernen

Erst nach vollständiger Realvalidierung.

- [ ] neue Runner-Dateien aus `devtools` in endgültigen Produktpfad verschieben;
- [ ] Versions-/Hashprüfung für Runner integrieren;
- [ ] Windows- und Linux-Launcher auf neue Schnittstelle umstellen;
- [ ] alte Host-Orchestrierung deaktivieren;
- [ ] redundante Guard-/Fallbacklogik entfernen, sofern durch DTU-Supervisor ersetzt;
- [ ] Regressionstests aktualisieren;
- [ ] Releases / Buildsystem anpassen;
- [ ] Upgradepfad für vorhandene Nutzer testen.

Während der Migration kann ein versteckter Entwickler-Fallback auf den alten Pfad
bestehen bleiben. Im Endzustand soll jedoch nur **eine** produktive OTA-Orchestrierung
existieren.

## 22. Stage 15 – endgültige Dokumentation

Nach erfolgreichem Umbau:

Dauerhaft dokumentieren:

- Architektur des autonomen DTU-Runners;
- Host↔Runner-Statusvertrag;
- Sicherheitsgrenzen vor/nach C5A8;
- Recovery- und Rebootverhalten;
- Cleanup/Retention;
- reale Testmatrix;
- Endanwenderablauf.

Historische Erkenntnisse aus `docs/dev/` nur dort übernehmen, wo sie dauerhaft relevant
sind.

Anschließend:

- [ ] diese Roadmap als erledigt markieren;
- [ ] relevante Erkenntnisse in normale Dokus übertragen;
- [ ] **`docs/dev/` vollständig löschen**.

## 23. Definition of Done

Der Umbau gilt erst als abgeschlossen, wenn alle folgenden Punkte erfüllt sind:

- [ ] Ein reales Mainboardupdate kann vollständig gestartet werden, danach kann Windows
      sofort beendet werden, und der OTA-Run läuft autonom weiter.
- [ ] ADB kann während des Transfers beliebig ausfallen und später denselben Run wieder
      lesen.
- [ ] Der DTU-Runner entscheidet selbst über alle sicherheitskritischen OTA-Phasen.
- [ ] Kein Windows-/ADB-Monitoringfehler kann einen begonnenen C5A8-Transfer stoppen.
- [ ] Nach C5A8 ist generischer Restore weiterhin sicher ausgeschlossen.
- [ ] Terminaler Erfolg wird lokal eindeutig erkannt und dauerhaft gespeichert.
- [ ] Terminale Fehler enthalten einen belastbaren Grund und Recoverystatus.
- [ ] Diagnoseinformationen bleiben bis zur Bestätigung erhalten.
- [ ] Zweite parallele OTA-Runs sind ausgeschlossen.
- [ ] Stale Locks/PIDs können nicht zu einem falschen Kill oder Cleanup führen.
- [ ] Rebootverhalten ist real untersucht und dokumentiert.
- [ ] Simulator bildet den neuen Runnervertrag korrekt ab.
- [ ] Windows ist nach `start` nur noch Client/Beobachter.
- [ ] Alte redundante Host-Orchestrierung ist entfernt oder klar als Entwicklerfallback
      isoliert.
- [ ] Alle relevanten Unit-/Simulator-/Hardwaretests sind grün bzw. dokumentiert.
- [ ] Dauerhafte Dokumentation ist aktualisiert.
- [ ] `docs/dev/` ist danach wieder entfernt.

## 24. Empfohlene unmittelbare Reihenfolge

Als nächstes nicht direkt den echten Firmwaretransfer anbinden.

Empfohlene Reihenfolge:

1. Stage 1 auf echter DTU-Hardware vollständig abnehmen.
2. Stage 2: vorhandenen Hook als harmlosen `verify`-/Attach-Child des Supervisors starten.
3. ADB-Abbruch/Reattach mit diesem Child testen.
4. Paketformat + lokale Hashprüfung implementieren.
5. Pre-C5A8-Orchestrierung verschieben.
6. Erst danach einen echten C5A8-Lauf autonom auf dem DTU testen.
7. Terminalverifikation und Recovery lokal abschließen.
8. Windows erst zum Schluss auf den dünnen Client umbauen.

Damit bleiben die Änderungsschritte klein, rückverfolgbar und auf echter Hardware
jeweils einzeln testbar.