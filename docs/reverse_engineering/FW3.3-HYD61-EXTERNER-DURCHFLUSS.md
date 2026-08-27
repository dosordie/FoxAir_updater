# Mainboard-Firmware V3.3 – HYD61 und externer Wasserdurchfluss

Stand: 27. August 2026

Dieses Dokument konzentriert sich auf den in `82400644 / V3.3` bestätigten externen Wasserdurchflusspfad über das interne Hydraulikmodul Unit `0x61`.

Ausführliche Pumpenregelung:

- [`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md)

Interne Modbusarchitektur:

- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md)

---

# 1. Ergebnis

V3.3 kann einen von einem externen Hydraulikmodul gelieferten Wasserdurchfluss direkt als autoritativen Durchflusswert benutzen.

Der Pfad wird aktiviert, wenn:

```text
MAIN:1036 / H30 == 3
```

und das externe Hydraulikmodul einen gültigen Durchfluss meldet.

Bestätigte Felder:

| Namespace | Register | Bedeutung | Skalierung |
|---|---:|---|---|
| `HYD61` | `2047` | Gültigkeits-/Vorhandenflag für externen Durchfluss | `0` ungültig, `!=0` gültig |
| `HYD61` | `2048` | externer Wasserdurchfluss | `raw/100 m³/h` |

Die offizielle PHNIX-Bezeichnung von HYD61:2047 ist noch unbekannt; die Gate-Funktion ist direkt im Binary bestätigt.

---

# 2. Firmwareentscheidung

Die relevante Durchflussroutine liegt ungefähr bei:

```text
VA 0x08061790
```

Die Auswahl des externen Pfades liegt ungefähr ab:

```text
VA 0x08061820
```

Sinngemäß:

```c
if (H30 == 3 && hyd61_flow_valid != 0) {
    base_flow = hyd61_flow;
} else {
    base_flow = calculate_flow_from_local_pump_pwm();
}
```

Runtime:

```text
0x20015C68 + 0x108 = hyd61_flow_valid
0x20015C68 + 0x10C = hyd61_flow
```

Der externe Wert wird direkt in den normalen Durchfluss-Datenpfad übernommen.

---

# 3. Herkunft der beiden Runtimefelder

Der Writer liegt im RX-Parser des internen Hydraulikmodul-Dialogs.

Bei `H30=3` fragt das Mainboard:

```text
Slave: 0x61
Function: 03
Start: 2001
Quantity: 90
```

ab.

Nach Berücksichtigung des Headers des internen RX-Abbilds ergibt sich:

```text
Remote 2047 -> 0x20015C68+0x108
Remote 2048 -> 0x20015C68+0x10C
```

Damit ist die Registerzuordnung bytegenau geschlossen.

---

# 4. Skalierung

HYD61:2048 wird ohne weitere Skalierung als Basiswert des normalen Durchfluss-Runtimepfades verwendet.

Der öffentlich sichtbare Durchfluss ist:

```text
MAIN:2077 raw / 100 = m³/h
```

Daher gilt auch für HYD61:2048:

```text
HYD61:2048 raw / 100 = m³/h
```

Beispiele:

```text
HYD61:2048 = 40  -> 0,40 m³/h
HYD61:2048 = 64  -> 0,64 m³/h
HYD61:2048 = 125 -> 1,25 m³/h
```

---

# 5. MAIN:1022 wird auch auf den externen Wert angewendet

MAIN:1022 ist ein signed Durchfluss-Korrekturoffset:

```text
1 raw = 0,01 m³/h
```

Für den externen Pfad gilt sinngemäß:

```text
wenn HYD61:2048 == 0:
    effective_flow = 0
sonst:
    effective_flow = HYD61:2048 + signed(MAIN:1022)
```

Bei einem Ergebnis kleiner 1 raw wird der wirksame Durchfluss auf 0 gesetzt.

Im Gegensatz zum lokalen H31/PWM-Pfad wird der externe H30=3-Durchfluss danach nicht gegen die lokale pumpenspezifische H31-Qmax-Tabelle begrenzt.

---

# 6. Externe Einspeisung ist technisch möglich

Ein eigener RS485-Teilnehmer könnte Unit `0x61` emulieren und so einen extern gemessenen Durchfluss einspeisen.

Für den reinen Durchflussdatenpfad wären mindestens erforderlich:

```text
MAIN:1036 / H30 = 3

Mainboard -> Emulator:
61 03 07 D1 00 5A ...
          ^2001   ^90 words

Emulatorantwort:
HYD61:2047 != 0
HYD61:2048 = externer Durchfluss x100
```

Beispiel:

```text
realer Wärmemengenzähler meldet 0,62 m³/h
-> HYD61:2048 = 62
```

Die Mainboard-Firmware würde diesen Wert dann anstelle der lokalen Pumpen-PWM-Kennlinie für den Durchfluss verwenden.

---

# 7. Warum ein 2-Register-Minimalemulator noch nicht sicher ist

`H30=3` ist kein isolierter Schalter für den Durchflusssensor.

Der interne Scheduler schaltet die Hydraulikkommunikation vollständig auf Unit `0x61`:

```text
RX:
Slave 0x61
FC03
Start 2001
Qty 90

TX:
Slave 0x61
FC10
Start 1001
Qty 90
```

Zusätzlich lesen zahlreiche andere Runtimehelper bei H30=3 Daten aus derselben externen Struktur `0x20015C68`.

Bestätigte bzw. aktive Offsetbereiche umfassen unter anderem:

```text
+0x1C
+0x24
+0x28
+0x6A
+0x70
+0x76
+0x7C
+0x82
+0x88
+0x108
+0x10C
```

Ein Emulator, der ausschließlich 2047 und 2048 sinnvoll füllt und alle anderen 88 Wörter mit 0 beantwortet, könnte daher andere Sensor-/I/O-/Hydraulikwerte verfälschen.

**Folge:** Vor einem Live-Test muss der minimal erforderliche vollständige HYD61-Antwortsatz für die konkrete Anlagenkonfiguration rekonstruiert werden.

---

# 8. Kein normaler MAIN-/ENG-Direktwrite gefunden

Der externe Runtimewert:

```text
0x20015C68+0x10C
```

wird im untersuchten Build durch den HYD61-RX-Parser beschrieben.

Bisher wurde kein direkter Laufzeit-Schreibpfad gefunden aus:

```text
MAIN:S 2001–2180
ENG:A 5001–5090
ENG:B 5091–5180
ENG:CTRL 8801–8820
```

auf dieses Feld.

Insbesondere:

```text
MAIN:2077
```

ist ein Status-/Ausgabewert und kein externer Soll-/Messwerteingang.

Damit ist der aktuell bekannte firmware-native Einspeisepunkt eindeutig der interne Hydraulikmodulbus.

---

# 9. MAIN:1022 ist kein Ersatz für HYD61:2048

MAIN:1022 ist über den normalen Mainboard-Modbus beschreibbar und beeinflusst den resultierenden Durchfluss. Es ist aber nur ein Offset:

```text
effective_flow = base_flow + signed(1022)
```

und wird bei `base_flow=0` nicht als eigener Messwert benutzt.

Dynamisches Nachführen von 1022 könnte theoretisch einen Sollwert nachbilden, ist aber nicht empfehlenswert:

- kein echter Messwerteingang,
- globale Korrektur des Durchflusses,
- lokaler H31-Qmax-Clamp bleibt aktiv,
- Basiswert muss gültig und ungleich 0 sein,
- Persistenz und Schreibendurance häufiger Parameterwrites noch offen.

---

# 10. Möglicher zukünftiger Emulator

Ein sinnvoller POC könnte später so aussehen:

```text
externer Durchflusssensor / Wärmemengenzähler
                |
                v
        Raspberry Pi / ESP32
                |
          RS485 4800 8N1
                |
      emuliert Slave 0x61
                |
                +--> beantwortet FC03 2001/90
                +--> nimmt FC10 1001/90 an
                |
                v
        FoxAir Mainboard H30=3
```

Vorher zu schließen:

1. welche HYD61-Wörter das Mainboard bei der konkreten FoxAir tatsächlich benutzt,
2. welche davon statisch aus den empfangenen FC10-1001..1090-Daten zurückgespiegelt werden können,
3. welche Werte echte Sensor-/I/O-Daten des Hydraulikmoduls sein müssen,
4. Kommunikations-Timeout- und Fehlerreaktion bei ausbleibender Unit-0x61-Antwort,
5. sichere Umschalt-/Rollback-Prozedur für H30.

---

# 11. Aktuelle Bewertung

**Bestätigt:**

```text
H30=3 aktiviert den Unit-0x61-Hydraulikpfad.
HYD61:2047 gated den externen Durchfluss.
HYD61:2048 liefert den Durchfluss raw/100 m³/h.
MAIN:1022 ist ein signed Korrekturoffset.
MAIN:2077 veröffentlicht den resultierenden effektiven Durchfluss.
```

**Technisch möglich:**

> Externen Durchfluss durch Emulation von Unit `0x61` einspeisen.

**Noch nicht live-testbereit:**

> Ein Minimalemulator mit nur 2047/2048 ist noch nicht als sicher bestätigt, weil H30=3 weitere Hydraulikdaten auf Unit `0x61` umschaltet.
