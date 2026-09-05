# Mainboard-Firmware V3.3 – HYD61 und externer Wasserdurchfluss

Stand: 5. September 2026

> [!IMPORTANT]
> **Dieses Dokument wurde konsolidiert und ist nicht mehr die kanonische Referenz.**
>
> Die vollständige und aktuellere Analyse befindet sich in:
>
> [`FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md`](FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md)

Der alte Dateiname bleibt bewusst als Redirect-/Kompatibilitätsstub erhalten, damit bestehende Links, Chatverweise und Suchtreffer nicht ins Leere laufen.

## Warum konsolidiert?

Beide Dokumente behandelten denselben V3.3-Datenpfad:

```text
MAIN:1036 / H30 = 3
        ↓
interner Modbus / Unit 0x61
        ↓
HYD61:2047 = Gültigkeits-/Vorhandenflag
HYD61:2048 = externer Wasserdurchfluss, raw/100 m³/h
        ↓
Mainboard-Runtime
        ↓
MAIN:1022 signed Korrekturoffset
        ↓
MAIN:2077 / T39
```

`FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md` ist umfangreicher und enthält zusätzlich den vollständigen FC03-/FC10-Kontext, Hinweise zur Emulation von Unit `0x61` und die Einordnung in die Pumpenregelung.

## AI / Lookup-Hinweis

```yaml
status: superseded
canonical_document: FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md
firmware: V3.3
keywords:
  - HYD61
  - Unit 0x61
  - H30
  - externer Durchfluss
  - external flow
  - 2047
  - 2048
  - 2077
```

Für neue Analysen bitte **nicht mehr dieses Dokument als Primärquelle verwenden**, sondern die oben verlinkte kanonische Datei.