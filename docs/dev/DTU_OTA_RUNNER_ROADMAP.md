# DTU OTA Runner – Roadmap für den vollständigen Umbau

> **Temporäre Entwicklungsdokumentation**
>
> Diese Datei dient ausschließlich als Arbeits-/Umbauplan im Branch `DTU_runner`.
> Nach Abschluss des Umbaus, Übernahme der dauerhaften Erkenntnisse in die normale
> Dokumentation und erfolgreicher Abnahme soll `docs/dev/` wieder vollständig gelöscht
> werden.

Stand: 1. September 2026

## 1. Zielbild

Der kritische Mainboard-OTA-Vorgang soll vollständig auf dem PHNIX-LTE-Modem laufen.
Windows/ADB übernimmt danach nur noch:

1. Vorprüfung und Paketvorbereitung;
2. Upload von Runner, Hook, Auftrag und Firmware;
3. detached Start des OTA-Runners;
4. read-only Status- und Logabfrage;
5. optional kontrollierte Requests wie `abort-request`;
6. Bestätigung eines terminalen Ergebnisses (`ack`);
7. kontrollierte Bereinigung (`cleanup`).

Nach erfolgreichem Start darf ein Verlust von Windows, ADB, USB oder Remote-ADB den
laufenden OTA-Vorgang nicht beeinflussen.

```text
Windows GUI / CLI
      │
      ├─ prüfen + Paket kopieren
      ├─ detached starten
      └─ danach nur beobachten / kontrollierte Requests
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
                   ├─ C350 auslösen
                   ├─ C357/C5A8 beobachten
                   ├─ Status 3/5 beobachten
                   └─ Step 12 / terminales Ergebnis
```

## 2. `/data` für Supervisor, `/tmp` für Hook

`/tmp/phnix_ota_hook` bleibt für flüchtigen, an aktuelle Prozesse gekoppelten Zustand:

- Helper-/GDB-/GDBServer-PIDs;
- Watchdog-PIDs;
- generierte GDB-Skripte;
- `run.active`, `transfer-started`, `injection-started`, `original-service-owns`;
- sonstige Runtime-Marker.

Nach einem DTU-Reboot sind diese Prozessbeziehungen ohnehin ungültig.

Der Supervisor hält dagegen unter `/data/foxair_ota_runner/` dauerhaft:

- Run-ID und Paketidentität;
- letzte Phase und Fortschritt;
- Zeitpunkt letzter Aktivität;
- `transfer_started`;
- `original_service_authoritative`;
- terminales Ergebnis oder Fehlergrund;
- Recovery-Ergebnis;
- Log;
- Acknowledgement und Cleanup-Zustand.

Das Design darf nicht darauf angewiesen sein, dass `/tmp` einen Reboot überlebt. Ob ein
laufendes OTA nach einem echten DTU-Reboot fortgesetzt werden kann, wird separat real
untersucht. `/data` soll mindestens eine sichere nachträgliche Klassifizierung erlauben.

## 3. Sicherheitsinvarianten

1. Maximal ein aktiver OTA-Run pro DTU.
2. ADB-Abbruch beendet niemals einen gestarteten OTA-Run.
3. Nach begonnenem C5A8 bleibt `phnixIot4G` autoritativ.
4. Generischer Restore bleibt nach begonnenem C5A8 verboten.
5. 100 % C5A8 ist kein terminaler Erfolg.
6. Erfolg bleibt an die bestätigte Mainboard-Abschlusssequenz gebunden.
7. Alte PID-Werte dürfen niemals allein Grundlage eines Kill sein.
8. Vor Prozessaktionen tatsächliche Prozessidentität prüfen.
9. Statusdateien immer atomar ersetzen.
10. Terminale Diagnoseinformationen nicht sofort löschen.
11. Windows darf den Runner nach Start nicht als Child besitzen.
12. Unklarer Zustand wird fail-closed behandelt.
13. OTA-Protokollentscheidungen werden nicht doppelt in Windows und DTU implementiert.

## 4. Zielstruktur auf dem DTU

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

Die konkrete Struktur darf noch vereinfacht werden. Entscheidend bleibt die Trennung
zwischen persistentem Supervisorstatus in `/data` und flüchtigem Hookzustand in `/tmp`.

## 5. Statusvertrag

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
  "recovery": "not-required",
  "reason": "",
  "detail": "",
  "runner_pid": 1234,
  "service_pid": 5678,
  "updated_at": 1788290000
}
```

Pflichtfelder: `schema`, `run_id`, `state`, `phase`, `terminal`, `updated_at`,
`transfer_started`, `original_service_authoritative`, `recovery`.

## 6. Supervisor-Zustandsmodell

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

Zusätzlich z. B. `aborted-before-transfer`, `recovery-running`,
`recovery-completed`, `guarded-hold`, `reboot-detected`, `orphaned-run`.

## 7. Stage 0 – autonomer Minimalrunner – ERLEDIGT

Real nachgewiesen:

- [x] Minimalrunner auf `/data` kopiert.
- [x] Start via `setsid /system/bin/sh ... &`.
- [x] Runner läuft nach Ende der ADB-Shell mit PPID 1 weiter.
- [x] spätere unabhängige ADB-Sitzungen lesen denselben Prozess/Status.
- [x] Abbruch der Windows-Überwachung beeinflusst den Runner nicht.
- [x] Testprozess kontrolliert beendet und Testverzeichnis entfernt.

## 8. Stage 1 – production-shaped Supervisor ohne OTA – FAST ERLEDIGT

Der Stage-1-Runner berührt weder Firmware noch `phnixIot4G`, GDB oder OTA.

### Reale Hardwarebestätigung vom 1. September 2026

Normaler Lauf `stage1-real-01`:

- Start mit PID `22836`.
- Initial noch PPID `22834`, danach derselbe Prozess mit PPID `1`.
- unabhängige Statusabfragen zeigten autonom `29 %`, `54 %` und anschließend
  `completed / terminal=true / 100 %`.
- terminaler Status blieb nach Prozessende unter `/data` erhalten.
- `ack` ließ den Status bestehen; der nachfolgende Cleanup konnte ihn weiterhin lesen.
- `cleanup` nach terminal + ack entfernte das Run-Verzeichnis kontrolliert.

Abort-Lauf `stage1-abort-01`:

- Start mit PID `29764`, später PPID `1`.
- `abort.request` wurde ohne ADB-Kill geschrieben.
- der Runner wechselte selbstständig zu `aborted`, `phase=abort-request`,
  `terminal=true`, `reason=abort_requested`.
- ein zweiter Abort auf den bereits terminalen Run wurde vom Windows-Testclient
  abgelehnt; dies ist korrekt, kann später UX-seitig als Hinweis statt Exception
  dargestellt werden.

### Stage-1-Abnahmetests

- [x] Normaler Lauf bis `completed`.
- [x] Host-Monitoring endet; Runner läuft detached mit PPID 1 weiter.
- [x] Spätere neue ADB-Abfragen lesen dieselbe Run-ID und fortgeschrittenen Status.
- [ ] Zweiter paralleler Start wird sicher verweigert.
- [x] `abort.request` führt kontrolliert zu `aborted`, nicht zu blindem Prozess-Kill.
- [x] Terminalstatus bleibt nach Prozessende vorhanden.
- [x] `ack` löscht noch keine Diagnose.
- [ ] `cleanup` vor terminal wird verweigert.
- [ ] `cleanup` ohne ack wird verweigert.
- [x] `cleanup` nach terminal + ack entfernt das richtige Run-Verzeichnis.
- [ ] Stale-/fremde PID wird nicht beendet.

Vor Stage 2 sollen mindestens Parallelstart, Cleanup-Sperren und Stale-PID-Test noch
real geprüft werden.

## 9. Stage 2 – Supervisor + Runtime-Hook, noch ohne Firmwaretransfer

Ziel: Der Supervisor startet den bestehenden Hook selbst; Windows beobachtet nur.

- [ ] Hook als Child des Supervisors starten.
- [ ] Hookstatus Run-spezifisch schreiben.
- [ ] Hook-PID und Prozessidentität überwachen.
- [ ] Hookstatus in Supervisorstatus übersetzen.
- [ ] Hook-Log dauerhaft dem Run zuordnen.
- [ ] `/tmp` nur als Runtime-Signal behandeln.
- [ ] Read-only `verify` als erster Child-Workflow.
- [ ] danach read-only Attach-Test als Child-Workflow.
- [ ] Windows-Monitor/ADB währenddessen beenden.
- [ ] Supervisor/Hook müssen unbeeinflusst weiterlaufen.
- [ ] Ergebnis persistent unter `/data` ablegen.

## 10. Stage 3 – Paketformat und doppelte lokale Verifikation

Windows prüft vor Upload; DTU prüft vor Nutzung erneut.

Paketdaten mindestens: Firmwaregröße/MD5/SHA-256, Softwarecode, Display-/Wire-Version,
Target SSID, Hook-Hash, erwartete `phnixIot4G`-Build-ID/SHA-256, Run-ID und Modus.

- [ ] falscher Firmwarehash → Ablehnung vor Serviceeingriff.
- [ ] falscher Hookhash → Ablehnung.
- [ ] falscher Servicebuild → Ablehnung.
- [ ] unvollständiges Paket → Ablehnung.
- [ ] falsche Run-ID/Paketzuordnung → Ablehnung.
- [ ] freier Speicher lokal geprüft.

## 11. Stage 4 – Pre-C5A8-Orchestrierung auf DTU verschieben

- [ ] Originaldienst/Build prüfen.
- [ ] MQTT/Cloud und Watchdogs prüfen.
- [ ] OTA_INFO / Resume-Zustand prüfen.
- [ ] persistenten Ausgangszustand sichern.
- [ ] Firmware/Staging/HTTP lokal vorbereiten.
- [ ] OTA-Command erzeugen/verifizieren.
- [ ] Hook starten und C350 auslösen.
- [ ] C36E-Annahme klassifizieren.
- [ ] Same-Version-/Precondition-Ablehnung lokal terminal behandeln.

Bis C5A8 bleibt nur die heute bereits erlaubte sichere Recovery zulässig.

## 12. Stage 5 – echter C5A8-Transfer autonom auf DTU

Erst nach Abnahme aller vorherigen Stufen.

- [ ] erster C5A8 setzt persistent `transfer_started=true`.
- [ ] Autoritätsübergang persistent markieren.
- [ ] Fortschritt aus OTA_INFO/Hook lokal übernehmen.
- [ ] Windows-/ADB-/USB-Ausfall beeinflusst OTA nicht.
- [ ] Hookfehler nach Autoritätsübergang stoppt Originaldienst nicht generisch.
- [ ] kein generischer Restore nach C5A8.
- [ ] erster Realtest mit serieller externer Beobachtung.

## 13. Stage 6 – terminale Mainboardverifikation lokal

Erfolg niemals nur wegen `100 %` oder `promotion-committed`.

- [ ] Transfer vollständig erkennen.
- [ ] Mainboard-Verarbeitungsphase verfolgen.
- [ ] Hersteller-Erfolgsmeldung berücksichtigen.
- [ ] Status 5 / Step 12 gemäß validierter Logik bestätigen.
- [ ] `result.json` schreiben.
- [ ] `status.json` terminal setzen.
- [ ] Run-Lock freigeben.
- [ ] Diagnose behalten.

## 14. Stage 7 – Recovery und kontrollierter Abort

Vor C5A8 darf ein kontrollierter Abort nur die bereits als sicher validierte Recovery
verwenden. Nach begonnenem C5A8 darf `abort.request` keinen generischen Abbruch auslösen;
der Runner überwacht dann weiter bis zu einem sicheren terminalen Ergebnis.

Ein Force-/Emergency-Eingriff ist ein separater Entwicklerpfad und nicht Teil des
normalen Endanwenderablaufs.

## 15. Stage 8 – DTU-Reboot / Prozessverlust

Zuerst ohne OTA real prüfen:

- [ ] bleibt `/data/foxair_ota_runner` nach DTU-Reboot erhalten?
- [ ] bleiben atomare Statusdateien konsistent?
- [ ] erwartetes Ende aller `setsid`-Prozesse bestätigen.
- [ ] Neustartverhalten von `phnixIot4G` erfassen.
- [ ] Pre-C5A8 / Post-C5A8 / terminal aus persistentem Status klassifizieren.

Nie alte `/tmp`-PIDs/Marker nach Reboot wiederverwenden. Automatische OTA-Fortsetzung
nach DTU-Reboot wird erst nach realer Analyse entschieden.

## 16. Stage 9 – Windows auf dünnen Client reduzieren

Zielkommandos:

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

- [ ] Run-ID anzeigen.
- [ ] DTU-Status pollen.
- [ ] ADB-Ausfall nur als Monitoringverlust darstellen.
- [ ] nach Reconnect denselben Run fortsetzen.
- [ ] niemals automatisch zweiten Run starten.
- [ ] terminale Ergebnisse per Popup anzeigen.
- [ ] Ack/Cleanup getrennt behandeln.
- [ ] neue OTA/Dry-Run-Versuche bei aktivem Run sperren.

Die bestehende serielle Windows-Fallbacklogik bleibt bis zur mindestens gleichwertigen
Realvalidierung des autonomen DTU-Pfads bestehen.

## 17. Stage 10 – Simulator an neuen Runnervertrag anpassen

Mindestens simulieren:

- [ ] normaler Erfolg und Same-Version.
- [ ] Fehler vor C5A8.
- [ ] ADB-Verlust/Reconnect während C5A8.
- [ ] `promotion-committed` ohne terminalen Erfolg.
- [ ] später `success + terminal=true`.
- [ ] Hookverlust vor/nach C5A8.
- [ ] Runner-Abbruch, stale lock, kaputte Statusdatei.
- [ ] Modem-Reboot mit persistentem letztem Run.

Der aktuelle Simulatorfehler des Stage-1-Runners ist kein Hardwareblocker; reale DTU
hat den detached Stage-1-Lauf bestätigt.

## 18. Stage 11 – automatisches Reattach-/Statuspolling in Windows

Wenn ADB wieder erreichbar, Run aber noch nicht terminal:

- [ ] alle etwa 5–10 s read-only `status` pollen.
- [ ] bei terminal sauber beenden.
- [ ] bei erneutem ADB-Verlust Monitoringverlust darstellen.
- [ ] keine falsche dauerhafte Anzeige „Abschlusskontrolle läuft“, wenn kein Polling läuft.
- [ ] niemals OTA-Aktion aus dem Polling auslösen.

## 19. Stage 12 – Cleanup und Retention

1. terminales `status.json`/`result.json` schreiben;
2. Windows liest Ergebnis;
3. Windows setzt `acknowledged`;
4. erst danach normaler Cleanup;
5. kleiner Abschlussbericht kann länger erhalten bleiben.

Optional: Payload nach z. B. 24 h entfernen, N alte Resultate behalten, Logs begrenzen.
Nicht terminale Runs niemals allein wegen Alters löschen.

## 20. Stage 13 – Failover-/Chaos-Tests

- [ ] Windows-Prozess beenden / PC herunterfahren.
- [ ] Remote-ADB stoppen / USB trennen / ADB offline.
- [ ] ADB reconnect.
- [ ] Hook vor C5A8 beenden.
- [ ] Hook nach C5A8 verlieren.
- [ ] Status während atomarem Schreiben lesen.
- [ ] Speicher knapp / Loglimit.
- [ ] Service-/Watchdog-PID-Wechsel.
- [ ] MQTT-Ausfall.
- [ ] langsamer C5A8.
- [ ] Polling minutenlang aussetzen.
- [ ] neuer Host verbindet sich an denselben Run.
- [ ] zweiter Start während aktivem Run.
- [ ] DTU-Reboot vor C5A8.
- [ ] DTU-Reboot nach C5A8 nur mit definierter sicherer Strategie.

## 21. Stage 14 – produktive Integration

- [ ] Runner aus `devtools` in Produktpfad verschieben.
- [ ] Runner-/Hook-Version und Hash prüfen.
- [ ] Windows-/Linux-Launcher umstellen.
- [ ] alte Host-Orchestrierung deaktivieren.
- [ ] redundante Guard-/Fallbacklogik erst nach Realabnahme entfernen.
- [ ] Regressionstests und Buildsystem aktualisieren.
- [ ] Upgradepfad testen.

Endzustand: nur eine produktive OTA-Orchestrierung.

## 22. Stage 15 – endgültige Dokumentation und `docs/dev` löschen

Dauerhaft übernehmen:

- autonome Architektur;
- Host↔Runner-Statusvertrag;
- Sicherheitsgrenzen vor/nach C5A8;
- Recovery-/Rebootverhalten;
- Cleanup/Retention;
- reale Testmatrix;
- Endanwenderablauf.

Danach:

- [ ] Roadmap erledigt markieren.
- [ ] Erkenntnisse in normale Dokus übertragen.
- [ ] **`docs/dev/` vollständig löschen.**

## 23. Definition of Done

- [ ] reales Mainboardupdate läuft nach Start ohne Windows autonom weiter.
- [ ] ADB kann beliebig ausfallen und später denselben Run lesen.
- [ ] DTU entscheidet selbst über sicherheitskritische OTA-Phasen.
- [ ] Monitoringfehler kann begonnenen C5A8 nicht stoppen.
- [ ] generischer Restore nach C5A8 ausgeschlossen.
- [ ] terminaler Erfolg lokal eindeutig und dauerhaft gespeichert.
- [ ] terminale Fehler mit belastbarem Grund/Recoverystatus.
- [ ] Diagnose bleibt bis Bestätigung erhalten.
- [ ] parallele OTA-Runs ausgeschlossen.
- [ ] stale Locks/PIDs führen nie zu falschem Kill/Cleanup.
- [ ] Rebootverhalten real untersucht.
- [ ] Simulator bildet Runnervertrag ab.
- [ ] Windows nach `start` nur Client/Beobachter.
- [ ] alte redundante Host-Orchestrierung entfernt oder klar isoliert.
- [ ] Unit-/Simulator-/Hardwaretests dokumentiert.
- [ ] dauerhafte Dokumentation aktualisiert.
- [ ] `docs/dev/` anschließend entfernt.

## 24. Unmittelbare Reihenfolge

1. Restliche Stage-1-Hardwaretests: Parallelstart, Cleanup-Sperren, stale PID.
2. Stage 2: Hook zunächst als harmlosen `verify`-/Attach-Child starten.
3. ADB-Abbruch/Reattach mit diesem Child testen.
4. Paketformat + lokale Hashprüfung implementieren.
5. Pre-C5A8-Orchestrierung verschieben.
6. Erst danach echten C5A8-Lauf autonom auf DTU testen.
7. Terminalverifikation und Recovery lokal abschließen.
8. Windows erst zum Schluss auf dünnen Client umbauen.
