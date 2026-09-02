# Autonomer DTU-OTA-Runner – Stand 2026-09-02

## Kurzstatus

Der neue Backendpfad im Branch `DTU_runner` kann ein Firmwareupdate nach dem Start
unabhängig von Windows und ADB auf der DTU ausführen und seinen Zustand dauerhaft
speichern. Ein vollständiges V3.4-Update wurde im QEMU-Simulator bis C36E Status 5
und erfolgreicher Promotion nachgewiesen. Auch ein Verlust der ADB-Verbindung sowie
die Wiederaufnahme einer unterbrochenen C5A8-Übertragung wurden erfolgreich geprüft.

Der Backendkern ist damit funktionsfähig, die vollständige Fehler-, Reboot- und
Recovery-Matrix ist aber noch nicht abgeschlossen. Der Stand ist deshalb noch keine
abschließende Produktionsfreigabe.

## Nachgewiesene Abläufe

| Test | Ergebnis |
| --- | --- |
| Reale DTU, V3.4 gegen bereits installiertes V3.4 | Sichere Same-Version-Beendigung; kein C357 und kein C5A8 |
| VM, vollständiges V3.4-Update | C350, Status 1, C357, C5A8 bis 100 %, Status 3, Promotion, Status 5 und Step 12 erfolgreich |
| ADB während C5A8 für 20 Sekunden getrennt | Übertragung lief auf der VM weiter; nach Reconnect war derselbe Run weiter fortgeschritten |
| Simulierter Dienst-/QEMU-Neustart während C5A8 | Alter Runner klassifizierte den Beobachtungsverlust konservativ als `recovery-required`; kein unsicherer Restore |
| Wiederaufnahme nach Neustart | OTA_INFO und Board-Resumezustand blieben erhalten; C544-Rehandshake, C350/C357 und C5A8 wurden ab dem bestätigten Block fortgesetzt |
| Wiederaufgenommener Lauf bis zum Ende | Status 3, Status 5 und Promotion wurden vollständig erreicht und quittiert |
| Runner-Leerlauf | 2-Sekunden-Polling, kein Busy-Loop; nach mehreren Minuten keine messbare dauerhafte CPU-Zeit |

Verwendetes V3.4-Testimage:

- Größe: `289806` Byte
- Softwarecode: `82400644`
- Wire-Version: `0034`
- Ziel-SSID: `0063`
- SHA-256: `97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890`

## Beobachtete Resume-Sequenz

Nach dem simulierten Neustart bei laufender C5A8-Übertragung wurde folgender
Originaldienstpfad beobachtet:

1. FC03-Anfrage auf `0x0004`;
2. Boardantwort C544 mit Softwarecode und installierter Version;
3. C37B-Quittung mit Status 7;
4. neues C350-Angebot für Version `0034`;
5. C36E Status 1;
6. C357 mit Größe und Hash;
7. C36E Status 2;
8. Wiederholung des letzten bestätigten Blocks und Fortsetzung beim nächsten Block;
9. vollständige C5A8-Übertragung;
10. C36E Status 3 und dessen C37B-Quittung;
11. Promotion;
12. C36E Status 5 und dessen C37B-Quittung.

Der alte Runner darf diesen autonom fortgesetzten Vorgang nicht rückwirkend als
eigenen Erfolg verbuchen: Seine lückenlose Beobachtungskette ist durch den Neustart
verloren gegangen. Die konservative terminale Einstufung als
`original-service-active-unmonitored` mit `recovery-required` ist daher beabsichtigt.

## Umgesetzte Sicherheitskorrekturen

- C350-, C357- und C5A8-Erkennung sowie `transfer_started` sind innerhalb eines Runs
  monoton/sticky und können nicht durch einen späteren Status-Snapshot verschwinden.
- C36E wird zusätzlich separat als gesehen gespeichert.
- Nach C5A8 ist ein generischer Restore weiterhin ausgeschlossen.
- Der Neustart des Originaldienstes akzeptiert nur eine eindeutig aufgelöste PID und
  bricht bei mehrdeutigen PID-Gruppen geschlossen ab.
- Ein persistierter Preflight-Fehlergrund wird im Ergebnis sichtbar ausgegeben.
- Aktive Runs werden über den Lock und nicht über historische Run-Verzeichnisse
  erkannt; nach erfolgreichem Cleanup wird kein alter Run mehr als aktiv gemeldet.
- Fortschritt und Bytezähler bleiben beim Übergang in einen terminalen Zustand
  erhalten, auch wenn der Originaldienst seine OTA_INFO bereits geleert hat.
- Der Supervisor pollt normalerweise im 2-Sekunden-Takt. Hashprüfungen erfolgen bei
  Preflight und Phasenwechseln, nicht in einer CPU-intensiven Schleife.

## Abgrenzung Simulator und reale DTU

Die bereits real validierte UART-/Board-Step-12-Hooklogik wurde nicht wegen einer
QEMU-Einschränkung geändert.

Simulator-spezifisch sind:

- das Ignorieren eines ausschließlich unter QEMU beobachteten SIGFPE;
- die VM-spezifische Yield-/Startbehandlung;
- das persistierte virtuelle Board-Resume-Modell;
- C544-/C37B- und Status-3/5-Antworten des virtuellen Boards.

Auf echter DTU bleibt SIGFPE ein zu meldendes Signal. Ein QEMU-Sonderfall kann daher
keinen Fehler auf realer Hardware verdecken.

## Aktueller Teststand

Die Backendtests laufen erfolgreich:

```text
python -m unittest \
  tests.test_dtu_ota_runner \
  tests.test_firmware_manifest \
  tests.test_ota_reattach_safety

Ran 15 tests – OK
```

Zusätzlich wurden Python-Syntax, Shell-Syntax und Patchformat geprüft.

## Noch offene Arbeiten

Vor einer abschließenden Produktionsfreigabe sind mindestens noch nötig:

1. Fehlerfälle nach C5A8 systematisch prüfen: Timeout, Stall, Prozessverlust und
   fehlerhafte Statusfolge;
2. vollständigen V3.4-VM-Erfolg nach der Zählerkorrektur wiederholen und im
   terminalen Ergebnis exakt `289806/289806` bestätigen;
3. vollständigen DTU-Reboot während eines aktiven Runs getrennt vom bereits
   geprüften Dienst-/QEMU-Neustart klassifizieren;
4. korrupte Statusdateien, Speichermangel, parallelen Start, stale Lock und stale PID
   als Matrix testen;
5. den optionalen Neustart des realen Originaldienstes erst dann als freigegebenes
   Standardmerkmal behandeln, wenn die eindeutige PID-Auflösung live erneut
   bestätigt wurde;
6. CLI/API konsolidieren und danach erst die getrennte Windows-GUI-Integration
   beginnen.

Ein weiterer realer, versionsändernder C5A8-Test wurde für diese Arbeiten nicht
ausgeführt und ist für die aktuelle Backendbewertung nicht erforderlich.

## Relevante Commits

- `394fc7f` – monotone OTA-Zustände, sicherer Dienstneustart und VM-Staging
- `ca93d9c` – ausschließlich QEMU-spezifische SIGFPE-Behandlung
- `46e257c` – terminalen OTA-Fortschritt erhalten
- `761c251` – aktive Runs von Run-Historie trennen
- `3a30172` – virtuellen Board-Resumezustand über Neustart erhalten
- `0ce1bfb` – Resume-Boot ohne veralteten Hook
- `6cf4bb1` – C544-Rehandshake des virtuellen Boards
- `a1afa72` – autonome Resume-Erkennung und Dokumentation

