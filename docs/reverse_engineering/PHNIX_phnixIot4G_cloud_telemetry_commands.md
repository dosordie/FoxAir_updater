# PHNIX `phnixIot4G` – Cloud-Telemetrie und Cloud-Kommandokanäle

Stand: 2026-08-25

Grundlage: statische Analyse des ungestrippten ARM-ELF `phnixIot4G` (Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`) sowie Live-Validierungen am realen LTE-Modem.

Diese Datei beschreibt, **welche Daten `phnixIot4G` zur Cloud überträgt und welche Kommandokanäle von der Cloud zum LTE-Modul/Mainboard existieren**.

> Sicherheits-/Datenschutzhinweis: Im Prozess existieren Cloud-Credentials. Diese Dokumentation enthält bewusst **keine DeviceSecret-/ProductSecret-Werte**. Solche Werte dürfen nicht in Logs, Support-ZIPs oder öffentliche Dokumentation übernommen werden.

---

## 1. Kurzfazit

Es existieren vier wesentliche ausgehende Cloud-Pfade:

1. **normaler Rohdaten-MQTT-Kanal** Mainboard -> Cloud
2. **Fehler-MQTT-Kanal** LTE-Modul -> Cloud
3. **OTA-Status-MQTT-Kanal** LTE/Mainboard-OTA -> Cloud
4. **PHNIX/linked-go HTTP-Diagnose-/Statistiklog** LTE-Modul -> Cloud

In Gegenrichtung existieren mindestens:

1. **normaler Rohdaten-MQTT-Kanal** Cloud -> Mainboard
2. **OTA-/Service-MQTT-Kanal** Cloud -> LTE-Modul
3. HTTP-Provisionierungsantworten für Gerätezuordnung/Credentials

Der normale MQTT-Pfad ist dabei besonders wichtig: Er ist kein semantisch dekodierter Registerdienst im LTE-Modul, sondern im Wesentlichen ein **Binärtunnel zur RS485-/Mainboard-Seite**.

---

## 2. MQTT-Topics

Die Topics werden dynamisch aus `ProductKey` und `DeviceName` aufgebaut.

```text
/<productKey>/<deviceName>/user/get
/<productKey>/<deviceName>/user/update
/<productKey>/<deviceName>/user/update/error
/<productKey>/<deviceName>/user/OTA_GET
/<productKey>/<deviceName>/user/OTA_UPDATE
```

Richtung:

```text
Cloud -> LTE/Mainboard    /user/get
LTE/Mainboard -> Cloud    /user/update
LTE Fehler -> Cloud       /user/update/error
Cloud -> OTA-Service      /user/OTA_GET
OTA-Status -> Cloud       /user/OTA_UPDATE
```

---

## 3. Normaler Cloud -> Mainboard-Kanal `/user/get`

Callback:

```text
aliMqtt_topic_get_msg_arrive @ 0x1EED0
```

Der empfangene MQTT-Payload wird praktisch unverändert an

```text
uart485_send_data_to_board()
```

übergeben.

Damit gilt:

```text
Cloud /user/get
 -> MQTT Payload (binär)
 -> aliMqtt_topic_get_msg_arrive()
 -> uart485_send_data_to_board()
 -> /dev/ttyHSL2
 -> Mainboard
```

### Konsequenz

Die Cloud kann über diesen Kanal normale Mainboard-/Modbus-/Serviceframes senden. Das LTE-Modul benötigt dafür keine lokale semantische Registertabelle.

Der Callback erhöht außerdem Statistikzähler für empfangene Cloud-Daten.

---

## 4. Mainboard -> Cloud-Kanal `/user/update`

Der RS485-Empfangspfad lautet vereinfacht:

```text
/dev/ttyHSL2
 -> getDevParameter()
 -> CRC-Prüfung
 -> unpack_mcu_modbus()
 -> ali_mqtt_push_msg(raw_frame, len)
 -> /user/update
```

Normale Mainboard-Telegramme werden damit als **rohe Binärframes** zur Cloud übertragen.

Das bedeutet: Die Warmlink-/Cloud-Seite kann einen wesentlich größeren Teil des Mainboardverkehrs sehen, als das LTE-Modul selbst lokal dekodiert.

---

## 5. Fehlerkanal `/user/update/error`

Relevante Funktion:

```text
aliMqtt_push_error_topic_to_phnix() @ 0x20100
```

Das LTE-Modul besitzt eine eigene Fehlerbitmap:

```text
ErrorStatue @ 0x93124
```

Bekannte Herstellerfehler:

```text
bit 0 -> 485 connected error
bit 1 -> Address error
bit 3 -> No PK
bit 4 -> No Three-Element-mqtt / Signalpfad
bit 5 -> Cloud connected error
bit 6 -> WF_double_error
bit 7 -> Crc error
```

Weitere höhere Bits werden ebenfalls verwendet.

Diese LTE-/Gateway-Fehler sind von Mainboard-Fehlerregistern zu unterscheiden.

---

## 6. OTA-Kommandokanal `/user/OTA_GET`

Callback:

```text
aliMqtt_topic_ota_get_msg_arrive @ 0x1ED98
```

Der Payload wird in einen lokalen Puffer kopiert und anschließend an

```text
ota_code_handle() @ 0x19958
```

gegeben.

`ota_code_handle()` parst ein JSON-Feld `code`, konvertiert es numerisch und dispatcht über eine Tabelle mit **neun Kommandos**.

### Statisch rekonstruierte Dispatch-Tabelle

| numerischer Code | Handler | Bedeutung |
|---:|---|---|
| `12` | `ota_dtu_set_ota_info()` | DTU-/LTE-OTA-Metadaten setzen |
| `32` | `down_dtu_ota_url_handle()` | DTU-/LTE-OTA-Download-URL / Download starten |
| `33` | `down_board_ota_url_handle()` | Mainboard-OTA-Download-URL / Download starten |
| `62` | `down_check_dtu_ver_handle()` | DTU-Version prüfen/anfordern |
| `63` | `down_check_board_ver_handle()` | Mainboard-Version prüfen/anfordern |
| `73` | `down_board_cancel_ota_handle()` | Mainboard-OTA abbrechen |
| `58` | `down_dtu_cancel_ota_handle()` | DTU-/LTE-OTA abbrechen |
| `103` | `down_board_ver_bcakroll_handle()` | Mainboard-Rollback |
| `114` | `device_reset_handle()` | Geräte-/Modem-Resetpfad |

Die Cloud besitzt damit nicht nur einen Firmwaredownload-Befehl, sondern explizite Pfade für Versionsabfrage, Cancel, Rollback und Reset.

---

## 7. OTA-Status LTE/Mainboard -> Cloud `/user/OTA_UPDATE`

Relevante Senderfunktionen:

```text
ota_dtu_send_version_to_phnix()
ota_dtu_send_is_can_ota_to_phnix()
ota_dtu_send_ota_progress()
ota_dtu_send_ota_finish()
ota_dtu_send_ota_Failed()
ota_dtu_send_ota_FirmwareDownloadFailed()

ota_device_send_version_to_phnix()
ota_device_send_is_can_ota_to_phnix()
ota_device_send_ota_progress()
ota_device_send_ota_finish()
ota_device_send_ota_Failed()
ota_device_send_Initialization()
ota_device_send_ota_FirmwareDownloadFailed()
```

### Statisch sichtbare ausgehende JSON-Codes

#### DTU-/LTE-Modul

```text
0002  DTU Hardware-/Softwarekennung melden
0022  DTU OTA erlaubt/nicht erlaubt
0042  DTU OTA Fortschritt
0052  DTU OTA fertig, progress=100
0082  DTU Upgrade fehlgeschlagen
0092  DTU Firmwaredownload fehlgeschlagen
```

#### Mainboard / Device

```text
0003  Mainboard Softwarecode/-version + SSID melden
0023  Mainboard OTA erlaubt/nicht erlaubt + SSID
0043  Mainboard OTA Fortschritt + SSID
0053  Mainboard OTA fertig, progress=100 + SSID
0083  Mainboard Upgrade fehlgeschlagen + SSID
0093  Mainboard Firmwaredownload fehlgeschlagen + SSID
0113  Mainboard OTA Initialisierungsstatus
```

Beispielhaft sichtbare Payloadfelder:

```text
deviceCode
dtuHardwareCode
dtuSoftwareCode
dtuSoftwareVer
deviceSoftwareCode
deviceSoftwareVer
ssid
isAllowDtuOTA
progress
upgradeFailed
FirmwareDownloadFailed
Initialization
```

---

## 8. Periodischer PHNIX-/linked-go Diagnose- und Statistikupload

Neben MQTT existiert ein separater HTTP-Logpfad.

Relevante Funktionen:

```text
Upload_bord_log() @ 0x10898
Check_upload_log() @ 0x11748
```

HTTP-Ziel:

```text
/cloudservice/api/dtuLog/report.json
```

`Upload_bord_log()` holt vor dem Aufbau des JSON u. a.:

```text
IMEI
ICCID
Aliyun DeviceName
PHNIX/Device-ID-artige Kennung
ErrorStatue
statistic_para
```

Im Herstellerformat sind folgende Identitäts-/Metadatenfelder sichtbar:

```text
imei
wf_code
device_code
iccid
```

Zusätzlich werden Fehler-/Statuskategorien und Statistikwerte übertragen.

---

## 9. Welche Statistikwerte gehen zur Cloud?

Die Strings und der Aufbau von `Upload_bord_log()` bestätigen, dass die lokale Struktur

```text
statistic_para @ 0x91B60
```

als Herstellerdiagnose hochgeladen wird.

Sicher benannte Werte:

```text
Online time
Work time
Device-change-t
On-Off-line-t
Up-D-t
Down-D-t
Ota-dev-t
Ota-dtu-t
Strongest Net csq
Weakest Net csq
Power-Reset-t
Active-Reset-t
Api-t
Average Net csq
Day-Up-D-t
Current Work time
Current Online time
```

Damit lautet die Antwort auf die Frage nach dem Mainboard-OTA-Zähler eindeutig:

> **Ja, `Ota-dev-t` gehört zum Hersteller-Statistik-/Diagnoselog und kann zur PHNIX/linked-go Cloud übertragen werden.**

Das gilt ebenfalls für mehrere weitere Langzeitzähler wie Power-Resets, Software-Resets, Onlinezeit und Signalstatistik.

---

## 10. Korrektur/Bedeutung von `Ota-dev-t`

`Ota-dev-t` liegt bei:

```text
statistic_para + 0x24
```

Der Zähler wird in

```text
ota_device_set_ota_file_download_info() @ 0x18DB8
```

erhöht.

Die Erhöhung erfolgt **bereits beim erfolgreichen Übernehmen/Verarbeiten der OTA-Datei-/Downloadinformationen**, nicht erst nach einem erfolgreichen Flashabschluss.

Danach wird die Statistik direkt persistent gespeichert (`static_write_data()`).

### Konsequenz

`Ota-dev-t` bedeutet nicht sicher:

```text
Anzahl erfolgreich installierter unterschiedlicher Mainboard-Firmwareversionen
```

sondern eher:

```text
Anzahl angenommener/gestarteter Mainboard-OTA-Vorgänge bzw. OTA-Aufträge
```

Damit können wahrscheinlich auch folgende Fälle mitzählen:

```text
Same-Version-OTA
wiederholter OTA-Auftrag
später abgebrochener OTA
fehlgeschlagener Transfer
erneuter Download-/OTA-Versuch
```

Ob jeder dieser Fälle tatsächlich zählt, hängt davon ab, ob der jeweilige Pfad erneut `ota_device_set_ota_file_download_info()` erreicht. Eine erfolgreiche Versionsänderung ist für das Inkrement aber **nicht erforderlich**.

Für GUI/Updater daher nicht "Firmware-Updates" anzeigen, sondern z. B.:

```text
Mainboard OTA-Vorgänge
```

mit Hinweis:

> Der Zähler wird bereits beim Übernehmen eines OTA-Auftrags erhöht und entspricht nicht zwingend der Zahl erfolgreicher oder unterschiedlicher Firmwareinstallationen.

---

## 11. Weitere Status-/Logkategorien

Im Hersteller-Logpfad sind u. a. folgende Kategorien/Schlüssel sichtbar:

```text
recovery
Online
Offline
Net dBm low
Net-flow over
other
Statistics
Current
```

Sowie Metafelder wie:

```text
type
keyword
important
nomal
statistics
content
```

Die genaue serverseitige Semantik jedes dieser Felder ist noch nicht vollständig rekonstruiert, aber sie gehören eindeutig zum eigenständigen PHNIX-DTU-Logformat.

---

## 12. Provisionierungs-/Gerätezuordnungs-HTTP

Zusätzlich zum Diagnoseupload existieren HTTP-Endpunkte für Gerätezuordnung/Provisionierung:

```text
/cloudservice/api/phnixiot/queryiotdevice.json
/cloudservice/api/communicationDevice/queryiotdevice.json
/cloudservice/api/communicationDevice/createDeviceBySign
/cloudservice/api/communicationDevice/create_communicationDeviceLog.json
```

Sichtbare Requestfelder umfassen je nach Pfad u. a.:

```text
productKey
deviceID
deviceCode
sign
imei
product_key
code
logMsg
```

Diese Pfade sind von der normalen MQTT-Telemetrie getrennt.

---

## 13. Datenschutz-/Updater-Hinweis

Eine lokale Modem-Info-Seite darf read-only auf Identitäts- und Statusdaten zugreifen, sollte aber sensible Cloud-Credentials nicht automatisch exportieren.

Insbesondere:

```text
DeviceSecret
ProductSecret
```

nicht in:

```text
Debuglogs
Support-ZIPs
GitHub-Dokumentation
Crashreports
Screenshots/Clipboard-Automatik
```

übernehmen.

Wenn eine GUI solche Werte überhaupt sichtbar macht, dann standardmäßig maskiert und nur nach expliziter Benutzeraktion.

---

## 14. Gesamtbild

```text
                    PHNIX / Aliyun Cloud
                           |
          +----------------+----------------+
          |                                 |
       MQTT                              HTTP
          |                                 |
   /user/get                         Provisionierung
   /user/update                      DTU-Log/Statistik
   /user/update/error                    |
   /user/OTA_GET                         |
   /user/OTA_UPDATE                      |
          |                                 |
          +--------- phnixIot4G ------------+
                         |
                    /dev/ttyHSL2
                         |
                      Mainboard
```

Das LTE-Modul ist damit gleichzeitig:

- transparenter Mainboard-Binärtunnel,
- OTA-Service-Endpunkt,
- Cloud-MQTT-Client,
- PHNIX-HTTP-Provisionierungsclient,
- Diagnose-/Statistiklogger.
