# Mainboard-Firmware V3.3 – Sicherheit eines abbrechbaren OTA-Vortests

Stand: 26. August 2026

Diese Datei untersucht primär einen OTA-Vorhandshake, der **vor dem ersten C5A8-Firmwaredatenblock** abgebrochen wird. Ergänzend ist inzwischen auch der V3.3-Fehlerfall eines **bereits begonnenen, aber stehenbleibenden C5A8-Transfers** rekonstruiert, insbesondere der `0x7530`-Interblock-Timeout und dessen C544-Recoverypfad. Es wurde keine Verbindung zu ser2net oder realer Hardware geöffnet und nichts gesendet.

> **Korrektur zur Mainboardbasis:** Die V3.3-BIN ist für `0x08050000` gelinkt. Frühere absolute Funktionsadressen aus einer fälschlich angenommenen Basis `0x08080000` lagen `+0x30000` zu hoch. Die hier verwendeten Adressen sind korrigiert. RAM-Adressen, EEPROM-Offets und echte Flashzielbereiche bleiben unverändert.

## Harte Sicherheitsgrenze

```text
C5A8 darf beim Vortest niemals gesendet werden.
```

Solange kein C5A8 verarbeitet wurde, bleibt `OTA+0x1C == 0`. Dieses Flag bewacht den destruktiven Flash-Erase-Zweig des C36A-Abbruchpfads.

**Neu statisch bestätigt:** `C36E Status 3` ist **kein** sicherer Stopppunkt. Wenn Status 3 erscheint, wurde der vollständige C5A8-Transfer bereits mit MD5 #1 erfolgreich geprüft und der interne OTA-Zustand weitergeschaltet. Ein fehlendes `C37B/3` hält die anschließende Promotion nicht an.

## Relevante Funktionen

| Funktion | Korrekte VA | Rolle |
|---|---:|---|
| zentraler OTA/FC10-Dispatcher | `0x08067Cxx–0x080681xx` | C350/C357/C36A/C37B/C5A8 empfangen |
| C350-Erkennung | `0x08067CE4` | C350 RX |
| C357-Erkennung | `0x08067D30` | C357 RX |
| C36A-Erkennung | `0x08067D74` | Cancel RX |
| C37B-Erkennung | `0x08067EB6` | Status-ACK RX |
| Status-/Handshake-Worker | `0x0806899C` | C36E/C544/C36C/C371 senden |
| C350/C357-Verarbeitung | `0x08076A88` ff. | Zielvergleich / Metadaten |
| OTA-Retry/EEPROM-Control | `0x08076470` | Timeouts, Retries, EEPROM-Recovery |
| C5A8-Worker | `0x08078628` | Datenblock/Flash-Staging |
| C36A-Abbruchworker | `0x08078D68` | Cancel, EEPROM-Clear, optional Staging-Erase |
| Boot-/Jumpworker | `0x08079354` | Jump `0x08000000` / `0x08050000` |
| EEPROM Write | `0x08050C08` | I²C-EEPROM schreiben |
| EEPROM Read | `0x08050C5E` | I²C-EEPROM lesen |
| Flash Unlock | `0x0808D144` | Flash |
| Flash Page Erase | `0x0808D1C0` | Flash |
| Flash Program Word | `0x0808D2E4` | Flash |
| Flash Lock | `0x0808D190` | Flash |

# C350

Der direkte C350-RX-Handler kopiert nur in RAM und setzt ein Verarbeitungsflag. Er enthält keinen Flash- oder EEPROM-Zugriff.

Der 12-Byte-Fingerprint wird in zwei Teile verglichen:

```text
Bytes 0..7   Ziel-/Produktidentität
Bytes 8..11  Build-/Versionsanteil
```

## Identische V3.3-Kennung

```text
C36E Status 0
```

Auswirkungen:

- RAM: temporäre Handshakeflags
- EEPROM: kein Write
- Flash: kein Zugriff
- Jump/Reset: keiner
- normale Regelung: läuft weiter

**Wichtig:** Status 0 ist ein Ablehnungs-/„kein neues Update“-Pfad, aber **kein globaler OTA-Reset**. Bereits vorher vorhandene persistente OTA-Records werden durch C350 Status 0 nicht pauschal gelöscht.

Im direkten C350->Status-0-Pfad wurden keine verzögerten Flash-, EEPROM- oder Boot-Control-Aktionen gefunden.

## Inkompatibles Ziel

Wenn Bytes 0..7 nicht passen:

```text
C36E Status 0
```

Ebenfalls kein EEPROM-, Flash-, Jump- oder Resetpfad.

## Kompatibles Ziel, anderer Build

Wenn Bytes 0..7 passen und Bytes 8..11 abweichen:

```text
C36E Status 1
```

Die angebotene Kennung wird nur in OTA-RAM-Metadaten übernommen. Kein persistenter Write.

### Wenn danach niemals C357 kommt

Für diesen Zustand wurde in der Mainboard-V3.3 **kein eigener C350->C357-Wartetimeout** gefunden.

Die bekannten `0x7530 = 30000`-Zähler gehören zu späteren OTA-Daten-/Status-/Retrypfaden und dürfen nicht als C350->C357-Timeout interpretiert werden.

Damit gilt:

- normaler Regel- und Warmlinkbetrieb läuft weiter,
- der C350-Status-1-Zustand bleibt nur in RAM,
- ein späteres C357 kann während derselben Laufzeit weiterhin verarbeitet werden,
- ein Neustart verwirft diesen C350-only-Zustand, weil noch nichts persistiert wurde.

# C357 ohne C5A8

C357 übernimmt:

```text
Dateilänge: Payload Bytes 3..5, 24 Bit Big Endian
MD5:        Payload Bytes 6..37, 32 ASCII-Hexzeichen
Maximal:    0x4B000 = 307200 Byte
```

Nach akzeptierten Metadaten:

```text
C36E Status 2
```

Erstmals persistente Änderung:

```text
EEPROM Offset 0x3F0
Byte 0 = 1
Byte 1..2 = CRC16 über Byte 0
```

Weiterhin gilt:

- keine Firmwaredaten im Flash
- kein Staging-Flashwrite
- kein Image-Copy
- kein Jump
- kein Reset

Der spätere C5A8-Wartepfad besitzt eine Timeoutschwelle von:

```text
0x7530 = 30000 Worker-Aufrufe
```

Eine sichere Umrechnung in Sekunden ist statisch nicht belegt.

# C5A8-Transfer stoppt – `0x7530`-Interblock-Timeout und C544-Recovery

Der bisher offene Fall „Firmwaretransfer beginnt, bleibt aber beispielsweise bei 50 % stehen und weder Sender noch Cancelpfad greifen ein“ ist für V3.3 statisch weitgehend geschlossen.

## Bedeutung des `0x7530`-Zählers

Im C5A8-Worker bei ungefähr `0x08078628` wird ein eigener Wartezähler nur dann erhöht, wenn der C5A8-Empfangszustand aktiv ist, aber kein neuer Datenblock zur Verarbeitung bereitsteht:

```text
state + 0x95 == 1    C5A8-Empfang/Warten aktiv
state + 0x8C == 0    kein neuer Datenblock vorhanden
state + 0x7AC++      Interblock-Wartezähler
```

Die Schwelle lautet:

```text
0x7530 = 30000 Worker-Aufrufe
```

Jeder verarbeitete gültige C5A8-Block setzt den Wartezähler wieder auf `0`. Damit ist `0x7530` kein Gesamt-OTA-Timeout, sondern ein **Timeout auf das Ausbleiben des nächsten C5A8-Datenblocks**.

Eine belastbare Umrechnung der 30000 Worker-Aufrufe in Sekunden ist weiterhin nicht belegt.

## Direkte Timeoutaktion

Beim Erreichen der Schwelle wird sinngemäß ausgeführt:

```text
state + 0x7AC = 0    Interblock-Zähler löschen
state + 0x95  = 0    aktiven C5A8-Wartezustand beenden
state + 0x96  = 1    Fallback-/Recoveryzustand setzen
0x20010AA0    = 1    nachgelagerten Fallbacktimer starten
```

In diesem Branch wurden **keine** direkten Aufrufe oder Flags für folgende Aktionen gefunden:

```text
kein C36A-Cancel
kein Staging-Erase
kein Target-Erase 0x08050000...
kein Image-Copy
kein MD5-Abschluss
kein Chain-Jump
kein MCU-Systemreset
```

Damit gilt:

> **C5A8-Timeout ist nicht identisch mit einem automatischen Cancel.**

## Nachgelagerter Fallbacktimer

Der OTA-Retry-/Control-Worker bei ungefähr `0x08076470` verarbeitet anschließend den gesetzten Fallbackzustand `state+0x96 == 1` und zählt `0x20010AA0` weiter.

Die dabei verwendete zweite Schwelle lautet:

```text
0x000249F0 = 150000 interne Aufrufe
```

Bei Erreichen dieser Schwelle wird unter anderem gesetzt:

```text
0x200133F8 + 0x14 = 1
```

Dieses Byte ist im Status-/Handshake-Scheduler eindeutig das **C544-Sendeflag**.

## C544 als Recovery-/Resynchronisationspfad

Der Warmlink-Sendescheduler prüft `0x200133F8+0x14`. Bei gesetztem Flag sendet er:

```text
Slave       0x63
FC          0x10
Register    0xC544
Quantity    13 Register
```

und löscht anschließend das Sendeflag wieder.

Damit ergibt sich der rekonstruierte V3.3-Pfad:

```text
C5A8-Transfer läuft
        ↓
kein weiterer Block
        ↓
0x7530 Interblock-Timeout
        ↓
C5A8-Wartezustand verlassen
        ↓
Fallbacktimer / 0x249F0
        ↓
C544-Softwareinfo senden
        ↓
Gegenstelle kann OTA-Zustand neu synchronisieren / Resume vorbereiten
```

C544 enthält die aktuelle Board-Softwareidentität und -version. Der originale LTE-Dienst `phnixIot4G` verwendet genau dieses Telegramm für seine bekannte Resume-Entscheidung. Der Modemdienst prüft dabei u. a. gespeicherten Offset, Dateilänge, Softwarecode und Zielversion und stößt bei gültigem Resume anschließend einen erneuten C350/C357-Handschlag an. Siehe [`PHNIX_phnixIot4G_C544_softcode_resume.md`](PHNIX_phnixIot4G_C544_softcode_resume.md).

## Abgrenzung zum echten C36A-Cancel

Der echte Cancelworker bei `0x08078D68` wird nur über das separate Cancel-Request-Flag:

```text
0x200133F8 + 0x1B = 1
```

aktiviert. Dieses Flag stammt aus dem C36A-RX-Pfad.

Der `0x7530`-Timeout setzt dieses Flag nicht. Er führt daher nicht automatisch die C36A-Aktionen aus, insbesondere nicht:

- EEPROM `0x3F0` auf 0 setzen,
- C36C-Cancelbestätigung vorbereiten,
- optionalen Staging-Erase ausführen.

## Zustand eines nur teilweise übertragenen Images

Ein bereits empfangener Teil der Firmware verbleibt zunächst im Stagingbereich ab:

```text
0x080A1000
```

Das aktuell laufende Mainimage bei:

```text
0x08050000
```

wird durch diesen Timeoutpfad nicht angefasst.

Die Promotion setzt einen vollständig abgeschlossenen C5A8-Transfer und die erfolgreiche erste MD5-Prüfung über das Stagingimage voraus. Ein halbes bzw. unvollständiges Image erreicht diesen Pfad nicht.

Damit wurde für den reinen Timeoutpfad kein Mechanismus gefunden, der ein unvollständiges Stagingimage:

- nach `0x08050000` kopiert,
- bootet,
- oder autonom zur Promotion freigibt.

## Wenn keine Gegenstelle mehr reagiert

Auch für den Extremfall:

```text
Transfer stoppt teilweise
kein C36A
kein Reboot
keine Gegenstelle reagiert auf C544
```

wurde aus dem `0x7530`-Pfad heraus kein autonomer destruktiver Folgepfad gefunden.

Statisch ergibt sich:

1. aktiver C5A8-Wartezustand endet,
2. C544 wird nach dem zweiten Fallbacktimer angefordert/gesendet,
3. vorhandene Teilblöcke bleiben im Stagingbereich,
4. das laufende Image bleibt unverändert,
5. kein automatischer Cancel, Erase, Copy, Jump oder Reset wird ausgelöst.

Ein neu eintreffender gültiger Warmlink-/Serviceframe löscht zudem den Fallbackzustand `state+0x96` wieder. Das passt zum vorgesehenen Rehandshake-/Resume-Verhalten.

**Bewertung: statisch bestätigt für den bekannten V3.3-Anwendungscode.**

# C36A / C36C – Cancel

C36A wird bei `0x08067D74` erkannt. Der RX-Handler setzt zunächst nur das Cancel-Flag `OTA+0x1B`.

Der Worker bei `0x08078D68`:

1. löscht das Cancel-Flag wieder,
2. beendet C5A8-/RX-Unterzustände,
3. beendet den aktiven C5A8-Wartezustand,
4. setzt EEPROM `0x3F0` auf `0` plus neue CRC,
5. bereitet C36C als Cancel-Bestätigung vor.

## Flash-Guard

Ein Flash-Erase wird nur aktiviert, wenn:

```text
OTA+0x1C == 1
```

Dieses Flag wird erst im C5A8-Worker bei ungefähr:

```text
0x0807873E–0x08078744
```

gesetzt, wenn `current_block >= total/last_block` gilt.

Damit:

```text
C36A vor jedem C5A8
→ OTA+0x1C = 0
→ kein Flash-Erase
```

## C36A nach einer abgeschlossenen Datenphase

Nur bei gesetztem Guard kann der Cancelpfad den Stagingbereich löschen:

```text
0x080A0000
0x080A1000
0x080A2000
...
0x080EB000
```

Dieser Zweig ist für den definierten Vorhandshake ohne C5A8 nicht erreichbar.

## C36C

Erwartet:

```text
Unit          0x63
Function      0x10
Startregister 0xC36C
Quantity      2
Payload       00 63 00 01
```

Kompletter RTU-Frame:

```text
63 10 C3 6C 00 02 04 00 63 00 01 75 40
```

# Erwartete C36E-Antworten

```text
Status 0:
63 10 C3 6E 00 02 04 00 63 00 00 35 59

Status 1:
63 10 C3 6E 00 02 04 00 63 00 01 F4 99

Status 2:
63 10 C3 6E 00 02 04 00 63 00 02 B4 98
```

# C37B und fehlendes ACK

Der C37B-Handler bei `0x08067EB6` verarbeitet nur Status:

```text
3, 4, 5, 6, 7
```

C36E 0/1/2 benötigen dort kein C37B-ACK.

Für Status 3–6 existiert ein Retrymechanismus mit:

```text
Retry-Schwelle: 30000 interne Aufrufe
Retryanzahl:    bis 15
```

## Statisch geklärt: `C37B/3` blockiert die Promotion nicht

Die zuvor offene Frage, ob das Mainboard nach `C36E Status 3` auf das zugehörige `C37B Status 3` warten muss, bevor Target-Erase/Copy beginnen, ist jetzt statisch beantwortet:

> **Nein. `C37B/3` ist nur ACK/Retry für die Statusmeldung und kein Promotion-Gate.**

Nach MD5 #1 erfolgreich setzt der C5A8-Abschlusspfad bereits den internen OTA-Status auf `3` und fordert C36E Status 3 an. Der Statussender setzt dabei:

```text
0x20010AB4 = 1
```

als ACK-/Retry-Flag.

Der status-3-spezifische C37B-Empfangspfad löscht nur:

```text
0x20010AB4 = 0
```

Er startet weder den Promotionworker noch setzt er einen Erase-/Copy-State.

Die Adresse `0x20010AB4` wird im bekannten V3.3-Image nur im C36E-Sender, C37B-Empfänger und Status-Retrypfad verwendet. Der Promotionworker `0x080770EC` referenziert dieses Flag nicht und wird unabhängig davon zyklisch aus dem normalen Scheduler aufgerufen.

Damit gilt:

```text
C36E Status 3 gesehen
!= sicherer Wartezustand

C37B/3 fehlt
!= Promotion gestoppt
```

Das ist für einen reinen C350/C357-Vortest zwar nicht direkt erreichbar, bestätigt aber die bisher konservativ gewählte Grenze **vor C5A8**.

# Neustartverhalten

## nach C350 Status 0

Kein durch C350 neu geschriebener persistenter OTA-State. Ein normaler Neustart beginnt wieder normal. Status 0 löscht jedoch nicht garantiert ältere, bereits vorher vorhandene persistente OTA-Records.

## nach C350 Status 1 ohne C357

Nur RAM-State. Ein Neustart verwirft die angebotene Ziel-/Buildkennung und startet ohne diesen Pending-C350-Zustand.

## nach C357

EEPROM `0x3F0=1+CRC` bleibt bestehen. Beim Boot wird der Pending-/Re-Handshake-Zustand erkannt, aber dadurch weder Flash programmiert noch direkt auf einen anderen Vector gesprungen.

## nach frühem C36A

EEPROM `0x3F0` wird auf 0 plus gültige CRC gesetzt. Der Pending-Zustand ist persistent beendet.

# Normalbetrieb während des Vorhandshakes

C350/C357/C36A sind Schedulerpfade innerhalb der normalen Anwendung. Für diese frühen Zustände wurden keine direkten Writer gefunden, die:

- Wärmepumpe stoppen,
- Verdichterfreigabe löschen,
- Regel-State-Machines deaktivieren,
- auf `0x08000000` oder `0x08050000` springen,
- einen MCU-Systemreset auslösen.

Die normale Main-App und Kommunikation laufen bis zur späteren Flash-/Promotionphase weiter.

## Kommunikationsausfall ist kein Notstopp

Die separat analysierten ~420-s-Watchdogs im LTE-Dienst `phnixIot4G` ändern diese Bewertung nicht. Bei ausbleibender normaler Mainboard-/RS485-Kommunikation werden Error-Bits gesetzt und teilweise aktive Healthchecks ausgelöst; ein automatischer Reboot nach ungefähr sieben Minuten ist dafür nicht belegt.

Damit darf ein geplanter OTA-Abbruch **nicht** darauf bauen, dass das LTE-Modem oder der Mainboard-Pfad nach Ausfall der normalen Kommunikation selbständig rebootet und dadurch eine Promotion stoppt.

Siehe [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md).

# Erreichbare destruktive Funktionen und Guards

| Funktion | vor C5A8 erreichbar? | Guard |
|---|---|---|
| EEPROM `0x3F0` setzen durch C357 | ja | gültige C357-Metadaten |
| EEPROM `0x3F0` löschen durch C36A | ja | C36A |
| Staging-Flash schreiben | **nein** | C5A8-Datenworker |
| Staging-Flash löschen via C36A | **nein** | `OTA+0x1C == 1` |
| Imagebereich `0x08050000` löschen/kopieren | **nein** | spätere MD5-/Commit-State-Machines |
| Jump `0x08050000` | **nein** | spätere Bootflags |
| Jump `0x08000000` | **nein** | später Transition-/Role-State |
| Systemreset | kein Vorhandshakepfad gefunden | – |

# Risikobewertung

| Test / Fehlerfall | Firmware-Flash | EEPROM | Jump/Reset | Risiko |
|---|---|---|---|---|
| C350 identische V3.3-Kennung | nein | nein | nein | **sehr niedrig** |
| C350 inkompatibles Ziel | nein | nein | nein | **sehr niedrig** |
| C350 kompatibel, anderer Build | nein | nein | nein | **niedrig** |
| C357 ohne C5A8 | nein | **ja, `0x3F0`** | nein | **niedrig bis moderat** |
| C5A8-Transfer teilweise, dann Timeout | **ja, nur Stagingbereich** | Pending-/Resume-State bleibt möglich | **kein autonomer Jump/Reset gefunden** | **moderat, Recovery/Resume vorgesehen** |

# Empfohlener minimaler ser2net-Vortest

## Stufe 1

```text
C350 mit identischer aktueller Kennung
→ C36E Status 0
→ STOP
```

Kein C357, kein C36A, kein C37B.

## Stufe 2

```text
C350 mit gleichem Ziel, anderem Build
→ C36E Status 1
C36A
→ C36C
STOP
```

Solange kein C5A8 gesendet wurde, ist der Flash-Guard nicht gesetzt.

## Stufe 3

```text
C350 kompatibel/anderer Build
→ C36E 1
C357 gültige Länge+MD5
→ C36E 2
KEIN C5A8
C36A
→ C36C
STOP
```

# Harte Stopbedingungen

Sofort nichts weiter senden, falls:

- irgendein C5A8 auftaucht oder vorbereitet wurde,
- ein C36E-Status > 2 erscheint,
- C36C nach Cancel ausbleibt,
- das Gerät unerwartet rebootet,
- reguläre Modbus-/Warmlink-Kommunikation aussetzt,
- ein unbekanntes OTA-Kommando eine weitere Phase startet,
- die 12-Byte-Kennung nicht exakt dem zuvor passiv bestimmten Ziel entspricht.

**Wichtig zu Status 3:** Falls entgegen der Testplanung `C36E Status 3` erscheint, nichts mehr senden und insbesondere **nicht** davon ausgehen, dass das Weglassen von `C37B/3` den Flashpfad anhält. Status 3 bedeutet, dass die sichere Vortestgrenze bereits überschritten wurde.

Für einen maximal konservativen ersten Test bleibt:

```text
C350 identisch → C36E 0 → STOP
```

die bevorzugte Grenze.

## Weiterführende Promotion-/Recoveryanalyse

Der vollständige Pfad nach C5A8 einschließlich Status-3-ACK/Retry, Target-Erase, zweiter MD5-Prüfung, EEPROM-Role-/Transition-State, Loader-Handoff und Power-Loss-Matrix ist separat dokumentiert:

[`FW3.3-OTA-PROMOTION-RECOVERY.md`](FW3.3-OTA-PROMOTION-RECOVERY.md)

Die C544-Seite des originalen LTE-Dienstes einschließlich Softwareinfo, Resume-Vergleich und erneutem C350/C357-Handschlag ist separat dokumentiert:

[`PHNIX_phnixIot4G_C544_softcode_resume.md`](PHNIX_phnixIot4G_C544_softcode_resume.md)
