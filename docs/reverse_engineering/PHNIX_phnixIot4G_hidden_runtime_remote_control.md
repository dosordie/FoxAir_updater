# PHNIX `phnixIot4G` – versteckte Runtime-, Reset-, Remote-Control- und Diagnosepfade

Stand: 2026-08-25

Grundlage: statische Analyse des ungestrippten ARM-ELF `phnixIot4G` (Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`) plus Live-Verifikation auf einem realen FoxAir/PHNIX-LTE-Modem per read-only ADB und `/proc/<pid>/mem`.

Diese Datei ergänzt insbesondere:

- `PHNIX_phnixIot4G_diagnostics_statistics_debug.md`
- `PHNIX_phnixIot4G_non_ota_architecture.md`
- `PHNIX_phnixIot4G_C544_softcode_resume.md`
- `PHNIX_phnixIot4G_normal_mqtt_bridge.md`

Schwerpunkt sind Funktionen, die für eine lokale Modem-Diagnose und für das Verständnis der Hersteller-Remote-Steuerung wichtig sind.

---

## 1. Feste RAM-Diagnose ohne RS485-Zugriff

Der analysierte Build ist ein 32-Bit ARM `EXEC`/non-PIE. Dadurch sind feste globale Adressen in diesem Build direkt über `/proc/<PID>/mem` lesbar.

Beispiel:

```sh
PID=$(pidof phnixIot4G)
dd if=/proc/$PID/mem bs=1 skip=$((ADDR)) count=LEN 2>/dev/null
```

Wichtig: Diese Methode ist read-only und erzeugt keine zusätzlichen Telegramme auf `/dev/ttyHSL2`.

### Mainboard-Firmwarecache aus C544

`otaDeviceInfo @ 0x933AC`

| Adresse | Feld | Live-Beispiel |
|---:|---|---|
| `0x935E1` | Softwarecode, 9 Byte | `82400644` |
| `0x935EA` | Softwareversion, 5 Byte | `V3.3` |
| `0x935EF` | Hardwarecode, 9 Byte | `82300314` |
| `0x935F8` | Hardwareversion, 5 Byte | `0000` |

Diese Werte stammen aus dem vom Mainboard gesendeten C544-Serviceframe und werden von `board_softcode_ver_handle()` stabil im RAM gehalten.

### SIM-/Aliyun-Identität

| Adresse | Feld | Live verifiziert |
|---:|---|---|
| `0x9365C` | ICCID | `89330112407972705790` |
| `0x93674` | IMSI | `208012402223359` |
| `0x93688` | IMEI | `860147058259753` |
| `0x98A58` | Aliyun DeviceName | identisch mit IMEI |
| `0x98A98` | Aliyun ProductKey | `a5cVutQfC8x` |
| `0x9896C` | Aliyun DeviceSecret | 32 ASCII-Zeichen, live befüllt |
| `0x989B0` | ProductSecret | im untersuchten Lauf leer |

Der ProductSecret wird offenbar im normalen laufenden Zustand nicht benötigt bzw. nicht dauerhaft im RAM gehalten, während der individuelle DeviceSecret aktiv befüllt ist.

Hinweis für Diagnose-/Support-Ausgaben: DeviceSecret niemals ungefragt loggen oder in Support-ZIPs exportieren; in der GUI standardmäßig maskieren.

---

## 2. SIM-Statusstruktur

`simStatus @ 0x98AB0`, 20 Byte.

Rekonstruierter Aufbau:

```c
struct SimCard_Status_type {
    uint32_t card_status;   // +0x00
    uint32_t app_type;      // +0x04
    uint32_t app_state;     // +0x08
    uint32_t pin_state_0;   // +0x0C
    uint32_t pin_state_1;   // +0x10
};
```

Live:

```text
card_status = 1
app_type    = 2
app_state   = 7
```

Sicher bekannte Werte:

```text
card_status:
0 = absent
1 = present
2 = error
3 = unknown

app_state:
0 = unknown
1 = detected
2 = PIN required
3 = PUK required
4 = personalization required
5 = PIN permanently blocked
6 = illegal
7 = READY
```

Damit kann ein lokaler Updater den echten SIM-Zustand anzeigen.

---

## 3. Serving-System / aktueller Mobilfunkzustand

`serving_system @ 0x981B4`

Die Getter lesen direkt:

```text
+0x00 Registration State
+0x04 CS Attach State
+0x08 PS Attach State
+0x0C Selected Network
+0x10 Radio Interface Count
+0x14 Radio Interface Array
```

Live:

```text
Registration State = 1
CS Attach State    = 1
PS Attach State    = 1
Selected Network   = 2
Radio count        = 1
Radio IF[0]        = 8
```

`Radio IF = 8` entspricht im eingebetteten QMI-Enum eindeutig `NAS_RADIO_IF_LTE_V01`, also LTE.

### Aktuelles PLMN

Im QMI-Serving-System-Response:

```text
0x98020 current_plmn_valid
0x98022 MCC uint16
0x98024 MNC uint16
0x98026 network_description[]
```

Live:

```text
MCC/MNC             = 262 / 01
network_description = TDG
```

### Roaming

```text
0x97FE8 roaming_indicator_valid
0x97FEC roaming_indicator
```

Live:

```text
valid     = 1
indicator = 0
```

QMI-Enum:

```text
0 = ROAMING ON
1 = ROAMING OFF
2 = ROAMING FLASHING
```

Damit ist der Roamingstatus direkt vom Modem lesbar und muss nicht nur aus IMSI vs. Serving-PLMN abgeleitet werden.

### Cell-ID / LAC

```text
0x98168 LAC uint16
0x9816C CELL_ID uint32
```

Live:

```text
LAC     = 0xFFFE  -> ungültig/Sentinel
CELL_ID = 44867840
```

Für LTE sollte `0xFFFE` nicht als numerischer LAC/TAC angezeigt werden, sondern als „nicht verfügbar“.

---

## 4. Mobilfunk-IP und Routing

Der Dienst selbst benutzt `/proc/net/route` zur Ermittlung des Default-Interfaces. Auf dem realen Modem war live:

```text
Interface: rmnet_data0
IP:        10.236.250.103/28
Gateway:   10.236.250.104
```

Dies ist eine private PDP-/Mobilfunk-IP, keine öffentliche Internet-IP.

Für eine lokale Diagnose ist ein read-only `ip addr` bzw. `/proc/net/route` sicherer und sinnvoller als ein eigener Cache im Prozess.

---

## 5. MQTT-Connected-State – echter SDK-State

`MQTT_init_signal @ 0x936A8` ist nur ein diagnostischer Initialisierungszustand.

Der belastbare Connected-State liegt im Aliyun-MQTT-Client:

```text
pclient @ 0x94EB4
client_state = *(pclient + 0x4DC)
```

Der SDK-Code behandelt `client_state == 2` als normalen/verbundenen Zustand.

Live:

```text
pclient = 3014729296
state   = 2
```

Damit kann die Modem-Info-Seite „MQTT / Cloud: verbunden“ aus dem echten Client-State ableiten.

---

## 6. Persistente Statistikdatei

Persistenz:

```text
/data/phnixIot_device_statisic
```

RAM-Struktur:

```text
statistic_para @ 0x91B60
Größe 128 Byte
```

`static_read_data()` liest die 128 Byte ein; `static_write_data()` schreibt jeweils die komplette 128-Byte-Struktur zurück.

Wichtige Felder:

| Offset | Herstellername | Bedeutung |
|---:|---|---|
| `0x00` | Strongest Net csq | stärkster CSQ |
| `0x04` | Weakest Net csq | schwächster CSQ |
| `0x08` | Online time | gesamte Onlinezeit |
| `0x0C` | Device-change-t | Device-Wechsel |
| `0x10` | On-Off-line-t | Online/Offline-Wechsel |
| `0x14` | Work time | gesamte Betriebszeit |
| `0x18` | Up-D-t | Uplink-/Upload-Ereignisse |
| `0x1C` | Down-D-t | Downlink-/Download-Ereignisse |
| `0x20` | Ota-dtu-t | DTU-OTA-Zähler |
| `0x24` | Ota-dev-t | Mainboard-/Device-OTA-Zähler |
| `0x28` | Power-Reset-t | Power-Reset-Zähler |
| `0x2C` | Active-Reset-t | vom Dienst aktiv ausgelöste vollständige Reboots |
| `0x38` | Api-t | API-Zähler |
| `0x3C` | Average Net csq | gespeicherter Durchschnitt |
| `0x40` | Day-Up-D-t | Tageszähler |
| `0x44` | Current Work time | Laufzeit seit Prozessstart |
| `0x48` | Current Online time | Onlinezeit seit Prozessstart |
| `0x4C` | Current Net csq | aktueller CSQ |
| `0x58` | interne CSQ-Summe | für Durchschnitt |
| `0x5C` | interne CSQ-Samples | für Durchschnitt |

### CSQ

Für die UI sollte die Einheit ausdrücklich `CSQ` heißen, nicht Prozent.

Näherungsweise:

```text
RSSI [dBm] ≈ -113 + 2 * CSQ
```

`CSQ 19` entspricht ungefähr `-75 dBm`.

`CSQ 0` wird vom Dienst selbst als ungültig/problematisch behandelt und sollte nicht als echtes Minimum interpretiert werden.

### Up-/Download-Zähler

Die Zähler sind keine Byte-/Trafficmengen. Sie werden bei Kommunikationsereignissen inkrementiert.

Live wurde bei ~409 Tagen Betriebszeit ein Uplink-Zähler um 589000 beobachtet, was nahezu exakt einem regulären Uplink pro Minute entspricht. Der Downlink-Zähler war mit ~1600 wesentlich kleiner.

Für die GUI sind daher Bezeichnungen wie `Uplink-Telegramme` / `Downlink-Telegramme` sinnvoller als „Datenmenge“.

---

## 7. `Active-Reset-t` vollständig geklärt

Ein normaler `kill phnixIot4G` erhöht diesen Counter nicht. Live wurde dies bestätigt.

Es gibt mindestens zwei echte Inkrementierungsstellen.

### 7.1 Cloud/MQTT länger als 30 Minuten offline

`TimerHandler()` läuft im Sekundentakt und prüft `get_ALI_Connt_State()`.

Bei bestehender Verbindung:

```text
Online time++
Current Online time++
cloud_offline_seconds = 0
Error-Bit 10 wird gelöscht
```

Bei nicht bestehender Verbindung:

```text
Error-Bit 10 wird gesetzt
Kommunikations-LED aus
cloud_offline_seconds++
```

Sobald:

```text
cloud_offline_seconds > 0x708 = 1800 Sekunden
```

passiert:

```text
cloud_offline_seconds = 0
statistic_para.Active-Reset-t++
static_write_data()
reboot
```

Damit hat der Dienst einen eigenen **30-Minuten-Cloud-Watchdog**, der das gesamte Linux-Modem rebootet.

### 7.2 Remote-RESET über MQTT

`device_reset_handle() @ 0x1986C`

Der Handler sendet zunächst:

```json
{"cmd":"RESET","code":"0114","param":{"result":"1"}}
```

über den OTA-MQTT-Kanal zurück.

Nur wenn dieser Publish erfolgreich ist:

```text
Active-Reset-t++
static_write_data()
sleep(5)
reboot
```

Damit ist die beste Bezeichnung für `Active-Reset-t`:

> Vom LTE-Dienst aktiv ausgelöste vollständige Modem/Linux-Reboots.

Nicht umfasst sind normale Prozess-Kills/Restarts.

---

## 8. Weitere Timer-/Watchdoglogik im `TimerHandler()`

Neben dem 30-Minuten-Cloud-Reboot existieren mehrere interne Kommunikations-Timer.

Auffällig:

```text
interner Kommunikationscounter +0x18 im app/runtime-Block
```

Nach >300 Sekunden wird periodisch `Check485Statue()` aufgerufen.

### `Check485Statue()`

`Check485Statue @ 0x156B4`

Wenn ein interner RX-/Statusmarker bei `0x930DC` Null ist, sendet der Dienst den festen 8-Byte-Request aus `.rodata` über `uart485_send_data_to_board()`.

Damit führt das LTE-Modul selbst aktiv einen RS485/Mainboard-Healthcheck aus.

Weitere Schwellwerte im Sekundentimer:

```text
>420 s -> Error-Bit 5 kann gesetzt werden
>420 s -> Error-Bit 6 kann gesetzt werden
>420 s -> Error-Bit 12 kann gesetzt werden
```

Die genaue Semantik der drei jeweils verwendeten Runtime-Counter muss noch vollständig benannt werden; statisch sicher ist, dass der Dienst mehrere unabhängige Kommunikations-/Subsystem-Timeouts im Bereich sieben Minuten überwacht.

---

## 9. Remote-Command-Dispatcher über OTA-MQTT

Callback:

```text
aliMqtt_topic_ota_get_msg_arrive @ 0x1ED98
```

Der MQTT-Payload wird in einen lokalen/globalen Buffer kopiert und an:

```text
ota_code_handle @ 0x19958
```

übergeben.

`ota_code_handle()` parsed JSON, liest das Feld `code` und vergleicht es mit einer festen 9-Einträge-Tabelle:

```text
ota_hanldle @ 0x91C20
```

Bestätigte Handler:

```text
ota_dtu_set_ota_info
down_dtu_ota_url_handle
down_board_ota_url_handle
down_check_dtu_ver_handle
down_check_board_ver_handle
down_board_cancel_ota_handle
down_board_ver_bcakroll_handle
down_dtu_cancel_ota_handle
device_reset_handle
```

Damit kann die Herstellercloud mindestens:

- DTU-/Modem-OTA anstoßen
- Mainboard-OTA anstoßen
- DTU-Version abfragen
- Mainboard-Version abfragen
- Mainboard-OTA abbrechen
- DTU-OTA abbrechen
- Mainboard-Rollback anfordern
- das komplette LTE-Modem rebooten

Der Dispatcher selbst enthält keine zusätzlich sichtbare Payload-Signaturprüfung. Die Zugriffssicherheit liegt davor im authentisierten Aliyun-MQTT/TLS-/Credential-Pfad. Das bedeutet nicht, dass der Broker frei zugänglich ist; lediglich im PHNIX-Command-Dispatcher gibt es keine zweite kryptographische Autorisierung pro Kommando.

---

## 10. DTU-/Modem-Selbstupdate

DTU-OTA lädt die neue Datei nach:

```text
/data/phnixIot4G_OTA
```

Der Download erfolgt mit libcurl.

Anschließend wird die Datei anhand der von der Cloud gelieferten MD5-Prüfsumme geprüft.

Nach erfolgreicher Prüfung folgt sinngemäß:

```sh
chmod a+x /data/phnixIot4G_OTA
mv /data/phnixIot4G_OTA /data/phnixIot4G
killall -9 phnixIot4G
```

Der laufende Prozess ersetzt also sein eigenes Binary und beendet sich danach hart. Ein externer Supervisor/Init-Mechanismus muss den Dienst anschließend erneut starten.

Sicherheitsrelevant: Die im PHNIX-OTA-Pfad sichtbare Integritätsprüfung ist MD5 gegen den von der Cloud gelieferten Wert. Eine zusätzliche eigenständige digitale Signaturprüfung des DTU-Binaries wurde in diesem Pfad bisher nicht gefunden.

---

## 11. Mainboard-OTA-Dateien und persistenter Zustand

Mainboard-Firmware:

```text
/cache/phnixIot_device_OTA
```

OTA-State/Resume:

```text
/data/phnixIot_device_OTA_INFO
```

Beim Neuaufsetzen eines Board-Downloads existieren u. a.:

```sh
rm -f /cache/phnixIot_device_OTA
true > /data/phnixIot_device_OTA_INFO
```

Das Board-OTA besitzt getrennte Cancel-, Rollback-, Download-, MD5- und Resume-/State-Machine-Pfade.

---

## 12. APN-Auswahl

Der aktive Startup-Pfad ermittelt per `AT+CGMM` den Modemtyp und setzt anschließend PDP-Kontexte.

Im Binary vorhandene APNs:

```text
orange.m2m.spec
acell.90164
cuiot
leer
```

Für `ModeType == 2` wird `orange.m2m.spec` gesetzt. Live wurde auf dem realen Modem genau dieser APN bestätigt.

Für andere Modemtypen wird teilweise zusätzlich die ICCID ausgewertet.

---

## 13. Modemtyp

Im Runtime-Block:

```text
app @ 0x988FC
ModeType = app + 0x16 = 0x98912
```

Live:

```text
ModeType = 2
```

Statische Zuordnung:

```text
1 = SIMCOM_SIM7600SA-H
2 = SIMCOM_SIM7600E-H
```

Damit ist das reale Modul als SIMCom SIM7600E-H identifiziert.

---

## 14. Debug-Port und Hardwarezugriffe

Der Dienst initialisiert:

```text
/dev/ttyGS0 @ 115200 8N1
/dev/ttyHSL2 für Mainboard-RS485
```

`DebugTrace()` schreibt Debugmeldungen sowohl auf die normale Prozessausgabe als auch auf `/dev/ttyGS0`.

GPIO-/Power-Funktionen enthalten direkte Shellzugriffe wie:

```sh
echo ... > /sys/class/gpio/...
echo off > /sys/power/autosleep
echo on > /sys/class/tty/ttyHSL1/device/power/control
```

`Reset_All_DOG()` pulst GPIO50 und wird indirekt regelmäßig über den Signal-/LED-Thread bedient.

---

## 15. Historischer/Testcode

Im Produktbinary liegen weiterhin Pfade wie:

```sh
cp /data/media/helloworld_bak /data/helloworld
chmod a+x /data/helloworld
cp /data/media/helloworld_bak /cache/helloworld_bak
chmod a+x /cache/helloworld_bak
```

Das bestätigt erneut, dass das Produktbinary aus einem größeren SIMCom-Demo-/Daemon-Codebestand hervorgegangen ist und ungenutzter bzw. historischer Code erhalten blieb.

---

## 16. Sicherheitsbewertung des kleinen Dienstes

`phnixIot4G` ist funktional weit mehr als ein Modbus-Tunnel. Der Prozess besitzt praktisch Root-/Systemdienst-Charakter und kann:

- GPIOs direkt schalten
- Linux-Power-Management verändern
- das gesamte System rebooten
- sich selbst per Cloud aktualisieren und ersetzen
- Mainboard-Firmware herunterladen und übertragen
- Mainboard-OTA abbrechen oder Rollback anfordern
- Device-/Cloud-Credentials verwalten
- MQTT-Remote-Kommandos ausführen
- persistent Statistik-/OTA-Zustände schreiben
- Mainboard-RS485 aktiv überwachen
- Diagnose-/Fehlerlogs an PHNIX hochladen

Die wesentliche Vertrauensgrenze liegt damit an der Cloud-/MQTT-Authentisierung und an den lokal gespeicherten Aliyun-Credentials.

Für eigene Tools gilt daher:

1. `/proc/<PID>/mem` nur read-only verwenden.
2. DeviceSecret standardmäßig maskieren und niemals automatisch exportieren.
3. `/dev/ttyHSL2` nicht parallel als zweiten Reader öffnen.
4. Keine unbekannten OTA-/Remote-Kommandos experimentell senden, solange ihr Seiteneffekt nicht statisch geklärt ist.
5. Änderungen an `/data/phnixIot_device_statisic` nur bei gestopptem Dienst durchführen, da `static_write_data()` die komplette 128-Byte-RAM-Struktur zurückschreibt.

---

## 17. Empfohlene Felder für eine lokale „Modem Info“-Seite

### Mainboard

```text
Firmware
Softwarecode
Hardwarecode
Hardwareversion
```

### Modem / SIM

```text
SIMCom-Modell
IMEI
ICCID
IMSI
SIM present/READY
Aliyun DeviceName
ProductKey
DeviceSecret nur maskiert/auf Wunsch sichtbar
```

### Mobilfunk

```text
LTE/RAT
Registration
CS Attach
PS Attach
MCC/MNC
Netzbeschreibung
Roaming
Cell-ID
CSQ aktuell / Mittel / Maximum
```

### Netzwerk

```text
rmnet_data0
PDP-IP
Prefix
Gateway
```

### Cloud

```text
MQTT echter SDK-State
MQTT_init_signal nur diagnostisch
ErrorStatue
```

### Statistik

```text
Gesamtbetriebszeit
Gesamt-Onlinezeit
aktuelle Laufzeit
aktuelle Onlinezeit
Uplink-/Downlink-Telegramme
DTU-OTA-Zähler
Mainboard-OTA-Zähler
Power-Reset-t
Active-Reset-t = vom Dienst aktiv ausgelöste vollständige Reboots
```

---

## 18. Noch offene Punkte

Noch lohnend für weitere Analyse:

- exakte Semantik von `Power-Reset-t`
- vollständige Zuordnung aller ErrorStatue-Bits, insbesondere 8, 10, 12 und weiterer höherer Bits
- exakte Namen der mehreren 420-s-Kommunikationswatchdogs
- tatsächliche SIMCom/Baseband-Firmwareversion
- LTE-RSRP/RSRQ/SINR, sofern ein aktiver QMI-Pfad die Werte im RAM hält
- Supervisor/Init-Mechanismus, der `phnixIot4G` nach `killall -9` wieder startet
- genaue Sicherheitsparameter des aktiven Aliyun-MQTT-TLS-Pfads und Abgrenzung zum alten AT-MQTT-Port-1883-Code
