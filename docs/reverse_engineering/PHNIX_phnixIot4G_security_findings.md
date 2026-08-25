# PHNIX `phnixIot4G` – Sicherheitsrelevante Reverse-Engineering-Befunde

Stand: 2026-08-25

Grundlage: statische Analyse des ungestrippten ARM-ELF `phnixIot4G`, Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`.

Diese Datei dokumentiert **beobachtete technische Eigenschaften des Originaldienstes**. Sie ist keine Aussage darüber, ob die gesamte Herstellercloud kompromittierbar ist. Die relevante Vertrauensgrenze liegt teilweise außerhalb des analysierten Binaries bei Aliyun, SIM/Mobilfunknetz und Backend-Autorisierung.

Sie ergänzt `PHNIX_phnixIot4G_runtime_counters_remote_control_security.md`.

## 1. Remote-OTA-Dispatcher prüft nur `code`

Der aktive Pfad lautet:

```text
Aliyun MQTT /user/OTA_GET
 -> aliMqtt_topic_ota_get_msg_arrive()
 -> ota_code_handle()
```

`ota_code_handle()`:

1. parst das JSON
2. holt das Feld `code`
3. wandelt den String numerisch um
4. sucht diesen Wert in `ota_hanldle @ 0x91C20`
5. ruft den zugehörigen Handler auf

Im rekonstruierten Kontrollfluss wird das JSON-Feld `cmd` **nicht als zusätzliche Bedingung geprüft**.

Damit ist für den lokalen Dispatcher die numerische `code`-Zuordnung entscheidend. Insbesondere:

```text
114 -> device_reset_handle()
```

Der Reset-Handler selbst benötigt keine weiteren Parameter aus dem empfangenen JSON.

## 2. Keine zweite Payload-Signaturprüfung im PHNIX-Dispatcher sichtbar

Zwischen MQTT-Empfang und Handler-Aufruf wurde keine zusätzliche PHNIX-eigene HMAC-/Signatur-/Challenge-Prüfung gefunden.

Die primäre Authentisierung/Aufsicht liegt damit offenbar in:

```text
Aliyun MQTT/TLS
ProductKey
DeviceName
DeviceSecret
Broker-/Topic-Autorisierung
```

Die Aussage ist bewusst eng: Es wurde **keine zusätzliche lokale Payload-Authentisierung im analysierten Anwendungspfad** gefunden. Das beweist nicht, dass die Aliyun-Seite selbst keine Zugriffskontrolle besitzt.

## 3. OTA-MQTT-Payload wird mit `strcpy()` in 1024-Byte-Puffer kopiert

Global:

```text
MQTT_get_data @ 0x94AB4
Größe: 1024 Byte
```

Im Callback:

```text
aliMqtt_topic_ota_get_msg_arrive() @ 0x1ED98
```

wird der MQTT-Payloadpointer mit:

```c
strcpy(MQTT_get_data, payload);
```

kopiert.

Der relevante PLT-Aufruf bei `0x1EE7C` löst auf `strcpy@GLIBC_2.4` auf. Vor diesem Aufruf ist keine Begrenzung auf 1023 Nutzbytes sichtbar.

Damit besteht im OTA-Empfangspfad eine klassische **unbegrenzte Kopie in einen festen globalen 1024-Byte-Puffer**.

Bewertung:

- Robustheitsfehler: ja
- potenzielle Speicherüberschreibung bei überlangem, NUL-terminiertem Payload: ja
- praktische Ausnutzbarkeit: nicht untersucht und nicht behauptet
- Zugriffsvoraussetzung: Payload muss zunächst den MQTT-/Brokerpfad bis zum Gerät erreichen

## 4. DeviceSecret wird nach MQTT-Initialisierung in Hersteller-Diagnoselog eingebaut

In `ali_mqtt_init()` existiert der Formatstring:

```text
productKey:%s
deviceName:%s
deviceSecret:%s
TOPIC_GET=%s
TOPIC_OTA_GET=%s
TOPIC_UPDATE=%s
TOPIC_OTA_UPDATE=%s
TOPIC_ERROR=%s
```

Der Code formatiert daraus nach erfolgreicher Initialisierung einen Diagnoseblock und übergibt ihn anschließend an:

```text
http_ommunicationDeviceLog() @ 0x17170
```

Damit wird der aktive **DeviceSecret im Klartext Teil des Hersteller-Logtexts**.

## 5. Hersteller-Diagnoselog verwendet unverschlüsseltes HTTP

`http_ommunicationDeviceLog()` baut die URL aus der im Binary hinterlegten Basis:

```text
http://cloud.linked-go.com:84
```

und dem Pfad:

```text
/cloudservice/api/communicationDevice/create_communicationDeviceLog.json
```

Der POST-Body besitzt die Form:

```json
{"communicationDeviceLogModel":{"deviceCode":"...","logMsg":"..."}}
```

Der Funktionsparameter wird direkt als `logMsg` eingesetzt.

Da `ali_mqtt_init()` den oben genannten Diagnoseblock inklusive `deviceSecret` an genau diese Funktion übergibt, ergibt sich im analysierten Build der statisch rekonstruierte Pfad:

```text
DeviceSecret im RAM
 -> Klartext-Diagnosestring
 -> http_ommunicationDeviceLog(logMsg)
 -> HTTP POST an cloud.linked-go.com:84
```

Damit besteht ein **sicherheitsrelevanter Klartextpfad für das DeviceSecret über HTTP**.

Dieser Befund ist im Binary statisch sehr stark belegt. Eine Paketmitschnitt-Livevalidierung wurde noch nicht durchgeführt.

## 6. Konsequenz für lokale Tools

Der FoxAir Updater kann DeviceSecret bei Bedarf read-only auslesen, sollte aber:

- Secret standardmäßig maskieren
- Secret niemals in normale Logs schreiben
- Secret nicht in Support-ZIPs aufnehmen
- Secret nicht in öffentliches Diagnose-JSON exportieren
- bei „anzeigen/kopieren“ explizit auf Credential-Sensitivität hinweisen

Bekannter aktiver RAM-Puffer:

```text
_device_secret @ 0x9896C
```

## 7. DTU-Self-OTA: MD5 ist Integrität, keine unabhängige Authentizität

Der DTU-Self-OTA erhält über den Remote-Kanal mindestens:

```text
Softwarecode
Softwareversion
fileMD5
fileSize
otaFileDownloadAddr
```

Anschließend:

```text
Download -> /data/phnixIot4G_OTA
MD5-Prüfung
chmod +x
mv über /data/phnixIot4G
killall -9 phnixIot4G
```

Da erwarteter MD5 und Downloadadresse über denselben autorisierten Steuerkanal kommen, ist der MD5-Wert eine Integritätsprüfung gegen Übertragungsfehler, aber **keine unabhängige kryptografische Signatur der Firmwareherkunft**.

Eine zusätzliche PHNIX-spezifische RSA-/ECDSA-Firmware-Signaturprüfung wurde in diesem DTU-OTA-Pfad nicht gefunden.

## 8. Remote-Cloudkanal ist gleichzeitig Raw-UART-Bridge

Der normale Topic-Callback:

```text
aliMqtt_topic_get_msg_arrive() @ 0x1EED0
```

reicht Payload und Länge direkt weiter an:

```text
uart485_send_data_to_board(payload, length)
```

Damit besitzt die Cloud grundsätzlich einen bidirektionalen Binärkanal bis zum Mainboard-UART. Der LTE-Dienst implementiert hier keine semantische Register-Allowlist.

Die Modbus-/CRC-/Adressvalidierung erfolgt nachgelagert bzw. auf dem Mainboard.

## 9. Remote-Reboot quittiert vor dem Reboot

`device_reset_handle()`:

```text
sendet RESET/result=1
prüft Rückgabewert des MQTT-Sendens
bei Erfolg:
  Active-Reset-t++
  static_write_data()
  sleep(5)
  system("reboot")
```

Das bedeutet: Der Herstellerpfad versucht vor dem tatsächlichen Neustart eine positive Quittung an die Cloud zu übertragen.

## 10. Cloud-Watchdog ist absichtlich selbstheilend, aber aggressiv

`TimerHandler()` erzwingt bei >1800 Sekunden ohne Aliyun-Verbindung einen vollständigen Linux-Reboot.

Das kann bei Backend-/DNS-/Mobilfunkproblemen zu periodischen Reboots führen. Diese Vorgänge werden über `Active-Reset-t` gezählt.

Für Diagnose ist daher die Kombination aus:

```text
Active-Reset-t
On-Off-line-t
Online time
Work time
ErrorStatue Bit 10
```

besonders interessant.

## 11. Dormante QMI-DMS-Funktionen erweitern theoretische lokale Fähigkeiten

Das Binary enthält vollständige, derzeit offenbar ungenutzte Funktionen:

```text
get_meid()
get_mac_address_from_nv()
get_rev_id()
dms_set_operating_mode()
dms_get_operating_mode()
```

Diese sind nicht als aktive Remote-Kommandos im PHNIX-Dispatcher verdrahtet. Insbesondere `dms_set_operating_mode()` sollte daher nicht mit dem bestätigten Remote-Rebootpfad verwechselt werden.

Die DMS-Enums im Binary enthalten auch Qualcomm-Betriebsmodi wie RESETTING/FACTORY_TEST_MODE, aber das bloße Vorhandensein der SDK-Enums beweist keinen PHNIX-Remote-Factory-Reset-Pfad.

## 12. Aktuell kein bestätigter Factory-Reset-Remote-Befehl

Trotz Strings/Enums aus Qualcomm DMS wurde im aktiven PHNIX-Remote-Command-Table **kein Factory-Reset-Handler** gefunden.

Bestätigte Remote-Aktionen sind derzeit:

```text
DTU OTA
Mainboard OTA
Versionsabfragen/-Trigger
DTU OTA Cancel
Mainboard OTA Cancel
Mainboard Rollback
kompletter Modem/Linux-Reboot
```

Ein „Werkseinstellungen löschen“-Remote-Pfad ist im bisher analysierten aktiven Dispatcher nicht nachgewiesen.

## 13. Priorität für weitere Validierung

Besonders lohnend wären künftig passive Liveprüfungen von:

1. HTTP-Diagnoseverkehr beim MQTT-Start: bestätigt er das DeviceSecret im `logMsg` auf dem Draht?
2. genaue Häufigkeit/Auslöser von `http_ommunicationDeviceLog()`
3. Verhalten des Cloud-Watchdogs bei bewusst unterbrochener Internetverbindung
4. `get_rev_id()` als read-only Quelle der SIM7600E-H/Baseband-Revision

Keine dieser Prüfungen erfordert Eingriffe in den Mainboard-Modbusbus.
