# V3.3 – Modbus-Korrekturen für `FoxAir_Control/data`

Stand: 5. September 2026

> [!IMPORTANT]
> **Diese frühe Korrekturliste wurde durch spätere, vollständigere Audits ersetzt.**
>
> Für neue Arbeiten bitte zuerst verwenden:
>
> 1. [`FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md`](FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md) – finale Umsetzungs-/Delta-Liste
> 2. [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md) – kanonischer Namespace-/Registereinstieg
> 3. [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md) – detaillierte Status-/Runtime-Provenance
> 4. [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md) – detaillierter Parameter-Audit

Der Dateiname bleibt als Redirect-/Kompatibilitätsstub erhalten, damit ältere Links und Chatverweise weiterhin funktionieren.

## Warum ersetzt?

Die ursprüngliche Datei war eine frühe umsetzbare Delta-Liste. Danach wurden unter anderem ergänzt bzw. präzisiert:

- SG Ready über `MAIN:1334=3` und `ENG:CTRL:8801` inklusive Live-Verifikation,
- fester 10-Minuten-Hold und `MAIN:2133` als effektives Feedback,
- Trennung von direktem User-Modbus und Warmlink-/LTE-Pfad `0x63`,
- vollständiger Statusbereich bis `MAIN:2180`,
- genauere 32-Bit-Energiezähler- und Leistungszuordnungen,
- Engineering-/DIAG-/INV1-/FAN4-Namespaces,
- zusätzliche Live- und Binary-Provenance.

Die technischen Detailinformationen der früheren Datei sind in den oben genannten aktuellen Audits enthalten; die ursprüngliche Fassung bleibt außerdem über die Git-Historie nachvollziehbar.

## AI / Lookup-Hinweis

```yaml
status: superseded
canonical_documents:
  - FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md
  - FW3.3-MODBUS-GESAMTKATALOG.md
  - FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md
  - FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md
firmware: V3.3
keywords:
  - Modbus
  - FoxAir_Control
  - register corrections
  - delta
  - 2001-2180
  - 1001-1540
```

Für neue Analysen diese Datei **nicht mehr als gleichrangige technische Primärquelle** verwenden.