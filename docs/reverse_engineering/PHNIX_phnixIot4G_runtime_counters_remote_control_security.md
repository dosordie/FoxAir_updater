# PHNIX `phnixIot4G` – Runtime-Counter, Remote-Kommandos und Sicherheitsgrenzen

Stand: 2026-08-25

Grundlage: statische Analyse des ungestrippten ARM-ELF `phnixIot4G` (Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`) plus Live-Validierung am realen LTE-Modem über read-only ADB-Zugriffe auf `/proc/<PID>/mem` und `/data/phnixIot_device_statisic`.

Diese Datei ergänzt insbesondere:

- `PHNIX_phnixIot4G_diagnostics_statistics_debug.md`
- `PHNIX_phnixIot4G_non_ota_architecture.md`
- `PHNIX_phnixIot4G_normal_mqtt_bridge.md`
- die OTA-Reverse-Engineering-Dokumente.

## 1. Persistente Statistikdatei

Die Herstellerstatistik liegt in:

```text
/data/phnixIot_device_statisic
```

Der Dateiname ist im Herstellerbinary tatsächlich so geschrieben.

RAM-Struktur:

```text
statistic_para @ 0x91B60
Größe: 128 Byte
```

`static_read_data(1)` liest die Datei beim Start von `phnixIot4G`. `static_write_data()` schreibt jeweils die komplette 128-Byte-Struktur zurück.

Wichtig für manuelle Änderungen: Die Datei sollte nicht bei laufendem `phnixIot4G` unabhängig vom RAM-Zustand gepatcht werden, da der Dienst seine eigene RAM-Kopie später wieder vollständig zurückschreiben kann.

## 2. Korrektur: `Power-Reset-t` ist praktisch ein Prozessstartzähler

Herstellername:

```text
statistic_para + 0x28 = Power-Reset-t
```

Der Startup-Pfad zeigt jedoch eindeutig:

```text
main/startup
 -> static_read_data(1)
 -> statistic_para[+0x28]++
 -> initHardware()
 -> weitere Threads/Initialisierung
```

Die Erhöhung erfolgt unmittelbar nach dem Einlesen der Statistik und noch vor `initHardware()`.

Damit bedeutet dieser Counter in diesem Build **nicht sicher „Stromausfall“ oder „Power-Cycle“**. Er zählt mindestens jeden normalen Start des Prozesses `phnixIot4G`.

### Live-Bestätigung

Am realen Gerät wurde `phnixIot4G` manuell beendet und anschließend wieder gestartet. Dabei blieb `Active-Reset-t` unverändert, während `Power-Reset-t` um 1 anstieg.

Empfohlene GUI-Bezeichnung:

```text
Starts des LTE-Dienstes
```

oder diagnostisch:

```text
Power-Reset-t / Dienststarts
```

Nicht ohne Zusatz als „Stromausfälle“ darstellen.

## 3. `Active-Reset-t` vollständig aufgelöst

Herstellername:

```text
statistic_para + 0x2C = Active-Reset-t
```

Dieser Zähler wird im analysierten aktiven Code an zwei relevanten Stellen erhöht.

### 3.1 Automatischer kompletter Reboot nach >30 Minuten ohne Aliyun-Verbindung

`TimerHandler()` läuft im Sekundentakt und prüft:

```text
get_ALI_Connt_State()
```

Bei vorhandener Aliyun/MQTT-Verbindung wird der Offline-Zähler auf 0 gesetzt.

Bei fehlender Verbindung wird er jede Sekunde erhöht. Überschreitet er:

```text
0x708 = 1800 s = 30 min
```

passiert:

```text
Offline-Zähler = 0
statistic_para[+0x2C]++
static_write_data()
system("reboot")
```

Damit besitzt `phnixIot4G` einen eigenen **30-Minuten-Cloud-Watchdog**, der das komplette Linux-Modem rebootet, wenn die Aliyun-Verbindung zu lange fehlt.

Zusätzlich wird bei fehlender Aliyun-Verbindung Error-Bit 10 gesetzt und die Kommunikations-LED beeinflusst; bei wieder vorhandener Verbindung wird das Bit gelöscht.

### 3.2 Remote-RESET über OTA-MQTT

```text
device_reset_handle() @ 0x1986C
```

sendet zuerst:

```json
{"cmd":"RESET","code":"0114","param":{"result":"1"}}
```

über `ali_mqtt_push_OTA_msg()` zurück.

Nur wenn das Senden erfolgreich war, folgt:

```text
statistic_para[+0x2C]++
static_write_data()
sleep(5)
system("reboot")
```

Der Counter zählt damit mindestens:

1. vom Dienst selbst ausgelöste Reboots nach >30 min Cloud-Ausfall
2. explizite Remote-RESET-Kommandos über den Hersteller-/Aliyun-Kanal

Ein normales `kill phnixIot4G`, ein Prozesscrash oder ein normaler Dienstneustart erhöht `Active-Reset-t` nicht automatisch.

Empfohlene GUI-Bezeichnung:

```text
Vom LTE-Dienst ausgelöste Reboots
```

## 4. Feste Remote-Kommandotabelle

`ota_code_handle()` parst aus der MQTT-Nachricht das JSON-Feld `code`, wandelt es in eine Zahl um und dispatcht über eine feste Tabelle `ota_hanldle @ 0x91C20`.

Die neun Einträge dieses Builds sind:

| numerischer Code | Handler | Funktion |
|---:|---|---|
| `12` | `ota_dtu_set_ota_info @ 0x1841C` | DTU-OTA-Metadaten/Version setzen |
| `32` | `down_dtu_ota_url_handle @ 0x19580` | DTU-OTA Download/Installation starten |
| `33` | `down_board_ota_url_handle @ 0x19688` | Mainboard-OTA Downloadinfo annehmen/starten |
| `62` | `down_check_dtu_ver_handle @ 0x19704` | DTU-Versionsabfrage/-Trigger |
| `63` | `down_check_board_ver_handle @ 0x19734` | Board-Versionsabfrage/-Trigger |
| `73` | `down_board_cancel_ota_handle @ 0x19764` | Mainboard-OTA abbrechen |
| `58` | `down_dtu_cancel_ota_handle @ 0x19828` | DTU-OTA abbrechen |
| `103` | `down_board_ver_bcakroll_handle @ 0x197F4` | Mainboard-Rollback anfordern |
| `114` | `device_reset_handle @ 0x1986C` | kompletten Modem/Linux-Reboot auslösen |

Die sichtbaren Antwortcodes verwenden vierstellige Strings wie `0114`; intern wird numerisch dispatcht.

## 5. Sicherheitsgrenze der Remote-Kommandos

Der aktive Empfangspfad lautet:

```text
Aliyun MQTT Topic /user/OTA_GET
 -> aliMqtt_topic_ota_get_msg_arrive()
 -> Payload in MQTT_get_data
 -> ota_code_handle()
 -> JSON code
 -> feste Handler-Tabelle
```

Im untersuchten PHNIX-Anwendungscode ist in diesem Pfad **keine zusätzliche PHNIX-eigene Payload-Signatur, HMAC- oder Challenge-Prüfung** vor dem Dispatch sichtbar.

Die primäre Vertrauensgrenze ist damit offenbar:

```text
Aliyun MQTT/TLS
+ ProductKey
+ DeviceName
+ DeviceSecret
+ Topic-/Broker-Autorisierung
```

Das ist kein Nachweis, dass der Aliyun-Cloudpfad insgesamt unsicher ist; es bedeutet lediglich, dass der Dienst empfangene, vom MQTT-Layer akzeptierte OTA-Kommandos lokal nicht noch einmal kryptografisch authentifiziert.

### Credential-Relevanz

Die aktiven Aliyun-Werte liegen im Prozessspeicher, u. a.:

```text
_device_secret @ 0x9896C
_product_secret @ 0x989B0
_device_name @ 0x98A58
_product_key @ 0x98A98
```

Live bestätigt wurde:

- `_device_name` ist auf dem untersuchten Gerät identisch zur IMEI
- `_product_key` ist befüllt
- `_device_secret` ist mit einem 32-stelligen Secret befüllt
- `_product_secret` ist im laufenden Zustand leer

Secrets niemals automatisch in Support-Logs, Diagnose-ZIPs oder öffentliche Dokumentation schreiben.

## 6. Normaler Cloudkanal besitzt direkten UART/RS485-Bridge-Pfad

Der normale MQTT-Callback:

```text
aliMqtt_topic_get_msg_arrive() @ 0x1EED0
```

nimmt den Payload des Topics `/user/get` und ruft direkt:

```text
uart485_send_data_to_board(payload, length)
```

auf.

Damit kann die Herstellercloud über den normalen MQTT-Kanal rohe Binärtelegramme zum Mainboard senden. `phnixIot4G` bildet hier keine eigene semantische Modbus-Allowlist; die weitere Protokoll-/CRC-Prüfung liegt beim Mainboard bzw. in den nachgelagerten Pfaden.

Dieser Punkt ist für die Sicherheitsarchitektur wesentlich: Das LTE-Modul ist nicht nur Telemetrie-Uplink, sondern ein bidirektionaler Remote-Tunnel zum Mainboard.

## 7. DTU-Self-OTA: Download + MD5 + Binary-Austausch

Der LTE-Dienst kann auch **sich selbst** aktualisieren.

Aktiver Pfad:

```text
down_dtu_ota_url_handle()
 -> ota_dtu_set_ota_file_download_info()
 -> ota_download_dtu_otaFile()
 -> ota_check_dtu_otaFile_md5()
```

Die Cloud liefert mindestens:

```text
dtuSoftwareCode
dtuSoftwareVer
fileMD5
fileSize
otaFileDownloadAddr
```

Das Ziel ist:

```text
/data/phnixIot4G_OTA
```

Nach erfolgreichem Download wird der MD5-Wert geprüft. Bei Erfolg sind im aktiven Pfad Shell-Kommandos vorhanden:

```sh
chmod a+x /data/phnixIot4G_OTA
mv /data/phnixIot4G_OTA /data/phnixIot4G
killall -9 phnixIot4G
```

Der neue Prozess wird danach offensichtlich durch die System-/Serviceüberwachung erneut gestartet.

### Sicherheitsbewertung

MD5 liefert hier Integrität gegen zufällige Übertragungsfehler. Da der erwartete MD5-Wert zusammen mit URL/Metadaten über denselben autorisierten OTA-Steuerkanal geliefert wird, ist diese Prüfung allein **keine unabhängige Firmware-Authentizitätssignatur**.

Im analysierten PHNIX-Code wurde für den DTU-Self-OTA keine zusätzliche RSA/ECDSA-Firmware-Signaturprüfung gefunden. Die im ELF enthaltenen RSA/X509/SHA-Funktionen gehören zu großen Teilen zu TLS/Aliyun/mbedTLS und beweisen keine Firmware-Signaturprüfung.

## 8. Mainboard-OTA besitzt Cancel und Rollback als echte Remote-Funktionen

Zwei bisher leicht zu übersehende Remote-Aktionen sind explizit vorhanden:

```text
down_board_cancel_ota_handle()
down_board_ver_bcakroll_handle()
```

Cancel setzt mehrere Board-OTA-State-Felder zurück/um und setzt:

```text
board_ota_step = 7
```

Rollback setzt einen eigenen Rollback-Flag und:

```text
board_ota_step = 8
```

Damit sind Cancel und Rollback nicht nur lokale interne Zustände, sondern direkt über den Remote-Kommandodispatch erreichbar.

## 9. `Power-Reset-t` und `Active-Reset-t` sauber unterscheiden

Für GUI/Diagnose sollte daher gelten:

```text
Power-Reset-t (+0x28)
= Starts von phnixIot4G; nicht zuverlässig gleichbedeutend mit Stromausfällen

Active-Reset-t (+0x2C)
= komplette Linux/Modem-Reboots, die phnixIot4G selbst aktiv anfordert
```

Diese Unterscheidung wurde durch Live-Test bestätigt.

## 10. Weitere interessante DMS/QMI-Funktionen – vorhanden, aber offenbar dormant

Im Binary sind weitere vollständige Qualcomm-DMS-Funktionen vorhanden:

```text
get_imei()                  @ 0x20440
get_meid()                  @ 0x20558
get_mac_address_from_nv()   @ 0x20670
get_rev_id()                @ 0x207CC
dms_set_operating_mode()    @ 0x208BC
dms_get_operating_mode()    @ 0x20990
```

Insbesondere `get_rev_id()` ist interessant, weil darüber sehr wahrscheinlich eine Modem-/Baseband-Revisionskennung über QMI DMS gelesen werden kann.

Für diese Funktionen wurden im aktuellen `phnixIot4G`-Produktpfad keine direkten Aufrufer gefunden. Sie wirken wie eingebundene SIMCom/QMI-SDK-Helfer bzw. Demo-/Library-Code.

Daher gilt:

- Vorhandensein im ELF: statisch bestätigt
- Nutzung im regulären PHNIX-Betrieb: bisher **nicht** bestätigt
- nicht einfach als bereits gepflegten RAM-Cache behandeln

## 11. Dormanter Legacy-Updater `UpdateAPP()`

Ebenfalls vollständig vorhanden:

```text
UpdateAPP() @ 0x13BB4
```

Die Funktion führt nacheinander Shell-Kommandos aus, u. a.:

```sh
cp /data/media/helloworld_bak /data/helloworld
chmod a+x /data/helloworld
cp /data/media/helloworld_bak /cache/helloworld_bak
chmod a+x /cache/helloworld_bak
sync
```

Zwischen den Schritten liegen Sleeps/Debugausgaben.

Für `UpdateAPP()` wurde im aktuellen Binary kein regulärer Aufrufer gefunden. Dieser Pfad ist deshalb als **dormanter Legacy-/SIMCom-Demo-Code** zu behandeln und nicht mit dem aktiven PHNIX-DTU-OTA zu verwechseln.

## 12. Watchdog-/GPIO-Verhalten

Unabhängig vom Cloud-Watchdog existiert:

```text
Reset_All_DOG() @ 0xB400
```

mit:

```text
GPIO50 High
sleep(2)
GPIO50 Low
```

Der aktive LED-/Signalpfad ruft über `AT_GetCSQ()` diesen GPIO-Puls wiederholt auf. Die genaue elektrische Bedeutung von GPIO50 ist ohne Schaltplan weiterhin nicht abschließend bewiesen; der Name und der periodische Pfad sprechen aber stark für eine externe Watchdog-/Dog-Funktion.

Davon getrennt ist der 30-Minuten-Aliyun-Watchdog rein softwareseitig und endet in `system("reboot")`.

## 13. Weitere Live-lesbare Runtime-Informationen

Mit read-only Zugriff auf `/proc/<PID>/mem` wurden auf realer Hardware bereits bestätigt:

```text
Mainboard C544-Cache:
0x935E1 Softwarecode
0x935EA Softwareversion
0x935EF Hardwarecode
0x935F8 Hardwareversion

SIM/Modem:
0x9365C ICCID
0x93674 IMSI
0x93688 IMEI
0x98AB0 SIM-Status

Netz:
0x981B4 Serving-System
0x98022 MCC
0x98024 MNC
0x9816C Cell-ID
0x97FE8 Roaming-valid
0x97FEC Roaming-indicator
0x98026 Netzbeschreibung

Aliyun:
0x94EB4 MQTT-client pointer
pclient + 0x4DC = MQTT client_state
State 2 = connected
```

Live wurden u. a. LTE (`radio_if = 8`), registriert/CS+PS attached, Roaming aktiv, gültiges Serving-PLMN sowie MQTT-State 2 bestätigt.

## 14. Neue Schlussfolgerungen

1. `Power-Reset-t` ist in diesem Build praktisch ein **Dienststartzähler** und darf nicht als reiner Stromausfallzähler interpretiert werden.
2. `Active-Reset-t` zählt aktiv vom PHNIX-Dienst ausgelöste komplette Reboots.
3. Ein 30-Minuten-Ausfall der Aliyun-Verbindung löst selbständig einen Linux-Reboot aus.
4. Die Cloud kann explizit einen Remote-Reboot mit Code 114 auslösen.
5. Der OTA-Command-Dispatcher enthält neun feste Befehle einschließlich Cancel und Rollback.
6. Der normale MQTT-Kanal ist ein bidirektionaler Raw-Bridge-Pfad zum Mainboard-UART.
7. DTU-Self-OTA ersetzt das laufende `phnixIot4G` nach Download und MD5-Prüfung direkt und beendet den alten Prozess mit `killall -9`.
8. Im PHNIX-Anwendungscode ist keine zweite kryptografische Payload-Authentifizierung der Remote-Kommandos sichtbar; die Hauptvertrauensgrenze ist Aliyun MQTT/TLS + Gerätecredentials.
9. `get_rev_id()`, Operating-Mode- und NV-MAC-QMI-Funktionen sind im Binary vorhanden, scheinen aber im regulären Produktpfad dormant zu sein.
10. `UpdateAPP()` ist alter SIMCom-/Demo-Code und nicht der aktive PHNIX-Updater.
