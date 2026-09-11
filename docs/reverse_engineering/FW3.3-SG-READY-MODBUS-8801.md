# SUPERSEDED – Mainboard-Firmware V3.3 – SG Ready über Modbus / Register 8801

Status: **SUPERSEDED**

Die frühere V3.3-SG-Ready-Dokumentation wurde am 11. September 2026 in die aktuelle, auf Firmware V3.4 angehobene Referenz übernommen und dort um den neuen `MAIN:1334 / SG01 = 7`-PV-Pfad ergänzt.

## Kanonisches Dokument

[`FW3.4-SG-READY-MODBUS-8801.md`](FW3.4-SG-READY-MODBUS-8801.md)

Die neue Datei erhält ausdrücklich die Provenance der V3.3-Live-Tests:

- klassischer virtueller SG-Ready-Pfad `SG01=3` über `ENG:CTRL:8801 = 1..4`,
- Rückmeldung über `MAIN:2133`,
- fester 10-Minuten-Hold des klassischen Pfads,
- Reset dieses Holds bei Änderung von `MAIN:1334`,
- Unterschied zwischen direktem User-/Mainboard-Modbus und Warmlink/LTE-Unit `0x63`.

Für den neuen V3.4-`SG01=7`-Pfad gilt inzwischen:

- `8801=1` / Low PV: **live bestätigt am 11.09.2026**,
- `8801=2` / Neutral: **live bestätigt am 11.09.2026**,
- `8801=3` / High PV: **live bestätigt am 11.09.2026**,
- damit sind alle drei vorgesehenen PV-Zustände praktisch bestätigt,
- Änderungen von `1336 / SG03` im aktiven Low-PV-State wirken grundsätzlich, zeigen live aber eine leichte, noch nicht quantifizierte Reaktionsverzögerung; ein klassischer 10-Minuten-Hold ist für reine `1336`-Änderungen statisch nicht erkennbar,
- die Hersteller-App zeigte beim virtuellen High-PV-Test einen falschen SG-Zustand; das passt sehr gut dazu, dass die Anzeige aus den physischen SG-Bits in `MAIN:2034` statt aus dem wirksamen Zustand `MAIN:2133` abgeleitet wird. Die genaue App-Implementierung ist noch nicht statisch bestätigt.
