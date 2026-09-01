# DTU OTA Runner – Roadmap für den vollständigen Umbau

> **Temporäre Entwicklungsdokumentation**
>
> Diese Datei ist der Arbeitsplan für den Branch `DTU_runner`.
> Die dauerhaften Erkenntnisse werden nach Abschluss des Gesamtprojekts in die normale
> Dokumentation übernommen; danach wird `docs/dev/` vollständig gelöscht.

Stand: 2. September 2026

## Aktueller Implementierungsstand im Branch

Der erste zusammenhängende Backendpfad ist implementiert und als Zwischenstand
prüfbar:

- produktionsnaher DTU-Supervisor unter `/data/foxair_ota_runner/runs/<RUN-ID>/`;
- paketierte Host- und DTU-Prüfung von Firmware, Manifest, Hook, Runner,
  Originaldienst-SHA und Build-ID;
- stabile Python-/CLI-Operationen `prepare`, `start`, `status`, `log`,
  `abort-request`, `ack`, `cleanup`, `current` und `active`;
- detached Start per `setsid`, atomare Status-/Result-Dateien und exklusiver Run-Lock;
- Same-Version im Work-QEMU-Lab erfolgreich bis C350/C36E Status 0 getestet,
  ohne C357/C5A8 und mit bestätigter Wiederherstellung;
- Simulatoradapter verwendet für den Runtime-Hook den echten QEMU-GDB-/RS485-Pfad;
- vorbereitete Runs werden nicht als verwaist klassifiziert; ein nachweislich toter
  Lock-Owner wird klassifiziert und gibt nur den Run-Lock frei, während seine
  Diagnose erhalten bleibt.
- Statusflags für C350, C36E, C357 und C5A8 werden monoton geführt; kurzlebige
  Zwischenphasen können die bestätigten Protokollereignisse nicht mehr verlieren.
- vollständiger Work-QEMU-Erfolgslauf `backend-v34-success-vm-05` mit echtem
  V3.4-Payload bestätigt: C350, C36E Status 1, C357, 289806 Byte C5A8,
  Status 3/5, Promotion, Erfolgsmeldung und finaler Board-Step 12.
- 100 % C5A8 blieb dabei korrekt nichtterminal; erst die Abschlusssequenz setzte
  `state=completed`, `phase=success`.
- Der Supervisor verbrauchte während des mehrminütigen Transfers praktisch keine
  messbare CPU-Zeit und hielt den Zwei-Sekunden-Polltakt ein.
- ADB wurde während eines aktiven C5A8-Laufs 20 Sekunden vollständig getrennt;
  derselbe autonome Run lief ohne Offsetverlust weiter und war nach Reconnect
  wieder lesbar.
- Ein simulierter LTE-/Dienstneustart nach begonnenem C5A8 wird konservativ als
  `original-service-active-unmonitored` mit `recovery=required` klassifiziert;
  der letzte bestätigte Offset bleibt dauerhaft erhalten und es erfolgt kein
  generischer Restore.
- Der Simulator bewahrt dabei OTA_INFO und Board-Resumezustand. Die neue
  Originaldienst-Instanz nimmt nach C544/C37B selbst den nachgewiesenen
  C350/C36E-1/C357/C36E-2-Rehandshake auf, akzeptiert einen wiederholten letzten
  Block und setzt C5A8 anschließend am nächsten Block fort.

Der QEMU-Pfad unterdrückt ausschließlich bei vorhandenem
`/data/phnixIot4G.tls-lab` ein emulationsbedingtes `SIGFPE`. Auf realer DTU bleibt
die live validierte GDB-Signalsemantik (`pass`) unverändert. Ebenso ist nur im
Simulator der Yield-Breakpoint so bedingt, dass der QEMU-Kaltstart bis
`UART=0` und Board-Step 12 weiterlaufen darf.

Noch nicht als abgeschlossen markieren: vollständiger Success-/Failure-/Chaos-Matrixlauf
und die begrenzte Abnahme auf der realen DTU.

## 1. Ziel und klarer Scope

Der komplette Mainboard-OTA-Vorgang soll autonom auf dem PHNIX-LTE-Modem laufen.
Nach dem Start darf ein Verlust von Windows, ADB, USB oder Remote-ADB den OTA-Vorgang
nicht beeinflussen.

**Work baut ab jetzt ausschließlich den neuen DTU-/Backendpfad. Die Windows-GUI ist
explizit nicht Bestandteil dieses Work-Auftrags.**

Die GUI wird erst später separat an die stabile Host-API des fertigen Backends angebunden.
Work soll daher keine GUI-Dateien umbauen, keine GUI-Workarounds einbauen und keine
zweite OTA-Logik im Windows-Frontend erzeugen.

Zielarchitektur:

```text
Host CLI / spätere GUI
      │
      ├─ prepare / dry-run
      ├─ start
      ├─ status / log
      ├─ abort-request
      ├─ ack
      └─ cleanup
                         │
                         ▼
                 DTU OTA Supervisor
                   ├─ Paket lokal erneut prüfen
                   ├─ exklusiven Run übernehmen
                   ├─ persistenten Run-Zustand führen
                   ├─ Runtime-Hook starten
                   ├─ OTA lokal überwachen
                   ├─ Recovery lokal entscheiden
                   └─ Ergebnis dauerhaft ablegen
                         │
                         ▼
                 phnix_ota_runtime_hook
                   ├─ Originaldienst verifizieren
                   ├─ C350 / C36E / C357 / C5A8
                   ├─ Fortschritt beobachten
                   ├─ Success-/Failure-Report
                   └─ Step 12 / terminales Ergebnis
```

## 2. Nicht neu erfinden: bestehende OTA-Logik ist Referenz

Der Umbau ist **keine neue Reverse-Engineering-Runde des OTA-Protokolls**.

Die bestehende und bereits auf realer Hardware validierte Logik in
`tools/phnix_ota/phnix_ota_runtime_hook` sowie die bisherige Host-Orchestrierung dienen
als Referenz für:

- C350-Auslösung;
- C36E-Annahme und Same-Version-Ablehnung;
- C357;
- Beginn und Fortschritt von C5A8;
- Autoritätsübergang auf den Originaldienst;
- Success-/Failure-Report;
- Step-12-Grenzen;
- erlaubte Recovery vor C5A8;
- Verbot eines generischen Restore nach begonnenem Transfer.

Work soll diese validierten Entscheidungen in den autonomen DTU-Lebenszyklus überführen
und nur dann fachlich ändern, wenn ein konkreter Fehler nachgewiesen wird.

Für Post-C5A8-Verhalten stehen reale Logs aus bereits erfolgreichen Mainboardupdates zur
Verfügung. Der Simulator muss diese Abläufe vollständig reproduzieren.

## 3. `/data` für Supervisor, `/tmp` für Hook

`/tmp/phnix_ota_hook` bleibt ausschließlich für flüchtigen, an aktuelle Prozesse
gekoppelten Hook-Zustand:

- Helper-/GDB-/GDBServer-PIDs;
- Watchdog-PIDs;
- generierte GDB-Skripte;
- `run.active`;
- `transfer-started`;
- `injection-started`;
- `original-service-owns`;
- sonstige Runtime-Marker.

Der Supervisor hält unter `/data/foxair_ota_runner/` dauerhaft:

- Run-ID;
- Paketidentität;
- letzte Phase und Fortschritt;
- Zeitpunkt letzter Aktivität;
- `transfer_started`;
- `original_service_authoritative`;
- `abort_allowed`;
- terminales Ergebnis oder Fehlergrund;
- Recovery-Ergebnis;
- Logs;
- Acknowledgement und Cleanup-Zustand.

Das Design darf nicht davon abhängen, dass `/tmp` einen Reboot überlebt.

## 4. Sicherheitsinvarianten

1. Maximal ein aktiver OTA-Run pro DTU.
2. ADB-/Hostverlust beendet niemals einen gestarteten OTA-Run.
3. Nach validiertem Autoritätsübergang bleibt `phnixIot4G` autoritativ.
4. Generischer Restore bleibt nach begonnenem C5A8 verboten.
5. 100 % C5A8 ist kein terminaler Erfolg.
6. Erfolg bleibt an die validierte Mainboard-Abschlusssequenz gebunden.
7. Alte PID-Werte sind niemals allein Grundlage eines Kill oder Cleanup.
8. Vor Prozessaktionen tatsächliche Prozessidentität prüfen.
9. Statusdateien atomar ersetzen.
10. Terminale Diagnoseinformationen nicht sofort löschen.
11. Host/ADB darf den Runner nach Start nicht als Child besitzen.
12. Unklarer Zustand wird fail-closed behandelt.
13. OTA-Protokollentscheidungen liegen nur auf dem DTU, nicht zusätzlich im Host.
14. `abort-request` darf nach dem Point-of-no-return keinen unsicheren Abbruch erzwingen.
15. Ein Dry-Run darf keinen GDB-Attach und kein C350 auslösen.
16. Auf der realen MDM9607-DTU mit einem ARMv7-Kern darf der Supervisor keinen
    Busy-Loop verwenden: reguläres Polling mindestens im 2-Sekunden-Takt,
    Hashprüfungen nur bei Preflight/Phasenwechsel und keine zyklische Vollanalyse
    großer Logs.
17. Der reale Rebootvertrag ist bestätigt: `/data/foxair_ota_runner` bleibt erhalten,
    `/tmp/phnix_ota_hook` verschwindet; alte GDB-, GDBServer- und OTA-HTTP-Prozesse
    sind nach Boot nicht vorhanden. Rebootzustände werden nur klassifiziert und
    niemals automatisch fortgesetzt.

## 5. Zielstruktur auf dem DTU

```text
/data/foxair_ota_runner/
├── version
├── active.lock/
│   ├── run_id
│   ├── pid
│   └── started_at
├── last_run_id
└── runs/<RUN-ID>/
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
    ├── payload/
    │   ├── firmware.bin
    │   ├── runtime_hook
    │   └── ota-command.json
    ├── abort.request       optional
    └── acknowledged        optional
```

Die konkrete Struktur darf vereinfacht werden, solange persistenter Supervisorzustand
und flüchtiger Hookzustand sauber getrennt bleiben.

## 6. Stabiler Host↔Runner-Vertrag

Der Backendumbau soll eine stabile, GUI-unabhängige Host-API hinterlassen.
Mindestens folgende Operationen:

```text
prepare
start
status
log
abort-request
ack
cleanup
```

`prepare` entspricht dem späteren Dry-Run:

- Firmware analysieren;
- Paket/Manifest erzeugen;
- Dateien hochladen;
- alle Hash-/Build-/Speicher-/Servicevoraussetzungen prüfen;
- **kein GDB-Attach**;
- **kein C350**;
- keine Änderung am OTA-Zustand des Mainboards.

Optionale Benutzerentscheidung wie ein kontrollierter Neustart von `phnixIot4G` vor dem
Update wird als Feld im Auftrag transportiert, z. B.:

```json
{
  "restart_service_before_update": true
}
```

Die Ausführung erfolgt auf dem DTU, nicht durch GUI-/Host-Sonderlogik.

## 7. Statusvertrag

Zielschema mindestens:

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
  "abort_allowed": false,
  "recovery": "not-required",
  "reason": "",
  "detail": "",
  "runner_pid": 1234,
  "service_pid": 5678,
  "updated_at": 1788290000
}
```

Pflichtfelder mindestens: `schema`, `run_id`, `state`, `phase`, `terminal`,
`updated_at`, `transfer_started`, `original_service_authoritative`, `abort_allowed`,
`recovery`.

## 8. Stage 0 – autonomer Minimalrunner – ERLEDIGT

Real nachgewiesen:

- [x] Start via `setsid /system/bin/sh ... &`.
- [x] Runner läuft nach Ende der ADB-Shell mit PPID 1 weiter.
- [x] spätere unabhängige ADB-Sitzungen lesen denselben Prozess/Status.
- [x] Ende der Windows-Überwachung beeinflusst den Runner nicht.

Wichtige Erkenntnis: normales `nohup` reicht auf dieser DTU-Firmware nicht zuverlässig;
`setsid` ist der validierte detached Startweg.

## 9. Stage 1 – production-shaped Supervisor ohne OTA – ERLEDIGT

Auf realer DTU-Hardware bestätigt:

- [x] normaler Lauf bis `completed`;
- [x] detached mit PPID 1;
- [x] spätere ADB-Abfragen sehen denselben Run und Fortschritt;
- [x] Parallelstart wird mit `active_run_exists` verweigert;
- [x] `abort.request` führt kontrolliert zu `aborted`;
- [x] Cleanup vor terminal wird verweigert;
- [x] Cleanup ohne Ack wird verweigert;
- [x] terminal + Ack + Cleanup funktioniert;
- [x] fremde/stale PID wird nicht beendet.

Beim Fremd-PID-Test wurde eine absichtlich falsche `runner.pid` auf einen lebenden
fremden Prozess gesetzt. Cleanup erkannte die fremde Prozessidentität, entfernte nur das
terminale Run-Verzeichnis und ließ den fremden Prozess weiterlaufen.

## 10. Stage 2 – Supervisor + echter Runtime-Hook – ERLEDIGT

Auf realer DTU-Hardware bestätigt:

### Verify

Run `stage2-verify-real-01`:

- [x] Hook als Child des Supervisors gestartet;
- [x] Hook-PID und Prozessidentität bestätigt;
- [x] `phnixIot4G`-SHA256 korrekt;
- [x] Service-PID und beide Watchdogs erkannt;
- [x] Hook `phase=verified`;
- [x] Supervisor `phase=hook-verify-ok`, terminal;
- [x] `transfer_started=false`;
- [x] `original_service_authoritative=false`.

### Read-only GDB Attach/Detach

Run `stage2-attach-real-01`:

- [x] echter GDB/GDBServer-Attach an `phnixIot4G`;
- [x] read-only Speicherzugriff;
- [x] sauberer Detach;
- [x] `phase=attach-test-ok`;
- [x] kein C350, kein C357, kein C5A8, kein Firmwaretransfer.

Direkt danach bestätigte `stage2-postattach-verify-01` erneut einen sauberen Service,
vorhandene Watchdogs und `TracerPid=0`.

Alle drei Runs wurden anschließend per Ack + Cleanup sauber entfernt.

Der ADB-Ausfalltest während eines laufenden Childs wird **nicht künstlich durch Sleep-Code
im Runtime-Hook erzeugt**. Er wird bei einem natürlich länger laufenden Backend-/Simulator-
Workflow getestet.

## 11. Stage 3 – Paketformat und doppelte lokale Verifikation

Work soll den vorhandenen Firmware-Manifestcode wiederverwenden und den Paketvertrag
vervollständigen.

Paketdaten mindestens:

- Firmwaregröße;
- MD5;
- SHA-256;
- Softwarecode;
- Display-Version;
- Wire-Version;
- Target SSID `0063`;
- Image Base;
- Hook-SHA256;
- Runner-/Paketversion;
- erwartete `phnixIot4G`-SHA256;
- erwartete Build-ID;
- Run-ID;
- Modus/Optionen.

Host prüft vor Upload; DTU prüft vor jeder Nutzung erneut.

Tests:

- [ ] falscher Firmwarehash → Ablehnung vor Serviceeingriff;
- [ ] falsche Größe → Ablehnung;
- [ ] falscher Hookhash → Ablehnung;
- [ ] falscher Servicebuild/SHA → Ablehnung;
- [ ] unvollständiges Paket → Ablehnung;
- [ ] falsche Run-ID/Paketzuordnung → Ablehnung;
- [ ] falsche SSID/Version/Softwarecode → Ablehnung;
- [ ] freier Speicher lokal geprüft.

## 12. Stage 4 – Pre-C5A8-Orchestrierung vollständig auf DTU

- [ ] Originaldienst/Build prüfen;
- [ ] MQTT/Cloud und Watchdogs prüfen;
- [ ] OTA_INFO / Resume-Zustand prüfen;
- [ ] persistenten Ausgangszustand sichern;
- [ ] optionalen Service-Neustart lokal ausführen;
- [ ] Firmware/Staging/HTTP lokal vorbereiten;
- [ ] OTA-Command erzeugen und verifizieren;
- [ ] Hook starten;
- [ ] C350 lokal auslösen;
- [ ] C36E klassifizieren;
- [ ] Same-Version lokal terminal behandeln;
- [ ] Precondition-/Parser-Ablehnung lokal terminal/recoverbar behandeln;
- [ ] ADB-/Hostverlust während dieser Phase hat keinen Einfluss auf den Runner.

Auf echter DTU darf dieser Pfad bis zur natürlichen Same-Version-Ablehnung vollständig
geprüft werden.

## 13. Stage 5 – vollständiger autonomer OTA-Pfad einschließlich C5A8

Der Post-C5A8-Pfad wird aus der vorhandenen validierten Hook-/Controllerlogik übernommen,
nicht neu erfunden.

- [ ] C36E Status 1 setzt den validierten Autoritätsübergang;
- [ ] erster C5A8 setzt persistent `transfer_started=true`;
- [ ] `original_service_authoritative=true` persistent abbilden;
- [ ] `abort_allowed=false` ab Point-of-no-return;
- [ ] C5A8-Fortschritt lokal übernehmen;
- [ ] Hook-/Debuggerverlust nach Autoritätsübergang stoppt Originaldienst nicht;
- [ ] kein generischer Restore nach C5A8;
- [ ] ADB-/Windows-Ausfall beeinflusst OTA nicht;
- [ ] langsamer Transfer bleibt korrekt überwacht.

**Reale DTU-Abnahme für Work muss keinen erzwungenen Firmwarewechsel durchführen.**
Der vollständige C5A8-/Post-C5A8-Pfad muss dagegen in der Simulator-VM gegen die
bereits bekannten realen Ablaufdaten und Logs vollständig durchgetestet werden.

## 14. Stage 6 – terminale Mainboardverifikation lokal

Erfolg niemals nur wegen `100 %` oder `promotion-committed`.

- [ ] Transfer vollständig erkennen;
- [ ] Mainboard-Verarbeitungsphase verfolgen;
- [ ] Hersteller-Erfolgsmeldung berücksichtigen;
- [ ] Failure-Report berücksichtigen;
- [ ] Status/Step 12 gemäß validierter Logik bestätigen;
- [ ] erst dann `success` oder `failed` terminal setzen;
- [ ] `result.json` schreiben;
- [ ] Run-Lock freigeben;
- [ ] Diagnose behalten.

## 15. Stage 7 – Recovery und kontrollierter Abort

Vor dem Point-of-no-return darf `abort-request` nur die bereits als sicher validierte
Recovery ausführen.

Nach dem Point-of-no-return:

- `abort_allowed=false`;
- normaler `abort-request` darf keinen generischen Stop/Restore erzeugen;
- Runner überwacht bis zu einem sicheren terminalen Ergebnis weiter.

Force-/Emergency-Eingriffe bleiben getrennte Entwicklerfunktionen und sind nicht Teil
des normalen Endanwenderpfads.

## 16. Stage 8 – DTU-Reboot / Prozessverlust

Mindestens untersuchen und implementieren:

- [ ] `/data/foxair_ota_runner` überlebt DTU-Reboot;
- [ ] atomare Statusdateien bleiben konsistent;
- [ ] alte `/tmp`-PIDs/Marker werden nie wiederverwendet;
- [ ] Pre-C5A8 / Post-C5A8 / terminal aus persistentem Zustand klassifizieren;
- [ ] Status kann `reboot-detected` / `orphaned-run` abbilden;
- [ ] stale Lock wird kontrolliert klassifiziert, niemals blind gelöscht;
- [ ] fremde PID wird niemals beendet.

**Kein automatisches OTA-Resume nach DTU-Reboot implementieren, solange das reale
Rebootverhalten nicht ausreichend validiert ist.** Sichere Klassifizierung ist Pflicht,
automatisches Resume nicht.

## 17. Stage 9 – stabile Backend-CLI/API – KEINE GUI

Work soll eine stabile, frontend-unabhängige Hostschicht liefern.

- [ ] `prepare`;
- [ ] `start`;
- [ ] `status`;
- [ ] `log`;
- [ ] `abort-request`;
- [ ] `ack`;
- [ ] `cleanup`;
- [ ] aktiven Run erkennen;
- [ ] nach Reconnect denselben Run wiederfinden;
- [ ] niemals automatisch zweiten Run starten;
- [ ] ADB-Verlust ausschließlich als Monitoringverlust behandeln;
- [ ] Windows und Linux können denselben Backendvertrag verwenden.

**Nicht Teil von Work:**

- keine Windows-GUI umbauen;
- keine Buttons/Popups ändern;
- kein GUI-Polling implementieren;
- keine GUI-spezifische Kompatibilitätsschicht bauen.

## 18. Stage 10 – Simulator-VM vollständig auf neuen Runnervertrag bringen

Der Simulator ist die vollständige Abnahmeplattform für den gefährlichen OTA-Pfad.

Mindestens simulieren/testen:

- [ ] erfolgreicher kompletter OTA-Lauf;
- [ ] Same-Version;
- [ ] Fehler vor C5A8;
- [ ] Fehler nach C5A8;
- [ ] ADB-/Hostverlust vor C5A8;
- [ ] ADB-/Hostverlust während C5A8;
- [ ] Reconnect und Fortsetzung desselben Runs;
- [ ] `promotion-committed` ohne terminalen Erfolg;
- [ ] später `success + terminal=true`;
- [ ] Failure-Report + Step 12;
- [ ] Hookverlust vor Autoritätsübergang;
- [ ] Hookverlust danach;
- [ ] Runner-Abbruch;
- [ ] stale lock;
- [ ] PID-Reuse/fremde PID;
- [ ] kaputte/teilweise Statusdatei;
- [ ] Modem-Reboot mit persistentem letzten Run;
- [ ] Speicher knapp;
- [ ] langsamer C5A8;
- [ ] neuer Host verbindet sich an denselben Run;
- [ ] zweiter Start während aktivem Run;
- [ ] atomare Statusleser während Schreibvorgängen.

Die simulierten Post-C5A8-Sequenzen müssen mit den bekannten realen Logs und der bereits
validierten Hooklogik übereinstimmen.

## 19. Stage 11 – reale DTU-Abnahme des fertigen Backends

Auf echter DTU-Hardware:

- [ ] `prepare`/Dry-Run vollständig erfolgreich;
- [ ] Paket wird auf DTU erneut vollständig verifiziert;
- [ ] optionaler Service-Neustart funktioniert kontrolliert;
- [ ] Start bis C350/C36E funktioniert lokal;
- [ ] Same-Version wird korrekt und sicher terminal beendet;
- [ ] Logs/Status/Result bleiben persistent;
- [ ] Ack/Cleanup funktionieren;
- [ ] keine stale Hook-/PID-/Lock-Reste;
- [ ] nach Test normaler `verify` wieder erfolgreich.

Ein realer erzwungener Firmwarewechsel ist für die Work-Abnahme nicht erforderlich.

## 20. Stage 12 – Backend-Produktivierung im Branch

- [ ] Stage1-/Stage2-Testgerüste nicht als produktive Parallelpfade stehen lassen;
- [ ] finalen Runner in Produktpfad verschieben;
- [ ] Runner-/Hook-Versionen und Hashes definieren;
- [ ] stabile Python-/CLI-Host-API bereitstellen;
- [ ] redundante neue Entwicklungswege konsolidieren;
- [ ] Unit-/Simulator-/CLI-Tests aktualisieren;
- [ ] Linux-/Windows-CLI-Aufruf dokumentieren;
- [ ] keine GUI-Dateien ändern.

Endzustand des Work-Auftrags: **ein fertiger neuer OTA-Backendpfad im `DTU_runner`-Branch,
ohne GUI-Integration.**

## 21. Nachgelagert – Windows-GUI-Integration – NICHT TEIL VON WORK

Diese Phase erledigen wir separat nach Abnahme des Backends.

Die GUI wird dann nur dünner Client der stabilen API:

```text
Firmware wählen
      ↓
prepare / dry-run
      ↓
start
      ↓
status alle ~5–10 s
      ↓
ADB weg → nur Monitoringverlust anzeigen
      ↓
ADB zurück → denselben run_id weiter pollen
      ↓
terminales Ergebnis
      ↓
Ack / Cleanup
```

Spätere GUI-Aufgaben:

- Fortschritt aus `status.json` anzeigen;
- aktiven Run beim Start/Reconnect erkennen;
- neue OTA-Versuche bei aktivem Run sperren;
- ADB-Ausfall nicht als OTA-Fehler behandeln;
- echtes automatisches Reattach-/Statuspolling;
- terminale Popups;
- Fehlerdiagnose behalten;
- Erfolg nach Bestätigung bereinigen;
- bei Fehler/Recovery keine automatische Diagnosebereinigung;
- vorhandene Option „`phnixIot4G` vor Update neu starten“ nur als Request-Flag setzen.

Die GUI enthält **keine eigene C350/C36E/C357/C5A8-/Recoverylogik**.

## 22. Cleanup / Retention

Normaler Lebenszyklus:

1. terminales `status.json` / `result.json` schreiben;
2. Host liest Ergebnis;
3. Host setzt `acknowledged`;
4. bei Erfolg darf kontrolliert bereinigt werden;
5. bei Fehler / `recovery-required` Diagnose standardmäßig behalten;
6. expliziter Diagnose-Cleanup bleibt möglich.

Nichtterminale Runs niemals allein wegen Alter löschen.

## 23. Definition of Done – Work / Backend

Der Work-Auftrag ist abgeschlossen, wenn:

- [ ] ein einziger produktionsnaher autonomer DTU-Runner existiert;
- [ ] Host nach `start` keine sicherheitskritische OTA-Entscheidung mehr trifft;
- [ ] vollständige Paket-/Hash-/Buildprüfung Host + DTU vorhanden ist;
- [ ] vollständiger OTA-Ablauf im Simulator erfolgreich durchläuft;
- [ ] Same-Version-Pfad auf echter DTU vollständig durchläuft;
- [ ] bekannte reale Post-C5A8-Sequenzen im Simulator korrekt reproduziert werden;
- [ ] ADB-/Hostverlust einen laufenden Run nicht beeinflusst;
- [ ] generischer Restore nach C5A8 ausgeschlossen ist;
- [ ] terminaler Erfolg/Fehler lokal eindeutig und dauerhaft gespeichert wird;
- [ ] parallele Runs ausgeschlossen sind;
- [ ] stale Locks/PIDs nie zu falschem Kill/Cleanup führen;
- [ ] Rebootzustand sicher klassifiziert wird;
- [ ] stabile CLI/API für spätere GUI vorhanden ist;
- [ ] Tests und Backenddokumentation aktuell sind;
- [ ] **keine Windows-GUI geändert wurde.**

## 24. Definition of Done – Gesamtprojekt später

Nach der separaten GUI-Integration zusätzlich:

- [ ] GUI verwendet ausschließlich die neue Backend-API;
- [ ] GUI pollt nach Reconnect denselben Run automatisch weiter;
- [ ] alter Windows-OTA-Orchestrierungspfad wird nicht mehr verwendet;
- [ ] dauerhafte Dokumentation wird aktualisiert;
- [ ] temporäre Entwicklungsdokumentation wird entfernt;
- [ ] **`docs/dev/` wird vollständig gelöscht.**

## 25. Unmittelbare Reihenfolge

1. Work bekommt den Backend-only-Auftrag auf Basis dieser Roadmap.
2. Stage 3–10 in einem zusammenhängenden Backendumbau implementieren; keine GUI anfassen.
3. Simulator-VM vollständig bis Success/Failure und Chaosfälle abnehmen.
4. Fertigen Backendpfad auf echter DTU bis zur natürlichen Same-Version-Ablehnung testen.
5. Backend/API stabilisieren und dokumentieren.
6. Erst danach separat die Windows-GUI an die fertige API anbinden.
7. Nach Gesamtabschluss permanente Doku aktualisieren und `docs/dev/` löschen.
