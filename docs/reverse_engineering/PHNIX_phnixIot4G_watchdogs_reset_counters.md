# PHNIX `phnixIot4G` – Watchdogs, Error-Bits und Reset-Counter

Stand: 2026-08-25

Grundlage: statische Analyse des ungestrippten ARM-ELF `phnixIot4G` (Build-ID `af4dcae12639bedce833ee5efa5da009777b6319`) plus Live-Beobachtung am realen FoxAir/PHNIX-LTE-Modem.

Diese Datei ergänzt insbesondere:

- `PHNIX_phnixIot4G_diagnostics_statistics_debug.md`
- `PHNIX_phnixIot4G_hidden_runtime_remote_control.md`

Schwerpunkt sind die bisher nur grob bekannten ~420-s-Timer im `TimerHandler()`, ihre echten Resetbedingungen und die genaue Bedeutung der Statistikfelder `Power-Reset-t` und `Active-Reset-t`.

---

## 1. Korrektur: `Power-Reset-t` ist kein reiner Stromausfallzähler

Persistente Statistik:

```text
/data/phnixIot_device_statisic
statistic_para @ 0x91B60
Power-Reset-t @ +0x28
```

Der Schreibpfad im Programmstart ist eindeutig:

```text
main()
  -> static_read_data(1)
  -> statistic_para[+0x28]++
  -> initHardware()
  -> weitere Threads/Initialisierung
```

Die Inkrementierung liegt direkt im normalen `main()`-Startup-Pfad um `0xB47C..0xB49C`.

Damit zählt `Power-Reset-t` in diesem Build praktisch **Starts des Prozesses `phnixIot4G`**, nicht ausschließlich echte Spannungsunterbrechungen des LTE-Moduls.

Live passt dies zum beobachteten Verhalten: Nach manuellem Kill/anschließendem Neustart des Dienstes stieg der Wert von 27 auf 28, während `Active-Reset-t` unverändert blieb.

### Konsequenz für die GUI

Nicht als:

```text
Power-Resets
```

interpretieren, wenn damit physische Stromausfälle gemeint sind.

Besser:

```text
Dienst-/Boot-Starts (Hersteller: Power-Reset-t)
```

oder kurz:

```text
phnixIot4G-Starts
```

Hinweis: Der Zähler wird beim Start zunächst nur im RAM erhöht. Persistiert wird die gesamte 128-Byte-Statistikstruktur bei den regulären `static_write_data()`-Ereignissen, u. a. periodisch bzw. bei anderen Statistik-/Reset-/OTA-Ereignissen.

---

## 2. `Active-Reset-t` bleibt davon klar getrennt

`Active-Reset-t @ statistic_para +0x2C` wird **nicht** bei normalem Prozessstart erhöht.

Bestätigte Inkrementierungsstellen:

1. mehr als 1800 s ohne Aliyun/MQTT-Verbindung -> kompletter Linux-Reboot
2. Remote-Kommando `RESET / code 0114` -> kompletter Linux-Reboot

Damit ist weiterhin die treffendste Bezeichnung:

```text
Vom LTE-Dienst aktiv ausgelöste vollständige Reboots
```

Ein normales `kill phnixIot4G` gehört nicht dazu.

---

## 3. Runtime-Struktur der Kommunikationswatchdogs

Globale Runtime-Struktur:

```text
app @ 0x988FC
Größe 0x70 Byte
```

`TimerHandler()` läuft im Sekundentakt und verwendet mindestens drei voneinander getrennte Alter-/Timeout-Counter:

```text
app +0x18
app +0x24
app +0x2C
```

Die drei Timer überwachen unterschiedliche Aspekte der Mainboard-/RS485-Kommunikation. Sie führen selbst **keinen Reboot** aus. Sie setzen Error-Bits und lösen teilweise aktive Healthcheck-Abfragen aus.

---

## 4. Watchdog A – `app +0x18`: Board-Service-/Healthcheck-Timer

### Timerverhalten

`TimerHandler()` erhöht `app+0x18` jede Sekunde.

Ab mehr als 300 Sekunden:

```text
alle 20 Sekunden -> Check485Statue()
```

Ab mehr als 420 Sekunden:

```text
set_Error_Flag(5)
```

Ab mehr als 600 Sekunden wird der Timer wieder auf 420 begrenzt:

```text
if timer > 600:
    timer = 420
```

Damit bleibt der Fehlerzustand bestehen, ohne dass der Counter unbegrenzt wächst.

### Aktiver Recovery-/Healthcheck

`Check485Statue() @ 0x156B4` prüft einen internen TX/RX-Statusmarker und sendet bei Bedarf den festen 8-Byte-Request:

```text
63 03 00 06 00 01 6C 49
```

also Slave `0x63`, FC03, Register `0x0006`, Anzahl 1.

Der Dienst versucht damit nach ungefähr fünf Minuten ausbleibender erwarteter Board-Servicekommunikation aktiv einen Mainboard-Healthcheck anzustoßen.

### Was setzt den Timer zurück?

In `getDevParameter()` sind zwei relevante Resetpfade sichtbar:

1. Empfang eines FC16-Serviceframes für Register `0x00C8`:

```text
frame[1] == 0x10
frame[2:3] == 0x00C8
-> app+0x18 = 0
-> Clear_Error_Flag(5)
```

Register `0x00C8` gehört zum ProductKey-/Servicepfad.

2. Ein von `unpack_mcu_modbus()` lokal vollständig behandeltes Service-/OTA-Frame (`return == 0`) setzt `app+0x18` ebenfalls auf 0.

### Error-Bit 5: auffällige Herstellerbenennung

`Upload_bord_log()` ordnet Bit 5 dem Text zu:

```text
Cloud connected error
```

Der tatsächliche 420-s-Setter hängt hier jedoch direkt an einem Board-Service-/RS485-Timer und aktiviert nach 300 s sogar `Check485Statue()`.

Damit besteht in diesem Build eine **semantische Inkonsistenz zwischen Hersteller-Fehlertext und realem Setter-Pfad**. Für eigene Diagnose sollte Bit 5 daher nicht blind nur als „Cloudfehler“ interpretiert werden.

Praktisch sinnvoller Hinweis:

```text
Bit 5: Herstellertext „Cloud connected error“; in TimerHandler an Board-Service-/485-Healthwatchdog gekoppelt.
```

---

## 5. Watchdog B – `app +0x24`: `exec_6063_time`, Alter des letzten Slave-0x63-Frames

Dieser Counter lässt sich besonders gut identifizieren, weil der Binary-Debugstring ausdrücklich lautet:

```text
app.exec_6063_time :%d
```

und dabei `app+0x24` ausgegeben wird.

### Resetbedingung

Sobald `getDevParameter()` ein Frame mit erstem Byte:

```text
0x63
```

sieht, passiert bereits vor der CRC-Auswertung:

```text
Clear_Error_Flag(6)
app+0x24 = 0
```

Damit misst dieser Counter im aktiven Pfad praktisch die Zeit seit dem letzten gesehenen Frame des Mainboard-Slaves `0x63`.

### Timeout

Solange Watchdog A (`app+0x18`) noch unter 420 s liegt:

```text
if app+0x24 >= 420:
    set_Error_Flag(6)
else:
    app+0x24++
    Clear_Error_Flag(6)
```

Ist Watchdog A bereits abgelaufen, wird dieser Block übersprungen. Der Code priorisiert damit offenbar den übergeordneten Service-/Healthfehler.

### Error-Bit 6

Der Herstellertext aus `Upload_bord_log()` lautet:

```text
WF_double_error
```

Die Bezeichnung ist kryptisch; der aktive Code zeigt jedoch klar, dass Bit 6 mit dem Ausbleiben von Slave-`0x63`-Frames gekoppelt ist.

Für eigene Diagnose ist daher sinnvoll:

```text
Bit 6: kein 0x63-Mainboardframe seit ~420 s
Herstellertext: WF_double_error
```

---

## 6. Watchdog C – `app +0x2C`: Zeit seit letztem CRC-gültigen 0x63-Modbusframe

Dieser Timer ist von Watchdog B getrennt.

### Resetbedingung

Im `0x63`-Pfad wird zunächst `Check_crc()` ausgeführt.

Nur wenn:

```text
Check_crc(...) == 1
```

setzt `getDevParameter()`:

```text
app+0x2C = 0
```

Ein bloß empfangenes `0x63`-Frame reicht hierfür also nicht; es muss CRC-gültig sein.

### Timeout

Im Sekundentimer:

```text
if app+0x2C > 420:
    set_Error_Flag(12)
else:
    Clear_Error_Flag(12)
    app+0x2C++
```

Damit ist Bit 12 ein versteckter Langzeitindikator für:

> seit mehr als etwa sieben Minuten kein CRC-gültiges Mainboard-/0x63-Modbusframe gesehen.

### Wichtig: Bit 12 hat keinen bekannten Hersteller-Text im normalen 0..7-Logblock

`Upload_bord_log()` baut die bekannten Textmeldungen nur aus den unteren Bits auf. Für Bit 12 wurde dort kein entsprechender menschenlesbarer String gefunden.

Dieser Fehler kann daher intern aktiv sein, ohne in der bekannten Hersteller-Fehlertextliste aufzutauchen.

---

## 7. Unterschied Bit 7 `Crc error` vs. Bit 12

Der Hersteller-Logblock enthält:

```text
Bit 7 -> Crc error
```

Im aktuell analysierten `getDevParameter()`-Pfad wird bei einem konkreten CRC-Fehler jedoch lediglich das Frame verworfen und ein Debugtext ausgegeben. Ein direkter `set_Error_Flag(7)` wurde im untersuchten aktiven RX-Pfad nicht gefunden.

Dagegen ist Bit 12 eindeutig an den **Langzeit-Timeout ohne CRC-gültiges Frame** gekoppelt.

Daher derzeitige Bewertung:

```text
Bit 7  = vorgesehener/älterer unmittelbarer CRC-Fehlerstatus; aktiver Setter im aktuellen RX-Pfad bisher nicht gefunden
Bit 12 = real aktiver ~420-s-Watchdog für fehlende CRC-gültige 0x63-Frames
```

Die beiden Bits dürfen nicht gleichgesetzt werden.

---

## 8. Weitere Error-Bits, die für die Diagnose wichtig sind

Aus den aktiven Pfaden sind zusätzlich sicher:

```text
Bit 4  -> CSQ ungültig / Signalproblem
Bit 8  -> UART485-/ProductKey-Startup noch nicht erfolgreich
Bit 10 -> Aliyun/MQTT aktuell nicht verbunden
Bit 12 -> >~420 s kein CRC-gültiges 0x63-Frame
```

### Bit 8

`uart485_thread_handle()` setzt Bit 8 direkt nach `uart485_init()` und vor dem ProductKey-Handshake:

```text
set_Error_Flag(8)
```

Erst wenn `uart485_get_productKey()` erfolgreich Daten geliefert hat, wird:

```text
Clear_Error_Flag(8)
```

aufgerufen.

Bit 8 ist damit ein sehr brauchbarer **UART485-/Startup-/ProductKey-Handshake-Status**.

### Bit 10

`TimerHandler()` setzt Bit 10 direkt abhängig von `get_ALI_Connt_State()`:

```text
Aliyun verbunden    -> Clear_Error_Flag(10)
Aliyun nicht online -> set_Error_Flag(10)
```

Nach 1800 s durchgehendem Offlinezustand folgt zusätzlich der bekannte aktive Modem-Reboot und `Active-Reset-t++`.

Bit 10 ist daher der deutlich belastbarere echte aktuelle Cloud-/MQTT-Fehlerindikator als der Herstellertext von Bit 5.

---

## 9. Zusammenfassung der drei ~420-s-Watchdogs

| Runtime-Feld | Schwellwert | Reset durch | Error-Bit | Praktische Bedeutung |
|---|---:|---|---:|---|
| `app+0x18` | >420 s | FC16 `0x00C8` / lokal behandeltes Serviceframe | 5 | Board-Service-/Healthpfad ausgeblieben; ab >300 s aktive FC03-Reg6-Healthchecks |
| `app+0x24` (`exec_6063_time`) | >=420 s | jedes empfangene Frame mit Slave `0x63` | 6 | seit ~7 min kein 0x63-Mainboardframe gesehen |
| `app+0x2C` | >420 s | CRC-gültiges 0x63-Modbusframe | 12 | seit ~7 min kein gültiges Mainboardframe gesehen |

Die Timer bilden damit eine Art gestufte Kommunikationsdiagnose:

```text
Service-/Health-Antwort vorhanden?
        ↓
überhaupt 0x63-Traffic vorhanden?
        ↓
ist der 0x63-Traffic CRC-gültig?
```

Das ist deutlich differenzierter als ein einzelnes „RS485 OK/Fehler“-Bit.

---

## 10. Konsequenz für eine Modem-Info-/Diagnoseseite

Statt nur:

```text
Mainboard / RS485: OK
```

kann ein eigener Updater langfristig deutlich genauer anzeigen:

```text
RS485 UART initialisiert:          Ja/Nein      (Bit 8)
Mainboard 0x63-Traffic vorhanden: Ja/Nein      (Bit 6 / app+0x24)
CRC-gültige Frames vorhanden:     Ja/Nein      (Bit 12 / app+0x2C)
Board-Service-Health:              Ja/Fehler     (app+0x18 / Bit 5 mit Vorsicht)
Cloud/MQTT aktuell verbunden:      Ja/Nein       (echter MQTT-State + Bit 10)
```

Die Runtime-Counter selbst können ebenfalls read-only über `/proc/<PID>/mem` ausgelesen werden:

```text
app base = 0x988FC

app+0x18 = 0x98914
app+0x24 = 0x98920
app+0x2C = 0x98928
```

Beispiel:

```sh
adb shell 'PID=$(pidof phnixIot4G); dd if=/proc/$PID/mem bs=1 skip=$((0x98914)) count=24 2>/dev/null | od -Ax -tu4'
```

Damit können die tatsächlichen Sekunden seit den letzten jeweiligen Ereignissen angezeigt werden, ohne irgendein zusätzliches RS485-Telegramm zu erzeugen.

---

## 11. Wichtigste Korrekturen gegenüber früheren Annahmen

1. `Power-Reset-t` ist **kein sicherer physischer Power-Cycle-Zähler**, sondern wird bei jedem `phnixIot4G`-Programmstart erhöht.
2. Die ~420-s-Mechanismen sind keine Reboot-Watchdogs, sondern gestufte Kommunikations-/Fehlerwatchdogs.
3. Bit 10 ist der direkte aktuelle Aliyun/MQTT-Offlineindikator.
4. Bit 5 trägt zwar den Herstellertext `Cloud connected error`, sein aktiver Timer-/Recoverypfad ist aber deutlich mit Board-Service/RS485 gekoppelt.
5. Bit 6 wird bei jedem gesehenen Slave-`0x63`-Frame zurückgesetzt und überwacht damit den grundsätzlichen Mainboardtraffic.
6. Bit 12 überwacht separat das Alter des letzten CRC-gültigen `0x63`-Frames.
7. Der bekannte Text `Crc error` für Bit 7 ist nicht dasselbe wie der aktive Bit-12-Langzeitwatchdog; ein direkter Bit-7-Setter wurde im aktuellen RX-Pfad bisher nicht gefunden.
