# PHNIX `phnixIot4G` – Debug, Fehler, Statistik und Signal-Thread

Stand: 2026-08-25

Grundlage: weitere statische Analyse des ungestrippten ARM-ELF `phnixIot4G` (Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`). Diese Datei vertieft die in `PHNIX_phnixIot4G_non_ota_architecture.md` identifizierten Nicht-OTA-Bereiche.

## 1. Debugschnittstelle `/dev/ttyGS0` ist real und aktiv initialisiert

`init_uart_debug()`:

```text
0x13C88
```

öffnet:

```text
/dev/ttyGS0
```

mit Flags `0x802` und ruft anschließend `set_opt()` mit:

```text
Baudrate 115200
Datenbits 8
Parity 'N'
Stopbits 1
```

also **115200 8N1**.

Der Debug-FD liegt global bei:

```text
0x920D8
```

`init_uart_debug()` wird beim regulären Programmstart aufgerufen (`main`-Startup-Pfad um `0xB440`).

### Debugausgabe

```text
Debugh()                  @ 0x13D70
DebugHex()                @ 0x13DA8
DebugTrace()              @ 0x13E20
DebugTrace_no_file_info() @ 0x13F34
```

`DebugTrace()` formatiert zunächst in einen lokalen Puffer, schreibt die Meldung auf die normale Prozessausgabe und zusätzlich mit `write()` auf den globalen `/dev/ttyGS0`-FD.

Das Präfix lautet:

```text
LOG_INFO---------- %s:%u %s:%s:\t
```

und der Build enthält:

```text
log.c
Nov 10 2022
17:26:01
```

**Praktischer Nutzen:** Wenn `/dev/ttyGS0` auf dem realen Modem erreichbar/gebunden ist, ist dies wahrscheinlich die wertvollste lokale Diagnosequelle, weil die Originalsoftware dort ihre internen Debugmeldungen live ausgibt.

Read-only Prüfung auf dem Modem:

```sh
ls -l /dev/ttyGS0
ps | grep '[p]hnixIot4G'
```

Wenn der Port auf USB nach außen geführt wird, kann passiv mit 115200 8N1 mitgelesen werden.

---

## 2. Wichtige Korrektur zu GPIO 50 / `Reset_All_DOG()`

`Reset_All_DOG()` selbst liegt bei:

```text
0xB400
```

und pulst GPIO 50:

```c
EAT_WriteGpio(50, 1);
sleep(2);
EAT_WriteGpio(50, 0);
```

Die OTA-State-Machine ruft diese Funktion nicht direkt auf. **Trotzdem wird GPIO 50 während eines langen Mainboard-OTA sehr wahrscheinlich weiter periodisch gepulst**, weil ein parallel laufender Signal-/LED-Thread aktiv bleibt.

### Indirekter Pfad

`led_thread_handle()`:

```text
0x17F8C
```

ruft in seiner Dauerschleife immer wieder:

```text
AT_GetCSQ() @ 0xC500
```

auf.

`AT_GetCSQ()` ruft in seiner Retryschleife unmittelbar:

```text
Reset_All_DOG() @ 0xB400
```

auf.

Damit gilt:

```text
led_thread_handle
 -> AT_GetCSQ
 -> Reset_All_DOG
 -> GPIO 50 High
 -> sleep(2)
 -> GPIO 50 Low
```

Der LED-Thread läuft parallel zum Board-OTA weiter.

**Folgerung:** Die frühere Aussage „GPIO 50 wird während eines zwölfminütigen C5A8-Transfers nicht bedient“ ist zu präzisieren: Der OTA-Thread bedient GPIO50 nicht, der unabhängig weiterlaufende Signalthread tut es aber indirekt über `AT_GetCSQ()`.

Die elektrische Bedeutung von GPIO50 bleibt ohne Schaltplan/RootFS-/Hardwarebeobachtung offen; für einen echten Transfer ist aber deutlich weniger wahrscheinlich, dass ein reiner „fehlender DOG-Feed während OTA“ nach einigen Minuten zum Reset führt.

---

## 3. Signal-LED-Schwellen

`led_thread_handle()` wertet den von `AT_GetCSQ()` gelieferten Wert aus.

Bestätigte Schwellwerte:

```text
CSQ 20..31  -> high LED an
CSQ 15..31  -> middle LED an
CSQ 1..31   -> weak LED an
CSQ <=0 oder >31 -> entsprechende Signal-LEDs aus
```

Zusätzlich wird bei gültigem CSQ `1..31` Error-Bit 4 gelöscht; bei ungültigem Wert wird Error-Bit 4 gesetzt.

Der Thread besitzt einen 16-Bit-Zähler und aktualisiert ungefähr alle 50 Schleifendurchläufe mehrere Signalstatistiken.

---

## 4. `statistic_para` – große Teile des 128-Byte-Formats jetzt benannt

Persistenz:

```text
/data/phnixIot_device_statisic
statistic_para @ 0x91B60
Größe 128 Byte
```

`Upload_bord_log()` baut aus den Feldern explizit benannte Statistikwerte. Dadurch lassen sich zahlreiche Offsets sicher zuordnen:

| Offset | Name im Herstellerlog | Bedeutung |
|---:|---|---|
| `0x00` | `Strongest Net csq` | stärkster beobachteter CSQ |
| `0x04` | `Weakest Net csq` | schwächster beobachteter CSQ |
| `0x08` | `Online time` | Online-Zeit |
| `0x0C` | `Device-change-t` | Device-Wechselzähler |
| `0x10` | `On-Off-line-t` | Online/Offline-Wechselzähler |
| `0x14` | `Work time` | Betriebszeit |
| `0x18` | `Up-D-t` | Upload-Zähler |
| `0x1C` | `Down-D-t` | Download-Zähler |
| `0x20` | `Ota-dtu-t` | DTU-OTA-Zähler |
| `0x24` | `Ota-dev-t` | Mainboard-/Device-OTA-Zähler |
| `0x28` | `Power-Reset-t` | Power-Reset-Zähler |
| `0x2C` | `Active-Reset-t` | aktiver/Software-Reset-Zähler |
| `0x38` | `Api-t` | API-Zähler |
| `0x3C` | `Average Net csq` | berechneter Durchschnitts-CSQ |
| `0x40` | `Day-Up-D-t` | Tages-Upload/Download-Zähler |
| `0x44` | `Current Work time` | aktuelle Betriebszeit |
| `0x48` | `Current Online time` | aktuelle Online-Zeit |
| `0x4C` | `Current Net csq` | letzter/aktueller CSQ |

Weitere Felder ab `0x50` werden für Logupload-/Tageswechsel-/Timingzustände verwendet und sind noch nicht alle semantisch benannt.

### Durchschnitts-CSQ

Der Signalthread akkumuliert:

```text
statistic_para+0x58 += current_csq
statistic_para+0x5C += 1
```

Vor dem Logupload wird daraus:

```text
Average Net csq = (+0x58) / (+0x5C)
```

berechnet und nach `+0x3C` geschrieben.

### Startverhalten

`static_read_data(1)` liest 128 Byte und setzt beim normalen Prozessstart mehrere „current/day/runtime“-Felder wieder auf 0, während Langzeitzähler und Min/Max-Werte erhalten bleiben.

**Praktischer Nutzen:** `/data/phnixIot_device_statisic` kann read-only dekodiert werden und liefert interne Langzeitdaten, die Warmlink nicht unbedingt anzeigt.

---

## 5. Automatischer Statistik-/Logupload

`TimerHandler()` läuft im Sekundentakt und verändert zahlreiche `statistic_para`-Felder.

Unter anderem:

```text
Work time (+0x14) wächst fortlaufend
Current Work time (+0x44) wächst fortlaufend
bei aktivem Aliyun-Link wachsen Online time (+0x08) und Current Online time (+0x48)
```

`Check_upload_log() @ 0x11748` berechnet einen Zeit-/Tagesindex und kann bei Wechseln folgende Felder setzen:

```text
+0x60
+0x64
+0x54
```

Danach ruft `TimerHandler()` abhängig von diesen Zuständen `Upload_bord_log()` auf.

Der Dienst besitzt also eine eigenständige periodische Hersteller-Telemetrie/Diagnosestatistik zusätzlich zum normalen Warmlink-Datenstrom.

---

## 6. Fehlerbitmap `ErrorStatue`

Global:

```text
ErrorStatue @ 0x93124  // 32 Bit Bitmap
ErrorTag    @ 0x9312B
```

Setzen/Löschen erfolgt bitweise:

```c
set_Error_Flag(n):   ErrorStatue |=  (1U << n)
Clear_Error_Flag(n): ErrorStatue &= ~(1U << n)
```

`Get_ErrorStatue()` liefert das komplette Bitmap.

### Auffälliger Bug in `Get_Error_Flag()`

`Get_Error_Flag(n) @ 0x178F0` verwendet im analysierten Build:

```c
(1U << n) | ErrorStatue
```

statt des erwarteten:

```c
(1U << n) & ErrorStatue
```

und prüft anschließend nur, ob das Ergebnis >0 ist.

Für normale Bitnummern ergibt die Funktion dadurch praktisch immer `1`.

Im bisher untersuchten Kontrollfluss wurde jedoch kein direkter Aufrufer dieser Funktion gefunden; der Bug scheint daher im aktuellen Build weitgehend toter/ungenutzter Altcode zu sein.

---

## 7. Hersteller-Fehlertexte

`Upload_bord_log()` baut Fehlerarrays anhand einer Bitmap auf. Sicher sichtbare Texte sind:

```text
bit 0 -> 485 connected error
bit 1 -> Address error
bit 3 -> No PK
bit 4 -> No Three-Element-mqtt
bit 5 -> Cloud connected error
bit 6 -> WF_double_error
bit 7 -> Crc error
```

Bit 2 wird in diesem konkreten Fehlerstring-Block übersprungen; andere höhere Error-Bits werden im Programm ebenfalls gesetzt und scheinen für interne LED-/Subsystemzustände benutzt zu werden.

Beispiele direkter Setter im Gesamtprogramm:

```text
Bit 4  -> ungültiger CSQ / Signalproblem
Bit 8  -> UART485-Initialisierungs-/Startproblem
Bit 10 -> Cloud-/Laufzeitpfade
```

Die vollständige Zuordnung aller 32 Bits bleibt noch offen, aber der Hersteller-Logblock 0..7 ist weitgehend rekonstruiert.

---

## 8. Fehler-LED codiert Fehlerbits als Blinkanzahl

`ChangeBlinkTime() @ 0x17960` scannt Error-Bits und setzt abhängig vom gesetzten Bit einen Blinkwert.

Für die unteren Fehlerindizes werden u. a. folgende Werte gewählt:

```text
Error 1 -> BlinkTime 2
Error 2 -> BlinkTime 4
Error 3 -> BlinkTime 6
Error 4 -> BlinkTime 8
Error 5 -> BlinkTime 10
Error 6 -> BlinkTime 10
Error 8 -> BlinkTime 12
Error 9 -> BlinkTime 14
Error 10 -> BlinkTime 16
```

`ChangeErrorLedStatue()` zählt anschließend Blink-/Pause-Zustände herunter und schaltet GPIO 76.

Damit ist die Fehler-LED keine einfache An/Aus-Anzeige, sondern kodiert den aktiven Fehlerzustand über Blinkfolgen.

---

## 9. GPIOs der LEDs

Aus dem LED-Pfad ist mindestens GPIO 76 eindeutig als Fehler-LED-Ausgang sichtbar:

```text
EAT_WriteGpio(76, 1/0)
```

Signal- und Kommunikations-LEDs besitzen getrennte Wrapper (`led_high_*`, `led_middle_*`, `led_weak_*`, `led_communication_*`); deren konkrete GPIO-Nummern können bei Bedarf separat aufgelöst werden.

---

## 10. Praktisch nächste Tests am realen LTE-Modem

Ohne irgendeine Änderung am Gerät sind besonders wertvoll:

### Debug-Port prüfen

```sh
ls -l /dev/ttyGS0
```

und passiv beobachten, ob auf der USB-Gadget-Serial-Schnittstelle 115200-8N1 Debugmeldungen erscheinen.

### Statistik sichern

```sh
ls -l /data/phnixIot_device_statisic
cp /data/phnixIot_device_statisic /cache/phnixIot_device_statisic.copy
```

Noch konservativer per ADB direkt vom Host:

```sh
adb pull /data/phnixIot_device_statisic .
```

### GPIO50 nur passiv beobachten

Keine GPIO-Schreibtests nötig. Für die DOG-Frage genügt zunächst zu beobachten, ob die parallel laufende Originalsoftware während längerer Laufzeit/Offline-Phasen stabil bleibt; der statische Pfad zeigt bereits den periodischen `AT_GetCSQ -> Reset_All_DOG`-Aufruf.

---

## 11. Wichtigste neue Schlussfolgerungen

1. `/dev/ttyGS0` ist nicht nur ein zufälliger String: der Port wird beim normalen Start als **115200 8N1 Debug-UART** geöffnet.
2. `DebugTrace()` schreibt sowohl auf normale Prozessausgabe als auch auf diesen Debug-FD.
3. GPIO50 wird während Mainboard-OTA indirekt durch den weiterlaufenden Signalthread bedient; die DOG-Risikoabschätzung muss entsprechend korrigiert werden.
4. `phnixIot_device_statisic` enthält viele klar benannte Hersteller-Langzeitmetriken und ist eine neue wertvolle Diagnosequelle.
5. Der Dienst misst Signal-Min/Max/Mittelwert selbst und speichert sie persistent.
6. Die Fehler-LED codiert interne Error-Bits als Blinkmuster.
7. `Get_Error_Flag()` enthält einen OR-vs-AND-Bug, scheint aber im aktuellen Pfad unbenutzt zu sein.

---

## 12. Read-only ADB-Modeminfo aus dem laufenden Prozess

Am 2026-08-25 wurde auf einem realen LTE-Modul bestätigt, dass der laufende Prozess `phnixIot4G` über `/proc/<PID>/mem` read-only ausgelesen werden kann. Da der untersuchte Build ein 32-Bit-ARM-ELF vom Typ `EXEC`/non-PIE ist, sind die statisch ermittelten globalen Adressen in genau diesem Build direkt nutzbar.

Grundprinzip:

```sh
PID=$(pidof phnixIot4G)
dd if=/proc/$PID/mem bs=1 skip=<adresse> count=<laenge> 2>/dev/null
```

Dieser Weg ist für eine lokale Diagnose- oder „Modem Info“-Seite besonders attraktiv, weil dafür **weder `/dev/ttyHSL2` geöffnet noch ein zusätzliches Modbus-/RS485-Telegramm gesendet werden muss**.

Wichtig: Diese Adressen sind buildabhängig. Vor Verwendung mit einem anderen `phnixIot4G`-Build muss dessen Build-ID bzw. Symbol-/Offsetlage erneut geprüft werden.

### 12.1 Mainboard-Firmwarecache aus `otaDeviceInfo`

Die vom Mainboard per C544-Serviceframe gelesene Geräte-/Firmwarekennung wird stabil in `otaDeviceInfo @ 0x933AC` gehalten.

| Adresse | Inhalt | Format |
|---:|---|---|
| `0x935E1` | Mainboard-Softwarecode | ASCII, 9 Byte |
| `0x935EA` | Mainboard-Softwareversion | ASCII, 5 Byte |
| `0x935EF` | Mainboard-Hardwarecode | ASCII, 9 Byte |
| `0x935F8` | Mainboard-Hardwareversion | ASCII, 5 Byte |

Die Softwareversion wird vom Handler nach Verarbeitung des C544-Rohwerts in eine Anzeigeform wie `V3.3` umgesetzt. Alle vier Felder wurden auf realer Hardware erfolgreich per ADB gelesen.

Für eine GUI eignen sich die Bezeichnungen:

```text
Mainboard Firmware
Softwarecode
Hardwarecode
Hardwareversion
```

### 12.2 SIM- und Modemidentität

Feste globale ASCII-Puffer:

| Adresse | Inhalt | Länge |
|---:|---|---:|
| `0x9365C` | ICCID | 22 Byte |
| `0x93674` | IMSI | 17 Byte |
| `0x93688` | IMEI | 32 Byte |

Alle drei Felder wurden live bestätigt. Die tatsächlichen Gerätekennungen werden hier bewusst nicht dokumentiert.

Empfohlene Anzeige:

```text
SIM
  ICCID
  IMSI

Modem
  IMEI
```

ICCID, IMSI und IMEI sind eindeutige Geräte-/Teilnehmerkennungen und sollten in Support-Logs standardmäßig maskiert oder nur auf ausdrückliche Anforderung exportiert werden.

### 12.3 SIM-Status

Globale Struktur:

```text
simStatus @ 0x98AB0
```

Bekannter Aufbau:

| Offset | Typ | Bedeutung |
|---:|---|---|
| `+0x00` | `uint32` | `card_status` |
| `+0x04` | `uint32` | `app_type` |
| `+0x08` | `uint32` | `app_state` |
| `+0x0C` | 8 Byte | PIN-Struktur |

Bestätigte relevante Enums:

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

Auf dem real getesteten Gerät wurden `card_status = 1` und `app_state = 7` beobachtet, also SIM vorhanden und READY.

### 12.4 Modemtyp

```text
ModeType @ 0x98912
Größe: 1 Byte
```

Aus dem aktiven AT-/Startup-Pfad:

```text
1 = SIMCom SIM7600SA-H
2 = SIMCom SIM7600E-H
3 = weiterer/China-Modellpfad
sonst = unbekannt
```

Live bestätigt wurde `ModeType = 2`, passend zu **SIMCom SIM7600E-H**.

### 12.5 Serving System / Registration / Attach / RAT

Globale Struktur:

```text
serving_system @ 0x981B4
```

Bekannte Felder:

| Offset | Typ | Bedeutung |
|---:|---|---|
| `+0x00` | `uint32` | Registration State |
| `+0x04` | `uint32` | CS Attach State |
| `+0x08` | `uint32` | PS Attach State |
| `+0x0C` | `uint32` | Selected Network |
| `+0x10` | `uint32` | Anzahl Radio Interfaces |
| `+0x14` | `uint32[]` | Radio Interface Array |

Live beobachtet wurden Registration, CS Attach und PS Attach jeweils im aktiven Zustand. `Radio Interface[0] = 8` ist anhand der eingebetteten QMI-Enum eindeutig:

```text
8 = NAS_RADIO_IF_LTE_V01
```

Damit ist eine direkte Anzeige `Mobilfunkstandard: LTE` möglich.

### 12.6 Serving PLMN / MCC / MNC / Netzbeschreibung

Im QMI-Response liegen:

| Adresse | Inhalt |
|---:|---|
| `0x98020` | `current_plmn_valid` |
| `0x98022` | MCC, `uint16` |
| `0x98024` | MNC, `uint16` |
| `0x98026` | `network_description`, ASCII |

Diese Felder wurden live bestätigt. Auf realer Hardware war `current_plmn_valid = 1`; MCC/MNC und eine kurze Netzbeschreibung waren befüllt.

Empfohlene Anzeige:

```text
Netzkennung: <MCC>/<MNC>
Netzbeschreibung: <vom Modem gelieferter Text>
```

Ein menschenlesbarer Providername kann optional über eine lokale MCC/MNC-Tabelle ergänzt werden. Der rohe vom Modem gelieferte Text sollte trotzdem separat erhalten bleiben.

### 12.7 Roamingstatus

Im selben QMI-Serving-System-Response:

| Adresse | Inhalt |
|---:|---|
| `0x97FE8` | `roaming_indicator_valid`, `uint32` |
| `0x97FEC` | `roaming_indicator`, `uint32` |

Enum:

```text
0 = ROAMING ON
1 = ROAMING OFF
2 = ROAMING FLASHING
```

Live wurden ein gültiger Roaming-Indikator und `ROAMING ON` beobachtet. Damit lässt sich Roaming direkt aus dem Modemstatus bestimmen; eine Ableitung aus Home-PLMN/Serving-PLMN ist nicht nötig.

Wenn `roaming_indicator_valid == 0`, sollte eine GUI den Wert als `nicht verfügbar` behandeln.

### 12.8 LAC und Cell-ID

Getter-/Strukturadressen:

| Adresse | Inhalt | Typ |
|---:|---|---|
| `0x98168` | LAC | `uint16` |
| `0x9816C` | Cell-ID | `uint32` |

Live wurde für LAC `0xFFFE` beobachtet. Dieser Wert ist als ungültiger/Sentinel-Wert zu behandeln und sollte nicht als dezimale LAC ausgegeben werden.

Die Cell-ID war dagegen befüllt und plausibel. Für LTE sollte daher bei ungültigem LAC z. B. angezeigt werden:

```text
Cell-ID: <Wert>
LAC/TAC: nicht verfügbar
```

### 12.9 Signalstärke

Für die Modem-Info-Seite ist weiterhin `statistic_para @ 0x91B60` der praktisch bestätigte Pfad:

```text
+0x00  Strongest CSQ
+0x04  Weakest CSQ
+0x3C  gespeicherter Average CSQ
+0x4C  Current CSQ
+0x58  laufende CSQ-Summe
+0x5C  Anzahl CSQ-Samples
```

Der Durchschnitt sollte bevorzugt direkt berechnet werden:

```text
average_csq = sum / samples
```

sofern `samples > 0`, weil das Herstellerfeld `+0x3C` nur zu bestimmten Log-/Upload-Zeitpunkten aktualisiert wird.

Die alternativen Globals `NasAPILevel @ 0x98AD8` und `NasAPIMode @ 0x98ADC` waren auf dem live getesteten Gerät `0/0` und eignen sich in diesem Build aktuell nicht als primäre GUI-Quelle.

### 12.10 Aliyun-Identität und sensible Credentials

Live bestätigt wurden folgende Aliyun-SDK-Puffer:

```text
_device_secret  @ 0x9896C
_product_secret @ 0x989B0
_device_name    @ 0x98A58
_product_key     @ 0x98A98
```

Der DeviceName entsprach auf dem getesteten Gerät der IMEI; ProductKey und DeviceSecret waren befüllt, ProductSecret war im laufenden Zustand leer.

**Sicherheitsregel für Updater und Dokumentation:** Credential-Inhalte wie `DeviceSecret` oder `ProductSecret` dürfen nicht in Repository-Dokumentation, normale Debuglogs, Support-ZIPs oder Telemetrie geschrieben werden. In einer lokalen GUI höchstens maskiert darstellen, z. B. `vorhanden` / `nicht geladen`; eine explizite Reveal-Funktion sollte bewusst getrennt und lokal bleiben.

Konkrete Secrets werden in diesem Dokument absichtlich nicht aufgeführt.

### 12.11 Echter MQTT-Connected-State

Das Aliyun-SDK hält einen Pointer auf den aktiven MQTT-Client:

```text
pclient @ 0x94EB4
```

Dieser Pointer ist dynamisch. Der eigentliche Client-State liegt bei:

```text
*(uint32 *)(pclient + 0x4DC)
```

Der SDK-Code prüft explizit auf State `2` für den normalen verbundenen Zustand. Live wurde auf realer Hardware `client_state = 2` bestätigt.

Empfohlene Logik:

```text
pclient == 0
  -> MQTT nicht initialisiert

client_state == 2
  -> MQTT / Cloud verbunden

sonst
  -> nicht verbunden / Verbindungsaufbau / anderer SDK-State
```

`MQTT_init_signal @ 0x936A8` wurde live ebenfalls mit Wert `1` beobachtet, soll aber nicht als alleiniger Connected-State verwendet werden.

### 12.12 Mobilfunk-IP und Default-Route

Die aktive IP-Konfiguration wird besser nicht aus einem PHNIX-RAM-Cache, sondern direkt read-only aus Linux gelesen:

```sh
ip addr
cat /proc/net/route
```

Live bestätigt war das Mobilfunkinterface:

```text
rmnet_data0
```

mit privater PDP-/Mobilfunk-IP und Default-Route über dasselbe Interface. `bridge0` stellt ein separates internes Netz dar und sollte höchstens unter erweiterten Netzwerkdetails angezeigt werden.

Empfohlene GUI-Felder:

```text
Mobilfunkinterface
Mobilfunk-IP / PDP-IP
Präfix
Default Gateway
```

Die Adresse darf nicht als öffentliche Internet-IP bezeichnet werden.

### 12.13 APN-Pfad

Der aktive Startup-Pfad lautet sinngemäß:

```text
main
 -> AT_GetCGMM
 -> AT_APN1
 -> AT_APN6
```

Der APN wird abhängig von `ModeType` und teilweise ICCID gesetzt. Im Build sind u. a. folgende APNs hinterlegt:

```text
orange.m2m.spec
acell.90164
cuiot
```

Für `ModeType == 2` wird der `orange.m2m.spec`-Pfad verwendet. Ein eigener stabiler `current_apn[]`-Runtimecache wurde bisher nicht identifiziert. Für eine Diagnose-GUI sollte daher zwischen „vom Programm erwarteter/gesetzter APN“ und einem tatsächlich separat aus dem Modem ausgelesenen aktuellen PDP-Context unterschieden werden.

### 12.14 Was noch offen ist

Noch nicht als stabiler `phnixIot4G`-Runtimepfad identifiziert:

```text
SIMCom/Baseband-Firmwareversion
LTE RSRP
LTE RSRQ
SINR
stabiler aktueller APN-Cache
```

Das Binary nutzt für IMEI und Netzstatus QMI-/AT-Funktionen, enthält aber im bisher untersuchten aktiven Pfad keinen offensichtlichen `AT+CGMR`-/Baseband-Version-Getter. Diese Werte sollten daher separat im RootFS/QMI-/Modempfad gesucht werden.

### 12.15 Umsetzungsempfehlung für eine lokale „Modem Info“-Seite

Sinnvolle Gliederung:

```text
Mainboard
  Firmware
  Softwarecode
  Hardwarecode
  Hardwareversion

Modem
  Modell
  IMEI

SIM
  ICCID
  IMSI
  Card Status
  App/PIN Status

Mobilfunk
  RAT / LTE
  Registration
  CS Attach
  PS Attach
  MCC/MNC
  Netzbeschreibung
  Roaming
  Cell-ID
  LAC/TAC
  Current / Average / Strongest CSQ

Netzwerk
  rmnet Interface
  Mobilfunk-IP
  Präfix
  Gateway

Cloud
  MQTT Connected-State
  DeviceName
  ProductKey
  Credential-Status nur maskiert

Statistik
  Betriebszeit
  Onlinezeit
  Upload-/Downloadzähler
  DTU-/Mainboard-OTA-Zähler
  Power-/Active-Reset-Zähler
  ErrorStatue
```

Alle Reads sollten unabhängig voneinander fehlertolerant sein. Ein fehlender Prozess, ein nicht lesbarer `/proc/<PID>/mem`, ein Null-Pointer oder ein ungültiger Einzelwert darf nicht die gesamte Seite scheitern lassen. Stattdessen den jeweiligen Wert als `nicht verfügbar` kennzeichnen.

**Nicht verwenden:** konkurrierendes Lesen von `/dev/ttyHSL2` oder vom UART-FD des laufenden Prozesses. Ein zweiter Reader kann Bytes aus dem normalen Warmlink-/Mainboard-Datenstrom stehlen. Für die Modem-Info-Seite sind die oben beschriebenen RAM-/Linux-Reads vorzuziehen.
