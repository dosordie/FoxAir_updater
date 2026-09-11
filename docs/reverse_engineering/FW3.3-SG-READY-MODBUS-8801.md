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

Neu hinzugekommen ist der in V3.4 statisch rekonstruierte `SG01=7`-Pfad mit `8801=1/2/3 -> Low PV / Neutral / High PV`. Die zugehörigen Realtests stehen noch aus.
