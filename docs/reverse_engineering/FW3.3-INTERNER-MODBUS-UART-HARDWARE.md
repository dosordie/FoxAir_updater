# Mainboard-Firmware V3.3 – interner Modbus: USART-, GPIO- und RS485-Hardware

Stand: 24. August 2026

Diese Datei verfolgt den in [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) rekonstruierten internen Modbus-Ring bis auf die STM32-Peripherie und GPIO-Pins des FoxAir-/PHNIX-Regelmainboards zurück.

Untersuchtes Binary:

```text
Produkt-/Softwarekennung: 82400644
Firmware:                 V3.3
Größe:                    287598 Byte
MD5:                      CEB6A4BF386FF644E23E410023E74673
SHA-256:                  6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A
Imagebasis:               0x08050000
```

---

# 1. Kurzfazit

Der interne Kommunikationsring, über den das Mainboard die Teilnehmer

```text
0x01  Verdichter-/Leistungs-/Inverterboard
0x02  optionaler HMI-Kanal
0x03  DWIN-/Wire-Controller
0x04  separater Fan-Driver-Pfad
0x05  Hydraulik-/Erweiterungsmodul
0x61  alternative H30-Modulvariante
```

anspricht, läuft auf dem STM32 über:

```text
USART3 = 0x40004800
Baud    = 4800
Format  = 8N1
TX      = PB10
RX      = PB11
RS485 DE/RE = PE6
```

Der Direction-Pin arbeitet:

```text
vor TX:   PE6 = 1
nach TX:  PE6 = 0
```

Damit ist der interne Boardbus bis zum MCU-Pin geschlossen.

Besonders wichtig:

> Der bekannte Mainboard-Slave-/Servicepfad mit Adresse `0x63` benutzt **nicht USART3**, sondern eine separate USART1-State-Machine. Der interne Leistungs-/Displaybus und der Warmlink-/Servicepfad sind damit nicht nur logisch, sondern auch hardwareseitig getrennte serielle Kanäle.

**Bewertung: bestätigt.**

---

# 2. USART3-Initialisierung

Die Initialisierungsroutine des relevanten UART liegt bei:

```text
0x08050794
```

Sie wird beim Systemstart aus der zentralen Hardwareinitialisierung um:

```text
0x08075BDE
```

aufgerufen.

Die Routine konfiguriert explizit:

```text
USART3 = 0x40004800
```

und setzt den Baudratenwert:

```text
0x12C0 = 4800
```

Der Baudratenhelper schreibt daraus den USART-BRR-Wert.

**Bewertung: bestätigt.**

---

# 3. Datenformat 8N1

Nach der Baudrate setzt die Initialisierungsroutine die USART-CR1/CR2/CR3-Felder über die Low-Level-Helper.

Die verwendeten Argumente ergeben:

```text
8 Datenbits
keine Parität
1 Stopbit
Receiver enabled
Transmitter enabled
USART enabled
```

Damit:

```text
4800 Baud, 8N1
```

**Bewertung: bestätigt.**

---

# 4. TX/RX-Pins: PB10 und PB11

Vor der USART3-Aktivierung konfiguriert `0x08050794` GPIOB:

```text
GPIOB = 0x40010C00
```

## PB10

Pinmaske:

```text
0x0400 = PB10
```

Konfiguration:

```text
GPIO_Mode_AF_PP
GPIO_Speed_50MHz
```

Damit ist:

```text
PB10 = USART3_TX
```

## PB11

Pinmaske:

```text
0x0800 = PB11
```

Konfiguration:

```text
GPIO_Mode_IN_FLOATING
```

Damit ist:

```text
PB11 = USART3_RX
```

Es wird also die normale/default STM32F1-USART3-Pinbelegung benutzt; eine Remap-Belegung über PC10/PC11 oder PD8/PD9 ist für diesen Pfad nicht aktiv.

**Bewertung: bestätigt.**

---

# 5. RS485-Richtungssteuerung PE6

Die gleiche Initialisierungsroutine konfiguriert:

```text
GPIOE = 0x40011800
Pin    = 0x0040 = PE6
Mode   = Push-Pull Output
```

PE6 taucht anschließend direkt in der TX-State-Machine des Kommunikationskontexts `0x20014BE4` auf.

## Vor dem Senden

Um:

```text
0x080537D4
```

wird aufgerufen:

```text
GPIOE->BSRR = 0x0040
```

Der zugrunde liegende Helper `0x08089CF0` schreibt direkt in GPIO `BSRR` (`+0x10`).

Damit:

```text
PE6 = 1
```

## Nach dem Senden / im Empfangszustand

Um:

```text
0x080538E4
```

wird aufgerufen:

```text
GPIOE->BRR = 0x0040
```

Der Helper `0x08089CF4` schreibt in GPIO `BRR` (`+0x14`).

Damit:

```text
PE6 = 0
```

Die Funktion entspricht exakt der üblichen RS485-Halbduplex-Richtungssteuerung:

```text
PE6 high → Transmitter freigeben
PE6 low  → Empfang / Sender deaktiviert
```

Die physische Verdrahtung zu `DE` und ggf. gemeinsamem `/RE` des RS485-Transceivers ist damit **sehr wahrscheinlich**; die MCU-Seite der Direction-Control ist direkt bestätigt.

---

# 6. TX-State-Machine des internen Busses

Der gemeinsame Kommunikationskontext liegt bei:

```text
0x20014BE4
```

Der Modbus-Request-Builder `0x080695F0` schreibt den fertigen RTU-Frame ab ungefähr:

```text
0x20014BE4 + 0x09
```

und hinterlegt die Frame-Länge bei:

```text
0x20014BE4 + 0x1E9
```

Anschließend setzt er ein Sendeflag bei:

```text
0x20014BE4 + 0x02
```

Die TX-State-Machine um:

```text
0x08053784 … 0x080538E2
```

macht daraus:

```text
Sendeflag
   ↓
PE6 = 1
   ↓
USART3-TX-ready prüfen
   ↓
Frame byteweise aus 0x20014BE4+9 senden
   ↓
TX complete abwarten
   ↓
PE6 = 0
   ↓
Empfangszustand
```

Der Byte-Sendehelper `0x0808AE6C` schreibt direkt in:

```text
USARTx->DR
```

und wird hier mit:

```text
USART3 = 0x40004800
```

aufgerufen.

**Bewertung: bestätigt.**

---

# 7. RX-State-Machine

Nach Rückschaltung von PE6 liest dieselbe Kommunikationsroutine Bytes über:

```text
USART3->DR
```

in den RX-Bereich des Kontexts `0x20014BE4`.

Der ReceiveData-Helper liegt bei:

```text
0x0808AE74
```

Die Routine sammelt die Antwort byteweise, prüft Länge/CRC und übergibt gültige Frames anschließend an die bereits rekonstruierte Modbus-Antwortverarbeitung.

Damit ist die komplette physische Richtung geschlossen:

```text
PB10 / USART3_TX
        ↓
RS485-Transceiver
        ↓
interner A/B-Bus
        ↓
Remote-Board
        ↓
RS485-Transceiver
        ↓
PB11 / USART3_RX
```

PE6 steuert dabei die Halbduplex-Richtung.

---

# 8. Verbindung zur Modbus-Scheduler-State-Machine

Der logische Scheduler bei:

```text
0x08064C40 … 0x08064FC6
```

ruft den Builder:

```text
0x080695F0
```

auf.

Dieser legt den Frame in `0x20014BE4` ab.

Daraus folgt die vollständig geschlossene Provenance:

```text
Scheduler-State
      ↓
Slave / FC / Startregister / Anzahl
      ↓
0x080695F0 Modbus-Builder
      ↓
0x20014BE4 TX-Frame
      ↓
PE6 = 1
      ↓
USART3 / PB10
      ↓
RS485
      ↓
0x01 / 0x02 / 0x03 / 0x04 / 0x05 / 0x61
      ↓
RS485
      ↓
USART3 / PB11
      ↓
0x20014BE4 RX
      ↓
Antwortparser
```

**Bewertung: bestätigt.**

---

# 9. Konsequenz für Messungen am realen Mainboard

Für einen Oszilloskop-/Logic-Analyzer-Test sind nun die MCU-Seite und das erwartete Protokoll bekannt:

```text
USART3 TX: PB10
USART3 RX: PB11
Direction: PE6
Baud:      4800
Format:    8N1
```

Am eigentlichen RS485-Transceiver sollte sich daher verfolgen lassen:

```text
PB10 → DI
PB11 ← RO
PE6  → DE und/oder /RE
A/B  → interner Boardbus
```

Die letzten drei Pfeile sind die erwartete Transceiver-Topologie und müssen am konkreten PCB noch durch Leiterbahnverfolgung bestätigt werden.

Ein passiver Mitschnitt auf A/B benötigt natürlich keine Manipulation von PE6.

---

# 10. Der 0x63-Service-/OTA-Pfad ist ein anderer UART

Eine zweite Kommunikations-State-Machine verwendet einen anderen Laufzeitbereich und sendet/empfängt über:

```text
USART1 = 0x40013800
```

In dieser Routine wird bei empfangenen Frames ausdrücklich die Slave-Adresse:

```text
0x63 = 99
```

geprüft.

Die relevante Empfangsprüfung liegt ungefähr bei:

```text
0x08053AE0
```

und führt danach in den bekannten 0x63-Service-/Mainboard-Slavepfad.

USART1 wird separat initialisiert; der Baudratenwert lautet:

```text
0x2580 = 9600 Baud
```

Die regulären USART1-Pins werden als:

```text
PA9  = TX
PA10 = RX
```

konfiguriert.

Damit gilt:

```text
interner Board-Masterbus:
    USART3 / PB10 / PB11 / 4800 Baud

Mainboard Service-/OTA-Slavepfad 0x63:
    USART1 / PA9 / PA10 / 9600 Baud
```

Diese Trennung ist besonders wichtig für die bisherigen Warmlink-/OTA-Analysen: die Adresse `0x63` gehört nicht als weiterer Teilnehmer in den USART3-Boardring.

**Bewertung: bestätigt** für UART, Baudrate und Slave-Prüfung.

Die komplette DE/RE-Verdrahtung des USART1-Transceivers wird in dieser Datei nicht weiter verfolgt, da der Fokus auf dem internen Leistungs-/Displaybus liegt.

---

# 11. Weitere serielle Schnittstellen der V3.3

Die Firmware initialisiert zusätzlich:

```text
USART2 = 0x40004400  @ 9600 Baud
UART4  = 0x40004C00  @ 9600 Baud
```

Diese gehören zu weiteren Kommunikations-/Gerätepfaden und sind **nicht** der hier analysierte interne Unit-0x01/03/04/05-Ring.

Ihre vollständige physische Funktion wird separat verfolgt, falls für die Gesamtarchitektur benötigt.

---

# 12. Praktischer Boardbus-Fingerabdruck

Ein Analyzer auf dem USART3-RS485-Paar sollte bei der untersuchten H33-Konfiguration zyklisch unter anderem sehen:

```text
03 03 0B B9 00 15 ...      Unit 3 HMI lesen
02 03 0B B9 00 15 ...      Unit 2 optionales HMI lesen
00 10 07 D1 00 5A ...      Broadcast 2001–2090
00 10 08 2B 00 5A ...      Broadcast 2091–2180
04 03 03 F3 00 0E ...      separaten Fan-Driver lesen
01 10 07 CF 00 10 ...      Unit 1: 16 Sollwörter schreiben
01 03 08 33 00 33 ...      Unit 1: 51 Rückmeldewörter lesen
05 03 07 D0 00 5A ...      Hydraulikpfad lesen
05 10 03 E9 00 5A ...      Hydraulikpfad schreiben
```

bei:

```text
4800 Baud, 8N1
```

Das ist ein sehr spezifischer Fingerabdruck des internen FoxAir-Boardbusses.

---

# 13. Noch offen

Für eine vollständig physische Dokumentation fehlen nur noch:

1. RS485-Transceiver-Typ auf dem Mainboard,
2. Leiterbahnzuordnung PB10/PB11/PE6 → DI/RO/DE-/RE,
3. Stecker-/Klemmen-Pins des internen A/B-Busses,
4. Board-P/N des Unit-0x01-Leistungsboards,
5. Zuordnung der A/B-Leitung auf dem zweiten Leistungsboard,
6. ggf. Abschluss-/Bias-Widerstände und deren Position.

Diese Punkte benötigen entweder PCB-Fotos/Leiterbahnverfolgung oder Schaltplaninformationen; die Firmwareseite ist jetzt bis zu den MCU-Pins geschlossen.

---

# 14. Verwandte Dokumente

- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) – Slave-Adressen, Scheduler und Boardrollen
- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md) – Kompressortransport über Unit 0x01
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) – Lüfterregler und Fan-Soll-/Istwerte
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) – Oil-Return-Sonderfrequenz

