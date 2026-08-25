# Mainboard-Firmware V3.3 – Warmlink/LTE Modbus-Dispatcher Slave 0x63

Stand: 24. August 2026

Diese Datei dokumentiert den separaten Modbus-Slave-/Servicepfad der Mainboard-Firmware V3.3, der auf dem Warmlink-/LTE-RS485-Anschluss mit Slave-Adresse `0x63` erreichbar ist.

Der wichtigste Befund ist die klare Trennung vom direkten User-/Mainboard-Modbus:

> **Der Warmlink-/LTE-Slave `0x63` ist kein transparenter Proxy auf den direkten Mainboard-Dispatcher. Er besitzt eine eigene Register- und Function-Code-Matrix.**

Diese Trennung erklärt die Livebeobachtung, dass `MAIN:1334` und `MAIN:2133` über LTE erreichbar sind, `ENG:CTRL:8801` dagegen nicht.

Untersuchtes Mainboard-Binary:

```text
Softwarecode: 82400644
Firmware:     V3.3
Imagebasis:   0x08050000
MD5:          CEB6A4BF386FF644E23E410023E74673
```

---

# 1. Physischer Kanal

Warmlink-/Servicepfad:

```text
USART1 = 0x40013800
Baud    = 9600
Format  = 8N1
TX      = PA9
RX      = PA10
Slave   = 0x63
```

Der interne Boardbus ist davon getrennt:

```text
USART3
4800 8N1
PB10/PB11
PE6 DE/RE
```

Damit sind Warmlink-/LTE-Bus und interner Display-/Inverterring physisch unterschiedliche serielle Kanäle.

---

# 2. Separater 0x63-Dispatcher

Die große Warmlink-/Service-Dispatcherfunktion liegt ungefähr bei:

```text
0x08067548
```

Sie ist nicht identisch mit dem direkten Mainboard-/Engineeringdispatcher um ungefähr:

```text
0x080664C8
```

Dies ist für die Interpretation der Registerrechte entscheidend.

---

# 3. Normale FC03-Bereiche des 0x63-Dispatchers

Statisch bestätigt:

```text
1001–1540
2001–2180
8001–8090
```

Dazu kommen einzelne Spezialreads, die nicht als gewöhnliche lineare Registerbereiche behandelt werden sollten.

## Konsequenz für reale Tests

```text
0x63 / FC03 / 1334 -> gültig
weil 1334 in 1001–1540 liegt

0x63 / FC03 / 2133 -> gültig
weil 2133 in 2001–2180 liegt

0x63 / FC03 / 8801 -> nicht im Dispatcherbereich
```

Der reale Test bestätigte genau dieses Verhalten:

```text
1334 lesen -> funktioniert
2133 lesen -> funktioniert
8801 lesen -> Timeout / 0 Byte RX
```

**Bewertung: statisch + live bestätigt.**

---

# 4. Normale FC06-Bereiche des 0x63-Dispatchers

Statisch bestätigt:

```text
1001–1540
8001–8090
```

Der 1xxx-Bereich besitzt zusätzliche Parameter-/Validierungslogik.

Wichtig:

```text
8801–8820
```

gehört auch beim FC06-Pfad nicht zum normalen Warmlink-`0x63`-Engineeringbereich.

---

# 5. Normale FC10-Bereiche des 0x63-Dispatchers

Statisch bestätigt sind mindestens:

```text
1001–1540
5091–5180
7001–7090
7091–7180
8001–8090
```

Dazu kommen spezielle OTA-/Serviceadressen im `0xCxxx`-Namespace.

Nicht enthalten:

```text
8801–8820
```

Damit schreibt der rekonstruierte normale `0x63`-FC10-Pfad **nicht** in das direkte Engineering-Control-Fenster `0x20016970`.

---

# 6. Der reale FC16-Test auf 8801

Gesendet wurde am Warmlink-/LTE-Bus:

```text
63 10 22 61 00 01 02 00 02 9C 80
```

Dekodiert:

```text
Slave  = 0x63
FC     = 0x10
Start  = 0x2261 = 8801
Qty    = 1
Value  = 2
```

Der Logger beobachtete einen formal passenden ACK auf:

```text
Slave 0x63
FC10
Start 8801
Qty 1
```

Gleichzeitig ergab der Cross-Bus-Gegencheck keinen belastbaren Nachweis, dass das echte direkte User-Modbus-Register `8801` dadurch verändert wurde.

Die statische Analyse erklärt nun, warum:

> `8801` ist im normalen FC10-Dispatcher von Slave `0x63` nicht enthalten.

Daher gilt:

- der beobachtete ACK ist **kein Beweis für Apply auf ENG:CTRL:8801**,
- seine genaue Quelle/Bedeutung bleibt separat offen,
- möglich sind zusätzliche Proxy-/Gatewaypfade oder anderes Busverhalten außerhalb des hier rekonstruierten normalen Mainboardhandlers,
- für SG Ready ist der direkte User-/Mainboard-Modbus der bestätigte `8801`-Pfad.

---

# 7. Warmlink-spezifisches Fenster 8001–8090

Dieses Fenster ist real und darf nicht mit `8801–8820` verwechselt werden.

```text
WARMLINK:SVC 8001–8090
Backing RAM: 0x20015EF0
```

Der `0x63`-Dispatcher unterstützt für dieses Fenster:

```text
FC03 = ja
FC06 = ja
FC10 = ja
```

Bekannte Spiegelungen in öffentliche V3.3-Statusregister:

```text
2151 <- Teil-/Statuspfad aus 8001
2153 <- 8002
2156 <- 8003
2154 <- 8004
2155 <- 8005
2157 <- 8007
2158 <- 8008
```

Register `8006` besitzt eine Änderungserkennung mit einem internen Timer von 150 Zyklen.

Die vollständige physikalische/Herstellersemantik des Subsystems bleibt offen.

---

# 8. Zwei unterschiedliche 8xxx-Namespaces

Die wichtigste Namensregel lautet:

```text
WARMLINK:SVC:8001–8090
    = eigener Service-/Statusblock des Slave-0x63-Dispatchers

ENG:CTRL:8801–8820
    = direkter Mainboard-/User-Engineering-Control-Block
```

`ENG:CTRL:8801` ist der inzwischen live bestätigte virtuelle SG-Ready-Befehl:

```text
1 = Mode 1
2 = Mode 2
3 = Mode 3
4 = Mode 4
```

Aber dieser `8801`-Block ist im normalen Warmlink-0x63-Dispatcher nicht freigegeben.

---

# 9. FC10-Servicefenster 5091 / 7001 / 7091

## 5091–5180

```text
FC10 = unterstützt
```

Ein 90-Wort-Konfigurations-/Synchronisationsfenster. Der direkte Engineeringdispatcher kennt denselben nummerischen Bereich ebenfalls, jedoch mit eigenen Rechten und Zustandsflags.

## 7001–7090

```text
FC10 = unterstützt
```

Der Beginn dieses Fensters ist als persistente Device-ID-Provisionierung
rekonstruiert. Akzeptiert wird exakt Startregister 7001 mit zehn Wörtern:

```text
7001 = 0x00AA   Marker
7002 = 0x005A   Marker
7003–7008       sechs Device-ID-Wörter
7009–7010       zwei reservierte Paketkopfwörter
```

Nach Prüfung von Function Code, Start, Menge, Bytecount und Markern werden die
acht Nutzwörter in den autoritativen RAM-Kopf bei `0x20016B50` übernommen. Der
nachgelagerte Persistenzpfad schreibt sie in ein externes 24C16-kompatibles
EEPROM. Die Semantik des übrigen Fensters 7011–7090 bleibt offen. Details:
[Device-ID, EEPROM und Provisionierung](PHNIX_phnixIot4G_device_identity_block.md).

## 7091–7180

```text
FC10 = unterstützt
```

Warmlink-/Service-Transferfenster B. Adressierung bestätigt, fachliche Einzelbedeutung noch offen.

Diese 7xxx-Bereiche gehören nicht in die normale User-Registerliste.

---

# 10. OTA-/Service-Namespace 0xCxxx

Der gleiche Slave-`0x63`-Kontext besitzt spezielle OTA/IAP-Handler, unter anderem für bekannte Adressen wie:

```text
0xC350
0xC357
0xC36C
0xC36E
0xC371
0xC378
0xC544
0xC5A8
```

Die vollständige OTA-Semantik ist in den eigenen OTA-Dokumenten maßgeblich.

Wichtig ist hier nur:

> Dass normale MAIN-Register und OTA-Register denselben Slave `0x63` benutzen können, bedeutet nicht, dass `0x63` ein transparenter Durchgriff auf alle direkten Mainboardregister ist.

---

# 11. Vergleich der beiden Mainboard-Slavedispatcher

| Bereich | direkter User-/Mainboarddispatcher | Warmlink/LTE `0x63` |
|---|---|---|
| 1001–1540 | FC03/FC06*/FC10 | FC03/FC06/FC10 |
| 2001–2180 | Status/read | FC03 |
| 5001–5090 | FC03/FC06/FC10 | kein normaler Bereich bestätigt |
| 5091–5180 | FC03 stateful / FC10 | FC10 |
| 6001–6090 | FC03 | kein normaler Bereich bestätigt |
| 7001–7090 | – | FC10 |
| 7091–7180 | – | FC10 |
| 8001–8090 | – | FC03/FC06/FC10 |
| 8801–8820 | FC03/FC06/FC10 | **nicht im normalen Dispatcher** |
| 60000 | direkter Sonder-FC06 | nicht als normaler 0x63-Pfad belegt |
| 60010 | direkter UID-Sonderpfad | nicht als normaler 0x63-Pfad belegt |
| 0xCxxx | – | OTA-/Service-Sonderhandler |

\* Direkter FC06 schützt die sechs Paketkopfblöcke.

---

# 12. Konsequenz für FoxAir_Control

Das Backendmodell darf Registerrechte nicht nur nach Registernummer bestimmen.

Mindestens erforderlich:

```text
backend / transport
slave
namespace
register
function-code rights
```

Konkret:

```text
User/Mainboard Modbus + 8801
    -> R/W erlaubt und live bestätigt

Warmlink/LTE 0x63 + 8801
    -> nicht als funktionaler R/W-Pfad freigeben

Warmlink/LTE 0x63 + 1334
    -> R/W bestätigt

Warmlink/LTE 0x63 + 2133
    -> R bestätigt
```

Ein empfangener Schreib-ACK sollte bei Proxy-/Servicepfaden nicht automatisch als semantischer Apply-Nachweis gelten, wenn der Zielwert über einen unabhängigen Pfad überprüfbar ist.

---

# 13. Abschlussstatus

| Punkt | Status |
|---|---|
| separater 0x63-Dispatcher | **bestätigt** |
| USART1 / 9600 / PA9-PA10 | **bestätigt** |
| FC03 1001–1540 | **bestätigt** |
| FC03 2001–2180 | **bestätigt + live** |
| FC03 8001–8090 | **bestätigt** |
| FC06 1001–1540 | **bestätigt** |
| FC06 8001–8090 | **bestätigt** |
| FC10 1001–1540 | **bestätigt** |
| FC10 5091–5180 | **bestätigt** |
| FC10 7001–7090 | **7001/10 als Device-ID-Provisionierung bestätigt; Restsemantik offen** |
| FC10 7091–7180 | **bestätigte Adressierung** |
| FC10 8001–8090 | **bestätigt** |
| 8801 fehlt im normalen 0x63-Dispatcher | **bestätigt + Live-Timeout konsistent** |
| reale Quelle des gesehenen 8801-FC16-ACK | **offen** |

Damit ist die zuvor scheinbar widersprüchliche Beobachtung `1334/2133 funktionieren über LTE, 8801 aber nicht` durch die Firmwarearchitektur erklärt.
