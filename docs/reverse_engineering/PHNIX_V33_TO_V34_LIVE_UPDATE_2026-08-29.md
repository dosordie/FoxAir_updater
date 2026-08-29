# PHNIX-Mainboard: erfolgreicher Live-Update V3.3 → V3.4

Stand: 29. August 2026

## Ergebnis

Der lokale FoxAir-Updater hat auf realer Hardware einen vollständigen
Versionswechsel von Mainboard-Firmware V3.3 (`0033`) auf V3.4 (`0034`)
durchgeführt. Firmwareidentität und Abschluss wurden unabhängig im passiven
RS485-Mitschnitt bestätigt.

Verwendete Firmwaremetadaten:

| Feld | Wert |
|---|---|
| Softwarecode | `82400644` |
| Ziel-SSID | `0063` |
| Version auf dem Bus | `0034` |
| Größe | `289806` Byte |
| MD5 | `149A586EDE6F035B385762EA48C71605` |
| SHA-256 | `97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890` |

## Gemessener Ablauf

Die Zeiten sind lokale Zeit (CEST). Der JSONL-Mitschnitt speichert dieselben
Ereignisse als UTC-Zeitstempel.

| Zeitpunkt | Beobachtung |
|---|---|
| 00:51:18 | C350-Angebot für `82400644` / `0034`; ACK und C36E Status 1 |
| 00:51:19 | C36E Status 2 |
| 00:51:20 | erster C5A8-Firmwareblock |
| 01:20:16 | letzter C5A8-Firmwareblock bestätigt |
| 01:20:18 | C36E Status 3 |
| 01:25:32 | C36E Status 5 |
| 01:25:34 | Runtime-Helfer meldet terminalen Erfolg, `board_ota_step=12` |
| 01:26:33 | C544 meldet Softwarecode `82400644`, Firmwareversion `0034` |

Damit dauerte die reine C5A8-Übertragung rund **28 Minuten 56 Sekunden**.
Vom letzten Datenblock bis Status 5 benötigte das Mainboard weitere rund
**5 Minuten 16 Sekunden**. Bis zur ersten C544-Versionsmeldung verging nochmals
ungefähr eine Minute. Für den vollständigen beobachteten Ablauf müssen daher
mindestens 35 Minuten eingeplant werden.

## Dienst- und Neustartbeobachtung

Der Controller sah vom Preflight bis zum terminalen Status 5 durchgehend den
gleichen `phnixIot4G`-Prozess (`PID 15045`). Im kritischen Übertragungs- und
Flashfenster ist damit kein Neustart des LTE-Dienstes belegt.

Das Mainboard durchlief dagegen den erwarteten Abschluss-/Neustartpfad. Dafür
sprechen Status 5 und die anschließende neue C544-Meldung mit Version `0034`.
Eine später abweichende LTE-Prozess-ID allein erlaubt keine zeitliche Zuordnung
und ist kein Nachweis für einen Neustart während des Flashens.

## Falsch-negativer Abschluss im damaligen Updater

Der damalige Lauf meldete zwei Sekunden nach dem terminalen Erfolg `Exit 1`,
weil zu diesem exakten Zeitpunkt noch keine MQTT-Verbindung in `netstat`
sichtbar war. Firmwareübertragung und Mainboardabschluss waren zu diesem
Zeitpunkt bereits erfolgreich. MQTT stellte sich anschließend normal wieder her.

Folgerungen für den Updater:

- Nach C36E Status 1 bleibt der Originaldienst ohne Controller-Gesamttimeout
  autoritativ.
- Nach Status 5 erhält Dienst-/Watchdog-/MQTT-Rückkehr ein 120-Sekunden-Fenster.
- MQTT bleibt beim normalen Vollupdate standardmäßig verbunden.
- Eine MQTT-Isolierung ist nur noch eine bewusst gewählte optionale Betriebsart.
- 100 % C5A8 bedeuten nur „vollständig übertragen“, noch nicht „geflasht und
  gestartet“. Erst Status 5 / Board-Step 12 ist terminaler Erfolg.

## Bewertung der MQTT-Verbindung

Die frühere MQTT-Sperre konnte den originalen Cloud-Offline-/Resetmechanismus
nach etwa 30 Minuten erreichen, während eine reale Übertragung bereits knapp
29 Minuten dauert und die Mainboard-Promotion weitere Minuten benötigt.

Die kontrollierten Cloud-One-Shot-Tests lieferten für die geprüften älteren
Versionsangaben keine OTA-Metadatenantwort. Zusammen mit dem erfolgreich vom
Originaldienst übernommenen lokalen Ablauf ist das beobachtete 30-Minuten-
Offlinefenster derzeit das konkretere Risiko. Deshalb ist „MQTT verbunden“ nun
der Standard. Wer für einen besonderen Labortest die frühere Isolierung benötigt,
kann sie explizit mit `--isolate-mqtt` beziehungsweise dem Alias
`--update-no-mqtt` anfordern.

## Verwendete Belege

- Host-/Windows-Log `update 3.4 log.txt`
- passiver RS485-Mitschnitt `warmlink_capture_2026-08-29_003.events.jsonl`
- zugehöriger Rohmitschnitt `warmlink_capture_2026-08-29_003.rx.bin`
- abschließender read-only Modemstatus: Originaldienst aktiv, kein Debugger,
  MQTT verbunden, Runtime-Helfer entfernt, OTA_INFO mit `0034`

Es wurden keine Firmwarebinärdateien oder gerätespezifischen Zugangsdaten in
dieser Dokumentation abgelegt.
