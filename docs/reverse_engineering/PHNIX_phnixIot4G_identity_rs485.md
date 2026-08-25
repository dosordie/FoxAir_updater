# PHNIX `phnixIot4G` – Identity-/ProductKey-Pfad über RS485

Stand: 2026-08-26

Grundlage: statische Analyse von `uart485_get_productKey()` im ungestrippten ARM-ELF `phnixIot4G`.

## Kurzfazit

Die Cloudidentität des LTE-Dienstes kommt nicht ausschließlich vom Modem oder aus lokaler Persistenz. Das Mainboard liefert über die Hersteller-RS485-Services mindestens:

```text
12-Byte deviceID-artige Identität
32-Byte ProductKey
```

Diese Werte werden direkt in die globalen Aliyun-/Warmlink-Identity-Puffer übernommen und sind Voraussetzung für den weiteren Startup-/Credential-Pfad.

Für einen reinen Mainboardwechsel ist die wichtigste praktische Erkenntnis:

> Bleiben LTE-DTU und SIM erhalten und liefert das Ersatzmainboard denselben
> ProductKey, bleibt die bisherige MQTT-Identität mit hoher Wahrscheinlichkeit
> erhalten. Ein Mainboardwechsel ändert jedoch voraussichtlich die zusätzliche
> 12-Byte-Kommunikationsmodul-ID; die Herstellercloud kann den Wechsel daher
> erkennen. Die serverseitige Reaktion darauf ist noch nicht live bestätigt.

---

## 1. Zentrale Funktion

```text
uart485_get_productKey() @ 0x14354
```

Sie arbeitet direkt auf dem RS485-UART und parst mehrere unterschiedliche Hersteller-Serviceantworten.

Der UART-FD wird aus dem globalen UART-Kontext übernommen; die Funktion baut/selectiert zunächst einen Request und liest anschließend bis zu 200 Byte Antwortdaten.

---

## 2. 12-Byte `deviceID` aus Boardantwort

Ein erkannter Antworttyp beginnt mit:

```text
0x63 0x03 0xB4 ...
```

Bei gültiger Länge kopiert der Code:

```c
memcpy(aliMqtt_get_deviceID_buf(), rx + 3, 12);
```

Ein weiterer Service-Antworttyp beginnt mit:

```text
0x63 0x10 0x07 0xD1 ...
```

und kopiert ebenfalls 12 Byte, diesmal aus:

```c
memcpy(aliMqtt_get_deviceID_buf(), rx + 7, 12);
```

Damit kann derselbe globale `deviceID`-Puffer aus unterschiedlichen Mainboard-Serviceantworten gefüllt werden.

Der globale Aliyun-Puffer liegt im späteren MQTT-Kontext; `aliMqtt_set_deviceID()` verwaltet zusätzlich einen eigenen Buffer bei etwa `0x94F44`.

---

## 3. 32-Byte ProductKey direkt vom Mainboard

Ein weiterer erkannter Frame besitzt Headerbytes:

```text
0x63 0x10 0x00 0xC8 ...
```

Nach CRC-Prüfung über `Check_crc()` ruft der Code:

```text
aliMqtt_get_product_buf()
```

auf und kopiert anschließend:

```c
memcpy(productKeyBuffer, rx + 7, 32);
```

Der ProductKey ist damit eindeutig Mainboard-seitig bereitgestellt.

**Praktische Konsequenz:** Ein LTE-Modem ist nicht vollständig unabhängig austauschbar. Für den normalen Hersteller-Startup braucht es die passende Mainboardidentität/ProductKey-Antwort auf RS485.

---

## 4. Startup-State 4 -> 5 hängt an dieser RS485-Identity-Phase

Wenn `uart485_get_productKey()` noch keine gültige Antwort erhalten hat und:

```text
dtu_run_step == 4
```

sendet die Funktion erneut einen Boardrequest. Nach dem entsprechenden Identity-/ProductKey-Fortschritt setzt sie:

```c
set_dtu_run_step(5);
```

Damit liegt die Reihenfolge sinngemäß bei:

```text
LTE/Modemgrundinitialisierung
 -> dtu_run_step 4
 -> Mainboard ProductKey/deviceID per RS485
 -> dtu_run_step 5
 -> weitere Credential-/Cloudinitialisierung
```

Dies bestätigt, dass die Mainboardidentität bereits vor der Aliyun-Cloudinitialisierung in den LTE-Prozess einfließt.

---

## 5. Sonder-/Testpfad mit IMEI und ICCID

Die Funktion enthält zusätzlich einen Sonderpfad, der bei einem internen Test-/Fallbackflag Informationen aus:

```text
DmsAPI_get_imei_cache()
UimAPI_get_iccid()
```

verwendet und daraus einen Diagnose-/Identitätsstring aufbaut.

Das zeigt, dass IMEI/ICCID lokal verfügbar sind, sie ersetzen im normalen Produktpfad aber nicht einfach den vom Mainboard gelieferten ProductKey.

---

## 6. Bedeutung für eigene Warmlink-Tools

Für eine vollständige lokale Replikation oder ein Ersatz-LTE-Gateway sollte zwischen folgenden Identitäten unterschieden werden:

```text
Mainboard ProductKey        32 Byte, über RS485
Mainboard/Service deviceID  12 Byte, über RS485
Modem IMEI                  aus DMS/QMI
SIM ICCID                   aus UIM/QMI
Aliyun DeviceName           Cloud-/SDK-Kontext
Aliyun DeviceSecret         Provisionierungs-/Credentialpfad
PHNIX deviceCode            separater Hersteller-Identifier
```

Diese Werte sind nicht austauschbar und besitzen unterschiedliche Herkunft und Rollen.

---

## 7. Zusätzlicher Befund aus der Mainboard-Firmware V3.3

Das untersuchte Mainboardimage ist:

```text
Datei:       phnixIot_device_OTA
Größe:      287598 Byte
SHA-256:     6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Software:    82400644 / intern 0033 / Anzeige V3.3
```

Im Image stehen fest einkompiliert:

```text
BIN-Offset 0x42780: 824006440033
BIN-Offset 0x427E0: a5cVutQfC8x
```

Der zweite String ist exakt der auf der untersuchten Anlage live gelesene
Aliyun-ProductKey. Der ProductKey wird zwar vom LTE-Dienst über RS485 vom
Mainboard angefordert, stammt bei V3.3 aber aus dem Mainboard-Firmwareimage und
ist damit **keine individuelle Mainboard-Seriennummer**. Er kennzeichnet sehr
wahrscheinlich die Produkt-/Firmwarefamilie.

Auch `82400644` und `0033` sind Build-/Softwarekennungen und keine
geräteindividuellen Seriennummern. Die Firmwaredatei selbst besitzt im
untersuchten OTA-Pfad keine nachgewiesene Bindung an ein einzelnes Mainboard.

Der 12-Byte-Block ab `0x07D1` bleibt davon getrennt. Seine zwölf Livebytes sind
für die untersuchte Anlage inzwischen bekannt:

```text
Register 2001..2006: 0x5746 0x3232 0x3130 0x3235 0x3034 0x3735
Big-Endian-ASCII:    WF2210250475
```

FoxAir Control bezeichnet ihn als **WiFi Barcode / Kommunikationsmodul-ID**,
nicht als Geräte-Serial-No. vom Typenschild. Das vermutete Format ist
`WF + YYMMDD + laufende Nummer`, hier also `WF + 221025 + 0475`.

Die Kennung steht weder als Klartext noch als direkte Folge der sechs
16-Bit-Worte im V3.3-OTA-Image. Sie ist deshalb sehr wahrscheinlich separat und
geräteindividuell in einem bei OTA nicht mitgelieferten nichtflüchtigen
Produktions-/Konfigurationsbereich abgelegt.

---

## 8. Folgen eines Mainboardwechsels

### 8.1 Nur Mainboard ersetzt, vorhandene LTE-DTU und SIM bleiben

Beim Start liest die vorhandene LTE-DTU erneut:

```text
Mainboard -> 12-Byte-Identitätsblock ab 0x07D1
Mainboard -> ProductKey ab 0x00C8
LTE-DTU   -> IMEI aus dem SIM7600/QMI-DMS-Pfad
Cloud     -> DeviceName/deviceCode und DeviceSecret
```

Live wurde auf der untersuchten Anlage bestätigt, dass der Aliyun
`DeviceName` mit der IMEI des LTE-Modems identisch ist. Der normale
Cloud-Control-Pfad adressiert das Gerät mit `deviceCode`; der MQTT-Login nutzt
`ProductKey`, `DeviceName` und `DeviceSecret`.

Wenn das Ersatzmainboard zur gleichen GL9-/Firmwarefamilie gehört und denselben
ProductKey liefert, bleiben erhalten:

- IMEI und damit der bisherige Aliyun `DeviceName`/wahrscheinliche PHNIX
  `deviceCode`;
- SIM und ICCID;
- die serverseitige Zuordnung des bisherigen Cloudgeräts;
- der zu dieser Modemidentität gehörende Credential-Pfad.

Deshalb sollte die Anlage in der bestehenden App mit hoher Wahrscheinlichkeit
weiter als dasselbe Gerät erscheinen und wieder steuerbar sein.

Das LTE-Programm vergleicht allerdings die aktuell vom Mainboard gelesenen
zwölf Identitätsbytes mit dem in `/data/phnixIot_device_statisic` gespeicherten
Wert. Bei einer Abweichung aktualisiert es die persistente Kopie und erhöht den
Statistikwert `Device-change-t`. Ein daraus resultierendes Sperren oder
Entkoppeln des Cloudkontos wurde im analysierten Programm nicht gefunden.
Da diese Kennung auch in PHNIX-Provisionierungs-/Diagnosepfade einfließt, ist
die Aussage zur unveränderten App-Zuordnung dennoch eine technische Prognose
und keine live bestätigte Garantie.

### 8.2 Ersatzmainboard liefert einen anderen ProductKey

Ein anderer ProductKey ändert den Aliyun-Produktkontext. Das bisherige
DeviceSecret muss dann nicht mehr zu `ProductKey + DeviceName` passen. Der
LTE-Dienst kann dadurch in der Credential-Phase (`dtu_run_step == 7`) verbleiben
und die PHNIX-/Linked-Go-Geräteabfrage wiederholt aufrufen.

Mögliche Ergebnisse sind:

1. Die Cloud liefert passende neue Credentials und provisioniert das Modem für
   die andere Produktfamilie.
2. Das Gerät erscheint als neues beziehungsweise neu zuzuordnendes Cloudgerät.
3. Die Provisionierung wird abgelehnt und die LTE-DTU bleibt cloudseitig
   offline.

Welches Verhalten die Herstellercloud aktuell wählt, ist aus dem lokalen
Binary nicht beweisbar.

### 8.3 Mainboard liefert keinen gültigen ProductKey

Ohne eine gültige Antwort auf den ProductKey-/Identity-Handshake kommt der
normale Startup nicht bis zur MQTT-Verbindung. Der UART-Thread wartet weiter
auf den ProductKey; die Cloudsteuerung bleibt offline.

### 8.4 LTE-DTU wird ebenfalls ersetzt

Bei einem Austausch der LTE-DTU ändert sich die IMEI. Da diese auf der
untersuchten Anlage zugleich der aktive Aliyun `DeviceName` ist, handelt es
sich cloudseitig um eine neue Geräteidentität. Eine automatische Übernahme der
alten App-/Kontozuordnung ist dann nicht zu erwarten; das neue Modem muss
provisioniert und wahrscheinlich dem Benutzerkonto neu zugeordnet werden.

### 8.5 Nur SIM wird ersetzt

Bei gleichbleibender LTE-DTU bleibt die IMEI erhalten, während sich ICCID und
IMSI ändern. Nach aktuellem Analysebild ist die ICCID nicht die primäre
MQTT-/Cloudkennung. Sofern die neue SIM eine funktionierende Datenverbindung
herstellt, sollte die Cloudidentität deshalb grundsätzlich erhalten bleiben.

### 8.6 Mainboardparameter und Cloudbindung sind getrennt

Eine erhaltene Cloudbindung bedeutet nicht, dass das Ersatzmainboard die
Konfiguration des alten Boards übernimmt. Sollwerte, Anlagenparameter,
Kalibrierungen und weitere nichtflüchtige Mainboarddaten liegen auf dem
jeweiligen Mainboard beziehungsweise dessen Speicher und müssen separat
gesichert oder neu eingestellt werden.

---

## 9. Empfohlenes read-only Backup vor einem Mainboardwechsel

Vor einem realen Austausch sollten lokal und nicht öffentlich gesichert werden:

- IMEI, ICCID und IMSI;
- Aliyun `DeviceName` und ProductKey;
- DeviceSecret nur geschützt und niemals in Supportlogs oder ein öffentliches
  Repository übernehmen;
- Rohantwort des Identity-Reads `63 03 07 D1 00 5A 9C FE`, insbesondere die
  ersten zwölf Datenbytes;
- ProductKey-Block `0x00C8..0x00D7`;
- `/data/phnixIot_device_statisic`;
- vollständiges Parameter-/Konfigurationsbackup des alten Mainboards.

Die Identity- und ProductKey-Bereiche sollten nicht auf Verdacht auf ein
Ersatzboard geschrieben werden. Zunächst reicht ein Vergleich der read-only
gelesenen Werte vor und nach dem Wechsel.

---

## 10. Beweisgrad der Wechselbewertung

### Bewiesen

- ProductKey und 12-Byte-Identitätsblock werden vor der Cloudinitialisierung
  vom Mainboard über RS485 gelesen.
- Die zwölf Livebytes der untersuchten Anlage ergeben `WF2210250475` und werden
  vom LTE-Dienst tatsächlich als `deviceID` übernommen.
- `WF2210250475` ist nicht als direkter String oder 16-Bit-Wortfolge im
  V3.3-OTA-Image enthalten.
- Der bei der untersuchten Anlage verwendete ProductKey steht fest im
  V3.3-Mainboardimage.
- Der aktive Aliyun `DeviceName` der untersuchten LTE-DTU ist identisch mit
  ihrer IMEI.
- Der MQTT-Login verwendet ProductKey, DeviceName und DeviceSecret.
- Eine geänderte Mainboard-ID wird lokal erkannt, persistiert und im
  `Device-change-t`-Zähler erfasst.
- Cloud-Schreibbefehle der App verwenden den `deviceCode`, nicht die
  Mainboard-Modbusadresse H10.

### Sehr wahrscheinlich

- Ein passendes Ersatzmainboard mit gleichem ProductKey funktioniert mit der
  vorhandenen LTE-DTU unter derselben bestehenden Cloudidentität weiter.
- Der fest im Firmwareimage enthaltene ProductKey bezeichnet eine
  Produktfamilie und keine individuelle Mainboard-Seriennummer.
- `WF2210250475` ist eine separat provisionierte, geräteindividuelle
  Kommunikationsmodul-/Produktionskennung.

### Noch offen

- exakter Speicherort und Provisionierungsweg von `WF2210250475`;
- herstellerseitige Bestätigung des Formats `WF + YYMMDD + laufende Nummer`;
- serverseitige Reaktion auf einen echten Mainboardwechsel mit abweichender
  12-Byte-Identität;
- serverseitige Reaktion auf einen anderen ProductKey;
- ob ein Hersteller-Ersatzboard bereits mit einer besonderen
  Produktions-/Servicezuordnung ausgeliefert wird.

---

## 11. Nächster sinnvoller Schritt

Noch zu klären sind:

- exakte Register-/Payloadbedeutung der Serviceantworten `0xB4xx`, `0x07D1` und `0x00C8`;
- wie `deviceCode`, `deviceID`, ProductKey und Aliyun DeviceName beim HTTP-Provisioning zusammengeführt werden;
- Vergleich der read-only Identity-Blöcke mehrerer Mainboards beziehungsweise
  Firmwarefamilien.
